import SwiftUI
import VideoMKCore

// The upload journey (docs/UI_DESIGN.md m): local pictures first, one persistent bar, one summary toast.

private let navy = Color(red: 8 / 255, green: 10 / 255, blue: 28 / 255)

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
                    Text("Adding \(ComposerPlan.plural(all.count, "photo"))").font(.system(size: 17, weight: .bold)).foregroundStyle(Theme.text)
                    Spacer()
                    Text("Newest first").font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                }
                .padding(.horizontal, 16).padding(.vertical, 10)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Adding \(ComposerPlan.plural(all.count, "photo")), \(doneCount) done")
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
        .accessibilityLabel("Photo failed to upload. Double tap to retry.")
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
            Color(navy).opacity(s == .queued ? 0.28 : 0.4)
            VStack { HStack { Spacer(); badge(s == .queued ? "clock" : "pause.fill") }; Spacer() }.padding(6)
        case .uploading:
            Color(navy).opacity(0.38)
            ProgressRing(symbol: "arrow.up")
        case .processing:
            ProcessingShimmer()
            if showLabel {
                VStack { Spacer(); HStack { glass(media.waiting ? "Getting it ready" : "Taking longer than usual", symbol: "sparkles"); Spacer() } }.padding(8)
            }
        case .done:
            if tick { VStack { HStack { Spacer(); Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundStyle(Theme.success).frame(width: 24, height: 24).background(.white, in: Circle()) }; Spacer() }.padding(6).transition(.opacity) }
        case .failed:
            Color(red: 0.72, green: 0.11, blue: 0.11).opacity(0.55)
            VStack(spacing: 6) {
                Image(systemName: "arrow.clockwise").font(.system(size: 18, weight: .semibold)).foregroundStyle(.white).frame(width: 44, height: 44).background(.white.opacity(0.25), in: Circle())
                Text("Tap to retry").font(.system(size: 11, weight: .bold)).foregroundStyle(Theme.danger).padding(.horizontal, 8).frame(height: 22).background(.white, in: Capsule())
            }
        case .alreadyThere:
            Color(navy).opacity(0.38)
            VStack { Spacer(); HStack { HStack(spacing: 4) { Image(systemName: "checkmark").font(.system(size: 10, weight: .bold)); Text("Already there").font(.system(size: 11, weight: .semibold)) }.foregroundStyle(Color(hex: 0x11142B)).padding(.horizontal, 8).frame(height: 22).background(.white.opacity(0.92), in: Capsule()); Spacer() } }.padding(8)
        }
    }

    private func badge(_ symbol: String) -> some View {
        Image(systemName: symbol).font(.system(size: 11, weight: .bold)).foregroundStyle(.white).frame(width: 24, height: 24).background(Color.black.opacity(0.5), in: Circle())
    }

    private func glass(_ text: String, symbol: String) -> some View {
        HStack(spacing: 4) { Image(systemName: symbol).font(.system(size: 10)); Text(text).font(.system(size: 11, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.7) }
            .foregroundStyle(.white).padding(.horizontal, 8).frame(height: 22).background(Color.black.opacity(0.45), in: Capsule())
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
                Circle().fill(Color.black.opacity(0.3))
                Circle().stroke(.white.opacity(0.35), lineWidth: 3)
                Circle().trim(from: 0, to: 0.28).stroke(.white, style: StrokeStyle(lineWidth: 3, lineCap: .round)).rotationEffect(.degrees(angle - 90))
                Image(systemName: symbol).font(.system(size: 15, weight: .semibold)).foregroundStyle(.white)
            }
            .frame(width: 44, height: 44)
        }
    }
}

struct ProcessingShimmer: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        if reduceMotion { Color.white.opacity(0.08) }
        else {
            TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.4) / 2.4
                GeometryReader { g in
                    LinearGradient(colors: [.clear, .white.opacity(0.32), .clear], startPoint: .leading, endPoint: .trailing)
                        .frame(width: g.size.width * 0.6).rotationEffect(.degrees(12)).offset(x: -g.size.width * 0.6 + g.size.width * 1.7 * t)
                }
            }
        }
    }
}

// MARK: the bar

/// One persistent, collapsible upload bar above the tab bar. Expanded it is a panel with the counts and what needs the person.
struct UploadBar: View {
    let media: MediaModel
    let onManageStorage: () -> Void
    @State private var storageNotNow = false
    @State private var confirmCancel = false
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        if let bar = media.bar, bar.kind != .finished, !media.barExpanded || bar.kind == .storageFull {
            Group {
                if bar.kind == .storageFull && !storageNotNow { storageCard(bar) } else { collapsed(bar) }
            }
            .padding(.horizontal, 12).padding(.bottom, 8)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .confirmationDialog("Cancel \(media.upload.queued + media.upload.uploading + media.upload.noSpace) uploads?", isPresented: $confirmCancel, titleVisibility: .visible) {
                Button("Cancel remaining", role: .destructive) { media.cancelUploads() }
                Button("Keep uploading", role: .cancel) {}
            } message: { Text("Photos already added stay.") }
        }
    }

    private func tint(_ bar: UploadBarState) -> Color {
        switch bar.kind { case .storageFull, .offline: Theme.warning; case .needsAttention: Theme.warning; default: Theme.primary }
    }

    private func collapsed(_ bar: UploadBarState) -> some View {
        let p = media.upload
        return VStack(spacing: 0) {
            Button { withAnimation(.snappy) { media.barExpanded.toggle() } } label: {
                HStack(spacing: 12) {
                    ZStack {
                        Circle().stroke(Theme.surface3, lineWidth: 4)
                        Circle().trim(from: 0, to: max(0.04, bar.fraction)).stroke(tint(bar), style: StrokeStyle(lineWidth: 4, lineCap: .round)).rotationEffect(.degrees(-90))
                        Image(systemName: bar.kind == .offline ? "icloud.slash" : "icloud.and.arrow.up").font(.system(size: 15, weight: .semibold)).foregroundStyle(tint(bar))
                    }.frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(bar.title).font(.system(size: 15, weight: .bold)).foregroundStyle(Theme.text).lineLimit(1)
                        Text(bar.subtitle).font(.system(size: 13)).foregroundStyle(Theme.textSecondary).lineLimit(2)
                    }
                    Spacer(minLength: 4)
                    if bar.kind == .needsAttention {
                        Text("Review").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.primary)
                    } else if bar.kind != .storageFull {
                        Button { p.paused ? media.resumeUploads() : media.pauseUploads() } label: { Image(systemName: p.paused ? "play.fill" : "pause.fill").font(.system(size: 17)).foregroundStyle(Theme.text).frame(width: 44, height: 44) }
                            .buttonStyle(.plain).accessibilityLabel(p.paused ? "Resume uploads" : "Pause uploads").accessibilityIdentifier("pauseUploads")
                    }
                    Image(systemName: media.barExpanded ? "chevron.down" : "chevron.up").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(width: 36, height: 44)
                }
                .padding(.horizontal, 14).padding(.vertical, 2)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(bar.title). \(bar.subtitle)")
            .accessibilityHint(media.barExpanded ? "Collapses the upload details" : "Shows the upload details")
            .accessibilityIdentifier("uploadBar")
            GeometryReader { g in Rectangle().fill(tint(bar)).frame(width: g.size.width * bar.fraction) }.frame(height: 3)
        }
        .background(bar.kind == .needsAttention || bar.kind == .storageFull ? Theme.warningContainer : Theme.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(bar.kind == .needsAttention || bar.kind == .storageFull ? Theme.warning : Theme.outline, lineWidth: 1))
        .elevation(3)
    }

    private func storageCard(_ bar: UploadBarState) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: "exclamationmark.triangle").font(.system(size: 18)).foregroundStyle(Theme.warning).frame(width: 40, height: 40).background(Theme.warningContainer, in: Circle())
                VStack(alignment: .leading, spacing: 3) {
                    Text(bar.title).font(.system(size: 16, weight: .bold)).foregroundStyle(Theme.text)
                    Text(bar.subtitle).font(.system(size: 14)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    if let m = media.meter { Text(m.label).font(.system(size: 12.5).monospacedDigit()).foregroundStyle(Theme.warning).padding(.top, 2) }
                }
            }
            HStack(spacing: 10) {
                Button(action: onManageStorage) { Text("Manage storage").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.onPrimary).padding(.horizontal, 18).frame(minHeight: 44).background(Theme.gradient, in: Capsule()) }
                    .buttonStyle(.plain).accessibilityIdentifier("manageStorage")
                Button { withAnimation(.snappy) { storageNotNow = true } } label: { Text("Not now").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.primary).padding(.horizontal, 18).frame(minHeight: 44).background(Theme.primaryContainer, in: Capsule()) }
                    .buttonStyle(.plain)
            }
        }
        .padding(14)
        .background(Theme.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Theme.warning, lineWidth: 1.5))
        .elevation(3)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("storageFullCard")
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
            VStack(alignment: .leading, spacing: 12) {
                HStack(spacing: 12) {
                    Image(systemName: "icloud.and.arrow.up").font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.primary).frame(width: 40, height: 40).background(Circle().stroke(Theme.surface3, lineWidth: 4))
                    VStack(alignment: .leading, spacing: 1) {
                        Text(bar.title).font(.system(size: 15, weight: .bold)).foregroundStyle(Theme.text)
                        Text(bar.subtitle).font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                    }
                    Spacer()
                    Button(action: onClose) { Image(systemName: "chevron.down").font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }.accessibilityLabel("Collapse")
                }
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: typeSize.isAccessibilitySize ? 2 : 4), spacing: 8) {
                    stat(bar.added, "Added"); stat(bar.gettingReady, "Getting ready"); stat(bar.waiting, "Waiting"); stat(bar.needYou, "Need you", danger: bar.needYou > 0)
                }
                if !failed.isEmpty {
                    Text("NEEDS ATTENTION").font(.system(size: 13, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary)
                    ForEach(Array(failed.prefix(4).enumerated()), id: \.element.id) { n, item in failedRow(item, n) }
                    if failed.count > 4 { Text("and \(failed.count - 4) more").font(.system(size: 13)).foregroundStyle(Theme.textSecondary) }
                }
                Text("You can close the app. Uploads carry on, and pick up where they stopped when you come back.").font(.system(size: 14)).foregroundStyle(Theme.textSecondary)
                HStack {
                    Button("Cancel remaining", role: .destructive, action: cancel).font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.danger).frame(minHeight: 44)
                    Spacer()
                    Button { media.upload.paused ? media.resumeUploads() : media.pauseUploads() } label: {
                        Label(media.upload.paused ? "Resume all" : "Pause all", systemImage: media.upload.paused ? "play.fill" : "pause.fill").font(.system(size: 16, weight: .semibold)).foregroundStyle(Theme.primary)
                            .padding(.horizontal, 18).frame(minHeight: 48).background(Theme.primaryContainer, in: Capsule())
                    }.buttonStyle(.plain)
                }
            }
            .padding(14)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(Theme.outline, lineWidth: 1))
            .elevation(3)
            .padding(.horizontal, 12)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("uploadPanel")
        }
    }

    private func stat(_ n: Int, _ label: String, danger: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(n)").font(.system(size: 24, weight: .bold).monospacedDigit()).foregroundStyle(danger ? Theme.danger : Theme.text)
            Text(label).font(.system(size: 13)).foregroundStyle(Theme.textSecondary).lineLimit(2)
        }
        .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading).padding(.horizontal, 10)
        .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .accessibilityElement(children: .combine)
    }

    private func failedRow(_ item: QueueItem, _ n: Int) -> some View {
        HStack(spacing: 12) {
            FailedThumb(item: item, media: media)
            VStack(alignment: .leading, spacing: 1) {
                Text(item.file.hasSuffix(".jpg") && item.file.count < 24 ? item.file : "Photo \(n + 1)").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                Text(item.reason ?? "Connection dropped. Tap to try again.").font(.system(size: 13)).foregroundStyle(Theme.danger).fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 4)
            Button { media.retryItem(item.id) } label: { Text("Retry").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.primary).padding(.horizontal, 16).frame(minHeight: 44).background(Theme.primaryContainer, in: Capsule()) }
                .buttonStyle(.plain).accessibilityIdentifier("retryItem")
        }
    }
}

private struct FailedThumb: View {
    let item: QueueItem
    let media: MediaModel
    @State private var image: UIImage?
    var body: some View {
        Group { if let image { Image(uiImage: image).resizable().scaledToFill() } else { Theme.surfaceRaised } }
            .frame(width: 44, height: 44).clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
            .task { image = await media.localImage(for: item) }
    }
}

// MARK: toast and the Videos-tab pill

struct UploadToast: View {
    let toast: MediaModel.ToastMessage
    let onAction: () -> Void
    let onDismiss: () -> Void
    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "checkmark.circle.fill").font(.system(size: 20)).foregroundStyle(Color(hex: 0x4ADE80))
            Text(toast.text).font(.system(size: 14.5)).foregroundStyle(.white).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            if let action = toast.action { Button(action: action == "Review" || action == "View" ? onAction : onDismiss) { Text(action).font(.system(size: 14, weight: .semibold)).foregroundStyle(Color(hex: 0xB9BBFF)).frame(minWidth: 44, minHeight: 44) } }
        }
        .padding(.leading, 14).padding(.trailing, 8).frame(minHeight: 52)
        .background(Color(hex: 0x23263F), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .padding(.horizontal, 12).padding(.bottom, 8)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("uploadToast")
    }
}

/// A slim pill above the tab bar on Videos while photos are uploading. Opens Media.
struct UploadPill: View {
    let media: MediaModel
    let onTap: () -> Void
    var body: some View {
        if let ob = media.organizeBar, media.bar == nil || media.bar?.kind == .finished {
            Button(action: onTap) {
                HStack(spacing: 8) {
                    Image(systemName: "sparkles").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.primary)
                    Text(ob.kind == .running ? ob.title.replacingOccurrences(of: "Organizing…", with: "Organizing") : ob.title).font(.system(size: 14, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text).lineLimit(1)
                    Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                }
                .padding(.horizontal, 14).frame(height: 36).background(Theme.surface, in: Capsule()).overlay(Capsule().stroke(Theme.outline, lineWidth: 1)).elevation(2).frame(minHeight: 44)
            }
            .buttonStyle(.plain).accessibilityLabel("\(ob.title). Opens Media.").accessibilityIdentifier("organizePill")
        } else if let bar = media.bar, bar.kind != .finished {
            Button(action: onTap) {
                HStack(spacing: 8) {
                    Image(systemName: "icloud.and.arrow.up").font(.system(size: 13, weight: .semibold)).foregroundStyle(Theme.primary)
                    Text(bar.title).font(.system(size: 14, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
                    Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(Theme.textSecondary)
                }
                .padding(.horizontal, 14).frame(height: 36).background(Theme.surface, in: Capsule()).overlay(Capsule().stroke(Theme.outline, lineWidth: 1)).elevation(2)
                .frame(minHeight: 44)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(bar.title). Opens Media.")
            .accessibilityIdentifier("uploadPill")
        }
    }
}
