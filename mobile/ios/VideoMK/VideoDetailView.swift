import AVKit
import Photos
import CoreTransferable
import SwiftUI
import UniformTypeIdentifiers
import VideoMKCore

/// One video. While it is being made this is the Making screen (`phone_4_making`): the scene being built shown large, the film strip filling, one live
/// line, the narration line, one switch. Once it is ready it is the player (`phone_5_player`): Share is the one labelled primary; Save, Edit, Info and
/// More are quiet icons; the end card offers Replay and New video; "Make another" opens Create with the same sentence and one choice changed.
struct VideoDetailView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let videoID: String
    @State private var player: AVPlayer?
    @State private var playbackURL: URL?
    @State private var videoDescription: String?
    @State private var showInfo = false
    @State private var ended = false
    @State private var playbackError: String?
    @State private var editing = false
    @State private var save = SaveState.idle
    @State private var watcher: PlaybackWatcher?
    @State private var showFeedback = false
    @State private var wasMaking = false          // this screen watched the video being made: when it is ready it starts by itself (the reveal)

    enum SaveState { case idle, saving, saved, failed }

    private var video: VideoItem? { model.video(videoID) }
    private var isRunning: Bool { video?.status.isRunning == true }

    var body: some View {
        VStack(spacing: 0) {
            TopBar(leading: { IconButton(symbol: "chevron.left", label: tr("common.back"), identifier: "backButton") { dismiss() } })
            ScrollView {
                if let video {
                    VStack(alignment: .leading, spacing: 0) {
                        switch video.status {
                        case .complete: playerSection(video).transition(.opacity)
                        case .running: makingSection(video).padding(.horizontal, Theme.gutter).transition(.opacity)
                        case .failed: message(tr("detail.failed_title"), tr("detail.failed_body"), icon: "exclamationmark", color: Theme.danger, container: Theme.dangerContainer, retry: video.canRetry == false ? nil : { model.tryAgain(video) }).padding(.horizontal, Theme.gutter)
                        case .rejected: message(tr("detail.rejected_title"), video.rejectReason ?? tr("detail.rejected_body"), icon: "hand.raised", color: Theme.warning, container: Theme.warningContainer).padding(.horizontal, Theme.gutter)
                        }
                    }
                    .frame(maxWidth: 640).frame(maxWidth: .infinity)
                    .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.reveal, value: video.status == .complete)
                } else {
                    VideosSkeleton().padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s)
                }
            }
            .scrollBounceBehavior(.basedOnSize)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { if isRunning { NotifyCard().padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.s).frame(maxWidth: 640).transition(.opacity) } }
        .background(Theme.background.ignoresSafeArea())
        .toolbar(.hidden, for: .navigationBar)
        .task(id: video?.status) { await loadPlayerIfReady() }
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .task(id: isRunning) {            // the video's own status, while this screen watches it being made
            guard isRunning else { return }
            wasMaking = true
            while !Task.isCancelled { await model.refreshMaking(videoID); try? await Task.sleep(for: .seconds(3)) }
        }
        .onDisappear { player?.pause(); watcher?.stop(); watcher = nil; model.tabBarHidden = false }
        .onAppear { model.tabBarHidden = true }
        .onChange(of: model.isPlayingVideo) { _, playing in if playing { ended = false } }
        .sheet(isPresented: $showInfo) { VideoInfoSheet(description: videoDescription ?? "") }
        .sheet(isPresented: $showFeedback) { FeedbackSheet(composer: model.makeFeedback(.afterVideo)) }
        .fullScreenCover(isPresented: $editing, onDismiss: {
            watcher?.stop(); watcher = nil; player = nil; playbackURL = nil  // the edit may have published a new version
            Task { await model.refresh(); await loadPlayerIfReady() }
        }) { EditorView(videoID: videoID) }
    }

    // MARK: making

    private func makingSection(_ video: VideoItem) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            MakingScreen(snapshot: model.makingSnapshot(for: video, now: context.date))
        }
    }

    // MARK: ready

    @ViewBuilder private func playerSection(_ video: VideoItem) -> some View {
        Group {
            if let player { InlinePlayer(player: player, landscape: video.aspectRatio >= 1.2, playing: model.isPlayingVideo).overlay { if ended { endCard(player) } } }
            else if let playbackError {
                VStack(spacing: Theme.Space.m) {
                    Text(playbackError).font(.role(.subhead)).foregroundStyle(Theme.onMedia.opacity(0.85)).multilineTextAlignment(.center)
                    Button(tr("common.try_again")) { Task { await loadPlayerIfReady() } }.font(.role(.headline)).frame(minHeight: Theme.minTouch).foregroundStyle(Theme.onMedia).accessibilityIdentifier("playbackRetry")
                }.frame(maxWidth: .infinity, maxHeight: .infinity).padding()
            } else { Poster(video: video, radius: 0).overlay { ProgressView().tint(Theme.onMedia) } }
        }
        .aspectRatio(video.aspectRatio, contentMode: .fit)
        .frame(maxHeight: video.isPortrait ? 520 : nil)
        .frame(maxWidth: .infinity)
        .background(Theme.mediaInk)
        .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.hero, style: .continuous))
        .padding(.horizontal, Theme.Space.m).padding(.top, Theme.Space.s)
        .accessibilityIdentifier("player")
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime)) { n in
            if let item = n.object as? AVPlayerItem, item === player?.currentItem { withAnimation(Theme.Motion.reveal) { ended = true } }
        }

        VStack(alignment: .leading, spacing: 0) {
            Text(video.displayTitle).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader).accessibilityIdentifier("videoTitle")
            if let caption = caption(video) { Text(caption).font(.role(.footnote)).monospacedDigit().foregroundStyle(Theme.textSecondary).padding(.top, Theme.Space.xs).accessibilityIdentifier("videoCaption") }
            actions(video).padding(.top, 22)
            if save == .failed { Label(tr("detail.save_failed"), systemImage: "exclamationmark.circle").labelStyle(DangerMarkLabel()).font(.role(.footnote)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, Theme.Space.m) }
            remix(video)
        }
        .padding(.horizontal, Theme.gutter).padding(.top, 22).padding(.bottom, Theme.Space.xxl)
    }

    /// "1:20 · 1080p": the only metadata under the title.
    private func caption(_ video: VideoItem) -> String? {
        let parts = [video.durationSeconds.map { VideoRow.duration($0) }, video.resolution].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// The video is over: Replay, or a new video. A scrim over the last frame.
    private func endCard(_ player: AVPlayer) -> some View {
        ZStack {
            Theme.mediaInk.opacity(0.62)
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 14) { replayButton(player); newVideoButton }
                VStack(spacing: Theme.Space.m) { newVideoButton; replayButton(player) }
            }
            .padding(Theme.Space.m)
        }
        .transition(.opacity)
    }

    private func replayButton(_ player: AVPlayer) -> some View {
        IconButton(symbol: "arrow.counterclockwise", label: tr("detail.replay"), style: .onMedia, size: 56, identifier: "replayButton") { player.seek(to: .zero); player.play(); ended = false }
    }

    private var newVideoButton: some View {
        Button { dismiss(); model.createRequested = true } label: {
            HStack(spacing: Theme.Space.s) {
                PlaySparkle(scale: 0.78).foregroundStyle(Color(hex: DesignTokens.primary.light))
                Text(tr("create.new_video")).font(.role(.headline)).foregroundStyle(Color(hex: DesignTokens.text.light)).lineLimit(1)
            }
            .padding(.horizontal, 22).frame(minHeight: 56).background(Theme.onMedia, in: Capsule()).contentShape(Capsule())
        }
        .buttonStyle(PressScale()).vmkOneLineCap().accessibilityIdentifier("endNewVideo")
    }

    /// Share is the ONE labelled primary. Save, Edit, Info and More are quiet icons, each with a spoken label.
    @ViewBuilder private func actions(_ video: VideoItem) -> some View {
        let stacked = typeSize.isAccessibilitySize
        let layout = stacked ? AnyLayout(VStackLayout(alignment: .leading, spacing: Theme.Space.m)) : AnyLayout(HStackLayout(spacing: Theme.Space.s))
        layout {
            if let playbackURL {
                ShareLink(item: SharedVideo(remoteURL: playbackURL, name: video.displayTitle, onShared: { Task { @MainActor in Haptics.play(.shareDone) } }), preview: SharePreview(video.displayTitle)) {
                    PrimaryLabel(title: tr("common.share"), symbol: "square.and.arrow.up")
                }
                .buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("shareButton")
            } else {
                PrimaryLabel(title: tr("common.share"), symbol: "square.and.arrow.up").modifier(PrimaryPlaceholder())
            }
            HStack(spacing: Theme.Space.s) {
                if let playbackURL {
                    if save == .saving { ProgressView().frame(width: 48, height: 48).background(Theme.surfaceRaised, in: Circle()) }
                    else { IconButton(symbol: save == .saved ? "checkmark" : "arrow.down.to.line", label: saveLabel, size: 48, identifier: "saveButton") { Task { await saveToPhotos(playbackURL, name: video.displayTitle) } } }
                }
                if video.editable { IconButton(symbol: "pencil", label: tr("common.edit"), size: 48, identifier: "editButton") { player?.pause(); editing = true } }
                if videoDescription != nil { IconButton(symbol: "info.circle", label: tr("detail.info"), size: 48, identifier: "infoButton") { showInfo = true } }
                Menu {
                    Button { dismiss(); model.createRequested = true } label: { Label(tr("create.new_video"), systemImage: "play") }.accessibilityIdentifier("makeAnother")
                    Button { showFeedback = true } label: { Label(tr("feedback.title"), systemImage: "bubble.left") }.accessibilityIdentifier("sendFeedbackLink")
                } label: { IconButtonFace(symbol: "ellipsis", size: 48) }
                .accessibilityLabel(tr("media.more")).accessibilityIdentifier("moreButton")
            }
        }
    }

    private var saveLabel: String { save == .saved ? tr("detail.saved") : tr("detail.save") }

    /// "Make another": the same sentence with one choice changed. Each chip opens Create filled in (nothing is sent until Create is tapped there), so it is
    /// only offered when the sentence is known and the server can make that variant.
    @ViewBuilder private func remix(_ video: VideoItem) -> some View {
        let options = RemixOption.make(video: video, sentence: model.brief(for: video.id) ?? video.title, caps: model.createModel.caps, appLanguage: Localization.shared.language)
        if !options.isEmpty {
            Text(tr("detail.make_another")).font(.role(.caption)).tracking(0.7).textCase(.uppercase).foregroundStyle(Theme.textSecondary).padding(.top, 34).accessibilityAddTraits(.isHeader)
            WrapLayout(spacing: Theme.Space.s) {
                ForEach(options) { o in
                    SparkleChip(title: o.title, identifier: "remix-\(o.id)", hint: tr("detail.remix_hint")) {
                        Haptics.play(.selection); player?.pause()
                        model.createPrefill = AppModel.CreatePrefill(text: o.sentence, platformChip: o.platformChip, minutes: o.minutes, language: o.language)
                    }
                }
            }
            .padding(.top, Theme.Space.m)
        }
    }

    private func message(_ title: String, _ body: String, icon: String, color: Color, container: Color, retry: (() -> Void)? = nil) -> some View {
        VStack(spacing: Theme.Space.l) {
            Image(systemName: icon).font(.role(.title)).foregroundStyle(color).frame(width: 64, height: 64).background(container, in: Circle()).accessibilityHidden(true)
            Text(title).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center).accessibilityAddTraits(.isHeader)
            Text(body).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            if let retry { Button(action: retry) { Label(tr("common.try_again"), systemImage: "arrow.clockwise") }.buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("tryAgain") }
        }
        .frame(maxWidth: .infinity).padding(.top, 48)
    }

    // MARK: loading and saving

    private func loadPlayerIfReady() async {
        guard model.video(videoID)?.status == .complete, player == nil else { return }
        playbackError = nil
        do {
            let info = try await model.playback(for: videoID)
            let url = info.url
            playbackURL = url
            videoDescription = info.description
            let p = AVPlayer(url: url)
            player = p
            watcher?.stop()
            let id = videoID
            watcher = PlaybackWatcher(player: p, onPlaying: { model.isPlayingVideo = $0 }, onComplete: { model.rating.recordCompleted(id) })
            if wasMaking, !reduceMotion { wasMaking = false; await revealPlay(p) }       // the reveal: it starts by itself, from silent to full in 300 ms (Reduce Motion: nothing autoplays)
        } catch let e as APIError { playbackError = e.message } catch { playbackError = APIError.server.message }
    }

    /// The first play after watching it being made: the sound comes up over 300 ms.
    private func revealPlay(_ p: AVPlayer) async {
        p.volume = 0; p.play()
        let steps = 10
        for i in 1...steps {
            try? await Task.sleep(for: .seconds(DesignTokens.Motion.reveal / Double(steps)))
            p.volume = Float(i) / Float(steps)
        }
    }

    /// Downloads the file, then adds it to the photo library (add-only permission, asked at this moment with a reason).
    private func saveToPhotos(_ url: URL, name: String) async {
        save = .saving
        do {
            let (tmp, _) = try await URLSession.shared.download(from: url)
            let dest = FileManager.default.temporaryDirectory.appendingPathComponent("\(UUID().uuidString).mp4")
            try FileManager.default.moveItem(at: tmp, to: dest)
            defer { try? FileManager.default.removeItem(at: dest) }
            guard await PHPhotoLibrary.requestAuthorization(for: .addOnly) == .authorized else { save = .failed; return }
            try await PHPhotoLibrary.shared().performChanges { _ = PHAssetChangeRequest.creationRequestForAssetFromVideo(atFileURL: dest) }
            save = .saved
        } catch { save = .failed }
    }
}

/// Makes every URL in the text tappable (photographer and Unsplash links in the credits, Wikipedia sources).
enum Linkified {
    static func attributed(_ text: String) -> AttributedString {
        var out = AttributedString(text)
        guard let detector = try? NSDataDetector(types: NSTextCheckingResult.CheckingType.link.rawValue) else { return out }
        for m in detector.matches(in: text, range: NSRange(text.startIndex..., in: text)) {
            if let r = Range(m.range, in: text), let url = m.url, let lower = AttributedString.Index(r.lowerBound, within: out), let upper = AttributedString.Index(r.upperBound, within: out) {
                out[lower..<upper].link = url
            }
        }
        return out
    }
}

/// Downloads the MP4 only when the user actually shares it, then hands the file to the share sheet.
struct SharedVideo: Transferable {
    let remoteURL: URL
    let name: String
    /// The file was handed to the share sheet's destination (the share went through): the one success haptic of sharing.
    var onShared: (@Sendable () -> Void)?

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .mpeg4Movie) { video in
            let (tmp, _) = try await URLSession.shared.download(from: video.remoteURL)
            let safe = video.name.replacingOccurrences(of: "/", with: "-")
            let dest = FileManager.default.temporaryDirectory.appendingPathComponent("\(safe).mp4")
            try? FileManager.default.removeItem(at: dest)
            try FileManager.default.moveItem(at: tmp, to: dest)
            video.onShared?()
            return SentTransferredFile(dest)
        }
    }
}

/// The description and the photo credits, one copy button. Opens from the (i) under the video.
struct VideoInfoSheet: View {
    let description: String
    @Environment(\.dismiss) private var dismiss
    @State private var copied = false
    var body: some View {
        NavigationStack {
            ScrollView {
                Text(Linkified.attributed(description)).font(.role(.subhead)).foregroundStyle(Theme.text).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled).padding(Theme.gutter)
            }
            .background(Theme.background)
            .navigationTitle(tr("detail.info")).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button { UIPasteboard.general.string = description; copied = true; Task { try? await Task.sleep(for: .seconds(2)); copied = false } } label: { Label(copied ? tr("common.copied") : tr("detail.copy_description"), systemImage: copied ? "checkmark" : "doc.on.doc") }
                        .accessibilityIdentifier("copyDescription")
                }
                ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() } }
            }
        }
        .presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
        .accessibilityIdentifier("descriptionGroup")
    }
}

/// The primary button's shape while its action is not ready yet (the link is still loading): same place, dimmed, not a control.
private struct PrimaryPlaceholder: ViewModifier {
    func body(content: Content) -> some View {
        content.font(.role(.headline)).foregroundStyle(Theme.onPrimary).padding(.horizontal, Theme.Space.xxl).frame(maxWidth: .infinity, minHeight: Theme.primaryHeight)
            .background(Theme.gradient, in: Capsule()).opacity(0.45).accessibilityHidden(true)
    }
}

/// One "Make another" chip: the same sentence with one choice changed. Built only from what the server can make today (`CreateCapabilities`).
struct RemixOption: Identifiable, Equatable {
    let id: String
    let title: String
    let sentence: String
    var platformChip: String?
    var minutes: Double?
    var language: String?

    static func make(video: VideoItem, sentence: String?, caps: CreateCapabilities, appLanguage: AppLanguage) -> [RemixOption] {
        guard let sentence = sentence.map(Brief.normalized), Brief.isValid(sentence) else { return [] }      // without a sentence there is nothing to open Create with
        var out: [RemixOption] = []
        if !video.isPortrait, let shorts = PlatformChips.make(caps).first(where: { $0.members.contains("shorts") }), shorts.supported {
            out.append(RemixOption(id: "short", title: tr("detail.remix_short"), sentence: sentence, platformChip: shorts.id))
        }
        let other = appLanguage == .es ? "en" : "es"
        if caps.languages.contains(where: { $0.id == other }) {
            out.append(RemixOption(id: "language", title: tr(other == "es" ? "detail.remix_spanish" : "detail.remix_english"), sentence: sentence, language: other))
        }
        if caps.lengthPresets.contains(0.5), (video.durationSeconds ?? 60) > 45 {
            out.append(RemixOption(id: "cut30", title: tr("detail.remix_30s"), sentence: sentence, minutes: 0.5))
        }
        return out
    }
}
