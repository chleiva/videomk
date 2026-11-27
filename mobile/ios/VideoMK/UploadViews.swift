import SwiftUI
import VideoMKCore

// The upload journey (docs/UI_DESIGN.md m): local pictures first, one persistent bar, one summary toast.


/// The "Adding 120 photos" section at the top of the Media grid: the person's own pictures, newest first, each with its state.
struct UploadBatchSection: View {
    let media: MediaModel
    let listed: [String: LibraryPhoto]       // photos the server already lists, by id
    @Environment(\.horizontalSizeClass) private var sizeClass

    private var items: [QueueItem] { media.queueItems.reversed().filter { !media.hiddenTiles.contains($0.id) } }
    private var columns: [GridItem] { Array(repeating: GridItem(.flexible(), spacing: 2), count: sizeClass == .regular ? 4 : 3) }

    var body: some View {
        let all = media.queueItems
        let doneCount = all.filter { $0.state == .done || $0.state == .duplicate }.count
        let processing = all.filter { UploadTiles.state(of: $0, paused: media.upload.paused, offline: media.upload.lastError != nil, listed: $0.libraryID.map { listed[$0] != nil } ?? false) == .processing }.count
        LazyVGrid(columns: columns, spacing: 2, pinnedViews: []) {
            Section {
                ForEach(items) { item in
                    UploadTile(item: item, media: media, server: item.libraryID.flatMap { listed[$0] }, showLabel: UploadTiles.showsProcessingLabel(processingCount: processing))
                }
            } header: {
                HStack {
                    Text(tr("upload.adding_title", all.count)).font(.role(.body, weight: .bold)).foregroundStyle(Theme.text)
                    Spacer()
                    Text(tr("upload.newest_first")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary)
                }
                .padding(.horizontal, Theme.gutter).padding(.vertical, 10)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(tr("upload.adding_a11y", tr("photos.count", all.count), doneCount))
                .accessibilityAddTraits(.isHeader)
                .accessibilityIdentifier("addingHeader")
            }
        }
    }
}

struct UploadTile: View {
    let item: QueueItem
    let media: MediaModel
    let server: LibraryPhoto?
    let showLabel: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var local: UIImage?
    @State private var remote: UIImage?
    @State private var tick = false

    private var state: UploadTileState {
        UploadTiles.state(of: item, paused: media.upload.paused, offline: media.upload.lastError != nil, listed: server != nil)
    }

    var body: some View {
        let s = state
        Color.clear.aspectRatio(1, contentMode: .fit)          // the square never changes size: pictures and states are drawn inside it
        .overlay {
            ZStack {
                Rectangle().fill(Theme.surfaceRaised)
                if let local { Image(uiImage: local).resizable().scaledToFill() }
                if let remote { Image(uiImage: remote).resizable().scaledToFill().transition(.opacity) }   // the server picture settles over the local one, same crop
                overlay(s)
            }
            .clipped()
        }
        .clipped()
        .saturation(s == .queued ? 0.55 : s == .waiting ? 0.5 : s == .failed ? 0 : 1)
        .contentShape(Rectangle())
        .onTapGesture { tapped(s) }
        .task(id: item.id) { local = await media.localImage(for: item) }
        .task(id: server?.id) {
            guard let server else { return }
            let img = await media.thumbnail(for: server)
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.28)) { remote = img }
        }
        .onChange(of: s) { _, new in
            guard new == .done else { return }
            tick = true
            Task { try? await Task.sleep(for: .milliseconds(900)); withAnimation(reduceMotion ? nil : .easeOut(duration: 0.3)) { tick = false } }
        }
        .task(id: s == .alreadyThere) {
            guard s == .alreadyThere else { return }
            try? await Task.sleep(for: .seconds(4))
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { media.hideTile(item.id) }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityHidden(s != .failed)              // the grid header carries the aggregate; only a failed tile asks for the person
        .accessibilityLabel(tr("upload.photo_failed_to_upload_double"))
        .accessibilityAddTraits(s == .failed ? .isButton : [])
        .accessibilityIdentifier("uploadTile")
    }

    private func tapped(_ s: UploadTileState) {
        switch s {
        case .failed: UIImpactFeedbackGenerator(style: .light).impactOccurred(); media.retryItem(item.id)
        case .processing where !media.waiting: Task { await media.refreshNow() }      // taking longer than usual: tap to look again
        default: break
        }
    }

    @ViewBuilder private func overlay(_ s: UploadTileState) -> some View {
        switch s {
        case .queued, .waiting:
            Theme.mediaInk.opacity(s == .queued ? 0.28 : 0.4)
            VStack { HStack { Spacer(); badge(s == .queued ? "clock" : "pause.fill") }; Spacer() }.padding(6)
        case .uploading:
            Theme.mediaInk.opacity(0.38)
            ProgressRing(symbol: "arrow.up")
        case .processing:
            ProcessingShimmer()
            if showLabel {
                VStack { Spacer(); HStack { glass(media.waiting ? tr("upload.getting_it_ready") : tr("upload.taking_longer_than_usual"), symbol: "sparkles"); Spacer() } }.padding(8)
            }
        case .done:
            if tick { VStack { HStack { Spacer(); Image(systemName: "checkmark").font(.role(.caption, weight: .bold)).foregroundStyle(Theme.success).frame(width: 24, height: 24).background(Theme.onMedia, in: Circle()) }; Spacer() }.padding(6).transition(.opacity) }
        case .failed:
            Theme.dangerSolid.opacity(0.55)
            VStack(spacing: 6) {
                Image(systemName: "arrow.clockwise").font(.role(.headline, weight: .semibold)).foregroundStyle(Theme.onMedia).frame(width: 44, height: 44).background(Theme.onMedia.opacity(0.25), in: Circle())
                Text(tr("upload.tap_to_retry")).font(.role(.caption, weight: .bold)).foregroundStyle(Theme.danger).padding(.horizontal, 8).frame(height: 22).background(Theme.onMedia, in: Capsule())
            }
        case .alreadyThere:
            Theme.mediaInk.opacity(0.38)
            VStack { Spacer(); HStack { HStack(spacing: 4) { Image(systemName: "checkmark").font(.role(.caption, weight: .bold)); Text(tr("upload.already_there")).font(.role(.caption, weight: .semibold)) }.foregroundStyle(Theme.mediaInk).padding(.horizontal, 8).frame(height: 22).background(Theme.onMedia.opacity(0.92), in: Capsule()); Spacer() } }.padding(8)
        }
    }

    private func badge(_ symbol: String) -> some View {
        Image(systemName: symbol).font(.role(.caption, weight: .bold)).foregroundStyle(Theme.onMedia).frame(width: 24, height: 24).background(Theme.mediaInk.opacity(0.5), in: Circle())
    }

    private func glass(_ text: String, symbol: String) -> some View {
        HStack(spacing: 4) { Image(systemName: symbol).font(.role(.caption, weight: .regular)); Text(text).font(.role(.caption, weight: .semibold)).fixedSize(horizontal: false, vertical: true) }
            .foregroundStyle(Theme.onMedia).padding(.horizontal, 8).padding(.vertical, 3).frame(minHeight: 22).background(Theme.mediaInk.opacity(0.45), in: RoundedRectangle(cornerRadius: Theme.Radii.field, style: .continuous))
    }
}

/// A calm ring with an arrow: indeterminate (the upload is one request per photo), static when Reduce Motion is on.
struct ProgressRing: View {
    let symbol: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        TimelineView(.animation(minimumInterval: 1 / 30, paused: reduceMotion)) { ctx in
            let angle = reduceMotion ? 0 : ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.4) / 1.4 * 360
            ZStack {
                Circle().fill(Theme.mediaInk.opacity(0.3))
                Circle().stroke(Theme.onMedia.opacity(0.35), lineWidth: 3)
                Circle().trim(from: 0, to: 0.28).stroke(Theme.onMedia, style: StrokeStyle(lineWidth: 3, lineCap: .round)).rotationEffect(.degrees(angle - 90))
                Image(systemName: symbol).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.onMedia)
            }
            .frame(width: 44, height: 44)
        }
    }
}

struct ProcessingShimmer: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        if reduceMotion { Theme.onMedia.opacity(0.08) }
        else {
            TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.4) / 2.4
                GeometryReader { g in
                    LinearGradient(colors: [.clear, Theme.onMedia.opacity(0.32), .clear], startPoint: .leading, endPoint: .trailing)
                        .frame(width: g.size.width * 0.6).rotationEffect(.degrees(12)).offset(x: -g.size.width * 0.6 + g.size.width * 1.7 * t)
                }
            }
        }
    }
}

// MARK: the bar

/// One persistent, collapsible upload bar above the tab bar: an opaque card (never glass, never under a fade). Expanded it is a panel with the
/// counts and what needs the person.
struct UploadBar: View {
    let media: MediaModel
    let onManageStorage: () -> Void
    @State private var storageNotNow = false

    var body: some View {
        if let bar = media.bar, bar.kind != .finished, !media.barExpanded || bar.kind == .storageFull {
            Group {
                if bar.kind == .storageFull && !storageNotNow { storageCard(bar) } else { collapsed(bar) }
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.s)
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }

    private func tint(_ bar: UploadBarState) -> Color {
        switch bar.kind { case .storageFull, .offline, .needsAttention: Theme.warning; default: Theme.primary }
    }

    private func collapsed(_ bar: UploadBarState) -> some View {
        let p = media.upload
        return HStack(spacing: Theme.Space.m) {
            Button { withAnimation(.snappy) { media.barExpanded.toggle() } } label: {
                HStack(spacing: Theme.Space.m) {
                    UploadRing(fraction: bar.fraction, symbol: bar.kind == .offline ? "icloud.slash" : bar.kind == .needsAttention || bar.kind == .storageFull ? "exclamationmark" : "arrow.up", tint: tint(bar))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(bar.title).font(.role(.subhead, weight: .semibold)).monospacedDigit().foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.85)
                        Text(bar.subtitle).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).lineLimit(2)
                    }
                    Spacer(minLength: Theme.Space.xs)
                    if bar.kind == .needsAttention { Text(tr("upload.review")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.primary) }
                }
                .frame(minHeight: Theme.minTouch).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(bar.title). \(bar.subtitle)")
            .accessibilityHint(media.barExpanded ? tr("upload.collapses_the_upload_details") : tr("upload.shows_the_upload_details"))
            .accessibilityIdentifier("uploadBar")
            if bar.kind != .needsAttention && bar.kind != .storageFull {
                IconButton(symbol: p.paused ? "play.fill" : "pause.fill", label: p.paused ? tr("upload.resume_uploads") : tr("upload.pause_uploads"), size: Theme.minTouch, identifier: "pauseUploads") { p.paused ? media.resumeUploads() : media.pauseUploads() }
            }
        }
        .padding(.leading, Theme.Space.l).padding(.trailing, Theme.Space.m).padding(.vertical, Theme.Space.s)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
        .elevation(3)
    }

    private func storageCard(_ bar: UploadBarState) -> some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            HStack(alignment: .top, spacing: Theme.Space.m) {
                Image(systemName: "exclamationmark.triangle").font(.role(.headline)).foregroundStyle(Theme.warning).dynamicTypeSize(...DynamicTypeSize.xxxLarge).frame(width: 40, height: 40).background(Theme.warningContainer, in: Circle()).accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(bar.title).font(.role(.headline)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                    Text(bar.subtitle).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    if let m = media.meter { Text(m.label).font(.role(.footnote).monospacedDigit()).foregroundStyle(Theme.textSecondary).padding(.top, 2) }
                }
            }
            HStack(spacing: Theme.Space.s) {
                Button(tr("upload.manage_storage"), action: onManageStorage).buttonStyle(TonalButtonStyle()).accessibilityIdentifier("manageStorage")
                Button(tr("organize.not_now")) { withAnimation(.snappy) { storageNotNow = true } }.buttonStyle(TextButtonStyle()).padding(.horizontal, Theme.Space.m).accessibilityIdentifier("storageNotNow")
            }
        }
        .padding(Theme.Space.l)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
        .elevation(3)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("storageFullCard")
    }
}

/// The progress ring of the upload bar: how far along, with a glyph that says what is happening.
struct UploadRing: View {
    let fraction: Double
    let symbol: String
    var tint: Color = Theme.primary
    var body: some View {
        ZStack {
            Circle().stroke(Theme.surface3, lineWidth: 3.5)
            Circle().trim(from: 0, to: max(0.04, fraction)).stroke(tint, style: StrokeStyle(lineWidth: 3.5, lineCap: .round)).rotationEffect(.degrees(-90))
            Image(systemName: symbol).font(.role(.footnote, weight: .bold)).foregroundStyle(tint).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
        }
        .frame(width: 36, height: 36).accessibilityHidden(true)
    }
}

struct UploadPanel: View {
    let media: MediaModel
    let onClose: () -> Void
    let cancel: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        if let bar = media.bar {
            let failed = media.queueItems.filter { $0.state == .failed }
            VStack(alignment: .leading, spacing: Theme.Space.m) {
                HStack(spacing: Theme.Space.m) {
                    UploadRing(fraction: bar.fraction, symbol: "arrow.up")
                    VStack(alignment: .leading, spacing: 2) {
                        Text(bar.title).font(.role(.subhead, weight: .semibold)).monospacedDigit().foregroundStyle(Theme.text)
                        Text(bar.subtitle).font(.role(.footnote)).foregroundStyle(Theme.textSecondary)
                    }
                    Spacer()
                    IconButton(symbol: "chevron.down", label: tr("upload.collapse"), size: Theme.minTouch, action: onClose)
                }
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: Theme.Space.s), count: typeSize.isAccessibilitySize ? 2 : 4), spacing: Theme.Space.s) {
                    stat(bar.added, tr("upload.stat_added")); stat(bar.gettingReady, tr("upload.stat_getting_ready")); stat(bar.waiting, tr("upload.stat_waiting")); stat(bar.needYou, tr("upload.stat_need_you"), danger: bar.needYou > 0)
                }
                if !failed.isEmpty {
                    Text(tr("upload.needs_attention")).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                    ForEach(Array(failed.prefix(4).enumerated()), id: \.element.id) { n, item in failedRow(item, n) }
                    if failed.count > 4 { Text(tr("upload.and_more", failed.count - 4)).font(.role(.footnote)).foregroundStyle(Theme.textSecondary) }
                }
                Text(tr("upload.you_can_close_the_app")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                HStack(spacing: Theme.Space.s) {
                    Button(tr("media.cancel_remaining"), action: cancel).buttonStyle(TextButtonStyle(tint: Theme.danger)).accessibilityIdentifier("cancelUploads")
                    Spacer()
                    Button { media.upload.paused ? media.resumeUploads() : media.pauseUploads() } label: {
                        Label(media.upload.paused ? tr("upload.resume_all") : tr("upload.pause_all"), systemImage: media.upload.paused ? "play.fill" : "pause.fill")
                    }.buttonStyle(TonalButtonStyle(fullWidth: false))
                }
            }
            .padding(Theme.Space.l)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
            .elevation(3)
            .padding(.horizontal, Theme.gutter)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("uploadPanel")
        }
    }

    private func stat(_ n: Int, _ label: String, danger: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(n)").font(.role(.title).monospacedDigit()).foregroundStyle(danger ? Theme.danger : Theme.text)
            Text(label).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).lineLimit(2)
        }
        .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading).padding(.horizontal, Theme.Space.m)
        .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private func failedRow(_ item: QueueItem, _ n: Int) -> some View {
        HStack(spacing: Theme.Space.m) {
            FailedThumb(item: item, media: media)
            VStack(alignment: .leading, spacing: 1) {
                Text(item.file.hasSuffix(".jpg") && item.file.count < 24 ? item.file : tr("attach.photo_n", n + 1)).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                Text(item.reason ?? tr("upload.connection_dropped")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: Theme.Space.xs)
            Button(tr("upload.retry")) { media.retryItem(item.id) }.buttonStyle(TonalButtonStyle(fullWidth: false)).accessibilityIdentifier("retryItem")
        }
    }
}

private struct FailedThumb: View {
    let item: QueueItem
    let media: MediaModel
    @State private var image: UIImage?
    var body: some View {
        Group { if let image { Image(uiImage: image).resizable().scaledToFill() } else { Theme.surfaceRaised } }
            .frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: Theme.Radii.thumb, style: .continuous))
            .task { image = await media.localImage(for: item) }
    }
}

// MARK: toast and the Videos-tab pill

struct UploadToast: View {
    let toast: MediaModel.ToastMessage
    let onAction: () -> Void
    let onDismiss: () -> Void
    var body: some View {
        ToastBar(text: toast.text, action: toast.action, identifier: "uploadToast", onAction: toast.action == tr("upload.review") || toast.action == tr("org.view") ? onAction : onDismiss)
    }
}

/// A slim, opaque pill above the tab bar on Videos while photos are uploading or being organized. Opens Media.
struct UploadPill: View {
    let media: MediaModel
    let onTap: () -> Void
    var body: some View {
        if let ob = media.organizeBar, media.bar == nil || media.bar?.kind == .finished {
            pill(symbol: "sparkles", title: ob.kind == .running ? ob.title.replacingOccurrences(of: "…", with: "") : ob.title, id: "organizePill")
        } else if let bar = media.bar, bar.kind != .finished {
            pill(symbol: "arrow.up.circle", title: bar.title, id: "uploadPill")
        }
    }

    private func pill(symbol: String, title: String, id: String) -> some View {
        Button(action: onTap) {
            HStack(spacing: Theme.Space.s) {
                Image(systemName: symbol).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary)
                Text(title).font(.role(.subhead, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text).lineLimit(1)
                Image(systemName: "chevron.right").font(.role(.caption, weight: .semibold)).foregroundStyle(Theme.textSecondary)
            }
            .padding(.horizontal, Theme.Space.l).frame(minHeight: 40).background(Theme.surface, in: Capsule()).elevation(2)
            .frame(minHeight: Theme.minTouch).contentShape(Capsule())
        }
        .buttonStyle(.plain).accessibilityLabel(tr("upload.opens_media_a11y", title)).accessibilityIdentifier(id)
    }
}
