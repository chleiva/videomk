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
    @State private var playbackError: String?
    @State private var copied = false

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
    }

    @ViewBuilder private func playerSection(_ video: VideoItem) -> some View {
        Group {
            if let player { VideoPlayer(player: player) }
            else if let playbackError {
                VStack(spacing: 12) {
                    Text(playbackError).foregroundStyle(Theme.textSecondary)
                    Button("Try again") { Task { await loadPlayerIfReady() } }
                }.frame(maxWidth: .infinity, maxHeight: .infinity)
            } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
        }
        .aspectRatio(16 / 9, contentMode: .fit)
        .background(.black)
        .clipShape(RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
        .accessibilityIdentifier("player")

        Text(video.displayTitle).font(.title3.bold()).foregroundStyle(Theme.text)
        HStack(spacing: 12) {
            if let playbackURL {
                ShareLink(item: SharedVideo(remoteURL: playbackURL, name: video.displayTitle), preview: SharePreview(video.displayTitle)) {
                    Label("Share", systemImage: "square.and.arrow.up").frame(maxWidth: .infinity)
                }.buttonStyle(.bordered)
            }
            Button {
                UIPasteboard.general.string = video.displayTitle
                copied = true
                Task { try? await Task.sleep(for: .seconds(2)); copied = false }
            } label: {
                Label(copied ? "Copied" : "Copy title", systemImage: copied ? "checkmark" : "doc.on.doc").frame(maxWidth: .infinity)
            }.buttonStyle(.bordered)
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
            let url = try await model.playbackURL(for: videoID)
            playbackURL = url
            let p = AVPlayer(url: url)
            player = p
        } catch let e as APIError { playbackError = e.message } catch { playbackError = APIError.server.message }
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
