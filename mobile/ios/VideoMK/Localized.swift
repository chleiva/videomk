import SwiftUI
import VideoMKCore

/// Markdown text from a catalog string (links inside a sentence, docs/I18N.md rule 2): `md(tr("signin.terms_md"))`.
func md(_ s: String) -> Text { Text((try? AttributedString(markdown: s)) ?? AttributedString(s)) }

/// Attached once at the root: system controls (date pickers, alerts, the keyboard's return key) follow the app language too,
/// and every view rebuilds when the language is changed in Settings.
struct LocalizedRoot: ViewModifier {
    func body(content: Content) -> some View {
        let l = Localization.shared
        content.environment(\.locale, l.locale).id(l.language)
    }
}

/// A sentence with `**emphasised**` words (markdown strong) coloured and bold, the rest in the base colour: `Newest first. **Auto** collections…`
func accentText(_ s: String, accent: Color, base: Color) -> Text {
    var a = (try? AttributedString(markdown: s)) ?? AttributedString(s)
    for run in a.runs {
        let strong = run.inlinePresentationIntent?.contains(.stronglyEmphasized) == true
        a[run.range].foregroundColor = strong ? accent : base
        if strong { a[run.range].inlinePresentationIntent = nil; a[run.range].font = .body.weight(.semibold) }
    }
    return Text(a)
}
