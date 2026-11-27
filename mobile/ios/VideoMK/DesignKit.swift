import SwiftUI
import VideoMKCore

// The building blocks of the design bar (docs/DESIGN_BAR_2026.md sections 4 and 5), one of each: the primary button, the icon button, the top bar,
// the pill, the suggestion chip, the floating tab bar, the live ring. Screens compose these; they do not draw their own.

/// The VideoMK mark (a play and two stars, white on the action gradient tile; docs/BRAND.md section 2). One asset (`BrandMark`, a vector SVG made by docs/brand/final/build_final.py), never redrawn.
struct BrandMark: View {
    var size: CGFloat = 30
    var body: some View {
        Image("BrandMark").resizable().interpolation(.high).scaledToFit()
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

// MARK: glass (only for things that float over content)

private struct GlassBackground<S: Shape>: ViewModifier {
    let shape: S
    let clear: Bool
    let tint: Color?
    @Environment(\.accessibilityReduceTransparency) private var reduceTransparency

    func body(content: Content) -> some View {
        if reduceTransparency {       // Reduce Transparency: glass becomes an opaque surface
            content.background(clear ? AnyShapeStyle(Theme.mediaInk.opacity(0.9)) : AnyShapeStyle(Theme.surface), in: shape).overlay(shape.stroke(Theme.outline, lineWidth: 0.5))
        } else if #available(iOS 26, *) {
            let glass: Glass = clear ? .clear : .regular
            content.glassEffect(tint.map { glass.tint($0) } ?? glass, in: shape)
        } else {
            content.background(clear ? AnyShapeStyle(.ultraThinMaterial) : AnyShapeStyle(.regularMaterial), in: shape)
                .overlay(shape.stroke(Theme.outline.opacity(0.6), lineWidth: 0.5))
        }
    }
}

extension View {
    /// Liquid Glass on iOS 26 (the clear variant over video and pictures), the system material before, an opaque surface with Reduce Transparency.
    func vmkGlass<S: Shape>(in shape: S, clear: Bool = false, tint: Color? = nil) -> some View { modifier(GlassBackground(shape: shape, clear: clear, tint: tint)) }
}

// MARK: the primary button (one per screen)

/// The ONE primary action of a screen: the action gradient in a full pill, a verb in the headline role, white on it. `fullWidth: false` hugs its label
/// (Share next to the quiet icons). Disabled: the same shape as an opaque `surface3` fill with a `text2` label and no shadow (never see-through).
struct PrimaryButtonStyle: ButtonStyle {
    var fullWidth = true
    var compact = false         // beside other controls (Share next to the quiet icons): less padding, the same height
    var looksDisabled = false   // cannot act yet but still takes the tap (Create shakes its caption): drawn as disabled
    var height: CGFloat?        // Create on the tool row: 48 (52 when it has its own row); the default is `primaryHeight`
    var minWidth: CGFloat?
    var calm = false            // a small shadow instead of the full glow (the compact Create pill)
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        let off = !isEnabled || looksDisabled
        return configuration.label
            .font(.role(.headline)).foregroundStyle(off ? Theme.textSecondary : Theme.onPrimary).multilineTextAlignment(.center)
            .padding(.horizontal, compact ? Theme.Space.l : (minWidth != nil ? Theme.Space.xl : Theme.Space.xxl)).padding(.vertical, minWidth != nil ? Theme.Space.xs : Theme.Space.s)
            .frame(minWidth: minWidth).frame(maxWidth: fullWidth ? .infinity : nil, minHeight: height ?? Theme.primaryHeight)
            .background(off ? AnyShapeStyle(Theme.surface3) : AnyShapeStyle(Theme.gradient), in: Capsule())
            .shadow(color: Theme.gradientStart.opacity(off ? 0 : (calm ? 0.24 : 0.32)), radius: calm ? 6 : 14, y: calm ? 3 : 8)
            .opacity(configuration.isPressed ? 0.88 : 1)
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .animation(Theme.Motion.press, value: configuration.isPressed)
            .contentShape(Capsule())
    }
}

/// A primary button with a title, an optional leading symbol and an optional trailing piece (the price on Create).
struct PrimaryButton<Trailing: View>: View {
    let title: String
    var symbol: String?
    var fullWidth = true
    var identifier = ""
    let action: () -> Void
    @ViewBuilder var trailing: Trailing

    var body: some View {
        Button(action: action) { PrimaryLabel(title: title, symbol: symbol, spread: fullWidth) { trailing } }
            .buttonStyle(PrimaryButtonStyle(fullWidth: fullWidth)).accessibilityIdentifier(identifier)
    }
}

extension PrimaryButton where Trailing == EmptyView {
    init(title: String, symbol: String? = nil, fullWidth: Bool = true, identifier: String = "", action: @escaping () -> Void) {
        self.init(title: title, symbol: symbol, fullWidth: fullWidth, identifier: identifier, action: action) { EmptyView() }
    }
}

/// The inside of a primary button (also the label of a ShareLink in the primary style).
struct PrimaryLabel<Trailing: View>: View {
    let title: String
    var symbol: String?
    var spread = false          // title left, trailing right (Create and its price)
    @ViewBuilder var trailing: Trailing
    var body: some View {
        HStack(spacing: Theme.Space.s) {
            if let symbol { Image(systemName: symbol).font(.role(.headline)).accessibilityHidden(true) }
            Text(title)
            if Trailing.self != EmptyView.self { if spread { Spacer(minLength: Theme.Space.s) }; trailing }
        }
    }
}

extension PrimaryLabel where Trailing == EmptyView {
    init(title: String, symbol: String? = nil) { self.init(title: title, symbol: symbol, spread: false) { EmptyView() } }
}

/// A tonal button (primary container, primary words): the labelled secondary action of a screen, such as "Add photos".
struct TonalButtonStyle: ButtonStyle {
    var fullWidth = true
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.role(.headline)).foregroundStyle(Theme.primary).multilineTextAlignment(.center)
            .padding(.horizontal, Theme.Space.xl).padding(.vertical, Theme.Space.s)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: Theme.primaryHeight - 6)
            .background(Theme.primaryContainer, in: Capsule())
            .opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.45)
            .contentShape(Capsule())
    }
}

/// A text button in the bar ("Select", "Cancel", "Use email"): primary colour, headline weight, a 44 pt target.
struct TextButtonStyle: ButtonStyle {
    var tint: Color = Theme.primary
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.role(.body, weight: .medium)).foregroundStyle(tint).lineLimit(1)
            .frame(minHeight: Theme.minTouch).contentShape(Rectangle())
            .opacity(isEnabled ? (configuration.isPressed ? 0.6 : 1) : 0.4)
    }
}

// MARK: the icon button (secondary actions only, always with a spoken label)

/// An icon-only control: a 44 pt circle with a spoken label the initializer requires and a tooltip on pointer devices.
/// `.quiet` is an opaque fill (on the page); `.glass` floats over content; `.onMedia` is the clear glass over video and pictures.
struct IconButton: View {
    enum Style { case quiet, glass, onMedia }
    let symbol: String
    let label: String
    var style: Style = .quiet
    var size: CGFloat = Theme.iconButton
    var tint: Color?
    var identifier: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) { IconButtonFace(symbol: symbol, style: style, size: size, tint: tint) }
            .buttonStyle(.plain)
            .accessibilityLabel(label)
            .help(label)
            .accessibilityIdentifier(identifier ?? "")
    }
}

/// The face of an icon button, for controls that are not a Button (a Menu, a ShareLink, a PhotosPicker).
struct IconButtonFace: View {
    let symbol: String
    var style: IconButton.Style = .quiet
    var size: CGFloat = Theme.iconButton
    var tint: Color?
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Image(systemName: symbol).font(.role(.headline, weight: .medium)).imageScale(size >= 52 ? .large : .medium).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            .foregroundStyle(tint ?? (style == .onMedia ? Theme.onMedia : Theme.text))
            .frame(width: size, height: size)
            .modifier(IconButtonSurface(style: style))
            .opacity(isEnabled ? 1 : 0.4)
            .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch)
            .contentShape(Circle())
    }
}

private struct IconButtonSurface: ViewModifier {
    let style: IconButton.Style
    func body(content: Content) -> some View {
        switch style {
        case .quiet: content.background(Theme.surfaceRaised, in: Circle())
        case .glass: content.vmkGlass(in: Circle())
        case .onMedia: content.vmkGlass(in: Circle(), clear: true)
        }
    }
}

// MARK: the top bar (one style)

/// The one top bar: an optional leading icon button (back or close), an optional large title (top-level screens), trailing controls. 20 pt gutter.
struct TopBar<Leading: View, Trailing: View>: View {
    var title: String?
    @ViewBuilder var leading: Leading
    @ViewBuilder var trailing: Trailing

    var body: some View {
        HStack(spacing: Theme.Space.s) {
            leading
            if let title {
                Text(title).textRole(.largeTitle).foregroundStyle(Theme.text).lineLimit(1).minimumScaleFactor(0.6).accessibilityAddTraits(.isHeader)
            }
            Spacer(minLength: Theme.Space.s)
            trailing
        }
        .padding(.horizontal, Theme.gutter).frame(minHeight: 56)
        .vmkOneLineCap()          // the bar stays one row; the page below scrolls and wraps
    }
}

extension TopBar where Leading == EmptyView {
    init(title: String?, @ViewBuilder trailing: () -> Trailing) { self.init(title: title, leading: { EmptyView() }, trailing: trailing) }
}
extension TopBar where Trailing == EmptyView {
    init(@ViewBuilder leading: () -> Leading) { self.init(title: nil, leading: leading, trailing: { EmptyView() }) }
}

// MARK: pills and chips

/// The small glyph that leads a pill (the shape of the format, a clock for the length, a sparkle for the look): 16 pt, quiet, never spoken.
struct PillGlyph: View {
    var symbol: String?
    var aspect: String?
    var body: some View {
        Group {
            if let aspect { AspectGlyph(ratio: aspect, line: 1.5, radius: 2.5).frame(width: 14, height: 14) }
            else if let symbol { Image(systemName: symbol).font(.role(.footnote, weight: .semibold)) }
        }
        .foregroundStyle(Theme.textSecondary).frame(width: 16, height: 16).accessibilityHidden(true)
    }
}

/// A choice that is already made: its value and a chevron, nothing else (no key label). Opens a native menu.
struct Pill<MenuContent: View>: View {
    let value: String
    let spoken: String
    var identifier: String = ""
    var glyph: PillGlyph?
    @ViewBuilder var menu: MenuContent

    var body: some View {
        Menu { menu } label: {
            HStack(spacing: 6) {
                if let glyph { glyph }
                Text(value).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1).truncationMode(.tail)
                Image(systemName: "chevron.down").font(.role(.caption, weight: .bold)).foregroundStyle(Theme.textTertiary).accessibilityHidden(true)
            }
            .padding(.leading, glyph == nil ? 14 : 12).padding(.trailing, glyph == nil ? 14 : 12).frame(minHeight: 38)
            .background(Theme.surfaceRaised, in: Capsule())
            .frame(minHeight: Theme.minTouch).contentShape(Capsule())
        }
        .menuOrder(.fixed)          // the menu lists its choices top to bottom in our order, wherever it opens
        .accessibilityLabel(spoken).accessibilityValue(value)
        .accessibilityIdentifier(identifier)
    }
}

/// The same pill for a choice with pictures: it opens a sheet instead of a menu (the Look, the Characters). One line, always: the value is a word,
/// and what does not fit in a word (the chosen faces) is drawn after it as `accessory`. An empty value leaves the accessory alone (the compact pill).
struct PillButton<Accessory: View>: View {
    let value: String
    let spoken: String
    var spokenValue: String?
    var identifier: String = ""
    var glyph: PillGlyph?
    let action: () -> Void
    @ViewBuilder var accessory: Accessory

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                if let glyph { glyph }
                if !value.isEmpty { Text(value).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1) }
                accessory
                Image(systemName: "chevron.down").font(.role(.caption, weight: .bold)).foregroundStyle(Theme.textTertiary).accessibilityHidden(true)
            }
            .padding(.leading, glyph == nil ? 14 : 12).padding(.trailing, glyph == nil ? 14 : 12).frame(minHeight: 38)
            .background(Theme.surfaceRaised, in: Capsule())
            .frame(minHeight: Theme.minTouch).contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spoken).accessibilityValue(spokenValue ?? value).accessibilityAddTraits(.isButton)
        .accessibilityIdentifier(identifier)
    }
}

extension PillButton where Accessory == EmptyView {
    init(value: String, spoken: String, spokenValue: String? = nil, identifier: String = "", glyph: PillGlyph? = nil, action: @escaping () -> Void) {
        self.init(value: value, spoken: spoken, spokenValue: spokenValue, identifier: identifier, glyph: glyph, action: action) { EmptyView() }
    }
}

/// The same pill, not a control: what was chosen, shown while the screen is locked.
struct StaticPill: View {
    let value: String
    var body: some View {
        Text(value).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1)
            .padding(.horizontal, 14).frame(minHeight: 38).background(Theme.surfaceRaised, in: Capsule())
    }
}

/// A suggestion: the sparkle (it marks an AI suggestion) and a few words on an opaque chip.
struct SparkleChip: View {
    let title: String
    var identifier = ""
    var hint: String?
    let action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: "sparkle").font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.primary).accessibilityHidden(true)
                Text(title).font(.role(.subhead, weight: .medium)).foregroundStyle(Theme.text).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 14).padding(.vertical, 6).frame(minHeight: 36)
            .background(Theme.surface, in: Capsule())
            .overlay(Capsule().strokeBorder(Theme.outline, lineWidth: 1))
            .frame(minHeight: Theme.minTouch).contentShape(Capsule())
        }
        .buttonStyle(.plain).accessibilityLabel(title).accessibilityHint(hint ?? "").accessibilityIdentifier(identifier)
    }
}

// MARK: glyphs and the live ring

/// "New video": a play triangle with a sparkle. Never a bare plus.
struct PlaySparkle: View {
    var scale: CGFloat = 1
    var body: some View {
        Image(systemName: "play.fill").font(.role(.title, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.large)
            .overlay(alignment: .topTrailing) { Image(systemName: "sparkle").font(.role(.caption, weight: .bold)).dynamicTypeSize(...DynamicTypeSize.large).offset(x: 9, y: -5) }
            .scaleEffect(scale).offset(x: -1)
            .accessibilityHidden(true)
    }
}

/// The live ring: the accent colours turning around a shape once every 2.4 s. Reduce Motion: a static two-tone border.
struct LiveRing<S: InsettableShape>: View {
    let shape: S
    var lineWidth: CGFloat = 2
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        if reduceMotion {
            shape.strokeBorder(LinearGradient(colors: [Theme.live, Theme.gradientEnd], startPoint: .bottomLeading, endPoint: .topTrailing), lineWidth: lineWidth)
        } else {
            TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                let t = ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: DesignTokens.Motion.ring) / DesignTokens.Motion.ring
                shape.strokeBorder(AngularGradient(colors: Theme.ringColors, center: .center, angle: .degrees(t * 360)), lineWidth: lineWidth)
            }
        }
    }
}

/// The small arc that turns beside "Checking your request". Reduce Motion: it stands still (the words carry the state).
struct LiveSpinner: View {
    var size: CGFloat = 22
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        ZStack {
            Circle().stroke(Theme.surface3, lineWidth: 2.4)
            if reduceMotion { arc } else {
                TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                    arc.rotationEffect(.degrees(ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 1.1) / 1.1 * 360))
                }
            }
        }
        .frame(width: size, height: size).accessibilityHidden(true)
    }
    private var arc: some View { Circle().trim(from: 0, to: 0.28).stroke(Theme.primary, style: StrokeStyle(lineWidth: 2.4, lineCap: .round)) }
}

// MARK: the floating tab bar

/// The bottom bar: two tabs on one glass capsule and the round New video button beside it. Content scrolls under it and fades out (`TabBarFade`).
struct FloatingTabBar: View {
    @Binding var selection: Int
    let onCreate: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var ns

    var body: some View {
        HStack(spacing: Theme.Space.m) {
            HStack(spacing: 4) {
                tab(0, "play.rectangle", tr("tab.videos"), "tabVideos")
                tab(1, "photo.on.rectangle", tr("tab.media"), "tabMedia")
            }
            // the capsule hugs its two tabs (no fixed width: a longer word such as "Biblioteca" at a large text size has the room it needs)
            .padding(.horizontal, 7).frame(height: Theme.fab).vmkGlass(in: Capsule())
            .accessibilityElement(children: .contain).accessibilityAddTraits(.isTabBar).accessibilityIdentifier("tabBar")
            Spacer(minLength: 0)
            Button(action: onCreate) {
                PlaySparkle().foregroundStyle(Theme.onPrimary)
                    .frame(width: Theme.fab, height: Theme.fab).background(Theme.gradient, in: Circle())
                    .shadow(color: Theme.gradientStart.opacity(0.42), radius: 16, y: 10)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(tr("create.new_video")).accessibilityHint(tr("videos.opens_the_screen_where_you")).accessibilityIdentifier("newVideo")
        }
        .padding(.horizontal, Theme.gutter).padding(.top, Theme.Space.s).padding(.bottom, 6)
        .frame(maxWidth: 560)
        .frame(maxWidth: .infinity)
    }

    private func tab(_ index: Int, _ symbol: String, _ title: String, _ id: String) -> some View {
        let selected = selection == index
        return Button {
            guard selection != index else { return }
            withAnimation(reduceMotion ? nil : Theme.Motion.spring) { selection = index }
            Haptics.play(.selection)
        } label: {
            VStack(spacing: 2) {
                Image(systemName: symbol).font(.role(.headline, weight: selected ? .medium : .regular)).imageScale(.large).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                Text(title).font(.role(.caption, weight: .semibold)).lineLimit(1).fixedSize().dynamicTypeSize(...DynamicTypeSize.xxxLarge)
            }
            .foregroundStyle(selected ? Theme.primary : Theme.textSecondary)
            .padding(.horizontal, Theme.Space.m).frame(minWidth: 92, minHeight: 50)
            .background { if selected { Capsule().fill(Theme.primaryContainer).matchedGeometryEffect(id: "tabSel", in: ns) } }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title).accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton).accessibilityIdentifier(id)
    }
}

/// The page fades out under the floating tab bar: a short ramp that is the page colour by the bar's top edge, and stays so behind the bar.
/// It is drawn inside each tab, beneath that tab's own floating bars (never over the whole screen), and is no taller than the bar plus its ramp.
struct TabBarFade: View {
    static let ramp: CGFloat = 28
    var body: some View {
        VStack(spacing: 0) {
            LinearGradient(colors: [Theme.background.opacity(0), Theme.background], startPoint: .top, endPoint: .bottom).frame(height: Self.ramp)
            Theme.background.ignoresSafeArea(edges: .bottom)
        }
        .frame(height: Theme.floatingBarHeight + Self.ramp).allowsHitTesting(false).accessibilityHidden(true)
    }
}

/// The bottom of a tab's root screen: that screen's own floating bars (upload, toast, next step), then the room the floating tab bar takes,
/// with the fade behind it all. Use as the content of `.safeAreaInset(edge: .bottom, spacing: 0)` so the last row always scrolls clear of the bar.
struct TabBarRoom<Bars: View>: View {
    var reserve = true          // false while the tab bar is hidden (selecting): the bars sit at the bottom edge
    @ViewBuilder var bars: Bars
    var body: some View {
        VStack(spacing: 0) {
            bars
            if reserve { Color.clear.frame(height: Theme.floatingBarHeight).allowsHitTesting(false) }
        }
        .frame(maxWidth: .infinity)
        .background(alignment: .bottom) { if reserve { TabBarFade() } }
    }
}

/// The one toast: a dark, opaque bar with one line and at most one action ("Deleted · Undo", "12 photos added · View"). It floats above the tab bar.
struct ToastBar: View {
    let text: String
    var symbol: String? = "checkmark.circle.fill"
    var action: String?
    var identifier = "toast"
    var onAction: () -> Void = {}
    var body: some View {
        HStack(spacing: Theme.Space.m) {
            if let symbol { Image(systemName: symbol).font(.role(.headline)).foregroundStyle(symbol.hasPrefix("checkmark") ? Theme.toastSuccess : Theme.onMedia.opacity(0.8)).accessibilityHidden(true) }
            Text(text).font(.role(.subhead, weight: .medium)).foregroundStyle(Theme.onMedia).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: Theme.Space.xs)
            if let action {
                Button(action: onAction) { Text(action).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.toastAccent).frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch).contentShape(Rectangle()) }
                    .buttonStyle(.plain).accessibilityIdentifier(identifier + "Action")
            }
        }
        .padding(.leading, Theme.Space.l).padding(.trailing, Theme.Space.m).frame(minHeight: 52)
        .background(Theme.toastSurface, in: Capsule())
        .elevation(3)
        .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.s)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(identifier)
    }
}

/// A small (i) that opens a popover with one short explanation: the only place for a sentence of help.
struct InfoPopover: View {
    let text: String
    let spoken: String
    var identifier = "infoPopover"
    @State private var shown = false
    var body: some View {
        Button { shown = true } label: {
            Image(systemName: "info.circle").font(.role(.body)).foregroundStyle(Theme.textSecondary).frame(width: Theme.minTouch, height: Theme.minTouch).contentShape(Rectangle())
        }
        .buttonStyle(.plain).accessibilityLabel(spoken).accessibilityIdentifier(identifier)
        .popover(isPresented: $shown) {
            Text(text).font(.role(.subhead)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(Theme.Space.l).frame(maxWidth: 300)
                .presentationCompactAdaptation(.popover)
        }
    }
}

/// "Deleted · Undo": shown for six seconds wherever the person is (a tab's floating bars, a pushed page, the photo viewer).
struct UndoToastHost: View {
    @Environment(AppModel.self) private var model
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    var body: some View {
        Group {
            if let p = model.undo.current {
                ToastBar(text: p.text, symbol: "trash", action: tr("common.undo"), identifier: "undoToast") { model.undo.undo(); Haptics.play(.selection) }.id(p.id)
            } else if let info = model.infoToast {
                ToastBar(text: info.text, symbol: "checkmark.circle.fill", identifier: "infoToast").id(info.id)
            }
        }
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: model.undo.current?.id)
        .animation(reduceMotion ? Theme.Motion.fade : Theme.Motion.spring, value: model.infoToast?.id)
        .onChange(of: model.infoToast?.id) { _, id in if id != nil, let t = model.infoToast { UIAccessibility.post(notification: .announcement, argument: t.text) } }
        .onChange(of: model.undo.current?.id) { _, id in if id != nil, let p = model.undo.current { UIAccessibility.post(notification: .announcement, argument: tr("undo.announce", p.text)) } }
    }
}

// MARK: sheets (one look)

/// The header of every sheet: its title in the title role and one close button. No system navigation bar.
struct SheetHeader: View {
    let title: String
    var closeLabel: String = tr("common.close")
    var closeID = "sheetClose"
    let onClose: () -> Void
    var body: some View {
        HStack(alignment: .center, spacing: Theme.Space.m) {
            Text(title).textRole(.title).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).accessibilityAddTraits(.isHeader).accessibilityIdentifier("sheetTitle")
            Spacer(minLength: Theme.Space.s)
            IconButton(symbol: "xmark", label: closeLabel, identifier: closeID, action: onClose)
        }
        .padding(.top, Theme.Space.xl)
    }
}

private struct SheetHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

private struct SheetHeaderHeightKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

/// A sheet as tall as what it holds (never half empty), on the opaque surface, with the 20 pt gutter. Past the screen it scrolls.
/// `header` stays pinned: only the body scrolls, so the title and the close button are always there and nothing slides under the grabber.
struct FittedSheet<Header: View, Content: View>: View {
    @ViewBuilder var header: Header
    @ViewBuilder var content: Content
    @State private var height: CGFloat = 360
    @State private var headerHeight: CGFloat = 0

    init(@ViewBuilder header: () -> Header, @ViewBuilder content: () -> Content) { self.header = header(); self.content = content() }

    var body: some View {
        ScrollView {
            content
                .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.l)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(GeometryReader { g in Color.clear.preference(key: SheetHeightKey.self, value: g.size.height) })
        }
        .scrollBounceBehavior(.basedOnSize)
        .safeAreaInset(edge: .top, spacing: 0) {
            header
                .padding(.horizontal, Theme.gutter).frame(maxWidth: .infinity, alignment: .leading).background(Theme.surface)
                .background(GeometryReader { g in Color.clear.preference(key: SheetHeaderHeightKey.self, value: g.size.height) })
        }
        .onPreferenceChange(SheetHeightKey.self) { h in Task { @MainActor in if h > 0, abs(h - height) > 0.5 { height = h } } }
        .onPreferenceChange(SheetHeaderHeightKey.self) { h in Task { @MainActor in if abs(h - headerHeight) > 0.5 { headerHeight = h } } }
        .presentationDetents([.height(height + headerHeight), .large])
        .presentationBackground(Theme.surface).presentationDragIndicator(.visible)
    }
}

extension FittedSheet where Header == EmptyView {
    init(@ViewBuilder content: () -> Content) { self.init(header: { EmptyView() }, content: content) }
}

/// A section label inside a sheet or a list: small, never the tertiary colour (it is essential text).
struct SectionLabel: View {
    let text: String
    init(_ text: String) { self.text = text }
    var body: some View {
        Text(text).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.textSecondary).frame(maxWidth: .infinity, alignment: .leading).accessibilityAddTraits(.isHeader)
    }
}

/// A choice among a few (a platform, an answer, a quality): the one chip shape of the app, a pill. Selected: the primary container and a tick
/// (never colour alone). `dashed` is the "write your own" chip. Long labels wrap and the pill grows with them.
struct ChoiceChip: View {
    let title: String
    var symbol: String?
    var selected = false
    var dashed = false
    var fullWidth = false
    var trailingSymbol: String?
    var spoken: String?
    var identifier = ""
    let action: () -> Void
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: Theme.minTouch / 2, style: .continuous)
        Button(action: action) {
            HStack(spacing: 6) {
                if selected { Image(systemName: "checkmark").font(.role(.footnote, weight: .bold)).accessibilityHidden(true) }
                else if let symbol { Image(systemName: symbol).font(.role(.footnote, weight: .semibold)).accessibilityHidden(true) }
                Text(title).font(.role(.subhead, weight: .semibold)).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
                if let trailingSymbol { Image(systemName: trailingSymbol).font(.role(.footnote)).accessibilityHidden(true) }
            }
            .foregroundStyle(selected ? Theme.primary : dashed ? Theme.textSecondary : Theme.text)
            .padding(.horizontal, Theme.Space.l).padding(.vertical, Theme.Space.s)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: Theme.minTouch, alignment: fullWidth ? .leading : .center)
            .background(selected ? Theme.primaryContainer : dashed ? Color.clear : Theme.surfaceRaised, in: shape)
            .overlay { if dashed { shape.strokeBorder(Theme.outline, style: StrokeStyle(lineWidth: 1.5, dash: [4, 4])) } }
            .opacity(isEnabled ? 1 : 0.5)
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(spoken ?? title).accessibilityAddTraits(selected ? .isSelected : []).accessibilityIdentifier(identifier)
    }
}

// MARK: pull to refresh (the sparkle of the logo, drawn by the pull)

/// The four-point sparkle of the mark, as one outline (so it can be drawn stroke by stroke).
struct SparkleShape: Shape {
    func path(in rect: CGRect) -> Path {
        let c = CGPoint(x: rect.midX, y: rect.midY), r = min(rect.width, rect.height) / 2, k = r * 0.18
        var p = Path()
        p.move(to: CGPoint(x: c.x, y: c.y - r))
        p.addQuadCurve(to: CGPoint(x: c.x + r, y: c.y), control: CGPoint(x: c.x + k, y: c.y - k))
        p.addQuadCurve(to: CGPoint(x: c.x, y: c.y + r), control: CGPoint(x: c.x + k, y: c.y + k))
        p.addQuadCurve(to: CGPoint(x: c.x - r, y: c.y), control: CGPoint(x: c.x - k, y: c.y + k))
        p.addQuadCurve(to: CGPoint(x: c.x, y: c.y - r), control: CGPoint(x: c.x - k, y: c.y - k))
        p.closeSubpath()
        return p
    }
}

private struct PullKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = nextValue() }
}

/// A scroll view whose pull to refresh draws the sparkle: the further the pull, the more of its outline; past the threshold it fills, the list
/// reloads, and it turns until the answer is in. Reduce Motion: the sparkle simply appears and stands still. VoiceOver keeps the system's
/// "refresh" action.
struct SparkleRefreshScroll<Content: View>: View {
    let action: @MainActor () async -> Void
    @ViewBuilder var content: Content
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pull: CGFloat = 0
    @State private var refreshing = false
    @State private var armed = true
    private let threshold: CGFloat = 76

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                GeometryReader { g in Color.clear.preference(key: PullKey.self, value: g.frame(in: .named("sparklePull")).minY) }.frame(height: 0)
                if refreshing { mark(progress: 1, turning: true).frame(maxWidth: .infinity).frame(height: 44).transition(.opacity) }
                content
            }
        }
        .coordinateSpace(name: "sparklePull")
        .overlay(alignment: .top) {
            if !refreshing, pull > 10 { mark(progress: min(1, (pull - 10) / (threshold - 10)), turning: false).frame(height: 44).offset(y: min(pull, threshold) / 2 - 22).allowsHitTesting(false) }
        }
        .onPreferenceChange(PullKey.self) { y in Task { @MainActor in moved(y) } }
        .accessibilityAction(named: tr("a11y.refresh")) { Task { await run() } }
    }

    private func moved(_ y: CGFloat) {
        pull = max(0, y)
        if y < 4 { armed = true }
        if y >= threshold, armed, !refreshing { armed = false; Haptics.play(.selection); Task { await run() } }
    }

    private func run() async {
        guard !refreshing else { return }
        withAnimation(Theme.Motion.spring) { refreshing = true }
        let began = ContinuousClock.now
        await action()
        let spent = ContinuousClock.now - began
        if spent < .milliseconds(700) { try? await Task.sleep(for: .milliseconds(700) - spent) }       // long enough to be seen: nothing flickers
        withAnimation(Theme.Motion.spring) { refreshing = false }
    }

    private func mark(progress: CGFloat, turning: Bool) -> some View {
        ZStack {
            SparkleShape().fill(Theme.primary).opacity(progress >= 1 ? 1 : 0)
            SparkleShape().trim(from: 0, to: reduceMotion ? 1 : progress).stroke(Theme.primary, style: StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
        }
        .frame(width: 26, height: 26)
        .modifier(Turning(on: turning && !reduceMotion))
        .accessibilityHidden(true).accessibilityIdentifier("sparkleRefresh")
    }
}

private struct Turning: ViewModifier {
    let on: Bool
    func body(content: Content) -> some View {
        if on {
            TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                content.rotationEffect(.degrees(ctx.date.timeIntervalSinceReferenceDate.truncatingRemainder(dividingBy: 2.4) / 2.4 * 360))
            }
        } else { content }
    }
}

// MARK: the empty-state scene (our own cartoon, slow parallax)

/// One of our flat-cartoon scenes (docs/VECTOR_CATALOG.md, "mountain cabin"), in its depth layers. The layers drift a little against each other,
/// the nearer the more, and the clouds wander: slow, endless, never the only signal. Reduce Motion: a still picture. Decoration: hidden from VoiceOver.
struct EmptyScene: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private static let depths: [CGFloat] = [0, 0.05, 0.2, 0.4, 0.6, 0.8, 1]

    var body: some View {
        Color.clear.aspectRatio(16.0 / 9.0, contentMode: .fit)
            .overlay {
                if reduceMotion { layers(phase: 0, clouds: 0) }
                else {
                    TimelineView(.animation(minimumInterval: 1 / 30)) { ctx in
                        let t = ctx.date.timeIntervalSinceReferenceDate
                        layers(phase: CGFloat(sin(t * 2 * .pi / 18)), clouds: CGFloat((t / 60).truncatingRemainder(dividingBy: 1)))
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radii.hero, style: .continuous))
            .accessibilityHidden(true).accessibilityIdentifier("emptyScene")
    }

    private func layers(phase: CGFloat, clouds: CGFloat) -> some View {
        GeometryReader { g in
            ZStack {
                ForEach(0..<Self.depths.count, id: \.self) { i in
                    Image("EmptyScene\(i)").resizable().scaledToFill()
                        .frame(width: g.size.width, height: g.size.height)
                        .scaleEffect(1.08)                                                       // room to drift without showing an edge
                        .offset(x: i == 1 ? (clouds - 0.5) * g.size.width * 0.06 : phase * Self.depths[i] * g.size.width * 0.022)
                }
            }
            .frame(width: g.size.width, height: g.size.height).clipped()
        }
    }
}
