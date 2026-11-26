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
    var onLimit: () -> Void = {}
    var hidden: Set<String> = []
    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var box = FrameBox()
    @State private var limitHit = false

    private var columns: [GridItem] { Array(repeating: GridItem(.flexible(), spacing: 2), count: sizeClass == .regular ? 4 : 3) }

    var body: some View {
        LazyVGrid(columns: columns, spacing: 2, pinnedViews: [.sectionHeaders]) {
            ForEach(feed.sections) { section in
                let shown = hidden.isEmpty ? section.items : section.items.filter { !hidden.contains($0.id) }
                if !shown.isEmpty {
                Section {
                    ForEach(shown) { photo in
                        PhotoTile(photo: photo, media: media, selected: selection.contains(photo.id), selecting: selection.active, order: selection.active ? selection.ordered.firstIndex(of: photo.id).map { $0 + 1 } : nil, dimmed: selection.active && selection.isFull && !selection.contains(photo.id))
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
                    if !section.title.isEmpty { SectionHeader(title: section.title, count: shown.count) }
                }
                }
            }
        }
        .coordinateSpace(name: "grid")
        .onPreferenceChange(TileFrames.self) { box.frames = $0 }
        .sensoryFeedback(.warning, trigger: limitHit)
    }

    private func tap(_ photo: LibraryPhoto) {
        if selection.active {
            if !selection.toggle(photo.id) { limitHit.toggle(); onLimit() }
        } else { onOpen(photo) }
    }

    private func selectUnder(_ point: CGPoint) {
        guard let hit = box.frames.first(where: { $0.value.contains(point) })?.key else { return }
        if !selection.contains(hit), selection.isFull { limitHit.toggle(); onLimit(); return }
        selection.select(hit)
    }
}

private struct SectionHeader: View {
    let title: String, count: Int
    var body: some View {
        HStack {
            Text(title).font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.text)
            Spacer()
            Text("\(count)").font(.system(size: 13).monospacedDigit()).foregroundStyle(Theme.textSecondary)
        }
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(.bar)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(tr("media.section_a11y", title, tr("photos.count", count)))
        .accessibilityAddTraits(.isHeader)
    }
}

struct PhotoTile: View {
    let photo: LibraryPhoto
    let media: MediaModel
    let selected: Bool
    let selecting: Bool
    var order: Int?
    var dimmed = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var image: UIImage?

    var body: some View {
        Color.clear.aspectRatio(1, contentMode: .fit)
            .overlay {
                ZStack {
                    Rectangle().fill(Theme.surfaceRaised)
                    if let image { Image(uiImage: image).resizable().scaledToFill() }
                }
                .clipShape(RoundedRectangle(cornerRadius: selected ? 10 : 0, style: .continuous))
                .scaleEffect(selected && !reduceMotion ? 0.92 : 1)
                .overlay { if selected { RoundedRectangle(cornerRadius: 10, style: .continuous).fill(Theme.primary.opacity(0.12)).scaleEffect(reduceMotion ? 1 : 0.92) } }
                .animation(reduceMotion ? nil : .easeOut(duration: 0.16), value: selected)
            }
            .overlay { if selected { Rectangle().stroke(Theme.gradientStart, lineWidth: 3) } }
            .clipped()
            .overlay(alignment: .topTrailing) {
                if selecting {
                    ZStack {
                        if selected {
                            Circle().fill(Theme.gradient)
                            Text(order.map(String.init) ?? "").font(.system(size: 12, weight: .bold).monospacedDigit()).foregroundStyle(.white)
                        } else {
                            Circle().fill(Color.black.opacity(0.18))
                        }
                        Circle().stroke(.white, lineWidth: 2)
                    }
                    .frame(width: 24, height: 24).padding(6).accessibilityHidden(true)
                }
            }
            .opacity(dimmed ? 0.45 : 1)
            .background(GeometryReader { g in Color.clear.preference(key: TileFrames.self, value: [photo.id: g.frame(in: .named("grid"))]) })
            .contentShape(Rectangle())
            .task(id: photo.id) { if image == nil { image = await media.thumbnail(for: photo) } }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(MediaGrouping.accessibilityLabel(photo) + (selected ? (order.map { tr("media.tile_selected_n", $0) } ?? tr("media.tile_selected")) : ""))
            .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
            .accessibilityHint(selecting ? tr(selected ? "media.hint_deselect" : "media.hint_select") : tr("media.hint_open"))
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
        .accessibilityElement(children: .ignore).accessibilityLabel(tr("media.loading_your_photos"))
    }
}
