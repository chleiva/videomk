import SwiftUI
import VideoMKCore

// Smart collections (docs/UI_DESIGN.md n): the prompt sheet, the progress bar and the pill.

/// The sheet after a big upload, or from "Organize my library". One sheet: the preview, "Put all in one collection" swaps the content in place.
struct OrganizeSheet: View {
    let media: MediaModel
    let request: MediaModel.OrganizeRequest
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var preview: OrganizePreview?
    @State private var phase: Phase = .loading
    @State private var showAll = false
    @State private var single = false
    @State private var name = ""
    @FocusState private var nameFocused: Bool
    @State private var detent: PresentationDetent = .height(700)

    enum Phase { case loading, ready, failed, nothing }

    init(media: MediaModel, request: MediaModel.OrganizeRequest) {
        self.media = media; self.request = request
        _preview = State(initialValue: request.preview)
        _phase = State(initialValue: request.preview == nil ? .loading : (request.preview!.groups.isEmpty ? .nothing : .ready))
        #if DEBUG
        if ProcessInfo.processInfo.environment["VMK_DEBUG_ORGANIZE"] == "single" { _single = State(initialValue: true); _name = State(initialValue: "Phuket Jul 2024") }
        #endif
    }

    private var groups: [OrganizeGroup] { preview?.groups ?? [] }
    private var allExisting: Bool { !groups.isEmpty && groups.allSatisfy(\.existing) }
    private var total: Int { preview?.total ?? 0 }
    private var organized: Int { preview?.organized ?? 0 }
    private var title: String {
        guard preview != nil else { return tr("organize.title_default") }
        return allExisting ? tr("organize.title_add_existing", organized) : tr(request.fromBatch ? "organize.title_new_batch" : "organize.title_total", total)
    }

    var body: some View {
        VStack(spacing: 0) {
            Group {
                switch phase {
                case .loading: content(skeleton: true)
                case .ready: single ? AnyView(singleContent) : AnyView(content(skeleton: false))
                case .failed: message("exclamationmark.triangle", tr("organize.check_failed_title"), tr("organize.check_failed_sub"), primary: tr("common.try_again"), { Task { await load() } })
                case .nothing: message("sparkles", tr("organize.nothing_title"), tr("organize.nothing_sub"), primary: tr("media.ok"), { dismiss() })
                }
            }
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.2), value: single)
        }
        .presentationBackground(Theme.surface)
        .presentationDetents([.height(700), .large], selection: $detent)
        .onChange(of: showAll) { _, v in if v { detent = .large } }
        .onChange(of: single) { _, v in if v { detent = .large } }
        .presentationDragIndicator(.visible)
        .task { if preview == nil { await load() } }
        .onAppear { UIAccessibility.post(notification: .announcement, argument: title) }
    }

    private func load() async {
        phase = .loading
        do {
            let p = try await withThrowingTaskGroup(of: OrganizePreview.self) { g in
                g.addTask { try await media.api.organizePreview(since: request.since) }
                g.addTask { try await Task.sleep(for: .seconds(15)); throw LibraryAPIError.network }
                let r = try await g.next()!; g.cancelAll(); return r
            }
            preview = p
            phase = p.groups.isEmpty ? .nothing : .ready
        } catch { phase = .failed }
    }

    // MARK: preview

    private func content(skeleton: Bool) -> some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text(title).font(.vmk(23, weight: .bold)).foregroundStyle(Theme.text).padding(.top, 22).accessibilityAddTraits(.isHeader)
                    Text(tr("organize.well_group_them_by_place")).font(.vmk(15)).foregroundStyle(Theme.textSecondary).padding(.top, 6)
                    VStack(spacing: 0) {
                        if skeleton { ForEach(0..<3, id: \.self) { _ in SkeletonRow() } }
                        else { ForEach(showAll ? groups : Array(groups.prefix(5))) { GroupRow(media: media, group: $0) } }
                    }.padding(.top, 14)
                    if !skeleton, groups.count > 5, !showAll {
                        Button { withAnimation(reduceMotion ? nil : .snappy) { showAll = true } } label: { Text(tr("organize.more", groups.count - 5)).font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: 44, alignment: .leading) }
                            .buttonStyle(.plain).accessibilityLabel(tr("organize.more_a11y", groups.count - 5)).accessibilityIdentifier("organizeMore")
                    }
                    if let p = preview, p.skipped > 0, !skeleton {
                        Text(tr("organize.skipped", p.skipped)).font(.vmk(13)).foregroundStyle(Theme.textSecondary).padding(.top, 4).accessibilityIdentifier("organizeSkipped")
                    }
                    Divider().padding(.top, 14)
                    if media.organizePref != .never { alwaysRow }
                }
                .padding(.horizontal, 20)
            }
            actions(skeleton: skeleton)
        }
    }

    private var alwaysRow: some View {
        Toggle(isOn: Binding(get: { media.organizePref.switchIsOn }, set: { media.setOrganizePref(OrganizePref.fromSwitch($0)) })) {
            VStack(alignment: .leading, spacing: 2) {
                Text(tr("organize.always_organize_new_uploads")).font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.text)
                Text(tr("organize.photos_from_later_uploads_join")).font(.vmk(13)).foregroundStyle(Theme.textSecondary)
            }
        }
        .tint(Theme.primary).padding(.vertical, 10).accessibilityIdentifier("alwaysOrganize")
    }

    private func actions(skeleton: Bool) -> some View {
        VStack(spacing: 10) {
            Button { runAuto() } label: {
                Text(tr("organize.organize")).font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 52).background(Theme.gradient.opacity(skeleton ? 0.4 : 1), in: Capsule())
            }.buttonStyle(.plain).disabled(skeleton).accessibilityIdentifier("organizeGo")
            if typeSize.isAccessibilitySize {
                putAllButton(skeleton); notNow
            } else {
                HStack(spacing: 10) { putAllButton(skeleton).frame(maxWidth: .infinity); notNow.frame(width: 110) }
            }
        }
        .padding(.horizontal, 20).padding(.top, 8).padding(.bottom, 8).background(Theme.surface)
    }

    private func putAllButton(_ skeleton: Bool) -> some View {
        Button { name = SuggestedNames.suggest(groups: groups).first ?? ""; single = true; Task { try? await Task.sleep(for: .milliseconds(300)); nameFocused = true } } label: {
            Text(tr("organize.put_all_in_one_collection")).font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.primary).frame(maxWidth: .infinity, minHeight: 46).background(Theme.primaryContainer, in: Capsule())
        }.buttonStyle(.plain).disabled(skeleton).accessibilityIdentifier("organizeSingle")
    }

    private var notNow: some View {
        Button { dismiss() } label: { Text(tr("organize.not_now")).font(.vmk(15, weight: .medium)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, minHeight: 46) }
            .buttonStyle(.plain).accessibilityIdentifier("organizeNotNow")
    }

    private func runAuto() {
        Haptics.play(.send)
        media.startOrganize(mode: .auto, since: request.since, total: organized)
        dismiss()
    }

    // MARK: one collection

    private var singleContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(tr("organize.put_all_title", organized)).font(.vmk(23, weight: .bold)).foregroundStyle(Theme.text).padding(.top, 22).accessibilityAddTraits(.isHeader)
            Text(tr("organize.give_it_a_name_you")).font(.vmk(15)).foregroundStyle(Theme.textSecondary).padding(.top, 6)
            TextField(tr("organize.collection_name"), text: $name).focused($nameFocused).font(.vmk(17)).padding(.horizontal, 14).frame(height: 52)
                .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous).stroke(Theme.primary, lineWidth: nameFocused ? 2 : 0))
                .padding(.top, 16).submitLabel(.done).accessibilityIdentifier("collectionName")
            Text(tr("organize.suggestions")).font(.vmk(12, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary).padding(.top, 16)
            ScrollView(.horizontal, showsIndicators: false) {
                WrapLayout(spacing: 8) { ForEach(SuggestedNames.suggest(groups: groups), id: \.self) { s in FixChip(title: s) { name = s } } }
            }
            Spacer()
            HStack(spacing: 10) {
                Button { single = false } label: { Text(tr("create.back")).font(.vmk(15, weight: .medium)).foregroundStyle(Theme.textSecondary).frame(minWidth: 70, minHeight: 50) }.buttonStyle(.plain)
                Button { create() } label: {
                    Text(tr("organize.create_collection")).font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 50)
                        .background(Theme.gradient.opacity(SuggestedNames.isValid(name) ? 1 : 0.4), in: Capsule())
                }.buttonStyle(.plain).disabled(!SuggestedNames.isValid(name)).accessibilityIdentifier("createCollection")
            }
            .padding(.bottom, 8)
        }
        .padding(.horizontal, 20)
    }

    private func create() {
        Haptics.play(.send)
        media.startOrganize(mode: .single, since: request.since, name: name.trimmingCharacters(in: .whitespacesAndNewlines), total: organized)
        dismiss()
    }

    private func message(_ symbol: String, _ title: String, _ text: String, primary: String, _ action: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: symbol).font(.vmk(40)).foregroundStyle(Theme.primary).accessibilityHidden(true)
            Text(title).font(.vmk(20, weight: .bold)).foregroundStyle(Theme.text)
            Text(text).font(.vmk(15)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
            Button(action: action) { Text(primary).font(.vmk(17, weight: .semibold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 52).background(Theme.gradient, in: Capsule()) }.buttonStyle(.plain).padding(.top, 8)
            if primary == tr("common.try_again") { Button(tr("organize.not_now")) { dismiss() }.foregroundStyle(Theme.textSecondary).frame(minHeight: 44) }
            Spacer()
        }
        .padding(.horizontal, 24)
    }
}

private struct GroupRow: View {
    let media: MediaModel
    let group: OrganizeGroup
    @Environment(\.dynamicTypeSize) private var typeSize
    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: -10) {
                ForEach(Array(group.sampleIDs.prefix(3).enumerated()), id: \.offset) { i, id in SampleThumb(media: media, id: id).zIndex(Double(i)) }
            }.frame(width: 70, alignment: .leading).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 1) {
                Text(group.name).font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(typeSize.isAccessibilitySize ? 3 : 1).minimumScaleFactor(0.8)
                Text(tr("photos.count", group.count)).font(.vmk(13)).foregroundStyle(Theme.textSecondary)
                if typeSize.isAccessibilitySize, group.existing { existing }
            }
            Spacer(minLength: 4)
            if group.existing, !typeSize.isAccessibilitySize { existing }
        }
        .frame(minHeight: 56).padding(.vertical, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(tr(group.existing ? "organize.group_a11y_existing" : "organize.group_a11y", group.name, tr("photos.count", group.count)))
    }
    private var existing: some View {
        Text(tr("organize.adds_to_existing")).font(.vmk(12, weight: .bold)).foregroundStyle(Theme.primary).padding(.horizontal, 10).frame(height: 24).background(Theme.primaryContainer, in: Capsule()).lineLimit(1).fixedSize()
    }
}

private struct SampleThumb: View {
    let media: MediaModel
    let id: String
    @State private var image: UIImage?
    var body: some View {
        Group { if let image { Image(uiImage: image).resizable().scaledToFill() } else { Theme.surfaceRaised } }
            .frame(width: 30, height: 30).clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous).stroke(Theme.surface, lineWidth: 2))
            .task(id: id) { image = await media.thumbnail(for: LibraryPhoto(id: id)) }       // the store fetches a fresh link by id when it has none
    }
}

private struct SkeletonRow: View {
    @State private var pulse = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous).fill(Theme.surfaceRaised).frame(height: 56).padding(.vertical, 4)
            .opacity(pulse && !reduceMotion ? 0.55 : 1)
            .onAppear { if !reduceMotion { withAnimation(.easeInOut(duration: 0.9).repeatForever(autoreverses: true)) { pulse = true } } }
            .accessibilityHidden(true)
    }
}

// MARK: progress bar and pill

/// The organise job in the upload bar's slot: same anatomy, one pattern. Never shown together with the upload bar.
struct OrganizeBar: View {
    let media: MediaModel
    @State private var confirmStop = false

    var body: some View {
        if let bar = media.organizeBar {
            VStack(spacing: 0) {
                HStack(spacing: 12) {
                    ZStack {
                        Circle().stroke(Theme.surface3, lineWidth: 4)
                        Circle().trim(from: 0, to: max(0.04, bar.fraction)).stroke(tint(bar), style: StrokeStyle(lineWidth: 4, lineCap: .round)).rotationEffect(.degrees(-90))
                        Image(systemName: bar.kind == .waiting ? "icloud.slash" : "sparkles").font(.vmk(15, weight: .semibold)).foregroundStyle(tint(bar))
                    }.frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(bar.title).font(.vmk(15, weight: .bold).monospacedDigit()).foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.8)
                        Text(bar.subtitle).font(.vmk(13)).foregroundStyle(Theme.textSecondary).lineLimit(2)
                    }
                    Spacer(minLength: 4)
                    if bar.kind == .failed {
                        Button(tr("common.try_again")) { media.retryOrganize() }.font(.vmk(15, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("organizeRetry")
                    }
                    Button { confirmStop = true } label: { Image(systemName: "xmark").font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }
                        .buttonStyle(.plain).accessibilityLabel(tr("organize.stop_organizing")).accessibilityIdentifier("stopOrganize")
                }
                .padding(.horizontal, 14).padding(.vertical, 2)
                GeometryReader { g in Rectangle().fill(tint(bar)).frame(width: g.size.width * bar.fraction) }.frame(height: 3)
            }
            .background(bar.kind == .failed ? Theme.warningContainer : Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous).stroke(bar.kind == .failed ? Theme.warning : Theme.outline, lineWidth: 1))
            .elevation(3)
            .padding(.horizontal, 12).padding(.bottom, 8)
            .accessibilityElement(children: .contain)
            .accessibilityValue(tr("common.percent_a11y", Int(bar.fraction * 100)))
            .accessibilityIdentifier("organizeBar")
            .confirmationDialog(tr("organize.stop_organizing_2"), isPresented: $confirmStop, titleVisibility: .visible) {
                Button(tr("organize.keep_going"), role: .cancel) {}
                Button(tr("organize.stop"), role: .destructive) { media.cancelOrganize() }
            } message: { Text(tr("organize.collections_already_made_stay_as")) }
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }
    private func tint(_ bar: OrganizeBarState) -> Color { bar.kind == .failed ? Theme.warning : bar.kind == .waiting ? Theme.textSecondary : Theme.primary }
}

/// Collections made by the organiser carry a small sparkle badge on their cover.
struct AutoBadge: View {
    var body: some View {
        Image(systemName: "sparkles").font(.vmk(11, weight: .semibold)).foregroundStyle(.white).frame(width: 22, height: 22).background(.black.opacity(0.5), in: Circle()).accessibilityHidden(true)
    }
}

struct AutoChip: View {
    var body: some View {
        HStack(spacing: 3) { Image(systemName: "sparkles").font(.vmk(10)); Text(tr("collections.auto")).font(.vmk(12, weight: .bold)) }
            .foregroundStyle(Theme.primary).padding(.horizontal, 8).frame(height: 20).background(Theme.primaryContainer, in: Capsule())
            .accessibilityLabel(tr("organize.automatic_collection"))
    }
}
