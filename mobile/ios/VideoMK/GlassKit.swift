import SwiftUI
import VideoMKCore

// The UX 2026 building blocks (docs/UX_2026_REDESIGN.md section 5): the brand mark, glass icon buttons, pills that open menus, the floating tab
// bar with its separate round (+). Glass is iOS 26 only (`glassEffect`); earlier systems get the same shapes in a material.

/// The Sparklet Trio mark on its gradient tile (docs/brand). One asset (`BrandMark`, a vector SVG), never redrawn.
struct BrandMark: View {
    var size: CGFloat = 30
    var body: some View {
        Image("BrandMark").resizable().interpolation(.high).scaledToFit()
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

extension View {
    /// Liquid Glass on iOS 26 (the clear variant over video and pictures), the system material before.
    @ViewBuilder func vmkGlass<S: Shape>(in shape: S, clear: Bool = false, tint: Color? = nil) -> some View {
        if #available(iOS 26, *) {
            let glass: Glass = clear ? .clear : .regular
            self.glassEffect(tint.map { glass.tint($0) } ?? glass, in: shape)
        } else {
            self.background(clear ? AnyShapeStyle(.ultraThinMaterial) : AnyShapeStyle(.regularMaterial), in: shape)
                .overlay(shape.stroke(Theme.outline.opacity(0.6), lineWidth: 0.5))
        }
    }
}

/// An icon-only control: a 44 pt glass circle, a spoken label that the initializer requires, a tooltip on pointer devices.
struct GlassIconButton: View {
    let symbol: String
    let label: String
    var prominent = false          // the one filled gradient control of a screen
    var size: CGFloat = 44
    var clear = false              // over video
    var identifier: String?
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.vmk(18, weight: .semibold)).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                .foregroundStyle(prominent ? Theme.onPrimary : Theme.text)
                .frame(width: size, height: size)
                .background { if prominent { Circle().fill(Theme.gradient) } }
                .modifier(GlassIfNeeded(prominent: prominent, clear: clear))
                .frame(minWidth: Theme.minTouch, minHeight: Theme.minTouch)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .help(label)
        .accessibilityIdentifier(identifier ?? "")
    }
}

private struct GlassIfNeeded: ViewModifier {
    let prominent: Bool
    let clear: Bool
    func body(content: Content) -> some View {
        if prominent { content.shadow(color: Theme.gradientStart.opacity(0.3), radius: 8, y: 3) }
        else { content.vmkGlass(in: Circle(), clear: clear) }
    }
}

/// A short control that opens a native menu: icon, the current value, a chevron. The value is the label (the state is always visible).
struct Pill<MenuContent: View>: View {
    let symbol: String
    let value: String
    let spoken: String
    var identifier: String = ""
    @ViewBuilder var menu: MenuContent

    var body: some View {
        Menu { menu } label: {
            HStack(spacing: 6) {
                Image(systemName: symbol).font(.vmk(14, weight: .semibold)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true)
                Text(value).font(.vmk(15, weight: .semibold)).foregroundStyle(Theme.text).lineLimit(1).truncationMode(.tail)
                Image(systemName: "chevron.down").font(.vmk(11, weight: .bold)).foregroundStyle(Theme.textTertiary).accessibilityHidden(true)
            }
            .padding(.horizontal, 12).frame(minHeight: 38)
            .background(Theme.surfaceRaised, in: Capsule())
            .frame(minHeight: Theme.minTouch).contentShape(Capsule())
        }
        .accessibilityLabel(spoken).accessibilityValue(value)
        .accessibilityIdentifier(identifier)
    }
}

/// The bottom bar: two tabs on one glass capsule and the round (+) beside it. Replaces the floating "New video" pill, so nothing is ever covered.
struct FloatingTabBar: View {
    @Binding var selection: Int
    let onCreate: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Namespace private var ns

    var body: some View {
        HStack(spacing: 12) {
            HStack(spacing: 0) {
                tab(0, "play.rectangle.on.rectangle", tr("tab.videos"), "tabVideos")
                tab(1, "photo.on.rectangle", tr("tab.media"), "tabMedia")
            }
            .padding(5).vmkGlass(in: Capsule())
            Button(action: onCreate) {
                Image(systemName: "plus").font(.vmk(24, weight: .semibold)).foregroundStyle(Theme.onPrimary).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                    .frame(width: 60, height: 60).background(Theme.gradient, in: Circle())
                    .shadow(color: Theme.gradientStart.opacity(0.4), radius: 12, y: 6)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(tr("create.new_video")).accessibilityHint(tr("videos.opens_the_screen_where_you")).accessibilityIdentifier("newVideo")
        }
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 6)
        .frame(maxWidth: 520)
        .frame(maxWidth: .infinity)
    }

    private func tab(_ index: Int, _ symbol: String, _ title: String, _ id: String) -> some View {
        let selected = selection == index
        return Button {
            guard selection != index else { return }
            withAnimation(reduceMotion ? nil : Theme.Motion.select) { selection = index }
            Haptics.play(.selection)
        } label: {
            VStack(spacing: 2) {
                Image(systemName: symbol).font(.vmk(20, weight: .regular)).dynamicTypeSize(...DynamicTypeSize.xxxLarge)
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

/// A small (i) that opens a popover with one short explanation: the only place for a sentence of help.
struct InfoPopover: View {
    let text: String
    let spoken: String
    var identifier = "infoPopover"
    @State private var shown = false
    var body: some View {
        Button { shown = true } label: {
            Image(systemName: "info.circle").font(.vmk(17)).foregroundStyle(Theme.textSecondary).frame(width: Theme.minTouch, height: Theme.minTouch).contentShape(Rectangle())
        }
        .buttonStyle(.plain).accessibilityLabel(spoken).accessibilityIdentifier(identifier)
        .popover(isPresented: $shown) {
            Text(text).font(.vmk(15)).foregroundStyle(Theme.text).fixedSize(horizontal: false, vertical: true).padding(16).frame(maxWidth: 300)
                .presentationCompactAdaptation(.popover)
        }
    }
}
