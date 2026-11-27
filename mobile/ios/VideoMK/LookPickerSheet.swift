import SwiftUI
import VideoMKCore

/// The one-sheet picker (tiles and cast together), kept beside the split one (`LookSheet` and `CharactersSheet`) for comparison.
/// The Look of a video, chosen by its picture (docs/CREATE_API.md, "Video look (chosen and enforced)"): at most four tiles (Auto, Real, Whiteboard,
/// Cartoon), always in the same places. One tap picks a look and the sheet steps aside. Cartoon keeps it open for the cast: ten faces, up to three,
/// one line that says what the choice means, and one switch for the board. Words, faces and limits are the server's. A look the plan does not include,
/// or that is not made from the attached photos or slides, stays in place, dimmed, with its reason; only a look this stage does not have is hidden.
struct LookPickerSheet: View {
    @Bindable var create: CreateModel
    let attached: LookRules.Attached
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var lengthLine: String?         // "Length changed to 30 s. A conversation needs 20 s or more.": takes the cast line's place for this visit
    @State private var closing: Task<Void, Never>?
    @State private var scrollTarget: String?

    private var looks: LookCapabilities? { create.caps.looks }
    private var choice: LookChoice { create.form.lookChoice }
    private var option: LookCapabilities.Option? { looks?.option(choice.look) }
    private var cast: LookCapabilities.Cast? { option?.cast == true ? looks?.cast.flatMap { $0.available && !$0.members.isEmpty ? $0 : nil } : nil }
    private var extras: [LookCapabilities.Extra] { option?.extras.filter(\.available) ?? [] }
    private var spring: Animation { reduceMotion ? Theme.Motion.fade : Theme.Motion.spring }

    var body: some View {
        FittedSheet(scrollTo: scrollTarget) {
            SheetHeader(title: tr("create.look"), closeLabel: tr("common.done"), closeID: "lookDone") { dismiss() }.padding(.bottom, Theme.Space.m)
        } content: {
            VStack(alignment: .leading, spacing: Theme.Space.l) {
                if let looks {
                    LookTiles(tiles: LookRules.tiles(looks, attached: attached), selected: choice.look, pick: pick)
                    if cast != nil || !extras.isEmpty {
                        CastPicker(create: create, cast: cast, extras: extras, lengthLine: $lengthLine).id("cast").transition(.opacity)
                    }
                }
            }
            .padding(.top, Theme.Space.xs)          // room for the ring of a chosen tile in the first row
        }
        .onDisappear { closing?.cancel() }
    }

    private func pick(_ t: LookRules.Tile) {
        guard !t.locked else { return }
        closing?.cancel(); scrollTarget = nil
        let nudge = withAnimation(spring) { create.pickLook(t.id, attached: attached) }
        Haptics.play(.selection)
        if let nudge {          // the length was moved for the person: the line says what was done (and VoiceOver hears it)
            let line = LookWords.moved(nudge, form: create.form, caps: create.caps)
            withAnimation(spring) { lengthLine = line }
            UIAccessibility.post(notification: .announcement, argument: line)
        }
        // A look with nothing more to choose: the tap was the whole job, the sheet steps aside (after a beat, so the ring is seen). Cartoon stays for its cast.
        let more = t.option.cast && looks?.cast?.available == true || t.option.extras.contains(where: \.available)
        if more { Task { try? await Task.sleep(for: .milliseconds(250)); scrollTarget = "cast" }; return }      // where the sheet scrolls, the cast comes to the top
        guard nudge == nil, !UIAccessibility.isVoiceOverRunning else { return }
        closing = Task { try? await Task.sleep(for: .milliseconds(320)); if !Task.isCancelled { dismiss() } }
    }
}

/// The Look sheet: the four tiles and nothing else, always the same height. One tap chooses and the sheet steps aside, for every look.
/// A look with characters shows its Characters pill on Create (`CharactersSheet`).
struct LookSheet: View {
    @Bindable var create: CreateModel
    let attached: LookRules.Attached
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var closing: Task<Void, Never>?

    var body: some View {
        FittedSheet {
            SheetHeader(title: tr("create.look"), closeLabel: tr("common.done"), closeID: "lookDone") { dismiss() }.padding(.bottom, Theme.Space.m)
        } content: {
            if let looks = create.caps.looks {
                LookTiles(tiles: LookRules.tiles(looks, attached: attached), selected: create.form.lookChoice.look, pick: pick)
                    .padding(.top, Theme.Space.xs)          // room for the ring of a chosen tile in the first row
            }
        }
        .onDisappear { closing?.cancel() }
    }

    private func pick(_ t: LookRules.Tile) {
        guard !t.locked else { return }
        closing?.cancel()
        let nudge = withAnimation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring) { create.pickLook(t.id, attached: attached) }
        Haptics.play(.selection)
        // the look needs a longer video: the length was moved, and Create says so right above the pills
        if let nudge { create.sayAboutLook(LookWords.moved(nudge, form: create.form, caps: create.caps)) }
        guard !UIAccessibility.isVoiceOverRunning else { return }          // VoiceOver hears "selected" first and closes the sheet itself
        closing = Task { try? await Task.sleep(for: .milliseconds(320)); if !Task.isCancelled { dismiss() } }      // after a beat, so the ring is seen
    }
}

/// The Characters sheet of a look that has them: the faces, the one line, the board switch. It stays until it is closed.
struct CharactersSheet: View {
    @Bindable var create: CreateModel
    @Environment(\.dismiss) private var dismiss
    @State private var lengthLine: String?

    var body: some View {
        let looks = create.caps.looks, option = looks?.option(create.form.lookChoice.look)
        FittedSheet {
            SheetHeader(title: tr("looks.cast"), closeLabel: tr("common.done"), closeID: "castDone") { dismiss() }.padding(.bottom, Theme.Space.m)
        } content: {
            CastPicker(create: create, cast: option?.cast == true ? looks?.cast.flatMap { $0.available && !$0.members.isEmpty ? $0 : nil } : nil,
                       extras: option?.extras.filter(\.available) ?? [], lengthLine: $lengthLine, showsLabel: false)
        }
    }
}

// MARK: tiles

/// The looks as pictures, two across. At the largest text sizes they are rows (a small picture, the name beside it), so all four fit one screen.
struct LookTiles: View {
    let tiles: [LookRules.Tile]
    let selected: String
    let pick: (LookRules.Tile) -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        if typeSize.isAccessibilitySize {
            VStack(spacing: Theme.Space.m) { ForEach(tiles) { tile($0, row: true) } }
        } else {
            VStack(spacing: Theme.Space.l) {
                ForEach(Array(stride(from: 0, to: tiles.count, by: 2)), id: \.self) { i in
                    HStack(alignment: .top, spacing: Theme.Space.m) {
                        tile(tiles[i], row: false)
                        if i + 1 < tiles.count { tile(tiles[i + 1], row: false) } else { Color.clear.frame(maxWidth: .infinity, maxHeight: 1) }
                    }
                }
            }
        }
    }

    private func reason(_ t: LookRules.Tile) -> String? {
        switch t.blocked {
        case .plan: t.option.requiresPlan.map { tr("looks.plan", $0) } ?? tr("looks.plan_none")
        case .photos: tr("looks.no_photos")
        case .deck: tr("looks.no_deck")
        case nil: nil
        }
    }

    /// The server's note as one line without its full stop (an older server still sends sentences).
    private func note(_ o: LookCapabilities.Option) -> String? { o.note.map { $0.hasSuffix(".") ? String($0.dropLast()) : $0 } }

    @ViewBuilder private func tile(_ t: LookRules.Tile, row: Bool) -> some View {
        let o = t.option, chosen = selected == o.id, why = reason(t)
        let words = VStack(alignment: .leading, spacing: 2) {
            Text(o.label).font(.role(.headline)).foregroundStyle(Theme.text).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            if let why {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    if t.blocked == .plan { Image(systemName: "lock.fill").font(.vmk(11)).accessibilityHidden(true) }
                    Text(why).font(.role(.footnote)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(Theme.text)          // the whole tile is at 40 percent: the reason starts from the text colour so it stays readable
            } else if !row, let line = note(o) {
                Text(line).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).lineLimit(1)
            }
        }
        let face = Group {
            if row { HStack(alignment: .center, spacing: Theme.Space.m) { LookPicture(option: o, selected: chosen, row: true); words } }
            else { VStack(alignment: .leading, spacing: Theme.Space.s) { LookPicture(option: o, selected: chosen, row: false); words } }
        }
        .frame(maxWidth: .infinity, alignment: .topLeading).contentShape(Rectangle())
        if t.locked {
            // "You cannot have this" has one look: in place, dimmed, with the reason where the note was. A tap answers softly and changes nothing.
            face.opacity(0.4)
                .accessibilityElement(children: .ignore).accessibilityLabel(o.label).accessibilityValue(why ?? "").accessibilityAddTraits(.isButton)
                .accessibilityIdentifier("lookTile-\(o.id)")
                .disabled(true)          // after the spoken element is made, so VoiceOver says "dimmed"
                .onTapGesture { Haptics.play(.selection) }
        } else {
            Button { pick(t) } label: { face }
                .buttonStyle(TilePress())
                .accessibilityElement(children: .ignore).accessibilityLabel(o.label).accessibilityValue(note(o) ?? "")
                .accessibilityAddTraits(chosen ? [.isButton, .isSelected] : .isButton)
                .accessibilityIdentifier("lookTile-\(o.id)")
        }
    }
}

/// The picture of a look, on the gutter: the server's preview cropped to the tile with a hairline edge (a white picture still has one on a white sheet).
/// Auto has no photograph: it is the sparkle of "we choose", as everywhere else. Chosen: a ring around it, outside the picture, and nothing else.
private struct LookPicture: View {
    let option: LookCapabilities.Option
    let selected: Bool
    let row: Bool
    private var radius: CGFloat { row ? Theme.Radii.thumb : Theme.Radii.card }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        Color.clear
            .frame(width: row ? 96 : nil, height: row ? 60 : nil).aspectRatio(row ? nil : 1.6, contentMode: .fit)
            .overlay {
                if option.isAuto { ZStack { Theme.primaryContainer; Image(systemName: "sparkles").font(.role(row ? .headline : .title, weight: .regular)).dynamicTypeSize(...DynamicTypeSize.xxxLarge).foregroundStyle(Theme.primary) } }
                else if let image = InlineImage.image(option.preview) { Image(uiImage: image).resizable().scaledToFill() }
                else { ZStack { Theme.makingGradient; Image(systemName: symbol).font(.role(row ? .headline : .title, weight: .regular)).dynamicTypeSize(...DynamicTypeSize.xxxLarge).foregroundStyle(Theme.onMedia.opacity(0.9)) } }
            }
            .clipShape(shape)
            .overlay(shape.strokeBorder(Theme.text.opacity(0.08), lineWidth: 1))
            .overlay(RoundedRectangle(cornerRadius: radius + 4, style: .continuous).strokeBorder(Theme.primary, lineWidth: selected ? 2.5 : 0).padding(-4))
            .accessibilityHidden(true)
    }

    private var symbol: String {
        switch option.id { case "real": "photo"; case "whiteboard": "pencil.and.scribble"; case "cartoon": "face.smiling"; default: "play.rectangle" }
    }
}

// MARK: cast

/// The characters of a look that has them: ten faces five across (people, then animals), up to `max`; none chosen means we choose. One line under them
/// says what the choice means, and one switch per extra the look allows (the board).
struct CastPicker: View {
    @Bindable var create: CreateModel
    let cast: LookCapabilities.Cast?
    let extras: [LookCapabilities.Extra]
    @Binding var lengthLine: String?
    var showsLabel = true
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var choice: LookChoice { create.form.lookChoice }
    private var spring: Animation { reduceMotion ? Theme.Motion.fade : Theme.Motion.spring }
    private var columns: Int { typeSize.isAccessibilitySize ? 3 : typeSize >= .xLarge ? 4 : 5 }
    private var gap: CGFloat { typeSize.isAccessibilitySize ? Theme.Space.m : Theme.Space.s }

    var body: some View {
        VStack(alignment: .leading, spacing: Theme.Space.m) {
            if let cast {
                if showsLabel { SectionLabel(tr("looks.cast")) }
                let members = cast.groups.flatMap(\.members), full = LookRules.castIsFull(choice, caps: create.caps.looks)
                FaceGrid(columns: columns, gap: gap, count: members.count) { i in face(members[i], inert: full && !choice.cast.contains(members[i].id)) }
                let line = lengthLine ?? LookRules.castLine(choice, caps: create.caps.looks)
                Text(line).font(.role(.footnote)).foregroundStyle(lengthLine == nil ? Theme.textSecondary : Theme.text)
                    .fixedSize(horizontal: false, vertical: true).frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier("castLine").animation(Theme.Motion.select, value: line)
            }
            ForEach(extras) { extra in
                Toggle(isOn: Binding(get: { choice.extras.contains(extra.id) }, set: { on in create.form.setLookExtra(extra.id, on: on); Haptics.play(.selection) })) {
                    Text(extra.label).font(.role(.body)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true)
                }
                .tint(Theme.primary).frame(minHeight: 52)
                .accessibilityHint(extra.note ?? "").accessibilityIdentifier("extra-\(extra.id)")
            }
        }
    }

    private func face(_ m: LookCapabilities.Member, inert: Bool) -> some View {
        let selected = choice.cast.contains(m.id)
        return Button { tap(m) } label: { FaceCell(name: m.name, selected: selected) { CastFace(member: m) } }
            .buttonStyle(TilePress())
            .opacity(inert ? 0.4 : 1)
            .accessibilityElement(children: .ignore).accessibilityLabel(m.name).accessibilityValue([m.role, m.topic].compactMap { $0 }.joined(separator: ", "))
            .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton).accessibilityIdentifier("cast-\(m.id)")
            .disabled(inert)         // the limit is reached: the others wait, dimmed, until one is let go
    }

    private func tap(_ m: LookCapabilities.Member) {
        let result = withAnimation(spring) { create.form.toggleCast(m.id, caps: create.caps) }
        guard result.tap != .full else { return }
        Haptics.play(.selection)
        if let nudge = result.nudge {          // a conversation needs a longer video: the length was moved, the line says so (and VoiceOver hears it)
            let line = LookWords.moved(nudge, form: create.form, caps: create.caps)
            withAnimation(spring) { lengthLine = line }
            UIAccessibility.post(notification: .announcement, argument: line)
        }
    }
}

/// The face of a character: the server's drawing, or a plain mark when it sent none.
struct CastFace: View {
    let member: LookCapabilities.Member
    var body: some View {
        ZStack {
            Theme.surfaceRaised
            if let image = InlineImage.image(member.thumbnail) { Image(uiImage: image).resizable().scaledToFill() }
            else { Image(systemName: member.kind == "animal" ? "pawprint.fill" : "person.fill").font(.role(.headline)).foregroundStyle(Theme.textSecondary) }
        }
    }
}

/// A face and its name. Chosen: a ring drawn on the edge of the face itself, so no face is ever larger or smaller than its neighbours and the first
/// one sits on the gutter. The name is whole at every text size (it wraps, it is never cut) and never changes colour or weight.
private struct FaceCell<Face: View>: View {
    let name: String
    let selected: Bool
    @ViewBuilder var face: Face

    var body: some View {
        VStack(spacing: 5) {
            face.aspectRatio(1, contentMode: .fit).clipShape(Circle())
                .overlay { if selected { ZStack { Circle().strokeBorder(Theme.surface, lineWidth: 4.5); Circle().strokeBorder(Theme.primary, lineWidth: 2.5) } } }
            Text(name).font(.role(.caption, weight: .regular)).foregroundStyle(Theme.text).multilineTextAlignment(.center).fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, minHeight: Theme.minTouch, alignment: .top).contentShape(Rectangle())
    }
}

/// Rows of equal cells, edge to edge.
private struct FaceGrid<Cell: View>: View {
    let columns: Int
    let gap: CGFloat
    let count: Int
    @ViewBuilder var cell: (Int) -> Cell

    var body: some View {
        VStack(spacing: Theme.Space.m) {
            ForEach(Array(stride(from: 0, to: count, by: columns)), id: \.self) { start in
                HStack(alignment: .top, spacing: gap) {
                    ForEach(start..<start + columns, id: \.self) { i in
                        if i < count { cell(i) } else { Color.clear.frame(maxWidth: .infinity, maxHeight: 1).accessibilityHidden(true) }
                    }
                }
            }
        }
    }
}

/// The chosen characters in a pill: up to three small faces that overlap, in the order they were chosen.
struct PillFaces: View {
    let members: [LookCapabilities.Member]
    var body: some View {
        HStack(spacing: -6) {
            ForEach(members.prefix(3)) { m in
                CastFace(member: m).frame(width: 20, height: 20).clipShape(Circle()).overlay(Circle().strokeBorder(Theme.surfaceRaised, lineWidth: 1.5))
            }
        }
        .accessibilityHidden(true)
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
    /// "Length changed to 30 s. A conversation needs 20 s or more."
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
