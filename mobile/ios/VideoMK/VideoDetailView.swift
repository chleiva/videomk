import AVKit
import Photos
import CoreTransferable
import SwiftUI
import UniformTypeIdentifiers
import VideoMKCore

struct VideoDetailView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let videoID: String
    @State private var player: AVPlayer?
    @State private var playbackURL: URL?
    @State private var videoDescription: String?
    @State private var copiedDescription = false
    @State private var showInfo = false
    @State private var ended = false
    @State private var playbackError: String?
    @State private var editing = false
    @State private var save = SaveState.idle
    @State private var watcher: PlaybackWatcher?
    @State private var showFeedback = false

    enum SaveState { case idle, saving, saved, failed }

    var body: some View {
        ScrollView {
            if let video = model.video(videoID) {
                VStack(alignment: .leading, spacing: 0) {
                    switch video.status {
                    case .complete: playerSection(video).transition(.opacity)
                    case .running: makingSection(video).padding(Theme.Space.xl).transition(.opacity)
                    case .failed: message(tr("detail.failed_title"), tr("detail.failed_body"), icon: "exclamationmark.triangle", color: Theme.danger, retry: { model.tryAgain(video) }).padding(Theme.Space.xl)
                    case .rejected: message(tr("detail.rejected_title"), video.rejectReason ?? tr("detail.rejected_body"), icon: "hand.raised", color: Theme.warning).padding(Theme.Space.xl)
                    }
                }
                .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.insert, value: video.status == .complete)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(.top, 80)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle(model.video(videoID)?.status == .complete ? (model.video(videoID)?.displayTitle ?? tr("detail.video")) : tr("detail.video"))
        .navigationBarTitleDisplayMode(.inline)
        .task(id: model.video(videoID)?.status) { await loadPlayerIfReady() }
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
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

    // MARK: making (the shared MakingCard in its detail form)

    private func makingSection(_ video: VideoItem) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let snapshot = model.makingSnapshot(for: video, now: context.date)
            VStack(alignment: .leading, spacing: 18) {
                Text(snapshot.title).font(.vmk(34, weight: .bold)).tracking(-0.8).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
                MakingCard(snapshot: snapshot, layout: .detail)
                Text(tr("making.leave_promise")).font(.vmk(15)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .center).multilineTextAlignment(.center)
            }
        }
        .accessibilityIdentifier("progressCard")
    }

    // MARK: ready

    @ViewBuilder private func playerSection(_ video: VideoItem) -> some View {
        Group {
            if let player { InlinePlayer(player: player, landscape: video.aspectRatio >= 1.2, playing: model.isPlayingVideo).overlay { if ended { endCard(player) } } }
            else if let playbackError {
                VStack(spacing: 12) {
                    Text(playbackError).foregroundStyle(.white.opacity(0.8)).multilineTextAlignment(.center)
                    Button(tr("common.try_again")) { Task { await loadPlayerIfReady() } }.frame(minHeight: Theme.minTouch).foregroundStyle(.white)
                }.frame(maxWidth: .infinity, maxHeight: .infinity).padding()
            } else { ProgressView().tint(.white).frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .aspectRatio(video.aspectRatio, contentMode: .fit)
        .frame(maxHeight: video.isPortrait ? 560 : nil)      // edge to edge: no inset, no rounded corners
        .frame(maxWidth: .infinity)
        .background(.black)
        .accessibilityIdentifier("player")
        .onReceive(NotificationCenter.default.publisher(for: .AVPlayerItemDidPlayToEndTime)) { n in
            if let item = n.object as? AVPlayerItem, item === player?.currentItem { withAnimation(Theme.Motion.fade) { ended = true } }
        }

        VStack(alignment: .leading, spacing: 14) {
            if let caption = caption(video) { Text(caption).font(.vmk(14).monospacedDigit()).foregroundStyle(Theme.textSecondary).padding(.top, 2).accessibilityIdentifier("videoCaption") }
            actions(video)
            if save == .failed { Text(tr("detail.save_failed")).font(.vmk(13)).foregroundStyle(Theme.danger).fixedSize(horizontal: false, vertical: true) }
        }
        .padding(.horizontal, Theme.Space.xl).padding(.vertical, Theme.Space.l)
    }

    /// "1:20 · 1080p": the only metadata under the video.
    private func caption(_ video: VideoItem) -> String? {
        let parts = [video.durationSeconds.map { VideoRow.duration($0) }, video.resolution].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// The video is over: replay or a new video. A scrim over the picture; the one place the words "New video" appear on this screen.
    private func endCard(_ player: AVPlayer) -> some View {
        ZStack {
            Color.black.opacity(0.6)
            HStack(spacing: 28) {
                endButton("arrow.counterclockwise", tr("detail.replay"), "replayButton") { player.seek(to: .zero); player.play(); ended = false }
                endButton("plus", tr("create.new_video"), "endNewVideo") { dismiss(); model.createRequested = true }
            }
        }
        .transition(.opacity)
    }

    private func endButton(_ symbol: String, _ label: String, _ id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: symbol).font(.vmk(22, weight: .semibold)).foregroundStyle(.white).frame(width: 56, height: 56).background(.white.opacity(0.18), in: Circle()).overlay(Circle().stroke(.white.opacity(0.3), lineWidth: 0.5))
                Text(label).font(.vmk(13, weight: .semibold)).foregroundStyle(.white).lineLimit(1).vmkOneLineCap()
            }
            .frame(minWidth: 72, minHeight: 88)
        }
        .buttonStyle(.plain).accessibilityLabel(label).accessibilityIdentifier(id)
    }

    /// Icons only, evenly spaced, each with a spoken label: Share (the one filled control), Save, Edit, Info, More.
    @ViewBuilder private func actions(_ video: VideoItem) -> some View {
        HStack(spacing: 0) {
            if let playbackURL {
                ShareLink(item: SharedVideo(remoteURL: playbackURL, name: video.displayTitle), preview: SharePreview(video.displayTitle)) {
                    Image(systemName: "square.and.arrow.up").font(.vmk(20, weight: .semibold)).foregroundStyle(Theme.onPrimary).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                        .frame(width: 56, height: 56).background(Theme.gradient, in: Circle()).shadow(color: Theme.gradientStart.opacity(0.3), radius: 8, y: 3)
                }
                .accessibilityLabel(tr("common.share")).accessibilityIdentifier("shareButton")
                .frame(maxWidth: .infinity)
                Group {
                    if save == .saving { ProgressView().frame(width: 44, height: 44) }
                    else { GlassIconButton(symbol: save == .saved ? "checkmark" : "arrow.down.to.line", label: saveLabel, identifier: "saveButton") { Task { await saveToPhotos(playbackURL, name: video.displayTitle) } } }
                }.frame(maxWidth: .infinity)
            }
            if video.editable { GlassIconButton(symbol: "slider.horizontal.3", label: tr("common.edit"), identifier: "editButton") { player?.pause(); editing = true }.frame(maxWidth: .infinity) }
            if videoDescription != nil { GlassIconButton(symbol: "info", label: tr("detail.info"), identifier: "infoButton") { showInfo = true }.frame(maxWidth: .infinity) }
            Menu {
                Button { dismiss(); model.createRequested = true } label: { Label(tr("create.new_video"), systemImage: "plus") }.accessibilityIdentifier("makeAnother")
                Button { showFeedback = true } label: { Label(tr("feedback.title"), systemImage: "bubble.left") }.accessibilityIdentifier("sendFeedbackLink")
            } label: {
                Image(systemName: "ellipsis").font(.vmk(18, weight: .semibold)).foregroundStyle(Theme.text).frame(width: 44, height: 44).vmkGlass(in: Circle()).frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Circle())
            }
            .accessibilityLabel(tr("media.more")).accessibilityIdentifier("moreButton").frame(maxWidth: .infinity)
        }
    }

    private var saveLabel: String { save == .saved ? tr("detail.saved") : tr("detail.save") }

    private func message(_ title: String, _ body: String, icon: String, color: Color, retry: (() -> Void)? = nil) -> some View {
        VStack(spacing: 14) {
            Image(systemName: icon).font(.vmk(30)).foregroundStyle(color).frame(width: 64, height: 64).background(color.opacity(0.14), in: Circle()).accessibilityHidden(true)
            Text(title).font(.vmk(22, weight: .bold)).foregroundStyle(Theme.text).multilineTextAlignment(.center).accessibilityAddTraits(.isHeader)
            Text(body).font(.vmk(15)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            if let retry { Button(action: retry) { Label(tr("common.try_again"), systemImage: "arrow.clockwise").font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: Theme.minTouch) }.buttonStyle(.plain).accessibilityIdentifier("tryAgain") }
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
        } catch let e as APIError { playbackError = e.message } catch { playbackError = APIError.server.message }
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

    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(exportedContentType: .mpeg4Movie) { video in
            let (tmp, _) = try await URLSession.shared.download(from: video.remoteURL)
            let safe = video.name.replacingOccurrences(of: "/", with: "-")
            let dest = FileManager.default.temporaryDirectory.appendingPathComponent("\(safe).mp4")
            try? FileManager.default.removeItem(at: dest)
            try FileManager.default.moveItem(at: tmp, to: dest)
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
                Text(Linkified.attributed(description)).font(.vmk(15)).foregroundStyle(Theme.text).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled).padding(20)
            }
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
