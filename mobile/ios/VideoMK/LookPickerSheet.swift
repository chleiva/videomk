import SwiftUI
import VideoMKCore

/// The Look of a video, chosen by its picture (docs/CREATE_API.md, "Video look (chosen and enforced)"): at most four tiles drawn from the server's own
/// previews (Auto, Real, Whiteboard, Cartoon). One tap picks a look and the sheet steps aside. Cartoon keeps it open for the cast: "Auto" and the
/// characters as faces (people, then animals), up to three, and one switch for the hand-drawn board. Nothing here is hard-coded: tiles, words, faces
/// and limits are the server's; what the plan does not include is shown locked, what cannot be made from the attached photos or slides is not shown.
struct LookPickerSheet: View {
    @Bindable var create: CreateModel
    let attached: LookRules.Attached
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var lengthLine: String?         // "Length is now 30 s: a conversation needs 20 s."
    @State private var full = false                // a fourth face was tapped: the line says the limit for a moment
    @State private var closing: Task<Void, Never>?

    private var looks: LookCapabilities? { create.caps.looks }
    private var choice: LookChoice { create.form.lookChoice }
    private var option: LookCapabilities.Option? { looks?.option(choice.look) }
    private var cast: LookCapabilities.Cast? { option?.cast == true ? looks?.cast.flatMap { $0.available && !$0.members.isEmpty ? $0 : nil } : nil }
    private var extras: [LookCapabilities.Extra] { option?.extras.filter(\.available) ?? [] }
    private var spring: Animation { reduceMotion ? Theme.Motion.fade : Theme.Motion.spring }

    var body: some View {
        FittedSheet {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                SheetHeader(title: tr("create.look"), closeLabel: tr("common.done"), closeID: "lookDone") { dismiss() }
                if let looks {
                    tiles(LookRules.tiles(looks, attached: attached))
                    let hidden = LookRules.hidden(looks, attached: attached)
                    if !hidden.isEmpty {
                        quietLine(tr(attached.deck ? "looks.not_with_deck" : "looks.not_with_photos", Localization.shared.list(hidden.map(\.label))), symbol: "photo.on.rectangle", id: "lookHiddenLine")
                    }
                    if let better = betterShapes { quietLine(better, symbol: "aspectratio", id: "lookShapeHint") }
                    if let cast { castSection(cast).transition(.opacity) }
                    if let lengthLine { quietLine(lengthLine, symbol: "clock", id: "lookLengthLine", strong: true).transition(.opacity) }      // right under what caused it
                    ForEach(extras) { extra in extraSwitch(extra) }
                }
            }
        }
        .accessibilityIdentifier("lookSheet")
        .onDisappear { closing?.cancel() }
    }

    // MARK: tiles

    /// Two tiles across; at the largest text sizes one per row, a wide picture over its words, so every word is whole.
    @ViewBuilder private func tiles(_ all: [LookRules.Tile]) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(spacing: Theme.Space.xl) { ForEach(all) { tile($0, wide: true) } }
        } else {
            VStack(spacing: Theme.Space.l) {
                ForEach(Array(stride(from: 0, to: all.count, by: 2)), id: \.self) { i in
                    HStack(alignment: .top, spacing: Theme.Space.m) {
                        tile(all[i], wide: false)
                        if i + 1 < all.count { tile(all[i + 1], wide: false) } else { Color.clear.frame(maxWidth: .infinity, maxHeight: 1) }
                    }
                }
            }
        }
    }

    private func tile(_ t: LookRules.Tile, wide: Bool) -> some View {
        let o = t.option, selected = choice.look == o.id
        let plan = t.locked ? (o.requiresPlan.map { tr("looks.plan", $0) } ?? tr("looks.plan_none")) : nil
        let picture = LookPicture(option: o, selected: selected, locked: t.locked, ratio: wide ? 2.4 : 1.6)
        let words = VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 5) {
                if o.isAuto { Image(systemName: "sparkle").font(.role(.footnote, weight: .bold)).foregroundStyle(Theme.primary).accessibilityHidden(true) }
                Text(o.label).font(.role(.headline)).foregroundStyle(selected ? Theme.primary : Theme.text).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            }
            if let line = plan ?? o.note {
                Text(line).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            }
        }
        return Button { pick(t) } label: {
            VStack(alignment: .leading, spacing: Theme.Space.s) { picture; words.padding(.horizontal, 3) }
                .frame(maxWidth: .infinity, alignment: .topLeading).contentShape(Rectangle())
        }
        .buttonStyle(TilePress())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(o.label).accessibilityValue(plan ?? o.note ?? "")
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier("lookTile-\(o.id)")
        .disabled(t.locked)         // after the spoken element is made, so VoiceOver says "dimmed"
    }

    private func pick(_ t: LookRules.Tile) {
        guard !t.locked else { return }
        closing?.cancel()
        let nudge = withAnimation(spring) { create.pickLook(t.id, attached: attached) }
        Haptics.play(.selection)
        say(nudge)
        // A look with nothing more to choose: the tap was the whole job, the sheet steps aside (after a beat, so the tick is seen). Cartoon stays for its cast.
        let more = t.option.cast && looks?.cast?.available == true || t.option.extras.contains(where: \.available)
        guard !more, nudge == nil, !UIAccessibility.isVoiceOverRunning else { return }
        closing = Task { try? await Task.sleep(for: .milliseconds(320)); if !Task.isCancelled { dismiss() } }
    }

    /// The length was moved for the person: one line says what was done (and VoiceOver hears it).
    private func say(_ nudge: LookRules.LengthNudge?) {
        guard let nudge else { return }
        let line = LookWords.moved(nudge, form: create.form, caps: create.caps)
        withAnimation(spring) { lengthLine = line }
        UIAccessibility.post(notification: .announcement, argument: line)
    }

    private var betterShapes: String? {
        let ids = LookRules.betterAspects(choice, caps: looks, aspect: create.form.aspect)
        guard !ids.isEmpty else { return nil }
        let ours = ["16:9": "aspect.landscape", "9:16": "aspect.vertical", "1:1": "aspect.square", "4:5": "aspect.portrait"]       // the words of the Format tiles
        return tr("looks.best_shape", Localization.shared.list(ids.map { id in (ours[id].map { tr($0) } ?? create.caps.aspect(id)?.label ?? id).lowercased() }))
    }

    // MARK: cast

    private var columns: Int { typeSize.isAccessibilitySize ? 3 : typeSize >= .xLarge ? 4 : 6 }

    /// "Auto" and the characters as faces: people in one group, animals in the next. Up to `max`; two or three talk to each other.
    private func castSection(_ cast: LookCapabilities.Cast) -> some View {
        let groups = cast.groups
        return VStack(alignment: .leading, spacing: Theme.Space.m) {
            SectionLabel(tr("looks.cast"))
            ForEach(Array(groups.enumerated()), id: \.offset) { index, group in
                FaceGrid(columns: columns, count: group.members.count + (index == 0 ? 1 : 0)) { i in
                    if index == 0, i == 0 { autoFace(cast) } else { face(group.members[i - (index == 0 ? 1 : 0)], cast: cast) }
                }
                .accessibilityElement(children: .contain).accessibilityLabel(tr(group.kind == "animal" ? "looks.group_animals" : "looks.group_people"))
            }
            castLine(cast)
        }
        .padding(.top, Theme.Space.xs)
    }

    private func autoFace(_ cast: LookCapabilities.Cast) -> some View {
        let selected = choice.cast.isEmpty
        let name = tr("look.auto")          // the short word of the pill: it fits under a face in every language; VoiceOver hears the server's own
        return Button { withAnimation(spring) { create.form.clearCast() }; full = false; Haptics.play(.selection) } label: {
            FaceCell(name: name, selected: selected) {
                ZStack { Theme.primaryContainer; Image(systemName: "sparkles").font(.role(.headline)).foregroundStyle(Theme.primary) }
            }
        }
        .buttonStyle(TilePress())
        .accessibilityElement(children: .ignore).accessibilityLabel(cast.autoLabel ?? name).accessibilityValue(cast.autoNote ?? "")
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton).accessibilityIdentifier("cast-auto")
    }

    private func face(_ m: LookCapabilities.Member, cast: LookCapabilities.Cast) -> some View {
        let selected = choice.cast.contains(m.id)
        return Button { tap(m, cast: cast) } label: {
            FaceCell(name: m.name, selected: selected) {
                ZStack {
                    Theme.surfaceRaised
                    if let image = InlineImage.image(m.thumbnail) { Image(uiImage: image).resizable().scaledToFill() }
                    else { Image(systemName: m.kind == "animal" ? "pawprint.fill" : "person.fill").font(.role(.headline)).foregroundStyle(Theme.textSecondary) }
                }
            }
        }
        .buttonStyle(TilePress())
        .accessibilityElement(children: .ignore).accessibilityLabel(m.name).accessibilityValue([m.role, m.topic].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton).accessibilityIdentifier("cast-\(m.id)")
    }

    private func tap(_ m: LookCapabilities.Member, cast: LookCapabilities.Cast) {
        let result = withAnimation(spring) { create.form.toggleCast(m.id, caps: create.caps) }
        switch result.tap {
        case .full:
            Haptics.play(.warning)
            withAnimation(spring) { full = true }
            UIAccessibility.post(notification: .announcement, argument: tr("looks.cast_max", cast.max))
        case .added, .removed:
            Haptics.play(.selection); full = false
            say(result.nudge)
        }
    }

    /// One quiet line under the faces: we choose (Auto), who presents (one), that they talk it through (two or three), or the limit.
    private func castLine(_ cast: LookCapabilities.Cast) -> some View {
        let ids = choice.cast
        let text: String? = full ? tr("looks.cast_max", cast.max)
            : ids.isEmpty ? cast.autoNote
            : ids.count >= cast.conversationFrom ? cast.conversationNote
            : cast.member(ids[0]).map { m in [m.name, m.role, m.topic].compactMap { $0 }.joined(separator: " · ") }
        let symbol = full ? "exclamationmark.circle" : ids.isEmpty ? "sparkle" : ids.count >= cast.conversationFrom ? "bubble.left.and.bubble.right" : "person"
        return quietLine(text ?? " ", symbol: symbol, id: "castLine", strong: full)
            .animation(Theme.Motion.select, value: text)
    }

    // MARK: the extra (one switch)

    private func extraSwitch(_ extra: LookCapabilities.Extra) -> some View {
        Toggle(isOn: Binding(get: { choice.extras.contains(extra.id) }, set: { on in create.form.setLookExtra(extra.id, on: on); Haptics.play(.selection) })) {
            Label(extra.label, systemImage: "scribble.variable").font(.role(.body)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
        }
        .tint(Theme.success).frame(minHeight: 52)
        .accessibilityHint(extra.note ?? "").accessibilityIdentifier("extra-\(extra.id)")
    }

    private func quietLine(_ text: String, symbol: String, id: String, strong: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 7) {
            Image(systemName: symbol).font(.role(.footnote, weight: .semibold)).foregroundStyle(strong ? Theme.warning : Theme.primary).frame(minWidth: 18).accessibilityHidden(true)
            Text(text).font(.role(.footnote, weight: strong ? .medium : .regular)).foregroundStyle(strong ? Theme.text : Theme.textSecondary).fixedSize(horizontal: false, vertical: true).accessibilityIdentifier(id)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// The picture of a look: the server's preview cropped to the tile, the ring and the tick when it is chosen, a lock when the plan does not include it.
private struct LookPicture: View {
    let option: LookCapabilities.Option
    let selected: Bool
    let locked: Bool
    var ratio: CGFloat = 1.6
    private let radius = Theme.Radii.card

    var body: some View {
        Color.clear.aspectRatio(ratio, contentMode: .fit)
            .overlay {
                if let image = InlineImage.image(option.preview) { Image(uiImage: image).resizable().scaledToFill() }
                else { ZStack { Theme.makingGradient; Image(systemName: symbol).font(.role(.title, weight: .regular)).foregroundStyle(Theme.onMedia.opacity(0.9)) } }
            }
            .clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .saturation(locked ? 0 : 1).opacity(locked ? 0.45 : 1)
            .overlay(alignment: .topLeading) {
                if locked {
                    Image(systemName: "lock.fill").font(.role(.caption, weight: .bold)).dynamicTypeSize(...DynamicTypeSize.large).foregroundStyle(Theme.onMedia).frame(width: 26, height: 26).background(Theme.mediaInk.opacity(0.72), in: Circle()).padding(Theme.Space.s)
                }
            }
            .overlay(alignment: .topTrailing) {
                if selected {
                    Image(systemName: "checkmark").font(.role(.caption, weight: .bold)).dynamicTypeSize(...DynamicTypeSize.large).foregroundStyle(Theme.onPrimary).frame(width: 26, height: 26).background(Theme.primary, in: Circle())
                        .overlay(Circle().strokeBorder(Theme.surface, lineWidth: 2)).padding(Theme.Space.s).transition(.scale.combined(with: .opacity))
                }
            }
            .padding(4)
            .overlay(RoundedRectangle(cornerRadius: radius + 4, style: .continuous).strokeBorder(Theme.primary, lineWidth: selected ? 2.5 : 0))
            .accessibilityHidden(true)
    }

    private var symbol: String {
        switch option.id { case "auto": "sparkles"; case "real": "photo"; case "whiteboard": "pencil.and.scribble"; case "cartoon": "face.smiling"; default: "play.rectangle" }
    }
}

/// A face and its name: a circle, ringed and ticked when chosen. The name is whole at every text size (it wraps, it is never cut).
private struct FaceCell<Face: View>: View {
    let name: String
    let selected: Bool
    @ViewBuilder var face: Face

    var body: some View {
        VStack(spacing: 5) {
            face.aspectRatio(1, contentMode: .fit).frame(maxWidth: 64).clipShape(Circle())
                .padding(3).overlay(Circle().strokeBorder(Theme.primary, lineWidth: selected ? 2.5 : 0))
                .overlay(alignment: .bottomTrailing) {
                    if selected {
                        Image(systemName: "checkmark").font(.role(.caption, weight: .bold)).dynamicTypeSize(...DynamicTypeSize.large).foregroundStyle(Theme.onPrimary).frame(width: 20, height: 20)
                            .background(Theme.primary, in: Circle()).overlay(Circle().strokeBorder(Theme.surface, lineWidth: 2)).transition(.scale.combined(with: .opacity))
                    }
                }
            Text(name).font(.role(.caption, weight: selected ? .semibold : .regular)).foregroundStyle(selected ? Theme.primary : Theme.text)
                .multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: Theme.minTouch, alignment: .top).contentShape(Rectangle())
    }
}

/// Rows of equal cells (the faces line up under each other from group to group).
private struct FaceGrid<Cell: View>: View {
    let columns: Int
    let count: Int
    @ViewBuilder var cell: (Int) -> Cell

    var body: some View {
        VStack(spacing: Theme.Space.m) {
            ForEach(Array(stride(from: 0, to: count, by: columns)), id: \.self) { start in
                HStack(alignment: .top, spacing: 6) {
                    ForEach(start..<start + columns, id: \.self) { i in
                        if i < count { cell(i) } else { Color.clear.frame(maxWidth: .infinity, maxHeight: 1).accessibilityHidden(true) }
                    }
                }
            }
        }
    }
}

/// A tile or a face under the finger: a touch smaller, no grey flash.
private struct TilePress: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1).opacity(configuration.isPressed ? 0.85 : 1)
            .animation(Theme.Motion.press, value: configuration.isPressed)
    }
}

/// Pictures the server sends inline (the look previews and the faces): decoded once, kept in memory.
@MainActor enum InlineImage {
    private static let cache = NSCache<NSString, UIImage>()
    static func image(_ uri: String?) -> UIImage? {
        guard let uri else { return nil }
        let key = uri as NSString
        if let hit = cache.object(forKey: key) { return hit }
        guard let data = DataURI.data(uri), let image = UIImage(data: data) else { return nil }
        cache.setObject(image, forKey: key)
        return image
    }
}

/// The sentences about a look and the length it needs.
enum LookWords {
    private static func what(_ nudge: LookRules.LengthNudge, _ form: CreateForm, _ caps: CreateCapabilities) -> (name: String?, need: String) {
        (nudge.conversation ? nil : caps.looks?.option(form.lookChoice.look)?.label, LengthLabel.chip(nudge.needSeconds / 60))
    }
    /// "Length is now 30 s: a conversation needs 20 s."
    static func moved(_ nudge: LookRules.LengthNudge, form: CreateForm, caps: CreateCapabilities) -> String {
        let w = what(nudge, form, caps)
        return w.name.map { tr("looks.length_moved_look", LengthLabel.chip(nudge.minutes), $0, w.need) } ?? tr("looks.length_moved_talk", LengthLabel.chip(nudge.minutes), w.need)
    }
    /// "A conversation needs 20 s."
    static func needs(_ nudge: LookRules.LengthNudge, form: CreateForm, caps: CreateCapabilities) -> String {
        let w = what(nudge, form, caps)
        return w.name.map { tr("looks.needs_look", $0, w.need) } ?? tr("looks.needs_talk", w.need)
    }
}
