import SwiftUI
import VideoMKCore

/// Create is one sentence (docs/DESIGN_BAR_2026.md, signatures 1 and 2): a caret and "A video about…", three examples that type themselves in,
/// two icons (photos, mic), three choices already made (platform, length, look) and one gradient button with its price. After the tap the form
/// dims and locks, the button becomes the live capsule ("Checking your request", then "Starting your video") and Cancel is the only control.
struct CreateView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var scheme
    @Bindable var create: CreateModel
    @State private var dictation = Dictation()
    @State private var showingAdd = false
    @State private var confirmDiscard = false
    @State private var addOnLibrary = false
    @State private var flash = false
    @State private var shake: CGFloat = 0
    @State private var showingImporter = false
    @State private var confirmDeckReplace = false      // a presentation was chosen while photos are attached
    @State private var confirmPhotosReplace = false    // photos were chosen while a presentation is attached
    @State private var pendingDeckPick = false
    @State private var typing: Task<Void, Never>?      // an example typing itself into the prompt
    @State private var typingTarget: String?
    @FocusState private var focused: Bool
    @Namespace private var morph

    private var balance: Int? { model.wallet.flatMap { $0.unlimited ? nil : $0.balance } }
    private var libraryCount: Int { model.composerLibrary.count }
    private var totalPhotos: Int { create.totalPhotos(library: libraryCount) }
    private var capsule: CreateCapsule { create.capsule }
    private var locked: Bool { capsule.isLocked }
    private var status: ComposerStatus { create.status(balance: balance, dictating: dictation.isListening) }
    private var unaffordable: Bool { status.kind == .notAffordable || status.kind == .noCredits }
    private var form: CreateForm { create.form }
    private var showsExamples: Bool { !locked && form.text.isEmpty && typingTarget == nil && totalPhotos == 0 && create.photos.loading == 0 && !form.hasDeck && !create.deck.isActive }

    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
                ScrollView {
                    VStack(alignment: .leading, spacing: Theme.Space.l) {
                        Group {         // locked and dimmed while the request is checked and started: nothing can change under the call
                            promptField.id("prompt")
                            if showsExamples { examples.transition(.opacity) }
                            if form.hasDeck { Text(tr("deck.prompt_hint")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("deckPromptHint") }
                            attachments
                            deckSection
                            if locked { chosen.transition(.opacity) }
                            notice
                        }
                        .disabled(locked).opacity(locked ? 0.5 : 1).saturation(locked ? 0.8 : 1)
                    }
                    .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.l).padding(.bottom, Theme.Space.xxl)
                    .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: locked)
                    .animation(reduceMotion ? nil : Theme.Motion.select, value: showsExamples)
                }
                .scrollDismissesKeyboard(.interactively)
                .onChange(of: create.deck.state) { _, state in
                    // a result (ready or a problem) is brought fully into view: on a small phone its buttons start under the bottom bar
                    switch state { case .ready, .failed: withAnimation(reduceMotion ? nil : Theme.Motion.spring) { proxy.scrollTo("deck", anchor: .bottom) }; default: break }
                }
                .safeAreaInset(edge: .top, spacing: 0) {
                    TopBar(leading: { IconButton(symbol: "xmark", label: capsule.canCancel ? tr("common.cancel") : tr("common.close"), identifier: "createCancel") { cancel() }.disabled(capsule.phase == .starting).opacity(locked ? 0.5 : 1) })
                }
                .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar(proxy) }
                .background { ZStack(alignment: .bottom) { Theme.background; if locked { Aura().transition(.opacity) } }.ignoresSafeArea().animation(Theme.Motion.reveal, value: locked) }
            }
            .toolbar(.hidden, for: .navigationBar)
            .confirmationDialog(tr("create.discard_this_video"), isPresented: $confirmDiscard, titleVisibility: .visible) {
                Button(tr("create.discard"), role: .destructive) { discard() }
                Button(tr("create.keep_editing"), role: .cancel) {}
            }
        }
        .task {
            await create.loadCapabilities(userID: model.userID)
            if let auto = create.autoOpenPhotos { create.autoOpenPhotos = nil; addOnLibrary = auto.library; try? await Task.sleep(for: .milliseconds(350)); showingAdd = true }
            else if let text = create.typeIn { create.typeIn = nil; try? await Task.sleep(for: .milliseconds(350)); typeIn(text) }
            else if !create.form.hasContent && !create.form.hasDeck && !create.deck.isActive && create.stage == .form && !locked {      // the caret is there at once on an empty prompt: type, then Create
                try? await Task.sleep(for: .milliseconds(450)); if !create.form.hasContent, typingTarget == nil { focused = true }
            }
        }
        .onAppear { dictation.onText = { create.form.text = $0 }; dictation.onKeyboardFallback = { focused = true } }
        .onDisappear { dictation.stop(); typing?.cancel() }
        .onChange(of: focused) { _, f in if f { finishTyping() } }
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
        .sheet(isPresented: Binding(get: { create.stage != .form }, set: { if !$0 { create.dismissOverlay() } })) {
            CreateStageSheet(create: create, balance: balance, mediaCount: totalPhotos, onSubmit: start, onEdit: { create.dismissOverlay(); focused = true })
        }
        .onChange(of: libraryCount, initial: true) { _, n in create.photos.libraryCount = n }
        .onChange(of: capsule.ending) { _, ending in if ending == .refusal { Haptics.play(.warning) } }
    }

    // MARK: the sentence

    /// The prompt: a caret and "A video about…", large and borderless. Nothing else competes with it.
    private var promptField: some View {
        TextField(form.hasDeck ? tr("deck.placeholder") : tr("create.describe_your_video_for_example"), text: $create.form.text, axis: .vertical)
            .focused($focused).lineLimit(1...12).textRole(.prompt).tint(Theme.primary)
            .textInputAutocapitalization(.sentences)
            .foregroundStyle(dictation.isListening ? Theme.textSecondary : Theme.text)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .topLeading)
            .accessibilityIdentifier("composerField")
            .overlay(alignment: .top) { dictationHint }
    }

    /// Three examples. A tap types the sentence into the prompt (Reduce Motion and VoiceOver: it is simply there).
    private var examples: some View {
        WrapLayout(spacing: Theme.Space.s) {
            ForEach(ExamplePrompt.all) { e in
                SparkleChip(title: e.label, identifier: "createExample", hint: tr("videos.fills_in_the_description_it")) { Haptics.play(.selection); typeIn(e.text) }
            }
        }
        .padding(.top, Theme.Space.xs)
    }

    private func typeIn(_ text: String) {
        typing?.cancel(); focused = false
        guard !reduceMotion, !UIAccessibility.isVoiceOverRunning else { create.form.text = text; typingTarget = nil; return }
        typingTarget = text; create.form.text = ""
        typing = Task {
            for ch in text {
                try? await Task.sleep(for: .milliseconds(16))
                if Task.isCancelled { return }
                create.form.text.append(ch)
            }
            typingTarget = nil
        }
    }

    /// The person took over (tapped the prompt) while an example was still typing: the whole sentence is there at once.
    private func finishTyping() {
        guard let target = typingTarget else { return }
        typing?.cancel(); typing = nil; typingTarget = nil; create.form.text = target
    }

    @ViewBuilder private var dictationHint: some View {
        if case .unavailable(let message) = dictation.state {
            Label(message, systemImage: "mic.slash").font(.role(.footnote)).foregroundStyle(Theme.text).padding(Theme.Space.m)
                .background(Theme.warningContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous)).offset(y: -52)
                .accessibilityIdentifier("dictationUnavailable")
                .task(id: message) { try? await Task.sleep(for: .seconds(12)); dictation.clearHint() }
        } else if case .keyboardHint(let message) = dictation.state {
            Label(message, systemImage: "keyboard").font(.role(.footnote)).foregroundStyle(Theme.textSecondary).padding(Theme.Space.m)
                .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous)).offset(y: -52)
                .accessibilityIdentifier("dictationKeyboardHint")
                .task { try? await Task.sleep(for: .seconds(8)); dictation.clearHint() }
        }
    }

    private var mic: some View {
        Button {
            Task { await dictation.toggle(currentText: create.form.text) }
            Haptics.play(.selection)
        } label: {
            if dictation.isListening {
                Image(systemName: "stop.fill").font(.vmk(16, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.xxxLarge).foregroundStyle(Theme.onPrimary)
                    .frame(width: Theme.iconButton, height: Theme.iconButton).background(Theme.dangerSolid, in: Circle())
                    .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Circle())
            } else { IconButtonFace(symbol: "mic") }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dictation.isListening ? tr("create.stop_dictation") : tr("create.dictate")).accessibilityHint(tr("create.say_what_video_you_want"))
        .accessibilityAddTraits(.isToggle).accessibilityIdentifier("micButton")
    }

    // photos

    /// One photo icon; a count badge when something is attached. When the account has presentations (and none is attached) it is a small menu:
    /// Photos, or Add a presentation.
    @ViewBuilder private var photoButton: some View {
        if create.deckAvailable && !create.deck.isActive {
            Menu {
                Button { focused = false; addOnLibrary = false; startPhotoAdd() } label: { Label(tr("media.add_photos"), systemImage: "photo") }.accessibilityIdentifier("photosMenuItem")
                Button { startDeckPick() } label: { Label(tr("create.add_presentation"), systemImage: "rectangle.on.rectangle") }.accessibilityIdentifier("deckButton")
            } label: { photoIcon }
            .accessibilityLabel(totalPhotos > 0 ? tr("photos.count", totalPhotos) : tr("media.add_photos")).accessibilityIdentifier("photoButton")
        } else {
            Button { focused = false; addOnLibrary = false; startPhotoAdd() } label: { photoIcon }
                .buttonStyle(.plain)
                .accessibilityLabel(totalPhotos > 0 ? tr("photos.count", totalPhotos) : tr("media.add_photos")).accessibilityHint(tr("create.choose_photos_from_this_phone")).accessibilityIdentifier("photoButton")
        }
    }

    /// The photo-plus glyph (the words "Add photos" are its spoken label); a count when something is attached.
    private var photoIcon: some View {
        IconButtonFace(symbol: "photo.badge.plus")
            .overlay(alignment: .topTrailing) {
                if totalPhotos > 0 { Text("\(totalPhotos)").font(.role(.caption, weight: .bold).monospacedDigit()).foregroundStyle(Theme.onPrimary).padding(.horizontal, 6).frame(minWidth: 20, minHeight: 20).background(Theme.primary, in: Capsule()).offset(x: 8, y: -6).accessibilityHidden(true) }
            }
    }

    /// The attached photos: every photo with its own (x), one tile to add more, and the count beneath. Only when something is attached.
    @ViewBuilder private var attachments: some View {
        if totalPhotos > 0 || create.photos.loading > 0 {
            VStack(alignment: .leading, spacing: Theme.Space.s) {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: Theme.Space.s) {
                        ForEach(Array(create.photos.items.enumerated()), id: \.element.id) { index, p in
                            Image(uiImage: p.thumbnail).resizable().scaledToFill().frame(width: 62, height: 62)
                                .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                                .overlay(alignment: .topTrailing) { if !locked { RemoveX(label: tr("attach.remove_photo", index + 1)) { withAnimation(reduceMotion ? nil : Theme.Motion.spring) { create.photos.remove(p.id) } } } }
                                .accessibilityElement(children: .contain).accessibilityLabel(tr("attach.photo_n_of", index + 1, create.photos.items.count)).accessibilityIdentifier("attachedPhoto")
                        }
                        ForEach(Array(model.composerLibrary.enumerated()), id: \.element.id) { index, photo in
                            LibraryStripTile(photo: photo, media: model.media, label: tr("attach.library_photo_n_of", index + 1, model.composerLibrary.count), showRemove: !locked) {
                                withAnimation(reduceMotion ? nil : Theme.Motion.spring) { model.composerLibrary.removeAll { $0.id == photo.id } }
                            }
                        }
                        if create.photos.loading > 0 { ProgressView().frame(width: 62, height: 62) }
                        if !locked {
                            Button { focused = false; addOnLibrary = false; startPhotoAdd() } label: {
                                Image(systemName: "photo.badge.plus").font(.role(.headline)).foregroundStyle(Theme.primary).frame(width: 62, height: 62)
                                    .background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                            }
                            .buttonStyle(.plain).accessibilityLabel(tr("create.add_more_photos")).accessibilityIdentifier("editPhotos")
                        }
                    }
                    .padding(.top, Theme.Space.m).padding(.trailing, Theme.Space.m)           // room for the (x) that sits over each corner
                }
                .padding(.horizontal, -Theme.gutter).contentMargins(.horizontal, Theme.gutter, for: .scrollContent)      // the strip runs to the screen edge
                Text(tr("photos.count", totalPhotos)).font(.role(.footnote).monospacedDigit()).foregroundStyle(Theme.textSecondary)
                    .accessibilityIdentifier("photosNote")
                if let n = create.photos.notice { Label(n, systemImage: "exclamationmark.circle").font(.role(.footnote)).foregroundStyle(Theme.text).accessibilityIdentifier("photosNotice") }
                if let p = create.photos.preparingText { Text(p).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary).accessibilityIdentifier("photosPreparing") }
            }
        } else if model.selectedTab == 1, !form.hasDeck, !create.deck.isActive, !locked {
            // Create was opened from the Media tab with nothing ticked: the library is one tap away
            Button { focused = false; addOnLibrary = true; startPhotoAdd() } label: { Label(tr("create.use_library"), systemImage: "photo.stack") }
                .buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("useLibrary")
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

    // three choices already made: platform, length, look. Values only, no key labels.

    private var pills: some View {
        WrapLayout(spacing: Theme.Space.s) {
            forPill
            lengthPill
            lookPill
        }
        .accessibilityElement(children: .contain)
    }

    /// The same three, as plain words, while the screen is locked.
    private var chosen: some View {
        WrapLayout(spacing: Theme.Space.s) { StaticPill(value: forValue); StaticPill(value: LengthLabel.chip(form.minutes)); StaticPill(value: lookValue) }
            .accessibilityElement(children: .combine).accessibilityIdentifier("chosenPills")
    }

    /// Short words only (a pill is 12 characters at most); the menu rows carry the long names.
    private func shortName(_ chip: PlatformChip) -> String {
        switch chip.id { case "other": tr("pill.video"); case "shorts": tr("pill.shorts"); default: chip.label }
    }

    private var forValue: String { form.isCustom(create.caps) ? tr("create.custom") : (form.chip(create.caps).map(shortName) ?? tr("pill.video")) }
    private var lookValue: String { form.look?.title ?? tr("pill.auto_look") }

    private var forPill: some View {
        let current = form.chip(create.caps)
        return Pill(value: forValue, spoken: tr("create.what_is_it_for"), identifier: "forPill") {
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
        return Pill(value: LengthLabel.chip(form.minutes), spoken: tr("create.length"), identifier: "lengthPill") {
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
        Pill(value: lookValue, spoken: tr("create.look"), identifier: "lookPill") {
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
        HStack(alignment: .center, spacing: Theme.Space.m) {
            Image(systemName: "info.circle").font(.role(.subhead)).foregroundStyle(Theme.warning).accessibilityHidden(true)
            Text(text).font(.role(.subhead)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(id)
            Spacer(minLength: Theme.Space.xs)
            FixChip(title: fix, action: action).accessibilityIdentifier(fixID)
        }
        .padding(Theme.Space.m).background(Theme.warningContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous))
    }

    // MARK: bottom bar

    /// Editing: photos and mic, the options icon, the three pills, the ONE gradient button with its price. After the tap: the live capsule and Cancel.
    private func bottomBar(_ proxy: ScrollViewProxy) -> some View {
        let s = status
        return VStack(spacing: 0) {
            if locked { waiting.transition(.opacity) }
            else {
                VStack(spacing: Theme.Space.m) {
                    HStack(spacing: Theme.Space.s) {
                        photoButton
                        mic
                        if dictation.isListening { Text(tr("create.listening_tap_to_stop")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).accessibilityIdentifier("listeningHint") }
                        Spacer(minLength: Theme.Space.s)
                        IconButton(symbol: "slider.horizontal.3", label: tr("create.options"), identifier: "moreOptions") { focused = false; create.showMore = true }
                    }
                    pills.frame(maxWidth: .infinity, alignment: .leading)
                    createButton(s, proxy).padding(.top, Theme.Space.xs)
                    caption(s)
                }
                .transition(.opacity)
            }
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s).padding(.bottom, Theme.Space.s)
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)      // the bar that is always visible stays compact; the sentence above scrolls at full size
        .background { if !locked { Theme.background.ignoresSafeArea(edges: .bottom) } }
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: capsule.phase)
    }

    private func createButton(_ s: ComposerStatus, _ proxy: ScrollViewProxy) -> some View {
        Button { tapCreate(s, proxy) } label: {
            PrimaryLabel(title: tr("create.create_video"), spread: true) {
                if showsPrice {          // not while a presentation is still being read: its price is not known yet
                    HStack(spacing: 4) { Image(systemName: "bolt.fill").font(.role(.subhead)); Text("\(form.options.credits)").monospacedDigit() }.accessibilityHidden(true)
                }
            }
            .matchedGeometryEffect(id: "label", in: morph, properties: .position)
        }
        .buttonStyle(PrimaryButtonStyle())
        .matchedGeometryEffect(id: "cta", in: morph)
        .accessibilityLabel(typeSize.isAccessibilitySize ? tr("create.create_a11y_credits", tr("credits.count", form.options.credits)) : tr("create.create_video"))
        .accessibilityValue(s.canSend ? tr("create.ready_costs", tr("credits.count", form.options.credits)) : tr("create.not_ready", s.message))
        .accessibilityHint(s.canSend ? tr("create.starts_video") : tr("create.tells_missing"))
        .accessibilityIdentifier("sendButton")
    }

    /// The live capsule: what is happening in three words, a turning ring, and Cancel as the only control (while cancelling is still honest).
    private var waiting: some View {
        VStack(spacing: Theme.Space.s) {
            HStack(spacing: Theme.Space.m) {
                Image(systemName: "sparkle").font(.role(.headline)).foregroundStyle(scheme == .dark ? Theme.live : Theme.gradientEnd).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 1) {
                    Text(capsuleTitle).font(.role(.headline)).foregroundStyle(Theme.text).accessibilityIdentifier("capsuleTitle")
                    Text(capsuleSub).font(.role(.caption)).foregroundStyle(Theme.textSecondary)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: Theme.Space.s)
                LiveSpinner()
            }
            .padding(.horizontal, 22).padding(.vertical, Theme.Space.s).frame(maxWidth: .infinity, minHeight: 64)
            .background(Theme.surface, in: Capsule())
            .overlay(LiveRing(shape: Capsule(), lineWidth: 2))
            .matchedGeometryEffect(id: "cta", in: morph)
            .elevation(3)
            .accessibilityElement(children: .combine).accessibilityLabel(capsuleTitle).accessibilityAddTraits(.updatesFrequently).accessibilityIdentifier("createCapsule")
            Button(tr("common.cancel")) { stopChecking() }
                .font(.role(.headline, weight: .medium)).foregroundStyle(Theme.textSecondary).frame(minWidth: 120, minHeight: Theme.minTouch)
                .opacity(capsule.canCancel ? 1 : 0).disabled(!capsule.canCancel).accessibilityHidden(!capsule.canCancel)
                .accessibilityIdentifier("checkingCancel")
        }
        .padding(.bottom, Theme.Space.s)
    }

    private var capsuleTitle: String { capsule.phase == .starting ? tr("create.starting_your_video") : tr("create.checking_your_request") }
    private var capsuleSub: String { capsule.phase == .starting ? tr("create.starting_sub") : capsule.isSlow ? tr("create.checking_slow") : tr("create.checking_sub") }

    /// One line under the button, only when it says something: what is left, what is missing, or what went wrong (with its one-tap fix).
    @ViewBuilder private func caption(_ s: ComposerStatus) -> some View {
        Group {
            if let error = create.startError, s.canSend {
                Label(error, systemImage: "exclamationmark.circle").font(.role(.footnote, weight: .medium)).foregroundStyle(Theme.text).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
                    .labelStyle(DangerMarkLabel()).accessibilityIdentifier("startError")
            } else if s.kind == .ready || s.kind == .price || (s.kind == .tooShort && !form.hasContent) {
                if let balance, balance - form.options.credits >= 0 { Text(tr("create.credits_left", balance - form.options.credits)).font(.role(.caption)).foregroundStyle(Theme.textSecondary).monospacedDigit().accessibilityIdentifier("costLine") } else { Color.clear.frame(height: 0) }
            } else {
                HStack(spacing: Theme.Space.s) {
                    Image(systemName: s.isProblem && s.kind != .tooShort ? "exclamationmark.circle" : "info.circle").font(.role(.footnote, weight: .semibold)).foregroundStyle(tint(s)).accessibilityHidden(true)
                    Text(s.message).font(.role(.footnote, weight: .medium)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                        .modifier(Shake(travel: reduceMotion ? 0 : 4, value: shake))
                        .accessibilityIdentifier(unaffordable ? "notEnoughCredits" : s.kind == .photoHint ? "photoCapacityHint" : "costLine")
                    Spacer(minLength: Theme.Space.xs)
                    if let fix = s.fix { FixChip(title: fix.title) { applyFix(fix) }.accessibilityIdentifier("fixChip") }
                }
                .padding(.horizontal, flash ? 6 : 0).background(flash ? Theme.warningContainer : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            }
        }
        .frame(minHeight: 18)
        .accessibilityElement(children: .contain).accessibilityIdentifier("statusLine")
    }

    private var showsPrice: Bool { create.deckComposer == .none || create.deckComposer == .ready }

    private func tint(_ s: ComposerStatus) -> Color { s.kind == .tooLong ? Theme.danger : (s.isProblem && s.kind != .tooShort) ? Theme.warning : Theme.textSecondary }

    private func applyFix(_ fix: ComposerStatus.Fix) {
        switch fix {
        case .useMinutes(let m, _): create.form.setMinutes(m); Haptics.play(.selection)
        case .addCredits: model.requestCredits = true
        }
    }

    private func tapCreate(_ s: ComposerStatus, _ proxy: ScrollViewProxy) {
        if locked { return }
        finishTyping()
        guard s.canSend else {
            Haptics.play(.warning)
            withAnimation(.linear(duration: 0.28)) { shake += 1 }
            withAnimation(Theme.Motion.press) { flash = true }
            Task { try? await Task.sleep(for: .milliseconds(450)); withAnimation(Theme.Motion.select) { flash = false } }
            UIAccessibility.post(notification: .announcement, argument: s.kind == .tooShort || s.kind == .price ? tr("create.describe_to_continue") : s.announcement)
            if s.kind == .tooShort || s.kind == .price { withAnimation { proxy.scrollTo("prompt", anchor: .top) }; focused = true }
            return
        }
        dictation.cancel(); focused = false
        Haptics.play(.send)
        create.create(mediaCount: totalPhotos, submit: start)
        if capsule.canCancel { UIAccessibility.post(notification: .announcement, argument: tr("create.checking_your_request")) }
    }

    /// The request is cleared (or confirmed): the capsule says "Starting your video" and the request goes out. The screen closes onto the Making card when the
    /// server has taken it (or when photos still have to go up: the card shows that); if it could not be started, the form is back with everything in it.
    private func start(_ brief: [String: String]?) {
        create.stage = .form
        guard create.beginStart() else { return }
        UIAccessibility.post(notification: .announcement, argument: tr("create.starting_your_video"))
        let uploads = !create.photos.items.isEmpty
        let id = model.submit(brief: form.text, options: form.options, photos: create.photos.items.map(\.data), meta: create.photos.items.map(\.meta), libraryMedia: model.composerLibrary.map(\.id), intake: brief,
                              deckID: create.deck.ready == nil ? nil : create.deck.deckID, deckName: create.deck.fileName, sendsMinutes: form.sendsDeckMinutes, held: true)
        Task {
            switch await model.startOutcome(id, wait: uploads ? .milliseconds(900) : .seconds(8), minimum: .milliseconds(900)) {
            case .accepted, .handedOff:
                model.releaseStart(id)
                create.started(); create.remember()
                create.photos.clear(); model.composerLibrary = []
                create.deck.consume(); create.form.clearDeck()
                create.form.text = ""
                dismiss()
            case .failed(let message):
                model.abandonStart(id)
                create.startFailed(message); Haptics.play(.warning)
                UIAccessibility.post(notification: .announcement, argument: message)
            case .refused(let problem):
                model.abandonStart(id)
                create.startRefused(message: problem.message, paused: problem.paused, retryAfter: problem.retryAfter)
            }
        }
    }

    /// The X: nothing typed (library photos do not count: they are still ticked in Media) closes at once and the next Create starts empty.
    private func cancel() {
        if capsule.canCancel { stopChecking(); return }
        if locked { return }
        finishTyping()
        if create.hasEdits { confirmDiscard = true } else { create.cancelCheck(); model.composerLibrary = []; dismiss() }
    }
    /// Cancel during the request check: the call is dropped (a late answer is ignored, nothing is sent) and the form is back exactly as it was.
    private func stopChecking() {
        create.cancelCheck(); Haptics.play(.selection)
        UIAccessibility.post(notification: .announcement, argument: tr("create.check_cancelled"))
    }
    private func discard() { dictation.cancel(); typing?.cancel(); create.cancelCheck(); create.photos.clear(); model.composerLibrary = []; create.removeDeck(); create.form.text = ""; dismiss() }
}

/// The soft light behind the live capsule (decoration only).
struct Aura: View {
    @Environment(\.colorScheme) private var scheme
    var body: some View {
        ZStack {
            Circle().fill(Theme.gradientEnd.opacity(0.42)).frame(width: 340, height: 340).offset(x: -110, y: 40)
            Circle().fill(Theme.live.opacity(0.26)).frame(width: 300, height: 300).offset(x: 120, y: 10)
            Circle().fill(Theme.gradientStart.opacity(0.5)).frame(width: 380, height: 380).offset(y: 170)
        }
        .blur(radius: 60).opacity(scheme == .dark ? 0.55 : 0.8)
        .frame(maxWidth: .infinity, maxHeight: 420, alignment: .bottom).clipped()
        .allowsHitTesting(false).accessibilityHidden(true)
    }
}

/// A line that went wrong: the mark is in the danger colour, the words stay in the text colour (state is never colour alone).
struct DangerMarkLabel: LabelStyle {
    func makeBody(configuration: Configuration) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) { configuration.icon.foregroundStyle(Theme.danger); configuration.title }
    }
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
        case .phone(let p): Image(uiImage: p.thumbnail).resizable().scaledToFill().frame(width: 62, height: 62).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous)).accessibilityIdentifier("attachedPhoto")
        case .library(let l): LibraryStripTile(photo: l, media: media, label: tr("create.library_photo_a11y"), showRemove: false) {}
        }
    }
}

