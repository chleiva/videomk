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
                VStack(alignment: .leading, spacing: Theme.Space.m) {
                    Text(title).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, Theme.Space.xl).accessibilityAddTraits(.isHeader)
                    Text(tr("organize.well_group_them_by_place")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
                    VStack(spacing: 0) {
                        if skeleton { ForEach(0..<3, id: \.self) { _ in SkeletonRow() } }
                        else { ForEach(showAll ? groups : Array(groups.prefix(5))) { GroupRow(media: media, group: $0) } }
                    }
                    if !skeleton, groups.count > 5, !showAll {
                        Button(tr("organize.more", groups.count - 5)) { withAnimation(reduceMotion ? nil : .snappy) { showAll = true } }
                            .buttonStyle(TextButtonStyle()).accessibilityLabel(tr("organize.more_a11y", groups.count - 5)).accessibilityIdentifier("organizeMore")
                    }
                    if let p = preview, p.skipped > 0, !skeleton {
                        Text(tr("organize.skipped", p.skipped)).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier("organizeSkipped")
                    }
                    if media.organizePref != .never { Divider().overlay(Theme.outline); alwaysRow }
                }
                .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.l)
            }
            actions(skeleton: skeleton)
        }
    }

    private var alwaysRow: some View {
        Toggle(isOn: Binding(get: { media.organizePref.switchIsOn }, set: { media.setOrganizePref(OrganizePref.fromSwitch($0)) })) {
            VStack(alignment: .leading, spacing: 2) {
                Text(tr("organize.always_organize_new_uploads")).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                Text(tr("organize.photos_from_later_uploads_join")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)       // the whole sentence, never clipped under the buttons
            }
        }
        .tint(Theme.success).padding(.vertical, Theme.Space.s).accessibilityIdentifier("alwaysOrganize")
    }

    /// Organize is the one primary; "Put all in one collection" is the labelled secondary; Not now is a text button.
    private func actions(skeleton: Bool) -> some View {
        VStack(spacing: Theme.Space.s) {
            Button(tr("organize.organize")) { runAuto() }.buttonStyle(PrimaryButtonStyle()).disabled(skeleton).accessibilityIdentifier("organizeGo")
            Button(tr("organize.put_all_in_one_collection")) { name = SuggestedNames.suggest(groups: groups).first ?? ""; single = true; Task { try? await Task.sleep(for: .milliseconds(300)); nameFocused = true } }
                .buttonStyle(TonalButtonStyle()).disabled(skeleton).accessibilityIdentifier("organizeSingle")
            Button(tr("organize.not_now")) { dismiss() }.buttonStyle(TextButtonStyle(tint: Theme.textSecondary)).accessibilityIdentifier("organizeNotNow")
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s).padding(.bottom, Theme.Space.s).background(Theme.surface)
    }

    private func runAuto() {
        Haptics.play(.send)
        media.startOrganize(mode: .auto, since: request.since, total: organized)
        dismiss()
    }

    // MARK: one collection

    private var singleContent: some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            Text(tr("organize.put_all_title", organized)).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(.top, Theme.Space.xl).accessibilityAddTraits(.isHeader)
            Text(tr("organize.give_it_a_name_you")).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true)
            TextField(tr("organize.collection_name"), text: $name).focused($nameFocused).font(.role(.body)).padding(.horizontal, Theme.Space.l).frame(minHeight: 52)
                .background(Theme.surfaceRaised, in: Capsule())
                .submitLabel(.done).accessibilityIdentifier("collectionName")
            SectionLabel(tr("organize.suggestions")).padding(.top, Theme.Space.xs)
            WrapLayout(spacing: Theme.Space.s) { ForEach(SuggestedNames.suggest(groups: groups), id: \.self) { s in ChoiceChip(title: s, selected: name == s) { name = s; Haptics.play(.selection) } } }
            Spacer()
            HStack(spacing: Theme.Space.m) {
                Button(tr("create.back")) { single = false }.buttonStyle(TextButtonStyle(tint: Theme.textSecondary)).padding(.horizontal, Theme.Space.m)
                Button(tr("organize.create_collection")) { create() }.buttonStyle(PrimaryButtonStyle()).disabled(!SuggestedNames.isValid(name)).accessibilityIdentifier("createCollection")
            }
            .padding(.bottom, Theme.Space.s)
        }
        .padding(.horizontal, Theme.gutter)
    }

    private func create() {
        Haptics.play(.send)
        media.startOrganize(mode: .single, since: request.since, name: name.trimmingCharacters(in: .whitespacesAndNewlines), total: organized)
        dismiss()
    }

    private func message(_ symbol: String, _ title: String, _ text: String, primary: String, _ action: @escaping () -> Void) -> some View {
        VStack(spacing: Theme.Space.m) {
            Spacer()
            Image(systemName: symbol).font(.vmk(40)).foregroundStyle(Theme.primary).accessibilityHidden(true)
            Text(title).textRole(.title).foregroundStyle(Theme.text).multilineTextAlignment(.center)
            Text(text).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
            Button(primary, action: action).buttonStyle(PrimaryButtonStyle()).padding(.top, Theme.Space.s)
            if primary == tr("common.try_again") { Button(tr("organize.not_now")) { dismiss() }.buttonStyle(TextButtonStyle(tint: Theme.textSecondary)) }
            Spacer()
        }
        .padding(.horizontal, Theme.gutter)
    }
}

/// One group of the preview. The name always has the whole row (two lines if it needs them); "Adds to an existing one" sits under it, never beside it.
private struct GroupRow: View {
    let media: MediaModel
    let group: OrganizeGroup
    var body: some View {
        HStack(alignment: .center, spacing: Theme.Space.m) {
            HStack(spacing: -10) {
                ForEach(Array(group.sampleIDs.prefix(3).enumerated()), id: \.offset) { i, id in SampleThumb(media: media, id: id).zIndex(Double(i)) }
            }.frame(width: 70, alignment: .leading).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(group.name).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(3).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                Text(tr("photos.count", group.count)).font(.role(.footnote)).foregroundStyle(Theme.textSecondary)
                if group.existing {
                    Label(tr("organize.adds_to_existing"), systemImage: "plus").font(.role(.caption, weight: .semibold)).foregroundStyle(Theme.primary).fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, Theme.Space.s).padding(.vertical, 3).background(Theme.primaryContainer, in: Capsule()).padding(.top, 2)
                }
            }
            Spacer(minLength: 0)
        }
        .frame(minHeight: 56).padding(.vertical, Theme.Space.xs)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(tr(group.existing ? "organize.group_a11y_existing" : "organize.group_a11y", group.name, tr("photos.count", group.count)))
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
            HStack(spacing: Theme.Space.m) {
                UploadRing(fraction: bar.fraction, symbol: bar.kind == .waiting ? "icloud.slash" : "sparkles", tint: tint(bar))
                VStack(alignment: .leading, spacing: 2) {
                    Text(bar.title).font(.role(.subhead, weight: .semibold).monospacedDigit()).foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.8)
                    Text(bar.subtitle).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).lineLimit(2)
                }
                Spacer(minLength: Theme.Space.xs)
                if bar.kind == .failed { Button(tr("common.try_again")) { media.retryOrganize() }.buttonStyle(TextButtonStyle()).accessibilityIdentifier("organizeRetry") }
                IconButton(symbol: "xmark", label: tr("organize.stop_organizing"), size: Theme.minTouch, identifier: "stopOrganize") { confirmStop = true }
            }
            .padding(.leading, Theme.Space.l).padding(.trailing, Theme.Space.m).padding(.vertical, Theme.Space.s)
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.videoCard, style: .continuous))
            .elevation(3)
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.s)
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
        Image(systemName: "sparkles").font(.role(.caption, weight: .semibold)).foregroundStyle(Theme.onMedia).frame(width: 22, height: 22).background(Theme.mediaInk.opacity(0.5), in: Circle()).accessibilityHidden(true)
    }
}

struct AutoChip: View {
    var body: some View {
        HStack(spacing: 3) { Image(systemName: "sparkles").font(.role(.caption, weight: .regular)); Text(tr("collections.auto")).font(.role(.caption, weight: .bold)) }
            .foregroundStyle(Theme.primary).padding(.horizontal, 8).frame(height: 20).background(Theme.primaryContainer, in: Capsule())
            .accessibilityLabel(tr("organize.automatic_collection"))
    }
}
