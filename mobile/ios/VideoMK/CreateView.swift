import PhotosUI
import SwiftUI
import VideoMKCore

/// Create is one sentence (docs/DESIGN_BAR_2026.md, signatures 1 and 2): a caret and "A video about…", examples that type themselves in (until the first
/// video), then ONE dock: a row of pills (platform, length, look, and Characters only for a look with a cast: never a fifth control, the rest is in
/// Options) and ONE tool row: photos, mic, Options on the left, the compact Create pill with its price at the trailing end. After the tap the form
/// dims and locks, the pill springs into the live capsule ("Checking your request", then "Starting your video") and Cancel is the only control.
/// (docs/design_bar/CREATE_SCREEN_REDESIGN_BRIEF.md)
struct CreateView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.colorScheme) private var scheme
    @Bindable var create: CreateModel
    @State private var dictation = Dictation()
    @State private var showingLibrary = false          // "Media": the person's own library, as a picker
    @State private var showingPhonePicker = false      // "Photo library": the system picker, directly
    @State private var phoneItems: [PhotosPickerItem] = []
    @State private var pendingSource: PhotoSource?     // what to open once a presentation was replaced (after asking)
    @State private var keyboardUp = false
    @State private var explaining = false              // a tap on the inactive Create: the line says what is missing, for a few seconds
    enum PhotoSource { case phone, library }
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
    /// Chips are the first-run accelerator: only an empty prompt, and only until the account has made its first video.
    private var showsExamples: Bool { !locked && !model.hasFinishedVideo && form.text.isEmpty && typingTarget == nil && totalPhotos == 0 && create.photos.loading == 0 && !form.hasDeck && !create.deck.isActive }

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
                        // the bar is the page colour up to the status bar, with a short fade under it: the sentence never scrolls under the X or the clock
                        .background(alignment: .top) {
                            VStack(spacing: 0) {
                                Theme.background.ignoresSafeArea(edges: .top)
                                LinearGradient(colors: [Theme.background, Theme.background.opacity(0)], startPoint: .top, endPoint: .bottom).frame(height: Theme.Space.l).offset(y: Theme.Space.l)
                            }
                            .opacity(locked ? 0 : 1).allowsHitTesting(false)
                        }
                }
                .safeAreaInset(edge: .bottom, spacing: 0) { bottomBar(proxy) }
                .background { ZStack(alignment: .bottom) { Theme.background; if locked { Aura().transition(.opacity) } }.ignoresSafeArea().animation(Theme.Motion.reveal, value: locked) }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
        .task {
            await create.loadCapabilities(userID: model.userID)
            if let auto = create.autoOpenPhotos { create.autoOpenPhotos = nil; try? await Task.sleep(for: .milliseconds(350)); open(auto.library ? .library : .phone) }
            else if let text = create.typeIn { create.typeIn = nil; try? await Task.sleep(for: .milliseconds(350)); typeIn(text) }
            else if !create.form.hasContent && !create.form.hasDeck && !create.deck.isActive && create.stage == .form && !locked {      // the caret is there at once on an empty prompt: type, then Create
                try? await Task.sleep(for: .milliseconds(450)); if !create.form.hasContent, typingTarget == nil { focused = true }
            }
        }
        .onAppear { dictation.onText = { create.form.text = $0 }; dictation.onKeyboardFallback = { focused = true } }
        .onDisappear { dictation.stop(); typing?.cancel() }
        .onChange(of: focused) { _, f in if f { finishTyping() } }
        .sheet(isPresented: $showingLibrary) {
            LibraryPickerSheet(attached: totalPhotos) { library in
                let known = Set(model.composerLibrary.map(\.id))
                model.composerLibrary += library.filter { !known.contains($0.id) }
                create.photos.libraryCount = model.composerLibrary.count
            }
        }
        // "Photo library" is the system picker itself: no sheet of ours in between. It only lets through what still fits in one video.
        .photosPicker(isPresented: $showingPhonePicker, selection: $phoneItems, maxSelectionCount: max(1, create.photos.remaining), selectionBehavior: .ordered, matching: .images, photoLibrary: .shared())
        .onChange(of: phoneItems) { _, items in
            guard !items.isEmpty else { return }
            let picked = items; phoneItems = []
            create.photos.add(picked); Haptics.play(.selection)
        }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardUp = true }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardUp = false }
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
            Button(tr("deck.replace_deck.confirm"), role: .destructive) { create.removeDeck(); if let s = pendingSource { pendingSource = nil; present(s) } }
            Button(tr("deck.replace_deck.keep"), role: .cancel) {}
        } message: { Text(tr("deck.replace_deck.message")) }
        .onChange(of: create.deck.state, initial: true) { _, _ in create.syncDeck() }
        .sheet(isPresented: $create.showMore) { CreateOptionsSheet(create: create) }
        .sheet(isPresented: $create.showLook) { LookSheet(create: create, attached: attached) }
        .sheet(isPresented: $create.showCast) { CharactersSheet(create: create) }
        .onChange(of: attached, initial: true) { _, a in create.syncLook(attached: a) }
        .onChange(of: create.caps.looks) { _, _ in create.syncLook(attached: attached) }
        .sheet(isPresented: Binding(get: { create.stage != .form }, set: { if !$0 { create.dismissOverlay() } })) {
            CreateStageSheet(create: create, balance: balance, mediaCount: totalPhotos, onSubmit: start, onEdit: { create.dismissOverlay(); focused = true })
        }
        .onChange(of: libraryCount, initial: true) { _, n in create.photos.libraryCount = n }
        .onChange(of: capsule.ending) { _, ending in if ending == .refusal { Haptics.play(.warning) } }
    }

    // MARK: the sentence

    /// The prompt: a caret and "A video about…", large and borderless. Nothing else competes with it.
    private var promptField: some View {
        TextField("", text: $create.form.text, prompt: Text(form.hasDeck ? tr("deck.placeholder") : tr("create.describe_your_video_for_example")).foregroundStyle(Theme.textTertiary), axis: .vertical)
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
            ForEach(ExamplePrompt.all.prefix(shortScreen ? 2 : 3)) { e in
                SparkleChip(title: e.label, identifier: "createExample", hint: tr("videos.fills_in_the_description_it")) { Haptics.play(.selection); typeIn(e.text) }
            }
        }
        .padding(.top, Theme.Space.xs)
    }

    /// A short screen (iPhone SE, any large text size) shows two examples, not three.
    private var shortScreen: Bool {
        typeSize.isAccessibilitySize || ((UIApplication.shared.connectedScenes.first as? UIWindowScene)?.screen.bounds.height ?? 800) < 700
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
                Image(systemName: "stop.fill").font(.role(.body, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.xxxLarge).foregroundStyle(Theme.onPrimary)
                    .frame(width: Theme.iconButton, height: Theme.iconButton).background(Theme.dangerSolid, in: Circle())
                    .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Circle())
            } else { IconButtonFace(symbol: "mic") }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(dictation.isListening ? tr("create.stop_dictation") : tr("create.dictate")).accessibilityHint(tr("create.say_what_video_you_want"))
        .accessibilityAddTraits(.isToggle).accessibilityIdentifier("micButton")
    }

    // photos

    /// One photo icon ("Add photos"). It is a two-item menu: "Photo library" opens the system picker at once, "Media" opens the person's own library.
    /// (A third item, "Add a presentation", only where the server offers it.) No explainer in between: photo icon, pick, Create.
    private var photoButton: some View {
        Menu { photoMenuItems } label: { IconButtonFace(symbol: "photo.badge.plus") }
            .menuOrder(.fixed)
            .accessibilityLabel(tr("media.add_photos")).accessibilityValue(totalPhotos > 0 ? tr("photos.count", totalPhotos) : "").accessibilityIdentifier("photoButton")
    }

    @ViewBuilder private var photoMenuItems: some View {
        Button { open(.phone) } label: { Label(tr("create.photo_library"), systemImage: "photo.on.rectangle") }.disabled(create.photos.remaining <= 0).accessibilityIdentifier("photosMenuItem")
        if model.media != nil { Button { open(.library) } label: { Label(tr("media.media"), systemImage: "photo.stack") }.disabled(create.photos.remaining <= 0).accessibilityIdentifier("mediaMenuItem") }
        if create.deckAvailable && !create.deck.isActive { Button { startDeckPick() } label: { Label(tr("create.add_presentation"), systemImage: "rectangle.on.rectangle") }.accessibilityIdentifier("deckButton") }
    }

    /// Choosing photos while a presentation is attached replaces it (after asking).
    private func open(_ source: PhotoSource) {
        focused = false
        if AttachRule.photos(deckActive: create.deck.isActive) == .confirm { pendingSource = source; confirmPhotosReplace = true } else { present(source) }
    }

    private func present(_ source: PhotoSource) { switch source { case .phone: showingPhonePicker = true; case .library: showingLibrary = true } }

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
                            Menu { photoMenuItems } label: {
                                Image(systemName: "photo.badge.plus").font(.role(.headline)).foregroundStyle(Theme.primary).frame(width: 62, height: 62)
                                    .background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
                            }
                            .menuOrder(.fixed).accessibilityLabel(tr("create.add_more_photos")).accessibilityIdentifier("editPhotos")
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
            Button { open(.library) } label: { Label(tr("create.use_library"), systemImage: "photo.stack") }
                .buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("useLibrary")
        }
    }

    // presentation


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

    /// With a look that has characters there is a fourth pill, and the row is laid out by what fits, never in more than two rows: all four in one row,
    /// or Characters under the three, or two and two, or two and two with the Characters pill reduced to its faces (large text, small phones).
    @ViewBuilder private var pills: some View {
        let s = Theme.Space.s
        if create.lookHasCast {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: s) { forPill; lengthPill; lookPill; castPill(compact: false) }
                VStack(alignment: .leading, spacing: s) { HStack(spacing: s) { forPill; lengthPill; lookPill }; castPill(compact: false) }
                VStack(alignment: .leading, spacing: s) { HStack(spacing: s) { forPill; lengthPill }; HStack(spacing: s) { lookPill; castPill(compact: false) } }
                VStack(alignment: .leading, spacing: s) { HStack(spacing: s) { forPill; lengthPill }; HStack(spacing: s) { lookPill; castPill(compact: true) } }
                WrapLayout(spacing: s) { forPill; lengthPill; lookPill; castPill(compact: true) }
            }
            .accessibilityElement(children: .contain)
        } else {
            WrapLayout(spacing: s) { forPill; lengthPill; lookPill }.accessibilityElement(children: .contain)
        }
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
    private var lookValue: String { create.caps.looks.map { LookRules.pillLabel(form.lookChoice, caps: $0) } ?? form.look?.title ?? tr("look.auto") }
    /// What is attached decides which looks can be made (the person's own photos or slides are the pictures of the video).
    private var attached: LookRules.Attached { LookRules.Attached(photos: totalPhotos > 0 || create.photos.loading > 0, deck: form.hasDeck || create.deck.isActive) }

    private var forPill: some View {
        let current = form.chip(create.caps)
        return Pill(value: forValue, spoken: tr("create.what_is_it_for"), identifier: "forPill", glyph: PillGlyph(symbol: form.isCustom(create.caps) ? "rectangle" : nil, aspect: form.isCustom(create.caps) ? nil : form.aspect)) {
            ForEach(PlatformChips.make(create.caps)) { chip in
                let selected = current?.id == chip.id && !form.isCustom(create.caps)
                Button {
                    if chip.supported { create.form.select(chip); Haptics.play(.selection) } else { Haptics.play(.warning) }
                } label: {
                    // the same word as on the pill ("Video"), so the menu and the pill never name one thing twice
                    let name = chip.id == "other" ? shortName(chip) : chip.label
                    if selected { Label(name, systemImage: "checkmark") } else { Text(chip.supported ? name : tr("create.chip_soon_a11y", name, create.caps.aspectName(chip.aspect))) }
                }
                .disabled(!chip.supported)
                .accessibilityIdentifier("platform-\(chip.id)")
            }
        }
    }

    private var lengthPill: some View {
        let max = form.chip(create.caps)?.maxMinutes
        return Pill(value: LengthLabel.chip(form.minutes), spoken: tr("create.length"), identifier: "lengthPill", glyph: PillGlyph(symbol: "clock")) {
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

    /// With the server's look picker: the pill says the look only and opens the sheet of four tiles (the characters have their own pill). Without it (an older server): the menu it always was.
    @ViewBuilder private var lookPill: some View {
        if create.caps.looks != nil {
            PillButton(value: lookValue, spoken: tr("create.look"), identifier: "lookPill", glyph: PillGlyph(symbol: "sparkle")) { focused = false; create.dismissLookNotice(); create.showLook = true }
        } else {
            Pill(value: lookValue, spoken: tr("create.look"), identifier: "lookPill", glyph: PillGlyph(symbol: "sparkle")) {
                Button { create.form.look = nil; Haptics.play(.selection) } label: { if form.look == nil { Label(tr("look.auto"), systemImage: "checkmark") } else { Text(tr("look.auto")) } }
                ForEach(VideoLook.allCases) { l in
                    Button { create.form.look = l; Haptics.play(.selection) } label: { if form.look == l { Label(l.title, systemImage: "checkmark") } else { Text(l.title) } }
                }
            }
        }
    }

    /// Only for a look with characters: who explains it. The chosen faces (or the sparkle of "we choose") sit in the pill; it opens the Characters sheet.
    /// `compact`: where the word does not fit in two rows of pills, the faces alone (none chosen: two figures and the sparkle); VoiceOver still hears "Characters".
    private func castPill(compact: Bool) -> some View {
        let looks = create.caps.looks, choice = form.lookChoice
        let faces = choice.cast.compactMap { looks?.cast?.member($0) }
        let extras = choice.extras.compactMap { id in looks?.option(choice.look)?.extras.first { $0.id == id }?.label }
        let spoken = ([faces.isEmpty ? tr("look.auto") : Localization.shared.list(faces.map(\.name))] + extras).joined(separator: ", ")
        return PillButton(value: compact ? "" : tr("looks.cast"), spoken: tr("looks.cast"), spokenValue: spoken, identifier: "castPill") { focused = false; create.dismissLookNotice(); create.showCast = true } accessory: {
            if compact, faces.isEmpty { Image(systemName: "person.2.fill").font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).accessibilityHidden(true) }
            if faces.isEmpty { Image(systemName: "sparkle").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary).accessibilityHidden(true) }
            else { PillFaces(members: faces) }
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
        } else if !form.hasDeck, let nudge = form.lookLengthNudge(create.caps) {
            // the length was shortened after the look was chosen: the video would still be made (one character presents), so this only offers the way back
            noticeRow(LookWords.needs(nudge, form: form, caps: create.caps), id: "lookLengthHint", fix: tr("create.use", LengthLabel.chip(nudge.minutes)), fixID: "lookLengthFix") { create.form.setMinutes(nudge.minutes); Haptics.play(.selection) }
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

    /// Editing: ONE dock. A row of pills (what it is for, how long, which look; Characters only for a look with a cast), then ONE tool row: photos, mic and
    /// Options on the left, the compact Create pill and its price at the trailing end. Nothing else is there unless it has something to say (a status line
    /// above the pills; before the first video, one caption under the tool row). After the tap: the live capsule and Cancel.
    private func bottomBar(_ proxy: ScrollViewProxy) -> some View {
        let s = status
        return VStack(spacing: 0) {
            if locked { waiting.transition(.opacity) }
            else {
                VStack(spacing: Theme.Space.s) {
                    statusLine(s)
                    if !(keyboardUp && typeSize.isAccessibilitySize) {      // largest text with the keyboard up: the room goes to the sentence
                        VStack(alignment: .leading, spacing: Theme.Space.s) {
                            if let line = create.lookNotice {      // the look was changed for the person (photos sent it back to Auto): said right above the pill it is about
                                Text(line).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("lookNotice").transition(.opacity)
                            }
                            pills
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    toolRow(s, proxy)
                    costCaption(s)
                }
                .accessibilityElement(children: .contain).accessibilityIdentifier("createDock")
                .transition(.opacity)
            }
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s).padding(.bottom, Theme.Space.m)
        .dynamicTypeSize(...DynamicTypeSize.accessibility1)      // the bar that is always visible stays compact; the sentence above scrolls at full size
        .background { if !locked { Theme.background.ignoresSafeArea(edges: .bottom) } }
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: capsule.phase)
        .animation(reduceMotion ? nil : Theme.Motion.select, value: statusText(s))
    }

    /// The tools (48 pt high) and Create. One row while it fits: photos, mic, Options on the left, Create at the trailing end (mic stays far from Create: a
    /// mis-tap next to it would spend credits). At accessibility text sizes, or where the row does not fit, Create drops to its own full-width row.
    @ViewBuilder private func toolRow(_ s: ComposerStatus, _ proxy: ScrollViewProxy) -> some View {
        if typeSize.isAccessibilitySize { twoRows(s, proxy) }
        else { ViewThatFits(in: .horizontal) { oneRow(s, proxy); twoRows(s, proxy) } }
    }

    private func oneRow(_ s: ComposerStatus, _ proxy: ScrollViewProxy) -> some View {
        HStack(spacing: Theme.Space.xs) { tools; middle; createButton(s, proxy, full: false) }
    }

    private func twoRows(_ s: ComposerStatus, _ proxy: ScrollViewProxy) -> some View {
        VStack(spacing: Theme.Space.s) {
            HStack(spacing: Theme.Space.xs) { tools; middle }
            createButton(s, proxy, full: true)
        }
    }

    /// Photos, mic, Options. While listening the mic is a filled Stop and the other two are off; Options keeps only its icon to leave room for "Listening…".
    private var tools: some View {
        HStack(spacing: Theme.Space.xs) {
            photoButton.disabled(dictation.isListening)
            mic
            optionsButton(labelled: !dictation.isListening).disabled(dictation.isListening)
        }
    }

    /// The flexible middle of the tool row: empty, or "Listening…" centred between the tools and Create.
    @ViewBuilder private var middle: some View {
        Spacer(minLength: Theme.Space.xs)
        if dictation.isListening {
            Text(tr("composer.listening")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).lineLimit(1).minimumScaleFactor(0.8).layoutPriority(-1).accessibilityIdentifier("listeningHint").transition(.opacity)
            Spacer(minLength: Theme.Space.xs)
        }
    }

    /// The sliders icon with its word: quality, subtitles, language and the format tiles (the platform and the look are pills).
    private func optionsButton(labelled: Bool) -> some View {
        Button { focused = false; create.showMore = true } label: {
            HStack(spacing: 2) {
                IconButtonFace(symbol: "slider.horizontal.3")
                if labelled { Text(tr("create.options")).font(.role(.subhead, weight: .medium)).foregroundStyle(Theme.text).lineLimit(1).padding(.trailing, Theme.Space.s) }
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(tr("create.options")).accessibilityIdentifier("moreOptions")
    }

    /// The ONE primary action: a compact pill, 48 pt high (52 on its own row), 112 pt wide at least, "Create", a bolt and the price as one unit.
    /// Inactive (nothing to send yet): an opaque fill, the secondary label, no shadow; it still takes the tap and says what is missing.
    private func createButton(_ s: ComposerStatus, _ proxy: ScrollViewProxy, full: Bool) -> some View {
        // Cannot afford this length but can afford a shorter one: the fix is written on the button ("Create · 1 min · 1") and one tap makes that video.
        let affordable = affordableFix(s)
        let credits = affordable?.credits ?? form.options.credits
        let inactive = !s.canSend && affordable == nil
        return Button { if let affordable { create.form.setMinutes(affordable.minutes); Haptics.play(.selection) }; tapCreate(status, proxy) } label: {
            HStack(spacing: 6) {
                Text(affordable.map { tr("create.create_length", LengthLabel.chip($0.minutes)) } ?? tr("create.create_video")).lineLimit(1).fixedSize()
                if showsPrice {          // not while a presentation is still being read: its price is not known yet
                    HStack(spacing: 3) { Image(systemName: "bolt.fill").font(.role(.subhead)); Text("\(credits)").monospacedDigit() }.accessibilityHidden(true)
                }
            }
        }
        .buttonStyle(PrimaryButtonStyle(fullWidth: full, looksDisabled: inactive, height: full ? 52 : 48, minWidth: full ? nil : 112, calm: true))
        .modifier(Morph(on: !reduceMotion, namespace: morph))
        .accessibilityLabel(affordable.map { tr("create.create_length", LengthLabel.spoken($0.minutes)) } ?? tr("create.create_video"))
        .accessibilityValue(!inactive ? tr("create.ready_costs", tr("credits.count", credits)) : tr("create.not_ready", explanation(s)))
        .accessibilityHint(!inactive ? tr("create.starts_video") : tr("create.tells_missing"))
        .accessibilityIdentifier("sendButton")
    }

    /// What is missing, in words (the empty prompt has no line of its own until it is asked for).
    private func explanation(_ s: ComposerStatus) -> String { s.kind == .price ? tr("create.describe_to_continue") : s.message }

    /// The length the balance can pay for, when the chosen one costs too much and the sentence is otherwise ready to send.
    private func affordableFix(_ s: ComposerStatus) -> (minutes: Double, credits: Int)? {
        guard s.kind == .notAffordable, case .useMinutes(let m, let c)? = s.fix, Brief.isValid(form.text) || form.hasDeck else { return nil }
        return (m, c)
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
            .modifier(Morph(on: !reduceMotion, namespace: morph))
            .elevation(3)
            .accessibilityElement(children: .combine).accessibilityLabel(capsuleTitle).accessibilityValue(capsuleSub).accessibilityAddTraits(.updatesFrequently).accessibilityIdentifier("createCapsule")
            Button { stopChecking() } label: {       // the text colour on an opaque capsule: readable on the aura in both appearances
                Text(tr("common.cancel")).font(.role(.headline, weight: .medium)).foregroundStyle(Theme.text).padding(.horizontal, Theme.Space.xxl).frame(minWidth: 120, minHeight: Theme.minTouch)
                    .background(Theme.surface, in: Capsule()).contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .opacity(capsule.canCancel ? 1 : 0).disabled(!capsule.canCancel).accessibilityHidden(!capsule.canCancel)
            .accessibilityIdentifier("checkingCancel")
        }
        .padding(.bottom, Theme.Space.s)
    }

    private var capsuleTitle: String { capsule.phase == .starting ? tr("create.starting_your_video") : tr("create.checking_your_request") }
    private var capsuleSub: String { capsule.phase == .starting ? tr("create.starting_sub") : capsule.isSlow ? tr("create.checking_slow") : tr("create.checking_sub") }

    /// What the status line says, or nil while the screen is quiet: only a real problem, or (for a few seconds) what a tap on the inactive Create asked for.
    private func statusText(_ s: ComposerStatus) -> String? {
        if let error = create.startError, s.canSend { return error }
        switch s.kind {
        case .ready, .sending: return nil
        case .price: return explaining ? tr("create.describe_to_continue") : nil
        case .dictating: return explaining ? s.announcement : nil
        default: return s.message
        }
    }

    /// One line above the pills, only when it says something: what is missing, what went wrong (with its one-tap fix). Never a standing helper.
    @ViewBuilder private func statusLine(_ s: ComposerStatus) -> some View {
        if let text = statusText(s) {
            Group {
                if let error = create.startError, s.canSend {
                    Label(error, systemImage: "exclamationmark.circle").font(.role(.footnote, weight: .medium)).foregroundStyle(Theme.text).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                        .labelStyle(DangerMarkLabel()).accessibilityIdentifier("startError")
                } else {
                    HStack(spacing: Theme.Space.s) {
                        Image(systemName: s.isProblem && s.kind != .tooShort ? "exclamationmark.circle" : "info.circle").font(.role(.footnote, weight: .semibold)).foregroundStyle(tint(s)).accessibilityHidden(true)
                        Text(text).font(.role(.footnote, weight: .medium)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                            .modifier(Shake(travel: reduceMotion ? 0 : 4, value: shake))
                            .accessibilityIdentifier(unaffordable ? "notEnoughCredits" : s.kind == .photoHint ? "photoCapacityHint" : "costLine")
                        Spacer(minLength: Theme.Space.xs)
                        if let fix = s.fix, affordableFix(s) == nil { FixChip(title: fix.title) { applyFix(fix) }.accessibilityIdentifier("fixChip") }       // a shorter length that fits is on the button itself
                    }
                    .padding(.horizontal, flash ? 6 : 0).background(flash ? Theme.warningContainer : .clear, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading).frame(minHeight: 18)
            .accessibilityElement(children: .contain).accessibilityIdentifier("statusLine")
            .transition(.opacity)
        }
    }

    /// Teaches the price once: before the first video, "2 credits. You have 11." under Create. Afterwards the balance lives in the header chip, and this
    /// line only returns when it runs low (fewer credits would be left than this video costs).
    @ViewBuilder private func costCaption(_ s: ComposerStatus) -> some View {
        let calm = s.kind == .ready || s.kind == .price || (s.kind == .tooShort && !form.hasContent)
        let cost = affordableFix(s)?.credits ?? form.options.credits
        if calm, showsPrice, let balance, balance >= cost {
            let first = !model.hasFinishedVideo
            if first || balance - cost < cost {
                HStack(spacing: 3) {
                    Image(systemName: "bolt.fill").font(.role(.caption)).accessibilityHidden(true)
                    Text(first ? tr("create.first_cost", tr("credits.count", cost), balance) : tr("create.credits_left", balance - cost)).font(.role(.caption)).monospacedDigit()
                }
                .foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, alignment: .trailing)
                .accessibilityElement(children: .ignore).accessibilityLabel(first ? tr("create.first_cost", tr("credits.count", cost), balance) : tr("create.credits_left", balance - cost)).accessibilityIdentifier("costCaption")
                .transition(.opacity)
            }
        }
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
            withAnimation(Theme.Motion.press) { flash = true; explaining = true }
            Task { try? await Task.sleep(for: .milliseconds(450)); withAnimation(Theme.Motion.select) { flash = false } }
            Task { try? await Task.sleep(for: .seconds(4)); withAnimation(Theme.Motion.select) { explaining = false } }
            UIAccessibility.post(notification: .announcement, argument: s.kind == .tooShort || s.kind == .price ? tr("create.describe_to_continue") : s.announcement)
            if s.kind == .tooShort || s.kind == .price { withAnimation { proxy.scrollTo("prompt", anchor: .top) }; focused = true }
            return
        }
        dictation.cancel(); focused = false; explaining = false
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
        // Closing never asks: a sentence, photos or a presentation stay as a draft and are there when Create opens again.
        // Nothing typed (library photos alone do not count: they are still ticked in Media): the next Create starts empty.
        dictation.cancel(); typing?.cancel(); create.cancelCheck()
        if !create.hasEdits { model.composerLibrary = [] }
        dismiss()
    }
    /// Cancel during the request check: the call is dropped (a late answer is ignored, nothing is sent) and the form is back exactly as it was.
    private func stopChecking() {
        create.cancelCheck(); Haptics.play(.selection)
        UIAccessibility.post(notification: .announcement, argument: tr("create.check_cancelled"))
    }

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

/// The Create pill and the live capsule are one shape that springs from one to the other. Reduce Motion: no travel, the two simply cross-fade.
private struct Morph: ViewModifier {
    let on: Bool
    let namespace: Namespace.ID
    func body(content: Content) -> some View {
        if on { content.matchedGeometryEffect(id: "cta", in: namespace) } else { content }
    }
}
