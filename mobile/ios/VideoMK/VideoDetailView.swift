import AVKit
import CoreTransferable
import SwiftUI
import UniformTypeIdentifiers
import VideoMKCore

struct VideoDetailView: View {
    @Environment(AppModel.self) private var model
    let videoID: String
    @State private var player: AVPlayer?
    @State private var playbackURL: URL?
    @State private var videoDescription: String?
    @State private var copiedDescription = false
    @State private var playbackError: String?
    @State private var copied = false
    @State private var editing = false

    var body: some View {
        ScrollView {
            if let video = model.video(videoID) {
                VStack(alignment: .leading, spacing: 16) {
                    switch video.status {
                    case .complete: playerSection(video)
                    case .running(let stage): ProgressCard(stage: stage)
                    case .failed: message("Something went wrong", "We couldn't finish this video. You haven't been charged for it.", icon: "exclamationmark.triangle", color: Theme.danger)
                    case .rejected: message("This request can't be turned into a video", video.rejectReason ?? "Try describing something different.", icon: "hand.raised", color: Theme.warning)
                    }
                }
                .padding(20)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(.top, 80)
            }
        }
        .background(Theme.background.ignoresSafeArea())
        .navigationTitle(model.video(videoID)?.displayTitle ?? "Video")
        .navigationBarTitleDisplayMode(.inline)
        .task(id: model.video(videoID)?.status) { await loadPlayerIfReady() }
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .onDisappear { player?.pause() }
        .toolbar {
            if let v = model.video(videoID), v.editable, v.status == .complete {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Edit") { player?.pause(); editing = true }.accessibilityIdentifier("editButton")
                }
            }
        }
        .fullScreenCover(isPresented: $editing, onDismiss: {
            player = nil; playbackURL = nil  // the edit may have published a new version
            Task { await model.refresh(); await loadPlayerIfReady() }
        }) { EditorView(videoID: videoID) }
    }

    @ViewBuilder private func playerSection(_ video: VideoItem) -> some View {
        Group {
            if let player { InlinePlayer(player: player, landscape: video.aspectRatio >= 1.2) }
            else if let playbackError {
                VStack(spacing: 12) {
                    Text(playbackError).foregroundStyle(Theme.textSecondary)
                    Button("Try again") { Task { await loadPlayerIfReady() } }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .aspectRatio(video.aspectRatio, contentMode: .fit)
        .frame(maxHeight: video.isPortrait ? 560 : nil)
        .frame(maxWidth: .infinity)
        .background(.black)
        .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .accessibilityIdentifier("player")

        Text(video.displayTitle).font(.title3.bold()).foregroundStyle(Theme.text)
        if let d = videoDescription {
            DisclosureGroup("Description and photo credits") {
                Text(Linkified.attributed(d)).font(.footnote).foregroundStyle(Theme.textSecondary)
                    .frame(maxWidth: .infinity, alignment: .leading).textSelection(.enabled).padding(.top, 6)
            }
            .tint(Theme.primary).accessibilityIdentifier("descriptionGroup")
        }
        VStack(spacing: 10) {
            HStack(spacing: 10) {
                if let playbackURL {
                    ShareLink(item: SharedVideo(remoteURL: playbackURL, name: video.displayTitle), preview: SharePreview(video.displayTitle)) {
                        Label("Share", systemImage: "square.and.arrow.up").lineLimit(1).frame(maxWidth: .infinity)
                    }.buttonStyle(.bordered)
                }
                Button {
                    UIPasteboard.general.string = video.displayTitle
                    copied = true
                    Task { try? await Task.sleep(for: .seconds(2)); copied = false }
                } label: {
                    Label(copied ? "Copied" : "Copy title", systemImage: copied ? "checkmark" : "doc.on.doc").lineLimit(1).frame(maxWidth: .infinity)
                }.buttonStyle(.bordered)
            }
            if let d = videoDescription {
                Button {
                    UIPasteboard.general.string = d
                    copiedDescription = true
                    Task { try? await Task.sleep(for: .seconds(2)); copiedDescription = false }
                } label: {
                    Label(copiedDescription ? "Copied" : "Copy description with credits", systemImage: copiedDescription ? "checkmark" : "text.alignleft").lineLimit(1).frame(maxWidth: .infinity)
                }.buttonStyle(.bordered).accessibilityIdentifier("copyDescription")
            }
        }
    }

    private func message(_ title: String, _ body: String, icon: String, color: Color) -> some View {
        Card {
            VStack(alignment: .leading, spacing: 8) {
                Label(title, systemImage: icon).font(.headline).foregroundStyle(color)
                Text(body).foregroundStyle(Theme.textSecondary)
            }
        }
    }

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
        } catch let e as APIError { playbackError = e.message } catch { playbackError = APIError.server.message }
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

struct ProgressCard: View {
    let stage: VideoStatus.Stage

    var body: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                Text("Making your video").font(.headline).foregroundStyle(Theme.text)
                Text("This usually takes a few minutes. You can leave this screen; it keeps going.").font(.callout).foregroundStyle(Theme.textSecondary)
                ForEach(VideoStatus.Stage.allCases, id: \.self) { s in
                    HStack(spacing: 10) {
                        if s < stage { Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.success) }
                        else if s == stage { ProgressView().controlSize(.small) }
                        else { Image(systemName: "circle").foregroundStyle(Theme.textSecondary) }
                        Text(s.title).foregroundStyle(s <= stage ? Theme.text : Theme.textSecondary)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
        .accessibilityIdentifier("progressCard")
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
