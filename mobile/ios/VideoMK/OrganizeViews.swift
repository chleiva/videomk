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
        guard preview != nil else { return "Organize your photos?" }
        return allExisting ? "Add \(organized.formatted()) new photos to your collections?" : "Organize \(request.fromBatch ? "\(total.formatted()) new" : total.formatted()) photos?"
    }

    var body: some View {
        VStack(spacing: 0) {
            Group {
                switch phase {
                case .loading: content(skeleton: true)
                case .ready: single ? AnyView(singleContent) : AnyView(content(skeleton: false))
                case .failed: message("exclamationmark.triangle", "Couldn't check your photos", "Try again in a moment.", primary: "Try again", { Task { await load() } })
                case .nothing: message("sparkles", "Nothing to organize right now", "Your photos are already in collections, or there aren't at least 5 from the same place and month yet.", primary: "OK", { dismiss() })
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
                    Text(title).font(.system(size: 23, weight: .bold)).foregroundStyle(Theme.text).padding(.top, 22).accessibilityAddTraits(.isHeader)
                    Text("We’ll group them by place and month into collections. Nothing is moved or deleted.").font(.system(size: 14.5)).foregroundStyle(Theme.textSecondary).padding(.top, 6)
                    VStack(spacing: 0) {
                        if skeleton { ForEach(0..<3, id: \.self) { _ in SkeletonRow() } }
                        else { ForEach(showAll ? groups : Array(groups.prefix(5))) { GroupRow(media: media, group: $0) } }
                    }.padding(.top, 14)
                    if !skeleton, groups.count > 5, !showAll {
                        Button { withAnimation(reduceMotion ? nil : .snappy) { showAll = true } } label: { Text("+ \(groups.count - 5) more collections").font(.system(size: 14.5, weight: .semibold)).foregroundStyle(Theme.primary).frame(minHeight: 44, alignment: .leading) }
                            .buttonStyle(.plain).accessibilityLabel("Plus \(groups.count - 5) more collections").accessibilityIdentifier("organizeMore")
                    }
                    if let p = preview, p.skipped > 0, !skeleton {
                        Text("\(p.skipped.formatted()) photos had no clear group and stay as they are.").font(.system(size: 13)).foregroundStyle(Theme.textSecondary).padding(.top, 4).accessibilityIdentifier("organizeSkipped")
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
                Text("Always organize new uploads").font(.system(size: 15.5, weight: .semibold)).foregroundStyle(Theme.text)
                Text("Photos from later uploads join matching collections automatically.").font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
            }
        }
        .tint(Theme.primary).padding(.vertical, 10).accessibilityIdentifier("alwaysOrganize")
    }

    private func actions(skeleton: Bool) -> some View {
        VStack(spacing: 10) {
            Button { runAuto() } label: {
                Text("Organize").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 52).background(Theme.gradient.opacity(skeleton ? 0.4 : 1), in: Capsule())
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
            Text("Put all in one collection").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.primary).frame(maxWidth: .infinity, minHeight: 46).background(Theme.primaryContainer, in: Capsule())
        }.buttonStyle(.plain).disabled(skeleton).accessibilityIdentifier("organizeSingle")
    }

    private var notNow: some View {
        Button { dismiss() } label: { Text("Not now").font(.system(size: 15, weight: .medium)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, minHeight: 46) }
            .buttonStyle(.plain).accessibilityIdentifier("organizeNotNow")
    }

    private func runAuto() {
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        media.startOrganize(mode: .auto, since: request.since, total: organized)
        dismiss()
    }

    // MARK: one collection

    private var singleContent: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("Put all \(organized.formatted()) photos in one collection").font(.system(size: 23, weight: .bold)).foregroundStyle(Theme.text).padding(.top, 22).accessibilityAddTraits(.isHeader)
            Text("Give it a name. You can rename it any time.").font(.system(size: 14.5)).foregroundStyle(Theme.textSecondary).padding(.top, 6)
            TextField("Collection name", text: $name).focused($nameFocused).font(.system(size: 17)).padding(.horizontal, 14).frame(height: 52)
                .background(Theme.surfaceRaised, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).stroke(Theme.primary, lineWidth: nameFocused ? 2 : 0))
                .padding(.top, 16).submitLabel(.done).accessibilityIdentifier("collectionName")
            Text("SUGGESTIONS").font(.system(size: 12.5, weight: .bold)).tracking(0.3).foregroundStyle(Theme.textSecondary).padding(.top, 16)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack { ForEach(SuggestedNames.suggest(groups: groups), id: \.self) { s in FixChip(title: s) { name = s } } }
            }
            Spacer()
            HStack(spacing: 10) {
                Button { single = false } label: { Text("Back").font(.system(size: 15, weight: .medium)).foregroundStyle(Theme.textSecondary).frame(minWidth: 70, minHeight: 50) }.buttonStyle(.plain)
                Button { create() } label: {
                    Text("Create collection").font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 50)
                        .background(Theme.gradient.opacity(SuggestedNames.isValid(name) ? 1 : 0.4), in: Capsule())
                }.buttonStyle(.plain).disabled(!SuggestedNames.isValid(name)).accessibilityIdentifier("createCollection")
            }
            .padding(.bottom, 8)
        }
        .padding(.horizontal, 20)
    }

    private func create() {
        UIImpactFeedbackGenerator(style: .medium).impactOccurred()
        media.startOrganize(mode: .single, since: request.since, name: name.trimmingCharacters(in: .whitespacesAndNewlines), total: organized)
        dismiss()
    }

    private func message(_ symbol: String, _ title: String, _ text: String, primary: String, _ action: @escaping () -> Void) -> some View {
        VStack(spacing: 12) {
            Spacer()
            Image(systemName: symbol).font(.system(size: 40)).foregroundStyle(Theme.primary).accessibilityHidden(true)
            Text(title).font(.system(size: 20, weight: .bold)).foregroundStyle(Theme.text)
            Text(text).font(.system(size: 15)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.center)
            Button(action: action) { Text(primary).font(.system(size: 17, weight: .semibold)).foregroundStyle(Theme.onPrimary).frame(maxWidth: .infinity, minHeight: 52).background(Theme.gradient, in: Capsule()) }.buttonStyle(.plain).padding(.top, 8)
            if primary == "Try again" { Button("Not now") { dismiss() }.foregroundStyle(Theme.textSecondary).frame(minHeight: 44) }
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
                Text(group.name).font(.system(size: 15.5, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(typeSize.isAccessibilitySize ? 3 : 1).minimumScaleFactor(0.8)
                Text("\(group.count.formatted()) photos").font(.system(size: 13)).foregroundStyle(Theme.textSecondary)
                if typeSize.isAccessibilitySize, group.existing { existing }
            }
            Spacer(minLength: 4)
            if group.existing, !typeSize.isAccessibilitySize { existing }
        }
        .frame(minHeight: 56).padding(.vertical, 4)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(group.name). \(group.count.formatted()) photos.\(group.existing ? " Adds to existing collection." : "")")
    }
    private var existing: some View {
        Text("+ Adds to existing").font(.system(size: 12, weight: .bold)).foregroundStyle(Theme.primary).padding(.horizontal, 10).frame(height: 24).background(Theme.primaryContainer, in: Capsule()).lineLimit(1).fixedSize()
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
        RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Theme.surfaceRaised).frame(height: 56).padding(.vertical, 4)
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
                        Image(systemName: bar.kind == .waiting ? "icloud.slash" : "sparkles").font(.system(size: 15, weight: .semibold)).foregroundStyle(tint(bar))
                    }.frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(bar.title).font(.system(size: 15, weight: .bold).monospacedDigit()).foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.8)
                        Text(bar.subtitle).font(.system(size: 13)).foregroundStyle(Theme.textSecondary).lineLimit(2)
                    }
                    Spacer(minLength: 4)
                    if bar.kind == .failed {
                        Button("Try again") { media.retryOrganize() }.font(.system(size: 15, weight: .semibold)).frame(minHeight: 44).accessibilityIdentifier("organizeRetry")
                    }
                    Button { confirmStop = true } label: { Image(systemName: "xmark").font(.system(size: 15, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(width: 44, height: 44) }
                        .buttonStyle(.plain).accessibilityLabel("Stop organizing").accessibilityIdentifier("stopOrganize")
                }
                .padding(.horizontal, 14).padding(.vertical, 2)
                GeometryReader { g in Rectangle().fill(tint(bar)).frame(width: g.size.width * bar.fraction) }.frame(height: 3)
            }
            .background(bar.kind == .failed ? Theme.warningContainer : Theme.surface, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .clipShape(RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(bar.kind == .failed ? Theme.warning : Theme.outline, lineWidth: 1))
            .elevation(3)
            .padding(.horizontal, 12).padding(.bottom, 8)
            .accessibilityElement(children: .contain)
            .accessibilityValue("\(Int(bar.fraction * 100)) percent")
            .accessibilityIdentifier("organizeBar")
            .confirmationDialog("Stop organizing?", isPresented: $confirmStop, titleVisibility: .visible) {
                Button("Keep going", role: .cancel) {}
                Button("Stop", role: .destructive) { media.cancelOrganize() }
            } message: { Text("Collections already made stay as they are.") }
            .transition(.move(edge: .bottom).combined(with: .opacity))
        }
    }
    private func tint(_ bar: OrganizeBarState) -> Color { bar.kind == .failed ? Theme.warning : bar.kind == .waiting ? Theme.textSecondary : Theme.primary }
}

/// Collections made by the organiser carry a small sparkle badge on their cover.
struct AutoBadge: View {
    var body: some View {
        Image(systemName: "sparkles").font(.system(size: 11, weight: .semibold)).foregroundStyle(.white).frame(width: 22, height: 22).background(.black.opacity(0.5), in: Circle()).accessibilityHidden(true)
    }
}

struct AutoChip: View {
    var body: some View {
        HStack(spacing: 3) { Image(systemName: "sparkles").font(.system(size: 10)); Text("Auto").font(.system(size: 12, weight: .bold)) }
            .foregroundStyle(Theme.primary).padding(.horizontal, 8).frame(height: 20).background(Theme.primaryContainer, in: Capsule())
            .accessibilityLabel("Automatic collection")
    }
}
