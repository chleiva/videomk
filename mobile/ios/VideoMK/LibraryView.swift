import SwiftUI
import VideoMKCore

struct LibraryView: View {
    @Environment(AppModel.self) private var model
    @State private var path: [String] = []
    @State private var showingCreate = false
    @State private var showingSettings = false
    @State private var draft = ""

    var body: some View {
        NavigationStack(path: $path) {
            Group {
                switch (model.loadState, model.videos.isEmpty) {
                case (.loading, true), (.idle, true): ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                case (.failed(let message), true): errorState(message)
                case (_, true): emptyState
                default: list
                }
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("Videos")
            .navigationDestination(for: String.self) { VideoDetailView(videoID: $0) }
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button { showingSettings = true } label: { Image(systemName: "gearshape") }
                        .accessibilityLabel("Settings").accessibilityIdentifier("settingsButton")
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button { draft = ""; showingCreate = true } label: { Image(systemName: "plus") }
                        .accessibilityLabel("New video").accessibilityIdentifier("newVideoButton")
                }
            }
        }
        .task { await model.refresh() }
        .task(id: model.hasRunningVideos) { await model.pollWhileRunning() }
        .sheet(isPresented: $showingCreate) {
            CreateView(initialBrief: draft) { id in
                showingCreate = false
                Task { await model.refresh(); path = [id] }
            }
        }
        .sheet(isPresented: $showingSettings) { SettingsView() }
    }

    private var list: some View {
        List(model.videos) { video in
            NavigationLink(value: video.id) { VideoRow(video: video) }
                .listRowBackground(Theme.surface)
                .accessibilityIdentifier("videoRow")
        }
        .scrollContentBackground(.hidden)
        .refreshable { await model.refresh() }
    }

    private var emptyState: some View {
        ScrollView {
            VStack(spacing: 20) {
                Image(systemName: "sparkles.tv").font(.system(size: 52)).foregroundStyle(Theme.gradient).accessibilityHidden(true)
                Text("Make your first video").font(.title2.bold()).foregroundStyle(Theme.text)
                Text("Describe what you want. The first one is on us.").foregroundStyle(Theme.textSecondary)
                VStack(spacing: 10) {
                    ForEach(ExampleBriefs.all, id: \.self) { example in
                        Button { draft = example; showingCreate = true } label: {
                            Text(example).font(.callout).foregroundStyle(Theme.text).multilineTextAlignment(.leading)
                                .frame(maxWidth: .infinity, alignment: .leading).padding(14)
                                .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                        }
                    }
                }
            }
            .padding(24)
        }
    }

    private func errorState(_ message: String) -> some View {
        ContentUnavailableView {
            Label("Couldn't load your videos", systemImage: "wifi.exclamationmark")
        } description: { Text(message) } actions: {
            Button("Try again") { Task { await model.refresh() } }.buttonStyle(.borderedProminent)
        }
    }
}

enum ExampleBriefs {
    static let all = [
        "How a bill becomes law in the United States, explained for teenagers.",
        "A visual tour of the most famous landmarks of Paris.",
        "Why the sky is blue, with a simple diagram.",
    ]
}

struct VideoRow: View {
    let video: VideoItem

    var body: some View {
        HStack(spacing: 12) {
            Thumbnail(url: video.previewGifURL, status: video.status)
                .frame(width: 112, height: 63)
                .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            VStack(alignment: .leading, spacing: 4) {
                Text(video.displayTitle).font(.headline).foregroundStyle(Theme.text).lineLimit(2)
                HStack(spacing: 8) {
                    StatusChip(status: video.status)
                    if let d = video.durationSeconds, video.status == .complete { Text(Self.duration(d)).font(.caption).foregroundStyle(Theme.textSecondary) }
                }
                if let created = video.createdAt { Text(Self.relative.localizedString(for: created, relativeTo: .now)).font(.caption).foregroundStyle(Theme.textSecondary) }
            }
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    static let relative: RelativeDateTimeFormatter = {
        let f = RelativeDateTimeFormatter(); f.unitsStyle = .short; return f
    }()

    static func duration(_ s: Double) -> String { String(format: "%d:%02d", Int(s) / 60, Int(s) % 60) }
}

struct Thumbnail: View {
    let url: URL?
    let status: VideoStatus

    var body: some View {
        ZStack {
            Theme.surfaceRaised
            if let url {
                AsyncImage(url: url) { phase in
                    if let image = phase.image { image.resizable().scaledToFill() } else { placeholder }
                }
            } else { placeholder }
        }
    }

    private var placeholder: some View {
        Image(systemName: status.isRunning ? "hourglass" : status == .complete ? "play.fill" : "exclamationmark.triangle")
            .foregroundStyle(Theme.textSecondary)
    }
}

struct StatusChip: View {
    let status: VideoStatus

    var body: some View {
        Text(label)
            .font(.caption.weight(.semibold))
            .padding(.horizontal, 8).padding(.vertical, 3)
            .foregroundStyle(color)
            .background(color.opacity(0.15), in: Capsule())
    }

    private var label: String {
        switch status {
        case .running: "Making"
        case .complete: "Ready"
        case .failed: "Failed"
        case .rejected: "Not allowed"
        }
    }

    private var color: Color {
        switch status {
        case .running: Theme.primary
        case .complete: Theme.success
        case .failed: Theme.danger
        case .rejected: Theme.warning
        }
    }
}
