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
                    case .failed: message(tr("detail.failed_title"), tr("detail.failed_body"), icon: "exclamationmark.triangle", color: Theme.danger, container: Theme.dangerContainer).padding(Theme.Space.xl)
                    case .rejected: message(tr("detail.rejected_title"), video.rejectReason ?? tr("detail.rejected_body"), icon: "hand.raised", color: Theme.warning, container: Theme.warningContainer).padding(Theme.Space.xl)
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
        .onDisappear { player?.pause(); watcher?.stop(); watcher = nil }
        .sheet(isPresented: $showFeedback) { FeedbackSheet(composer: model.makeFeedback(.afterVideo)) }
        .fullScreenCover(isPresented: $editing, onDismiss: {
            watcher?.stop(); watcher = nil; player = nil; playbackURL = nil  // the edit may have published a new version
            Task { await model.refresh(); await loadPlayerIfReady() }
        }) { EditorView(videoID: videoID) }
    }

    // MARK: making (the shared MakingCard in its detail form)

    private func makingSection(_ video: VideoItem) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(tr("detail.making_overline").uppercased()).font(.vmk(12, weight: .bold)).tracking(0.8).foregroundStyle(Theme.textTertiary).accessibilityHidden(true)
            TimelineView(.periodic(from: .now, by: 1)) { context in
                let snapshot = model.makingSnapshot(for: video, now: context.date)
                VStack(alignment: .leading, spacing: 10) {
                    Text(snapshot.title).font(.vmk(28, weight: .bold)).tracking(-0.4).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader)
                    Text(tr("making.leave_promise")).font(.vmk(15)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).padding(.bottom, 8)
                    MakingCard(snapshot: snapshot, layout: .detail)
                }
            }
            .accessibilityIdentifier("progressCard")
        }
    }

    // MARK: ready

    @ViewBuilder private func playerSection(_ video: VideoItem) -> some View {
        Group {
            if let player { InlinePlayer(player: player, landscape: video.aspectRatio >= 1.2) }
            else if let playbackError {
                VStack(spacing: 12) {
                    Text(playbackError).foregroundStyle(Theme.textSecondary)
                    Button(tr("common.try_again")) { Task { await loadPlayerIfReady() } }.frame(minHeight: Theme.minTouch)
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else { ProgressView().tint(.white).frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .aspectRatio(video.aspectRatio, contentMode: .fit)
        .frame(maxHeight: video.isPortrait ? 560 : nil)      // edge to edge: no inset, no rounded corners
        .frame(maxWidth: .infinity)
        .background(.black)
        .accessibilityIdentifier("player")

        VStack(alignment: .leading, spacing: 16) {
            Text(video.displayTitle).font(.vmk(22, weight: .bold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, 4)
            actions(video)
            makeAnotherCard
            FeedbackLink { showFeedback = true }
            if let d = videoDescription {
                DisclosureGroup(tr("detail.description_credits")) {
                    VStack(alignment: .leading, spacing: 10) {
                        Text(Linkified.attributed(d)).font(.vmk(13)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled)
                        Button {
                            UIPasteboard.general.string = d
                            copiedDescription = true
                            Task { try? await Task.sleep(for: .seconds(2)); copiedDescription = false }
                        } label: {
                            Label(copiedDescription ? tr("common.copied") : tr("detail.copy_description"), systemImage: copiedDescription ? "checkmark" : "text.alignleft").font(.vmk(15, weight: .semibold)).frame(maxWidth: .infinity, minHeight: Theme.minTouch)
                        }.buttonStyle(.bordered).accessibilityIdentifier("copyDescription")
                    }.padding(.top, 8)
                }
                .tint(Theme.primary).accessibilityIdentifier("descriptionGroup")
            }
        }
        .padding(Theme.Space.xl)
    }

    /// Share is the one primary action; Save and Edit sit under it, equal and tonal.
    @ViewBuilder private func actions(_ video: VideoItem) -> some View {
        let stacked = typeSize.isAccessibilitySize
        VStack(spacing: 10) {
            if let playbackURL {
                ShareLink(item: SharedVideo(remoteURL: playbackURL, name: video.displayTitle), preview: SharePreview(video.displayTitle)) {
                    Label(tr("common.share"), systemImage: "square.and.arrow.up").multilineTextAlignment(.center)
                }
                .buttonStyle(PrimaryButtonStyle()).accessibilityIdentifier("shareButton")
            }
            (stacked ? AnyLayout(VStackLayout(spacing: 10)) : AnyLayout(HStackLayout(spacing: 10))) {
                if let playbackURL { secondary(saveLabel, symbol: saveSymbol) { Task { await saveToPhotos(playbackURL, name: video.displayTitle) } }.disabled(save == .saving).accessibilityIdentifier("saveButton") }
                if video.editable { secondary(tr("common.edit"), symbol: "slider.horizontal.3") { player?.pause(); editing = true }.accessibilityIdentifier("editButton") }
            }
            if save == .failed { Text(tr("detail.save_failed")).font(.vmk(13)).foregroundStyle(Theme.danger).frame(maxWidth: .infinity, alignment: .leading).fixedSize(horizontal: false, vertical: true) }
        }
    }

    private func secondary(_ title: String, symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Label(title, systemImage: symbol).font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.primary).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity, minHeight: 50).padding(.horizontal, 8)
                .background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
        }.buttonStyle(.plain)
    }

    private var saveLabel: String { save == .saved ? tr("detail.saved") : tr("detail.save") }
    private var saveSymbol: String { save == .saved ? "checkmark" : "arrow.down.to.line" }

    /// The "next" card: the retention hook after a result. (A vertical version of the same script needs a backend call: not built.)
    private var makeAnotherCard: some View {
        Button { dismiss(); model.createRequested = true } label: {
            HStack(spacing: 14) {
                Image(systemName: "plus").font(.vmk(18, weight: .semibold)).foregroundStyle(Theme.primary).dynamicTypeSize(...DynamicTypeSize.xxxLarge).frame(width: 40, height: 40).background(Theme.primaryContainer, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text(tr("detail.make_another")).font(.vmk(16, weight: .semibold)).foregroundStyle(Theme.text).multilineTextAlignment(.leading)
                    Text(tr("detail.make_another_sub")).font(.vmk(14)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.leading)
                }
                Spacer(minLength: 4)
                Image(systemName: "chevron.right").font(.vmk(14, weight: .semibold)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
            }
            .padding(14).frame(maxWidth: .infinity, minHeight: Theme.minTouch)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous).stroke(Theme.outline, lineWidth: 1))
        }
        .buttonStyle(.plain).accessibilityIdentifier("makeAnother")
    }

    private func message(_ title: String, _ body: String, icon: String, color: Color, container: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(title, systemImage: icon).font(.vmk(17, weight: .semibold)).foregroundStyle(color)
            Text(body).font(.vmk(15)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
        }
        .padding(16).frame(maxWidth: .infinity, alignment: .leading)
        .background(container, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
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
