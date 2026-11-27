import SwiftUI
import VideoMKCore

/// The type scale: every size in the app is a text style (so it follows Dynamic Type) chosen from the spec's table
/// (largeTitle 34, title 28, title2 22, title3 20, headline 17 semibold, body 17, callout 16, subheadline 15, footnote 13, caption 12, caption2 11).
/// `Font.vmk(15, weight: .semibold)` keeps call sites readable while the scale lives here. Sizes of 40 and up are decorative (icons, the hero
/// number) and stay fixed. Never use `.font(.system(size:))` in a view: `scripts/check_fonts.py` fails on it.
extension Font {
    static func vmk(_ size: CGFloat, weight: Font.Weight = .regular, design: Font.Design = .default) -> Font {
        guard let style = vmkStyle(for: size) else { return .system(size: size, weight: weight, design: design) }
        return .system(style, design: design, weight: weight)
    }

    static func vmkStyle(for size: CGFloat) -> Font.TextStyle? {
        switch size {
        case ..<11.6: .caption2
        case ..<12.6: .caption
        case ..<14.0: .footnote
        case ..<15.6: .subheadline
        case ..<16.6: .callout
        case ..<17.6: .body
        case ..<21: .title3
        case ..<24: .title2
        case ..<31: .title
        case ..<40: .largeTitle
        default: nil
        }
    }
}

extension Font {
    /// A type role of the design bar (section 4): the platform text style with the role's weight. This is what screens use; a screen never names a size.
    static func role(_ r: DesignTokens.TypeRole, weight: Font.Weight? = nil, design: Font.Design = .default) -> Font {
        let style: Font.TextStyle = switch r {
        case .largeTitle: .largeTitle
        case .prompt: .title
        case .title: .title2
        case .headline: .headline
        case .body: .body
        case .subhead: .subheadline
        case .footnote: .footnote
        case .caption: .caption
        }
        let w: Font.Weight = weight ?? { switch r.weight { case .bold: .bold; case .semibold: .semibold; case .medium: .medium; case .regular: .regular } }()
        return .system(style, design: design, weight: w)
    }
}

extension View {
    /// Text in a role, with the role's tracking (large titles are set tight).
    func textRole(_ r: DesignTokens.TypeRole, weight: Font.Weight? = nil) -> some View { font(.role(r, weight: weight)).tracking(CGFloat(r.tracking)) }

    /// The ceiling for text that must stay on one line or sits in a fixed-size control (tab labels, chips, the composer bar).
    func vmkOneLineCap() -> some View { dynamicTypeSize(...DynamicTypeSize.accessibility1) }
}

extension DynamicTypeSize {
    /// The largest size the app lays out (accessibility extra large, AX3); beyond it everything still scrolls but is not designed for.
    static let appMax: DynamicTypeSize = .accessibility3
}
