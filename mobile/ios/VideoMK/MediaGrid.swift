import SwiftUI
import VideoMKCore

/// Which photos are selected, in the order they were picked.
@MainActor @Observable
final class PhotoSelection {
    var active = false
    private(set) var ordered: [String] = []
    var limit: Int?
    var ids: Set<String> { Set(ordered) }
    var count: Int { ordered.count }
    func contains(_ id: String) -> Bool { ordered.contains(id) }
    var isFull: Bool { limit.map { ordered.count >= $0 } ?? false }
    /// Returns false when the limit stopped the selection.
    @discardableResult func toggle(_ id: String) -> Bool {
        if let i = ordered.firstIndex(of: id) { ordered.remove(at: i); return true }
        guard !isFull else { return false }
        ordered.append(id); return true
    }
    func select(_ id: String) { if !contains(id), !isFull { ordered.append(id) } }
    func select(all ids: [String]) { for id in ids { select(id) } }
    func set(_ ids: [String]) { ordered = limit.map { Array(ids.prefix($0)) } ?? ids }
    func clear() { ordered = []; active = false }
    func removeAll(_ gone: Set<String>) { ordered.removeAll { gone.contains($0) } }
}

private struct TileFrames: PreferenceKey {
    static let defaultValue: [String: CGRect] = [:]
    static func reduce(value: inout [String: CGRect], nextValue: () -> [String: CGRect]) { value.merge(nextValue()) { $1 } }
}

private final class FrameBox { var frames: [String: CGRect] = [:] }

/// The timeline grid: square thumbnails under sticky month headers, 3 columns (4 on iPad), lazily built. Long-press starts selecting; drag adds.
struct PhotoGrid: View {
    let feed: PhotoFeed
    let media: MediaModel
    @Bindable var selection: PhotoSelection
    var onOpen: (LibraryPhoto) -> Void
    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var box = FrameBox()
    @State private var limitHit = false

    private var columns: [GridItem] { Array(repeating: GridItem(.flexible(), spacing: 2), count: sizeClass == .regular ? 4 : 3) }

    var body: some View {
        LazyVGrid(columns: columns, spacing: 2, pinnedViews: [.sectionHeaders]) {
            ForEach(feed.sections) { section in
                Section {
                    ForEach(section.items) { photo in
                        PhotoTile(photo: photo, media: media, selected: selection.contains(photo.id), selecting: selection.active)
                            .onTapGesture { tap(photo) }
                            .gesture(LongPressGesture(minimumDuration: 0.35).sequenced(before: DragGesture(minimumDistance: 0, coordinateSpace: .named("grid")))
                                .onChanged { value in
                                    guard case .second(true, let drag) = value else { return }
                                    if !selection.active { selection.active = true; UIImpactFeedbackGenerator(style: .medium).impactOccurred() }
                                    if let p = drag?.location { selectUnder(p) } else { selection.select(photo.id) }
                                })
                            .onAppear { if photo.id == feed.photos.suffix(15).first?.id || photo.id == feed.photos.last?.id { Task { await feed.loadMore() } } }
                    }
                } header: {
                    if !section.title.isEmpty { SectionHeader(title: section.title, count: section.items.count) }
                }
            }
        }
        .coordinateSpace(name: "grid")
        .onPreferenceChange(TileFrames.self) { box.frames = $0 }
        .sensoryFeedback(.warning, trigger: limitHit)
    }

    private func tap(_ photo: LibraryPhoto) {
        if selection.active {
            if !selection.toggle(photo.id) { limitHit.toggle() }
        } else { onOpen(photo) }
    }

    private func selectUnder(_ point: CGPoint) {
        guard let hit = box.frames.first(where: { $0.value.contains(point) })?.key else { return }
        if !selection.contains(hit), selection.isFull { limitHit.toggle(); return }
        selection.select(hit)
    }
}

private struct SectionHeader: View {
    let title: String, count: Int
    var body: some View {
        HStack {
            Text(title).font(.subheadline.weight(.semibold)).foregroundStyle(Theme.text)
            Spacer()
            Text("\(count)").font(.caption.monospacedDigit()).foregroundStyle(Theme.textSecondary)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(.bar)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title), \(count) \(count == 1 ? "photo" : "photos")")
        .accessibilityAddTraits(.isHeader)
    }
}

struct PhotoTile: View {
    let photo: LibraryPhoto
    let media: MediaModel
    let selected: Bool
    let selecting: Bool
    @State private var image: UIImage?

    var body: some View {
        Color.clear.aspectRatio(1, contentMode: .fit)
            .overlay {
                if let image { Image(uiImage: image).resizable().scaledToFill() }
                else { Rectangle().fill(Theme.surfaceRaised) }
            }
            .clipped()
            .overlay { if selected { Rectangle().fill(Theme.primary.opacity(0.25)) } }
            .overlay(alignment: .bottomTrailing) {
                if selecting {
                    Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 22)).symbolRenderingMode(.palette)
                        .foregroundStyle(selected ? .white : Color.white.opacity(0.9), selected ? Theme.primary : Color.black.opacity(0.25))
                        .padding(6).accessibilityHidden(true)
                }
            }
            .background(GeometryReader { g in Color.clear.preference(key: TileFrames.self, value: [photo.id: g.frame(in: .named("grid"))]) })
            .contentShape(Rectangle())
            .task(id: photo.id) { if image == nil { image = await media.thumbnail(for: photo) } }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(MediaGrouping.accessibilityLabel(photo))
            .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
            .accessibilityHint(selecting ? "Double tap to \(selected ? "deselect" : "select")" : "Double tap to open. Press and hold to select.")
            .accessibilityIdentifier("mediaTile")
    }
}

/// Skeleton tiles while the first page loads.
struct SkeletonGrid: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.horizontalSizeClass) private var sizeClass
    @State private var pulse = false
    var body: some View {
        let cols = Array(repeating: GridItem(.flexible(), spacing: 2), count: sizeClass == .regular ? 4 : 3)
        LazyVGrid(columns: cols, spacing: 2) {
            ForEach(0..<21, id: \.self) { _ in
                Rectangle().fill(Theme.surfaceRaised).aspectRatio(1, contentMode: .fit).opacity(pulse && !reduceMotion ? 0.55 : 1)
            }
        }
        .onAppear { if !reduceMotion { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { pulse = true } } }
        .accessibilityElement(children: .ignore).accessibilityLabel("Loading your photos")
    }
}
