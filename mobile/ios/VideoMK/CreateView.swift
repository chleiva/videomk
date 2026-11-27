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
    @State private var confirmDiscard = false
    @State private var soonTip = false
    @State private var addOnLibrary = false
    @State private var flash = false
    @State private var showingCost = false
    @State private var shake: CGFloat = 0
    @State private var showingImporter = false
    @State private var confirmDeckReplace = false      // a presentation was chosen while photos are attached
    @State private var confirmPhotosReplace = false    // photos were chosen while a presentation is attached
    @State private var pendingDeckPick = false
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
                    VStack(alignment: .leading, spacing: 16) {
                        HStack { GlassIconButton(symbol: "xmark", label: tr("common.cancel"), identifier: "createCancel") { cancel() }; Spacer() }
                        Group {         // locked and dimmed while the request is being checked: nothing can change under the call
                            promptArea.id("prompt")
                            if form.hasDeck { Text(tr("deck.prompt_hint")).font(.vmk(13)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("deckPromptHint") }
                            attachments
                            deckSection
                            pills
                            notice
                        }
                        .disabled(checking).opacity(checking ? 0.45 : 1).animation(reduceMotion ? nil : .easeOut(duration: 0.2), value: checking)
                    }
                    .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 24)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: create.deck.state) { _, state in
                    // a result (ready or a problem) is brought fully into view: on a small phone its buttons start under the bottom bar
                    switch state { case .ready, .failed: withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.3)) { proxy.scrollTo("deck", anchor: .bottom) }; default: break }
                }
                .background(Theme.background.ignoresSafeArea())
                .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar(proxy) }
            }
            .toolbar(.hidden, for: .navigationBar)
            .confirmationDialog(tr("create.discard_this_video"), isPresented: $confirmDiscard, titleVisibility: .visible) {
                Button(tr("create.discard"), role: .destructive) { discard() }
                Button(tr("create.keep_editing"), role: .cancel) {}
            }
        }
        .presentationDetents([.large]).presentationDragIndicator(.visible)
        .interactiveDismissDisabled(create.hasEdits || checking)
        .task {
            await create.loadCapabilities(userID: model.userID)
            if let auto = create.autoOpenPhotos { create.autoOpenPhotos = nil; addOnLibrary = auto.library; try? await Task.sleep(for: .milliseconds(350)); showingAdd = true }
            else if !create.form.hasContent && !create.form.hasDeck && !create.deck.isActive && create.stage == .form {      // the keyboard opens at once on an empty prompt: type, then Create
                try? await Task.sleep(for: .milliseconds(450)); if !create.form.hasContent { focused = true }
            }
        }
        .onAppear { dictation.onText = { create.form.text = $0 }; dictation.onKeyboardFallback = { focused = true } }
        .onDisappear { dictation.stop() }
        .sheet(isPresented: $showingAdd, onDismiss: { if pendingDeckPick { pendingDeckPick = false; startDeckPick() } }) {
            AddPhotosSheet(attached: totalPhotos, minutes: form.minutes, startOnLibrary: addOnLibrary, onDeck: nil) { phone, library in
                create.photos.add(phone)
                let known = Set(model.composerLibrary.map(\.id))
                model.composerLibrary += library.filter { !known.contains($0.id) }
                create.photos.libraryCount = model.composerLibrary.count
            }
        }
        .fileImporter(isPresented: $showingImporter, allowedContentTypes: deckContentTypes(create.caps.deck), allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls): if let url = urls.first { create.pickDeck(url); Haptics.play(.selection) }
            case .failure(let e): if (e as? CocoaError)?.code != .userCancelled { create.rejectDeck(name: "", problem: .corrupt) }
            }
        }
        .alert(tr("deck.replace_photos.title"), isPresented: $confirmDeckReplace) {      // an alert, not a dialog: on iOS 26 a dialog opened from a sheet showed no way to say no
            Button(tr("deck.replace_photos.confirm"), role: .destructive) { clearAttachedPhotos(); showingImporter = true }
            Button(tr("deck.replace_photos.keep"), role: .cancel) {}
        } message: { Text(tr("deck.replace_photos.message", totalPhotos)) }
        .alert(tr("deck.replace_deck.title"), isPresented: $confirmPhotosReplace) {
            Button(tr("deck.replace_deck.confirm"), role: .destructive) { create.removeDeck(); showingAdd = true }
            Button(tr("deck.replace_deck.keep"), role: .cancel) {}
        } message: { Text(tr("deck.replace_deck.message")) }
        .onChange(of: create.deck.state, initial: true) { _, _ in create.syncDeck() }
        .sheet(isPresented: $create.showMore) { CreateOptionsSheet(create: create) }
        .sheet(isPresented: Binding(get: { create.stage != .form && create.stage != .checking(slow: false) }, set: { if !$0 { create.dismissOverlay() } })) {
            CreateStageSheet(create: create, balance: balance, mediaCount: totalPhotos, onSubmit: finish, onEdit: { create.dismissOverlay(); focused = true })
        }
        .onChange(of: libraryCount, initial: true) { _, n in create.photos.libraryCount = n }
    }

    // MARK: pieces

    /// The prompt: large, borderless, the keyboard open at once. Photo and mic are two glass icons under it.
    private var promptArea: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField(form.hasDeck ? tr("deck.placeholder") : tr("create.describe_your_video_for_example"), text: $create.form.text, axis: .vertical)
                .focused($focused).lineLimit(3...12).font(.vmk(22)).tint(Theme.primary)
                .textInputAutocapitalization(.sentences)
                .foregroundStyle(dictation.isListening ? Theme.textSecondary : Theme.text)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
                .accessibilityIdentifier("composerField")
            HStack(spacing: 8) {
                photoButton
                GlassIconButton(symbol: "slider.horizontal.3", label: tr("create.options"), identifier: "moreOptions") { focused = false; create.showMore = true }
                Spacer(minLength: 8)
                if dictation.isListening { Text(tr("create.listening_tap_to_stop")).font(.vmk(13)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("listeningHint") }
                mic
            }
        }
        .overlay(alignment: .top) { dictationHint }
    }

    private var mic: some View {
        Button {
            Task { await dictation.toggle(currentText: create.form.text) }
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        } label: {
            Image(systemName: dictation.isListening ? "stop.fill" : "mic").font(.vmk(dictation.isListening ? 16 : 19, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                .foregroundStyle(dictation.isListening ? .white : Theme.text).frame(width: 44, height: 44)
                .background { if dictation.isListening { Circle().fill(Theme.danger) } }
                .modifier(MicGlass(listening: dictation.isListening))
                .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dictation.isListening ? tr("create.stop_dictation") : tr("create.dictate")).accessibilityHint(tr("create.say_what_video_you_want"))
        .accessibilityAddTraits(.isToggle).accessibilityIdentifier("micButton")
    }

    @ViewBuilder private var dictationHint: some View {
        if case .unavailable(let message) = dictation.state {
            Label(message, systemImage: "mic.slash").font(.footnote).foregroundStyle(Theme.warning).padding(10)
                .background(Theme.warningContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous)).offset(y: -44)
                .accessibilityIdentifier("dictationUnavailable")
                .task(id: message) { try? await Task.sleep(for: .seconds(12)); dictation.clearHint() }
        } else if case .keyboardHint(let message) = dictation.state {
            Label(message, systemImage: "keyboard").font(.footnote).foregroundStyle(Theme.textSecondary).padding(10)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous)).offset(y: -44)
                .accessibilityIdentifier("dictationKeyboardHint")
                .task { try? await Task.sleep(for: .seconds(8)); dictation.clearHint() }
        }
    }

    // photos

    /// One photo icon; a count badge when something is attached. When the account has presentations (and none is attached) it is a small menu:
    /// Photos, or Add a presentation.
    @ViewBuilder private var photoButton: some View {
        if create.deckAvailable && !create.deck.isActive {
            Menu {
                Button { focused = false; addOnLibrary = false; startPhotoAdd() } label: { Label(tr("create.add_photos"), systemImage: "photo") }.accessibilityIdentifier("photosMenuItem")
                Button { startDeckPick() } label: { Label(tr("create.add_presentation"), systemImage: "rectangle.on.rectangle") }.accessibilityIdentifier("deckButton")
            } label: { photoIcon }
            .accessibilityLabel(totalPhotos > 0 ? tr("photos.count", totalPhotos) : tr("create.add_photos")).accessibilityIdentifier("photoButton")
        } else {
            Button { focused = false; addOnLibrary = false; startPhotoAdd() } label: { photoIcon }
                .buttonStyle(.plain)
                .accessibilityLabel(totalPhotos > 0 ? tr("photos.count", totalPhotos) : tr("create.add_photos")).accessibilityHint(tr("create.choose_photos_from_this_phone")).accessibilityIdentifier("photoButton")
        }
    }

    private var photoIcon: some View {
        Image(systemName: "photo").font(.vmk(19, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.xxxLarge).foregroundStyle(Theme.text).frame(width: 44, height: 44).vmkGlass(in: Circle())
            .overlay(alignment: .topTrailing) {
                if totalPhotos > 0 { Text("\(totalPhotos)").font(.vmk(11, weight: .bold).monospacedDigit()).foregroundStyle(Theme.onPrimary).padding(.horizontal, 6).frame(minWidth: 20, minHeight: 20).background(Theme.gradient, in: Capsule()).offset(x: 6, y: -6).accessibilityHidden(true) }
            }
            .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Circle())
    }

    /// The attached photos: the count, every photo with its own (x), and one tile to add more. Only when something is attached.
    @ViewBuilder private var attachments: some View {
        if totalPhotos > 0 || create.photos.loading > 0 {
            VStack(alignment: .leading, spacing: 8) {
                Text(tr("photos.count", totalPhotos)).font(.vmk(13, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.textSecondary)
                    .accessibilityIdentifier("photosNote")
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(Array(create.photos.items.enumerated()), id: \.element.id) { index, p in
                            Image(uiImage: p.thumbnail).resizable().scaledToFill().frame(width: 56, height: 56)
                                .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous))
                                .overlay(alignment: .topTrailing) { RemoveX(label: tr("attach.remove_photo", index + 1)) { withAnimation(reduceMotion ? nil : .snappy) { create.photos.remove(p.id) } } }
                                .accessibilityElement(children: .contain).accessibilityLabel(tr("attach.photo_n_of", index + 1, create.photos.items.count)).accessibilityIdentifier("attachedPhoto")
                        }
                        ForEach(Array(model.composerLibrary.enumerated()), id: \.element.id) { index, photo in
                            LibraryStripTile(photo: photo, media: model.media, label: tr("attach.library_photo_n_of", index + 1, model.composerLibrary.count)) {
                                withAnimation(reduceMotion ? nil : .snappy) { model.composerLibrary.removeAll { $0.id == photo.id } }
                            }
                        }
                        if create.photos.loading > 0 { ProgressView().frame(width: 56, height: 56) }
                        Button { focused = false; addOnLibrary = false; startPhotoAdd() } label: {
                            Image(systemName: "photo.badge.plus").font(.vmk(18, weight: .semibold)).foregroundStyle(Theme.primary).frame(width: 56, height: 56)
                                .background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous))
                        }
                        .buttonStyle(.plain).accessibilityLabel(tr("create.add_more_photos")).accessibilityIdentifier("editPhotos")
                    }
                    .padding(.top, 12).padding(.trailing, 12)           // room for the (x) that sits over each corner
                }
                if let n = create.photos.notice { Text(n).font(.caption).foregroundStyle(Theme.danger).accessibilityIdentifier("photosNotice") }
                if let p = create.photos.preparingText { Text(p).font(.caption.weight(.semibold)).foregroundStyle(Theme.primary).accessibilityIdentifier("photosPreparing") }
            }
        } else if model.selectedTab == 1, !form.hasDeck, !create.deck.isActive {
            // Create was opened from the Media tab with nothing ticked: the library is one tap away
            Button { focused = false; addOnLibrary = true; startPhotoAdd() } label: {
                Label(tr("create.use_library"), systemImage: "photo.stack").font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.primary)
                    .padding(.horizontal, 16).frame(minHeight: 44).background(Theme.primaryContainer, in: Capsule())
            }
            .buttonStyle(.plain).accessibilityIdentifier("useLibrary")
        }
    }

    // presentation

    /// Choosing photos while a presentation is attached replaces it (after asking).
    private func startPhotoAdd() { if AttachRule.photos(deckActive: create.deck.isActive) == .confirm { confirmPhotosReplace = true } else { showingAdd = true } }

    /// Choosing a presentation while photos are attached replaces them (after asking).
    private func startDeckPick() {
        focused = false
        if AttachRule.deck(photos: totalPhotos + create.photos.loading) == .confirm { confirmDeckReplace = true } else { showingImporter = true }
    }

    private func clearAttachedPhotos() { create.clearPhotos(library: &model.composerLibrary) }

    @ViewBuilder private var deckSection: some View {
        if create.deck.isActive { DeckCard(create: create) { startDeckPick() }.id("deck") }
    }

    // pills: For, Length, Look, and the one Options sheet

    private var pills: some View {
        WrapLayout(spacing: 8) {
            forPill
            lengthPill
            lookPill
        }
        .accessibilityElement(children: .contain)
    }

    /// Short words only (a pill is 12 characters at most); the menu rows carry the long names.
    private func shortName(_ chip: PlatformChip) -> String {
        switch chip.id { case "other": tr("pill.video"); case "shorts": tr("pill.shorts"); default: chip.label }
    }

    private var forPill: some View {
        let current = form.chip(create.caps)
        let value = form.isCustom(create.caps) ? tr("create.custom") : (current.map(shortName) ?? tr("pill.video"))
        return Pill(symbol: form.aspect == "16:9" ? "rectangle" : "rectangle.portrait", value: value, spoken: tr("create.what_is_it_for"), identifier: "forPill") {
            ForEach(PlatformChips.make(create.caps)) { chip in
                let selected = current?.id == chip.id && !form.isCustom(create.caps)
                Button {
                    if chip.supported { create.form.select(chip); Haptics.play(.selection) } else { Haptics.play(.warning) }
                } label: {
                    if selected { Label(chip.label, systemImage: "checkmark") } else { Text(chip.supported ? chip.label : tr("create.chip_soon_a11y", chip.label, create.caps.aspectName(chip.aspect))) }
                }
                .disabled(!chip.supported)
                .accessibilityIdentifier("platform-\(chip.id)")
            }
        }
    }

    private var lengthPill: some View {
        let max = form.chip(create.caps)?.maxMinutes
        return Pill(symbol: "clock", value: LengthLabel.chip(form.minutes), spoken: tr("create.length"), identifier: "lengthPill") {
            ForEach(create.caps.lengthPresets, id: \.self) { m in
                let credits = ComposerPlan.credits(forMinutes: m, multiplier: form.creditsMultiplier)
                let over = max.map { m > $0 + 1e-9 } ?? false
                Button { create.form.setMinutes(m); Haptics.play(.selection) } label: {
                    let title = "\(LengthLabel.chip(m))  ·  \(tr("credits.count", credits))"
                    if form.minutes == m { Label(title, systemImage: "checkmark") } else { Text(title) }
                }
                .disabled(over)
                .accessibilityLabel(tr("create.length_a11y", LengthLabel.spoken(m), tr("credits.count", credits)))
                .accessibilityIdentifier("length-\(m < 1 ? "\(Int((m * 60).rounded()))s" : "\(Int(m))")")
            }
            if let chip = form.chip(create.caps), let max { Text(tr("create.max_length", chip.label, LengthLabel.clock(max))) }
        }
    }

    private var lookPill: some View {
        Pill(symbol: "sparkles", value: form.look?.title ?? tr("pill.auto"), spoken: tr("create.look"), identifier: "lookPill") {
            Button { create.form.look = nil; Haptics.play(.selection) } label: { if form.look == nil { Label(tr("look.auto"), systemImage: "checkmark") } else { Text(tr("look.auto")) } }
            ForEach(VideoLook.allCases) { l in
                Button { create.form.look = l; Haptics.play(.selection) } label: { if form.look == l { Label(l.title, systemImage: "checkmark") } else { Text(l.title) } }
            }
        }
    }

    // notices: at most one, only when something needs a decision

    @ViewBuilder private var notice: some View {
        if form.deckVerticalWarning {
            noticeRow(tr("deck.vertical_warning"), id: "deckVerticalWarning", fix: tr("create.use", "16:9"), fixID: "deckUse169") { create.form.aspect = "16:9"; create.form.normalize(create.caps); Haptics.play(.selection) }
        } else if let advice = form.fourKAdvice(create.caps) {
            noticeRow(advice.text, id: "fourKAdvice", fix: tr("create.use", create.caps.resolutionLabel(advice.useResolution)), fixID: "use1080p") { create.form.setResolution(advice.useResolution); Haptics.play(.selection) }
        } else if let hint = form.maxLengthHint(create.caps) {
            noticeRow(hint.text, id: "maxLengthHint", fix: tr("create.use", LengthLabel.chip(hint.fixMinutes)), fixID: "maxFixChip") { create.form.setMinutes(hint.fixMinutes); Haptics.play(.selection) }
        }
    }

    private func noticeRow(_ text: String, id: String, fix: String, fixID: String, action: @escaping () -> Void) -> some View {
        HStack(alignment: .center, spacing: 10) {
            Image(systemName: "info.circle").font(.vmk(14)).foregroundStyle(Theme.warning).accessibilityHidden(true)
            Text(text).font(.vmk(14)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(id)
            Spacer(minLength: 4)
            FixChip(title: fix, action: action).accessibilityIdentifier(fixID)
        }
        .padding(12).background(Theme.warningContainer.opacity(0.5), in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
    }

    // MARK: bottom bar

    private func bottomBar(_ proxy: ScrollViewProxy) -> some View {
        let s = status
        let ready = s.canSend && !checking
        return VStack(spacing: 8) {
            Button { tapCreate(s, proxy) } label: {
                HStack(spacing: 8) {
                    if checking { ProgressView().tint(Theme.onPrimary) }
                    Text(checking ? checkingLine : tr("create.create_video")).font(.vmk(19, weight: .bold))
                    if showsPrice, !checking {          // not while a presentation is still being read: its price is not known yet
                        Text(verbatim: "·").font(.vmk(19, weight: .bold))
                        HStack(spacing: 3) { Image(systemName: "bolt.fill").font(.vmk(15)); Text("\(form.options.credits)").font(.vmk(19, weight: .bold).monospacedDigit()) }
                    }
                }
                .foregroundStyle(ready || checking ? Theme.onPrimary : Theme.textTertiary).multilineTextAlignment(.center).frame(maxWidth: .infinity, minHeight: 54).padding(.vertical, 6)
                .background { Capsule().fill(Theme.surface3).opacity(ready || checking ? 0 : 1); Capsule().fill(Theme.gradient).opacity(ready || checking ? 1 : 0) }
                .shadow(color: Theme.gradientStart.opacity(ready ? 0.3 : 0), radius: 10, y: 4)
            }
            .buttonStyle(.plain).disabled(checking)
            .accessibilityLabel(typeSize.isAccessibilitySize ? tr("create.create_a11y_credits", tr("credits.count", form.options.credits)) : tr("create.create_video"))
            .accessibilityValue(ready ? tr("create.ready_costs", tr("credits.count", form.options.credits)) : checking ? tr("create.checking_a11y") : tr("create.not_ready", s.message))
            .accessibilityHint(ready ? tr("create.starts_video") : tr("create.tells_missing"))
            .accessibilityIdentifier("sendButton")
            caption(s)
        }
        .padding(.horizontal, 20).padding(.top, 10).padding(.bottom, 8)
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)      // the bar that is always visible stays compact; the form above scrolls at full size
        .background(.bar)
    }

    /// One line under the button, only when it says something: what is left, what is missing, or what is wrong (with its one-tap fix).
    @ViewBuilder private func caption(_ s: ComposerStatus) -> some View {
        Group {
            if checking {
                Button(tr("common.cancel")) { stopChecking() }.font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: 44).accessibilityIdentifier("checkingCancel")
            } else if s.kind == .ready {
                if let balance { Text(tr("create.credits_left", balance - form.options.credits)).font(.vmk(14)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("costLine") } else { Color.clear.frame(height: 0) }
            } else if s.kind == .price || (s.kind == .tooShort && !form.hasContent) {
                Text(tr("create.describe_to_continue")).font(.vmk(14)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("costLine")
            } else {
                HStack(spacing: 8) {
                    Image(systemName: s.isProblem && s.kind != .tooShort ? "exclamationmark.triangle" : "info.circle").font(.vmk(14, weight: .semibold)).foregroundStyle(tint(s)).accessibilityHidden(true)
                    Text(s.message).font(.vmk(14, weight: .medium)).foregroundStyle(tint(s)).fixedSize(horizontal: false, vertical: true)
                        .modifier(Shake(travel: reduceMotion ? 0 : 4, value: shake))
                        .accessibilityIdentifier(unaffordable ? "notEnoughCredits" : s.kind == .photoHint ? "photoCapacityHint" : "costLine")
                    Spacer(minLength: 4)
                    if let fix = s.fix { FixChip(title: fix.title) { applyFix(fix) }.accessibilityIdentifier("fixChip") }
                }
                .padding(.horizontal, flash ? 6 : 0).background(flash ? Theme.warningContainer : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
        .frame(minHeight: 22)
        .accessibilityElement(children: .contain).accessibilityIdentifier("statusLine")
    }

    /// What the button says while the request is checked: one short honest line.
    private var checkingLine: String { if case .checking(let slow) = create.stage, slow { tr("create.checking_slow") } else { tr("create.checking_your_request") } }

    private var showsPrice: Bool { create.deckComposer == .none || create.deckComposer == .ready }

    private func tint(_ s: ComposerStatus) -> Color { s.kind == .tooLong ? Theme.danger : (s.isProblem && s.kind != .tooShort) ? Theme.warning : Theme.textSecondary }

    private func applyFix(_ fix: ComposerStatus.Fix) {
        switch fix {
        case .useMinutes(let m, _): create.form.setMinutes(m); Haptics.play(.selection)
        case .addCredits: model.requestCredits = true
        }
    }

    private func tapCreate(_ s: ComposerStatus, _ proxy: ScrollViewProxy) {
        if checking { return }
        guard s.canSend else {
            Haptics.play(.warning)
            withAnimation(.linear(duration: 0.28)) { shake += 1 }
            withAnimation(.easeOut(duration: 0.15)) { flash = true }
            Task { try? await Task.sleep(for: .milliseconds(450)); withAnimation(.easeOut(duration: 0.2)) { flash = false } }
            UIAccessibility.post(notification: .announcement, argument: s.kind == .tooShort || s.kind == .price ? tr("create.describe_to_continue") : s.announcement)
            if s.kind == .tooShort || s.kind == .price { withAnimation { proxy.scrollTo("prompt", anchor: .top) }; focused = true }
            return
        }
        dictation.cancel(); focused = false
        Haptics.play(.send)
        create.create(mediaCount: totalPhotos, submit: finish)
        if checking { UIAccessibility.post(notification: .announcement, argument: tr("create.checking_your_request")) }
    }

    /// The request is cleared (or confirmed): the video starts, the screen closes onto the library.
    private func finish(_ brief: [String: String]?) {
        model.submit(brief: form.text, options: form.options, photos: create.photos.items.map(\.data), meta: create.photos.items.map(\.meta), libraryMedia: model.composerLibrary.map(\.id), intake: brief,
                     deckID: create.deck.ready == nil ? nil : create.deck.deckID, deckName: create.deck.fileName, sendsMinutes: form.sendsDeckMinutes)
        create.remember()
        create.photos.clear(); model.composerLibrary = []
        create.deck.consume(); create.form.clearDeck()
        create.stage = .form; create.form.text = ""
        UINotificationFeedbackGenerator().notificationOccurred(.success)
        dismiss()
    }

    /// The X: nothing typed (library photos do not count: they are still ticked in Media) closes at once and the next Create starts empty.
    private func cancel() {
        if checking { stopChecking(); return }
        if create.hasEdits { confirmDiscard = true } else { create.cancelCheck(); model.composerLibrary = []; dismiss() }
    }
    /// Cancel during the request check: the call is dropped (a late answer is ignored, nothing is sent) and the form is back exactly as it was.
    private func stopChecking() {
        create.cancelCheck(); Haptics.play(.selection)
        UIAccessibility.post(notification: .announcement, argument: tr("create.check_cancelled"))
    }
    private func discard() { dictation.cancel(); create.cancelCheck(); create.photos.clear(); model.composerLibrary = []; create.removeDeck(); create.form.text = ""; dismiss() }
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
        case .phone(let p): Image(uiImage: p.thumbnail).resizable().scaledToFill().frame(width: 56, height: 56).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous)).accessibilityIdentifier("attachedPhoto")
        case .library(let l): LibraryStripTile(photo: l, media: media, label: tr("create.library_photo_a11y"), showRemove: false) {}
        }
    }
}

private struct MicGlass: ViewModifier {
    let listening: Bool
    func body(content: Content) -> some View { if listening { content } else { content.vmkGlass(in: Circle()) } }
}
