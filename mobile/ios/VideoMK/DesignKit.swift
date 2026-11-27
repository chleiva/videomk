import SwiftUI
import VideoMKCore

// The building blocks of the design bar (docs/DESIGN_BAR_2026.md sections 4 and 5), one of each: the primary button, the icon button, the top bar,
// the pill, the suggestion chip, the floating tab bar, the live ring. Screens compose these; they do not draw their own.

/// The Sparklet Trio mark on its gradient tile (docs/brand). One asset (`BrandMark`, a vector SVG), never redrawn.
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
/// (Share next to the quiet icons). Disabled: the same shape at 45%.
struct PrimaryButtonStyle: ButtonStyle {
    var fullWidth = true
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.role(.headline)).foregroundStyle(Theme.onPrimary).multilineTextAlignment(.center)
            .padding(.horizontal, Theme.Space.xxl).padding(.vertical, Theme.Space.s)
            .frame(maxWidth: fullWidth ? .infinity : nil, minHeight: Theme.primaryHeight)
            .background(Theme.gradient, in: Capsule())
            .shadow(color: Theme.gradientStart.opacity(isEnabled ? 0.32 : 0), radius: 14, y: 8)
            .opacity(isEnabled ? (configuration.isPressed ? 0.88 : 1) : 0.45)
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
        Image(systemName: symbol).font(.vmk(size >= 52 ? 20 : 18, weight: .medium)).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
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

/// A choice that is already made: its value and a chevron, nothing else (no key label). Opens a native menu.
struct Pill<MenuContent: View>: View {
    let value: String
    let spoken: String
    var identifier: String = ""
    @ViewBuilder var menu: MenuContent

    var body: some View {
        Menu { menu } label: {
            HStack(spacing: 6) {
                Text(value).font(.role(.subhead, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1).truncationMode(.tail)
                Image(systemName: "chevron.down").font(.role(.caption, weight: .bold)).foregroundStyle(Theme.textTertiary).accessibilityHidden(true)
            }
            .padding(.horizontal, 14).frame(minHeight: 38)
            .background(Theme.surfaceRaised, in: Capsule())
            .frame(minHeight: Theme.minTouch).contentShape(Capsule())
        }
        .accessibilityLabel(spoken).accessibilityValue(value)
        .accessibilityIdentifier(identifier)
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
        Image(systemName: "play.fill").font(.vmk(22, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.large)
            .overlay(alignment: .topTrailing) { Image(systemName: "sparkle").font(.vmk(11, weight: .bold)).dynamicTypeSize(...DynamicTypeSize.large).offset(x: 9, y: -5) }
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
            .padding(.horizontal, 7).frame(height: Theme.fab).vmkGlass(in: Capsule())
            .frame(maxWidth: 230)
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
                Image(systemName: symbol).font(.vmk(20, weight: selected ? .medium : .regular)).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                Text(title).font(.vmk(11, weight: .semibold)).lineLimit(1).minimumScaleFactor(0.8).vmkOneLineCap()
            }
            .foregroundStyle(selected ? Theme.primary : Theme.textSecondary)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background { if selected { Capsule().fill(Theme.primaryContainer).matchedGeometryEffect(id: "tabSel", in: ns) } }
            .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title).accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton).accessibilityIdentifier(id)
    }
}

/// The page fades out under the floating tab bar, so nothing is cut off behind it.
struct TabBarFade: View {
    var body: some View {
        LinearGradient(stops: [.init(color: Theme.background.opacity(0), location: 0), .init(color: Theme.background.opacity(0.9), location: 0.55), .init(color: Theme.background, location: 1)], startPoint: .top, endPoint: .bottom)
            .frame(height: 150).allowsHitTesting(false).accessibilityHidden(true)
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
