import SwiftUI
import VideoMKCore

/// The Create screen (docs/UI_DESIGN.md o): a deterministic form with a Create button that is always visible. Prompt, photos, what it is for,
/// length, more options. No chat box, no send arrow.
struct CreateView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @Bindable var create: CreateModel
    @State private var dictation = Dictation()
    @State private var showingAdd = false
    @State private var showingPhotos = false
    @State private var confirmDiscard = false
    @State private var soonTip = false
    @State private var addOnLibrary = false
    @State private var flash = false
    @State private var shake: CGFloat = 0
    @FocusState private var focused: Bool

    private var balance: Int? { model.wallet.flatMap { $0.unlimited ? nil : $0.balance } }
    private var libraryCount: Int { model.composerLibrary.count }
    private var totalPhotos: Int { create.totalPhotos(library: libraryCount) }
    private var checking: Bool { if case .checking = create.stage { true } else { false } }
    private var status: ComposerStatus { create.status(balance: balance, dictating: dictation.isListening, checking: checking) }
    private var unaffordable: Bool { status.kind == .notAffordable || status.kind == .noCredits }
    private var form: CreateForm { create.form }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: 0) {
                        promptCard.id("prompt")
                        photosRow.padding(.top, 12)
                        section("What is it for?").padding(.top, 20)
                        platformChips.padding(.top, 8)
                        recommendation(proxy).padding(.top, 10)
                        alsoWorks
                        section("Length").padding(.top, 18)
                        lengthChips.padding(.top, 8)
                        maxHint.padding(.top, 6)
                        photoHint.padding(.top, 8)
                        moreOptions.padding(.top, 18).id("more")
                    }
                    .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 24)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: create.showMore) { _, open in if open { withAnimation { proxy.scrollTo("format", anchor: .top) } } }
                .task { if create.showMore { try? await Task.sleep(for: .milliseconds(300)); proxy.scrollTo("more", anchor: .top) } }
                .background(Theme.background.ignoresSafeArea())
                .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar(proxy) }
            }
            .navigationTitle("New video").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { cancel() }.accessibilityIdentifier("createCancel") } }
            .confirmationDialog("Discard this video?", isPresented: $confirmDiscard, titleVisibility: .visible) {
                Button("Discard", role: .destructive) { discard() }
                Button("Keep editing", role: .cancel) {}
            }
        }
        .presentationDetents([.large]).presentationDragIndicator(.visible)
        .interactiveDismissDisabled(create.hasEdits)
        .task {
            await create.loadCapabilities(userID: model.userID)
            if let auto = create.autoOpenPhotos { create.autoOpenPhotos = nil; addOnLibrary = auto.library; try? await Task.sleep(for: .milliseconds(350)); showingAdd = true }
        }
        .onAppear { dictation.onText = { create.form.text = $0 }; dictation.onKeyboardFallback = { focused = true } }
        .onDisappear { dictation.stop() }
        .sheet(isPresented: $showingAdd) {
            AddPhotosSheet(attached: totalPhotos, minutes: form.minutes, startOnLibrary: addOnLibrary) { phone, library in
                create.photos.add(phone)
                let known = Set(model.composerLibrary.map(\.id))
                model.composerLibrary += library.filter { !known.contains($0.id) }
                create.photos.libraryCount = model.composerLibrary.count
            }
        }
        .sheet(isPresented: $showingPhotos) { AttachedPhotosSheet(create: create) { showingPhotos = false; showingAdd = true } }
        .sheet(isPresented: Binding(get: { create.stage != .form && create.stage != .checking(slow: false) }, set: { if !$0 { create.dismissOverlay() } })) {
            CreateStageSheet(create: create, balance: balance, mediaCount: totalPhotos, onSubmit: finish, onEdit: { create.dismissOverlay(); focused = true })
        }
        .onChange(of: libraryCount, initial: true) { _, n in create.photos.libraryCount = n }
    }

    // MARK: pieces

    private func section(_ t: String) -> some View {
        Text(t.uppercased()).font(.system(size: 13, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary).accessibilityAddTraits(.isHeader)
    }

    private var promptCard: some View {
        ZStack(alignment: .bottomTrailing) {
            TextField("Describe your video. For example: how bees make honey, explained for kids.", text: $create.form.text, axis: .vertical)
                .focused($focused).lineLimit(3...10).font(.system(size: 19)).tint(Theme.primary)
                .textInputAutocapitalization(.sentences)
                .foregroundStyle(dictation.isListening ? Theme.textSecondary : Theme.text)
                .frame(maxWidth: .infinity, minHeight: 112 - 32, alignment: .topLeading)
                .padding(.bottom, 34)
                .accessibilityIdentifier("composerField")
            HStack(spacing: 8) {
                if dictation.isListening { Text("Listening… tap to stop").font(.system(size: 13)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("listeningHint") }
                else if !form.hasContent { Text("Tap the mic to speak").font(.system(size: 13)).foregroundStyle(Theme.textTertiary) }
                mic
            }
        }
        .padding(16)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(dictation.isListening ? Theme.danger.opacity(0.6) : Theme.outline, lineWidth: 1))
        .overlay(alignment: .top) { dictationHint }
    }

    private var mic: some View {
        Button {
            Task { await dictation.toggle(currentText: create.form.text) }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        } label: {
            ZStack {
                Circle().fill(dictation.isListening ? Theme.danger : Theme.surfaceRaised).frame(width: 44, height: 44)
                Image(systemName: dictation.isListening ? "stop.fill" : "mic").font(.system(size: dictation.isListening ? 16 : 20)).foregroundStyle(dictation.isListening ? .white : Theme.text)
            }.frame(width: 44, height: 44)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dictation.isListening ? "Stop dictation" : "Dictate").accessibilityHint("Say what video you want instead of typing")
        .accessibilityAddTraits(.isToggle).accessibilityIdentifier("micButton")
    }

    @ViewBuilder private var dictationHint: some View {
        if case .unavailable(let message) = dictation.state {
            Label(message, systemImage: "mic.slash").font(.footnote).foregroundStyle(Theme.warning).padding(10)
                .background(Theme.warningContainer, in: RoundedRectangle(cornerRadius: 12, style: .continuous)).offset(y: -44)
                .accessibilityIdentifier("dictationUnavailable")
                .task(id: message) { try? await Task.sleep(for: .seconds(12)); dictation.clearHint() }
        } else if case .keyboardHint(let message) = dictation.state {
            Label(message, systemImage: "keyboard").font(.footnote).foregroundStyle(Theme.textSecondary).padding(10)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 12, style: .continuous)).offset(y: -44)
                .accessibilityIdentifier("dictationKeyboardHint")
                .task { try? await Task.sleep(for: .seconds(8)); dictation.clearHint() }
        }
    }

    // photos

    @ViewBuilder private var photosRow: some View {
        if totalPhotos == 0 && create.photos.loading == 0 {
            Button { focused = false; addOnLibrary = false; showingAdd = true } label: {
                HStack(spacing: 14) {
                    Image(systemName: "photo.badge.plus").font(.system(size: 20)).foregroundStyle(Theme.primary).frame(width: 40, height: 40).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                    VStack(alignment: .leading, spacing: 1) {
                        Text("Add photos").font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.text)
                        Text("Optional · from this phone or My media").font(.system(size: 14)).foregroundStyle(Theme.textSecondary).lineLimit(1).minimumScaleFactor(0.85)
                    }
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                }
                .padding(.horizontal, 14).frame(minHeight: 64)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(Theme.outline, lineWidth: 1))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Add photos").accessibilityHint("Choose photos from this phone or My media. Optional.").accessibilityIdentifier("photoButton")
        } else {
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 10) {
                    Image(systemName: "photo.badge.plus").font(.system(size: 15)).foregroundStyle(Theme.primary).frame(width: 32, height: 32).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                    Text(totalPhotos == 1 ? "1 photo" : "\(totalPhotos) photos").font(.system(size: 17, weight: .bold).monospacedDigit()).foregroundStyle(Theme.text)
                        .accessibilityIdentifier("photosNote")
                    Spacer()
                    Button("Edit") { focused = false; showingPhotos = true }.font(.system(size: 16, weight: .semibold)).frame(minWidth: 44, minHeight: 44).accessibilityIdentifier("photoButton")
                }
                HStack(spacing: 8) {
                    ForEach(Array(create.thumbs(library: model.composerLibrary).prefix(4).enumerated()), id: \.offset) { _, t in ThumbCell(thumb: t, media: model.media) }
                    if totalPhotos > 4 {
                        Button { showingPhotos = true } label: { Text("+\(totalPhotos - 4)").font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.primary).frame(width: 56, height: 56).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 12, style: .continuous)) }.buttonStyle(.plain).accessibilityLabel("\(totalPhotos - 4) more photos")
                    }
                    if create.photos.loading > 0 { ProgressView().frame(width: 56, height: 56) }
                    Spacer(minLength: 0)
                }
                if let n = create.photos.notice { Text(n).font(.caption).foregroundStyle(Theme.danger).accessibilityIdentifier("photosNotice") }
                if let p = create.photos.preparingText { Text(p).font(.caption.weight(.semibold)).foregroundStyle(Theme.primary).accessibilityIdentifier("photosPreparing") }
            }
            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(Theme.outline, lineWidth: 1))
        }
    }

    // platform

    private var platformChips: some View {
        ScrollViewReader { chipsProxy in
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(PlatformChips.make(create.caps)) { chip in
                    let selected = form.chip(create.caps)?.id == chip.id && !form.isCustom(create.caps)
                    Button {
                        if chip.supported { create.form.select(chip); UISelectionFeedbackGenerator().selectionChanged() }
                        else { UINotificationFeedbackGenerator().notificationOccurred(.warning); soonTip = true; Task { try? await Task.sleep(for: .seconds(2)); soonTip = false } }
                    } label: {
                        HStack(spacing: 6) {
                            if selected { Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)) }
                            else { Image(systemName: icon(chip)).font(.system(size: 15)) }
                            Text(chip.label).font(.system(size: 16, weight: .semibold)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                            if !chip.supported { Text("Soon").font(.system(size: 11, weight: .bold)).foregroundStyle(Theme.textSecondary).padding(.horizontal, 6).frame(height: 18).background(Theme.surface3, in: Capsule()) }
                        }
                        .foregroundStyle(selected ? Theme.primary : Theme.text).padding(.horizontal, 16).padding(.vertical, 8).frame(minHeight: 44)
                        .background(selected ? Theme.primaryContainer : Theme.surface, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).stroke(selected ? Theme.primary : Theme.outline, lineWidth: selected ? 1.5 : 1))
                        .opacity(chip.supported ? 1 : 0.62)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(chip.supported ? chip.label : "\(chip.label), \(create.caps.aspectName(chip.aspect)), coming soon, dimmed")
                    .accessibilityAddTraits(selected ? .isSelected : [])
                    .accessibilityIdentifier("platform-\(chip.id)")
                    .id(chip.id)
                }
            }
            .padding(.horizontal, 16)
        }
        .onAppear { if let id = form.chip(create.caps)?.id { chipsProxy.scrollTo(id, anchor: .center) } }       // the chosen one is always in view
        }
        .padding(.horizontal, -16)
        .overlay(alignment: .bottomLeading) { if soonTip { Text("Coming soon").font(.system(size: 13, weight: .semibold)).foregroundStyle(.white).padding(.horizontal, 12).frame(height: 30).background(Color(hex: 0x23263F), in: Capsule()).offset(y: 34).transition(.opacity) } }
        .accessibilityElement(children: .contain).accessibilityLabel("What is it for?")
    }

    private func icon(_ chip: PlatformChip) -> String { chip.id == "other" ? "sparkles" : chip.aspect == "16:9" ? "rectangle" : chip.aspect == "4:5" ? "rectangle.portrait" : "rectangle.portrait" }

    private func recommendation(_ proxy: ScrollViewProxy) -> some View {
        HStack(spacing: 8) {
            Image(systemName: form.aspect == "16:9" ? "rectangle" : "rectangle.portrait").font(.system(size: 14)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            let parts = form.recommendation(create.caps).components(separatedBy: " · ")
            (Text(parts.first.map { "\($0) · " } ?? "").foregroundStyle(Theme.textSecondary) + Text(parts.dropFirst().joined(separator: " · ")).fontWeight(.bold).foregroundStyle(Theme.text))
                .font(.system(size: 15.5)).lineLimit(2).accessibilityIdentifier("recommendation")
            Spacer(minLength: 4)
            if form.canChangeFormat(create.caps) {
                Button("Change") { withAnimation(reduceMotion ? nil : .snappy) { create.showMore = true } }.font(.system(size: 15.5, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("changeFormat")
            }
        }
        .accessibilityElement(children: .combine)
    }

    /// "Also works: Square, Landscape": the platform's other formats, switching only the format.
    @ViewBuilder private var alsoWorks: some View {
        let others = form.alsoWorks(create.caps)
        if !others.isEmpty {
            WrapLayout(spacing: 8) {
                Text("Also works:").font(.system(size: 13.5)).foregroundStyle(Theme.textSecondary).frame(minHeight: 44)
                ForEach(others, id: \.id) { o in
                    Button { create.form.aspect = o.id; UISelectionFeedbackGenerator().selectionChanged() } label: {
                        Text(o.name).font(.system(size: 13.5, weight: .semibold)).foregroundStyle(Theme.primary).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true).padding(.horizontal, 12).padding(.vertical, 6).frame(minHeight: 30).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 15, style: .continuous)).frame(minHeight: 44)
                    }.buttonStyle(.plain).accessibilityLabel("Use \(o.name) instead").accessibilityIdentifier("also-\(o.id)")
                }
            }
            .accessibilityElement(children: .contain)
        }
    }

    /// Longer than the platform allows: one gentle line and a one-tap chip.
    @ViewBuilder private var maxHint: some View {
        if let hint = form.maxLengthHint(create.caps) {
            HStack(spacing: 8) {
                Image(systemName: "info.circle").font(.system(size: 14)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                Text(hint.text).font(.system(size: 14)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("maxLengthHint")
                Spacer(minLength: 4)
                FixChip(title: "Use \(LengthLabel.chip(hint.fixMinutes))") { create.form.setMinutes(hint.fixMinutes); UISelectionFeedbackGenerator().selectionChanged() }
                    .accessibilityLabel("Use \(LengthLabel.spoken(hint.fixMinutes)) instead").accessibilityIdentifier("maxFixChip")
            }
        }
    }

    // length

    private var lengthChips: some View {
        let presets = create.caps.lengthPresets
        let wide = typeSize >= .xxxLarge
        return Group {
            if wide { LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) { ForEach(presets, id: \.self) { lengthChip($0, fixedWidth: nil) } } }
            else { ScrollViewReader { sp in ScrollView(.horizontal, showsIndicators: false) { HStack(spacing: 8) { ForEach(presets, id: \.self) { lengthChip($0, fixedWidth: 70).id($0) } }.padding(.horizontal, 16) }
                .onAppear { sp.scrollTo(form.minutes, anchor: .center) }.onChange(of: form.minutes) { _, m in withAnimation { sp.scrollTo(m, anchor: .center) } } }.padding(.horizontal, -16) }
        }
        .accessibilityElement(children: .contain).accessibilityLabel("Length")
    }

    private func lengthChip(_ m: Double, fixedWidth: CGFloat?) -> some View {
        let selected = form.minutes == m, credits = ComposerPlan.credits(forMinutes: m), costly = balance.map { credits > $0 } ?? false
        return Button { create.form.setMinutes(m); UISelectionFeedbackGenerator().selectionChanged() } label: {
            VStack(spacing: 2) {
                Text(LengthLabel.chip(m)).font(.system(size: 16, weight: .bold)).foregroundStyle(selected ? Theme.primary : Theme.text).fixedSize(horizontal: false, vertical: true)
                HStack(spacing: 2) { Image(systemName: "bolt.fill").font(.system(size: 10)); Text("\(credits)").font(.system(size: 13, weight: .semibold).monospacedDigit()) }
                    .foregroundStyle(costly ? Theme.warning : selected ? Theme.primary : Theme.textSecondary)
            }
            .padding(.horizontal, 6).frame(minWidth: fixedWidth).frame(maxWidth: fixedWidth == nil ? .infinity : nil, minHeight: 58)
            .background(selected ? Theme.primaryContainer : Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 1.5 : 0))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(LengthLabel.spoken(m)), \(ComposerPlan.plural(credits, "credit"))")
        .accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("length-\(m < 1 ? "\(Int((m * 60).rounded()))s" : "\(Int(m))")")
    }

    @ViewBuilder private var photoHint: some View {
        if let hint = PhotoCapacity.hint(photos: totalPhotos, minutes: form.minutes, options: create.caps.lengthPresets) {
            VStack(alignment: .leading, spacing: 0) {
                Text(hint).font(.system(size: 15)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("photoCapacityHint")
                if let fix = ComposerPlan.photoFix(photos: totalPhotos, minutes: form.minutes, balance: balance, lengths: create.caps.lengthPresets) {
                    FixChip(title: fix.title) { if case .useMinutes(let m, _) = fix { create.form.setMinutes(m); UISelectionFeedbackGenerator().selectionChanged() } }.accessibilityIdentifier("fixChip").accessibilityLabel(fix.title.replacingOccurrences(of: "⚡", with: "credits "))
                }
            }
        }
    }

    // more options

    private var moreOptions: some View {
        VStack(alignment: .leading, spacing: 0) {
            Button { withAnimation(reduceMotion ? nil : .snappy) { create.showMore.toggle() } } label: {
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("More options").font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.text)
                        if !create.showMore { Text(form.moreSummary(create.caps)).font(.system(size: 14)).foregroundStyle(Theme.textSecondary).lineLimit(1) }
                    }
                    Spacer()
                    Image(systemName: create.showMore ? "chevron.up" : "chevron.down").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.text)
                }
                .padding(.horizontal, 16).frame(minHeight: 56).contentShape(Rectangle())
            }
            .buttonStyle(.plain).accessibilityAddTraits(.isButton).accessibilityValue(create.showMore ? "expanded" : "collapsed").accessibilityIdentifier("moreOptions")
            if create.showMore {
                Divider()
                VStack(alignment: .leading, spacing: 0) {
                    section("Look").padding(.bottom, 8)
                    HStack(alignment: .top, spacing: 10) { look(nil, "Auto"); ForEach(VideoLook.allCases) { look($0, $0.title) } }
                    Divider().padding(.vertical, 12)
                    Toggle(isOn: $create.form.captions) { Label("Subtitles", systemImage: "captions.bubble").font(.system(size: 17)).foregroundStyle(Theme.text) }.tint(Theme.primary).frame(minHeight: 48).accessibilityIdentifier("subtitlesToggle")
                    Divider()
                    languageRow
                    Divider().padding(.bottom, 12)
                    section("Format").padding(.bottom, 8).id("format")
                    formatTiles
                    resolutionControl.padding(.top, 10)
                }
                .padding(16)
            }
        }
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(Theme.outline, lineWidth: 1))
    }

    private func look(_ look: VideoLook?, _ title: String) -> some View {
        let selected = form.look == look
        return Button { create.form.look = look; UISelectionFeedbackGenerator().selectionChanged() } label: {
            VStack(spacing: 6) {
                LookSwatch(look: look).aspectRatio(3 / 3.6, contentMode: .fit).clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 2 : 0))
                    .padding(selected ? 3 : 0).background(selected ? Theme.primaryContainer : .clear, in: RoundedRectangle(cornerRadius: 19, style: .continuous))
                Text(title).font(.system(size: 15, weight: selected ? .semibold : .regular)).foregroundStyle(selected ? Theme.primary : Theme.text).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            }
        }
        .buttonStyle(.plain).frame(maxWidth: .infinity)
        .accessibilityLabel(look == nil ? "Auto, the producer decides the look" : title).accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("look-\(look?.rawValue ?? "auto")")
    }

    private var languageRow: some View {
        Menu {
            Button { create.form.language = "auto" } label: { if form.language == "auto" { Label("Same as my description", systemImage: "checkmark") } else { Text("Same as my description") } }
            ForEach(create.caps.languages, id: \.id) { l in Button { create.form.language = l.id } label: { if form.language == l.id { Label(l.label, systemImage: "checkmark") } else { Text(l.label) } } }
        } label: {
            HStack {
                Label("Language", systemImage: "globe").font(.system(size: 17)).foregroundStyle(Theme.text)
                Spacer(minLength: 8)
                Text(form.language == "auto" ? "Same as my description" : (create.caps.languages.first { $0.id == form.language }?.label ?? form.language)).font(.system(size: 15)).foregroundStyle(Theme.textSecondary).lineLimit(1)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.textSecondary)
            }.frame(minHeight: 48)
        }
        .accessibilityIdentifier("languageRow")
    }

    private var formatTiles: some View {
        HStack(spacing: 10) {
            ForEach([("16:9", "Landscape", "rectangle"), ("9:16", "Vertical", "rectangle.portrait"), ("1:1", "Square", "square"), ("4:5", "Portrait", "rectangle.portrait")], id: \.0) { id, name, symbol in
                let ready = create.caps.readyAspects.contains { $0.id == id }
                let selected = form.aspect == id
                let beta = create.caps.aspect(id)?.beta == true
                Button { if ready { create.form.aspect = id; UISelectionFeedbackGenerator().selectionChanged() } else { UINotificationFeedbackGenerator().notificationOccurred(.warning) } } label: {
                    VStack(spacing: 5) {
                        Image(systemName: symbol).font(.system(size: 22)).foregroundStyle(selected ? Theme.primary : Theme.textSecondary)
                        Text("\(name)\n\(id)").font(.system(size: 13, weight: .semibold)).multilineTextAlignment(.center).foregroundStyle(selected ? Theme.primary : Theme.text).fixedSize(horizontal: false, vertical: true)
                    }
                    .padding(.horizontal, 4).padding(.vertical, 8).frame(maxWidth: .infinity, minHeight: 76)
                    .background(selected ? Theme.primaryContainer : Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).stroke(Theme.primary, lineWidth: selected ? 1.5 : 0))
                    .overlay(alignment: .topTrailing) { if !ready || beta { Text(ready ? "Beta" : "Soon").font(.system(size: 10.5, weight: .bold)).foregroundStyle(Theme.textSecondary).padding(.top, 5).padding(.trailing, 7) } }
                    .opacity(ready ? 1 : 0.62)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(name) \(id)\(ready ? (beta ? ", beta" : "") : ", coming soon, dimmed")").accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("aspect-\(id)")
            }
        }
    }

    private var resolutionControl: some View {
        HStack(spacing: 0) {
            ForEach(["720p", "1080p"], id: \.self) { r in
                let ready = create.caps.resolutions.contains { $0.id == r }
                let selected = form.resolution == r
                Button { if ready { create.form.resolution = r; UISelectionFeedbackGenerator().selectionChanged() } } label: {
                    Text(r).font(.system(size: 17, weight: .semibold)).foregroundStyle(ready ? Theme.text : Theme.textTertiary).frame(maxWidth: .infinity, minHeight: 40)
                        .background(selected ? Theme.surface : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .shadow(color: .black.opacity(selected ? 0.08 : 0), radius: 3, y: 1)
                }
                .buttonStyle(.plain).disabled(!ready).opacity(ready ? 1 : 0.6)
                .accessibilityLabel(ready ? r : "\(r), not available yet").accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier("resolution-\(r)")
            }
        }
        .padding(3).background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
    }

    // MARK: bottom bar

    private func bottomBar(_ proxy: ScrollViewProxy) -> some View {
        let s = status
        let ready = s.canSend && !checking
        return VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 8) {
                if checking { ProgressView().controlSize(.small) }
                else { Image(systemName: s.isProblem && s.kind != .tooShort ? "exclamationmark.triangle" : s.kind == .tooShort || s.kind == .price ? "info.circle" : "bolt.fill").font(.system(size: 14, weight: .semibold)).foregroundStyle(s.isProblem && s.kind != .tooShort ? tint(s) : Theme.primary).accessibilityHidden(true) }
                Text(checking ? "Checking your request…" : s.kind == .price || s.kind == .tooShort && false ? (form.hasContent ? s.message : "Describe your video to continue") : s.message)
                    .font(.system(size: 14, weight: .medium)).foregroundStyle(tint(s)).fixedSize(horizontal: false, vertical: true)
                    .modifier(Shake(travel: reduceMotion ? 0 : 4, value: shake))
                    .accessibilityIdentifier(unaffordable ? "notEnoughCredits" : "costLine")
                Spacer(minLength: 4)
                if let fix = s.fix, !checking { FixChip(title: fix.title) { applyFix(fix) }.accessibilityIdentifier("fixChip") }
            }
            .frame(minHeight: 28)
            .padding(.horizontal, flash ? 6 : 0).background(flash ? Theme.warningContainer : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .accessibilityElement(children: .contain).accessibilityIdentifier("statusLine")
            Button { tapCreate(s, proxy) } label: {
                HStack(spacing: 8) {
                    if checking { ProgressView().tint(.white) }
                    Text("Create video ·").font(.system(size: 19, weight: .bold))
                    HStack(spacing: 3) { Image(systemName: "bolt.fill").font(.system(size: 15)); Text("\(form.options.credits)").font(.system(size: 19, weight: .bold).monospacedDigit()) }
                }
                .foregroundStyle(ready || checking ? Color.white : Theme.textTertiary).frame(maxWidth: .infinity, minHeight: 54)
                .background { Capsule().fill(Theme.surface3).opacity(ready || checking ? 0 : 1); Capsule().fill(Theme.gradient).opacity(ready || checking ? 1 : 0) }
                .shadow(color: Theme.gradientStart.opacity(ready ? 0.3 : 0), radius: 10, y: 4)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(typeSize.isAccessibilitySize ? "Create video, \(ComposerPlan.plural(form.options.credits, "credit"))" : "Create video")
            .accessibilityValue(ready ? "Ready, costs \(ComposerPlan.plural(form.options.credits, "credit"))" : checking ? "Checking your request" : "Not ready. \(s.message)")
            .accessibilityHint(ready ? "Starts your video" : "Tells you what is missing")
            .accessibilityIdentifier("sendButton")
        }
        .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
        .background(.bar)
        .overlay(alignment: .top) { Divider() }
    }

    private func tint(_ s: ComposerStatus) -> Color { s.kind == .tooLong ? Theme.danger : (s.isProblem && s.kind != .tooShort) ? Theme.warning : Theme.textSecondary }

    private func applyFix(_ fix: ComposerStatus.Fix) {
        switch fix {
        case .useMinutes(let m, _): create.form.setMinutes(m); UISelectionFeedbackGenerator().selectionChanged()
        case .addCredits: model.requestCredits = true
        }
    }

    private func tapCreate(_ s: ComposerStatus, _ proxy: ScrollViewProxy) {
        if checking { return }
        guard s.canSend else {
            UINotificationFeedbackGenerator().notificationOccurred(.warning)
            withAnimation(.linear(duration: 0.28)) { shake += 1 }
            withAnimation(.easeOut(duration: 0.15)) { flash = true }
            Task { try? await Task.sleep(for: .milliseconds(450)); withAnimation(.easeOut(duration: 0.2)) { flash = false } }
            UIAccessibility.post(notification: .announcement, argument: s.kind == .tooShort || s.kind == .price ? "Describe your video to continue" : s.announcement)
            if s.kind == .tooShort || s.kind == .price { withAnimation { proxy.scrollTo("prompt", anchor: .top) }; focused = true }
            return
        }
        dictation.cancel(); focused = false
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        create.create(mediaCount: totalPhotos, submit: finish)
    }

    /// The request is cleared (or confirmed): the video starts, the screen closes onto the library.
    private func finish(_ brief: [String: String]?) {
        model.submit(brief: form.text, options: form.options, photos: create.photos.items.map(\.data), meta: create.photos.items.map(\.meta), libraryMedia: model.composerLibrary.map(\.id), intake: brief)
        create.remember()
        create.photos.clear(); model.composerLibrary = []
        create.stage = .form; create.form.text = ""
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        dismiss()
    }

    private func cancel() {
        if create.hasEdits { confirmDiscard = true } else { create.cancelCheck(); dismiss() }
    }
    private func discard() { dictation.cancel(); create.cancelCheck(); create.photos.clear(); model.composerLibrary = []; create.form.text = ""; dismiss() }
}

// MARK: attached photos

extension CreateModel {
    enum Thumb { case phone(AttachedPhoto), library(LibraryPhoto) }
    func thumbs(library: [LibraryPhoto]) -> [Thumb] { photos.items.map(Thumb.phone) + library.map(Thumb.library) }
}

struct ThumbCell: View {
    let thumb: CreateModel.Thumb
    let media: MediaModel?
    var body: some View {
        switch thumb {
        case .phone(let p): Image(uiImage: p.thumbnail).resizable().scaledToFill().frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous)).accessibilityIdentifier("attachedPhoto")
        case .library(let l): LibraryStripTile(photo: l, media: media, label: "My media photo", showRemove: false) {}
        }
    }
}

/// Everything attached, with a remove button on each (the Create screen shows only the first four).
struct AttachedPhotosSheet: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    let create: CreateModel
    let onAdd: () -> Void
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    AttachedPhotosStrip(photos: create.photos, library: model.composerLibrary, media: model.media) { id in model.composerLibrary.removeAll { $0.id == id } }
                    Button { onAdd() } label: { Label("Add more photos", systemImage: "photo.badge.plus").font(.headline).frame(maxWidth: .infinity, minHeight: 48) }.buttonStyle(.borderedProminent).tint(Theme.primary)
                }
                .padding(20)
            }
            .navigationTitle("Photos").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
        }
        .presentationDetents([.medium, .large])
    }
}
