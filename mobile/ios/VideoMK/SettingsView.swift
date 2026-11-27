import SwiftUI
import VideoMKCore

/// Settings: the account, the language, what photos tell the video, help and legal, and deleting the account. One row style on opaque cards,
/// the app's own header, no system list. Sign out asks nothing (signing in again undoes it); only deleting the account confirms.
struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @State private var showDelete = false
    @State private var showFeedback = false
    @AppStorage(PhotoMetaSettings.datesKey) private var useDates = true
    @AppStorage(PhotoMetaSettings.locationsKey) private var useLocations = true

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: Theme.Space.xl) {
                SheetHeader(title: tr("settings.title"), closeLabel: tr("common.done"), closeID: "settingsDone") { dismiss() }

                SettingsCard {
                    if case .signedIn(let email) = model.phase, let email {
                        // the whole address, on two lines if it needs them (never cut in the middle)
                        SettingsRow(symbol: "person.crop.circle") { Text(email).font(.role(.body)).foregroundStyle(Theme.text).lineLimit(2).fixedSize(horizontal: false, vertical: true) }
                            .accessibilityIdentifier("accountEmail")
                        SettingsDivider()
                    }
                    Button { dismiss(); Task { await model.signOut() } } label: { SettingsRow(symbol: "rectangle.portrait.and.arrow.right") { Text(tr("settings.sign_out")).font(.role(.body)).foregroundStyle(Theme.text) } }
                        .buttonStyle(.plain).accessibilityIdentifier("signOutButton")
                }

                SettingsCard {
                    Menu {
                        Picker(tr("settings.language"), selection: Binding(get: { Localization.shared.choice }, set: { model.setLanguage($0) })) {
                            Text(tr("settings.language_system")).tag(LanguageChoice.system)
                            Text(AppLanguage.en.nativeName).tag(LanguageChoice.en)
                            Text(AppLanguage.es.nativeName).tag(LanguageChoice.es)
                        }
                    } label: {
                        SettingsRow(symbol: "globe", value: languageValue, trailing: "chevron.up.chevron.down") { Text(tr("settings.language")).font(.role(.body)).foregroundStyle(Theme.text) }
                    }
                    .accessibilityIdentifier("languagePicker")
                }

                VStack(alignment: .leading, spacing: Theme.Space.s) {
                    SectionLabel(tr("settings.photos"))
                    SettingsCard {
                        Toggle(isOn: $useDates) { Text(tr("settings.photo_dates")).font(.role(.body)).foregroundStyle(Theme.text) }.tint(Theme.success).padding(.horizontal, Theme.Space.l).frame(minHeight: 52).accessibilityIdentifier("usePhotoDates")
                        SettingsDivider()
                        Toggle(isOn: $useLocations) { Text(tr("settings.photo_locations")).font(.role(.body)).foregroundStyle(Theme.text) }.tint(Theme.success).padding(.horizontal, Theme.Space.l).frame(minHeight: 52).accessibilityIdentifier("usePhotoLocations")
                        if let media = model.media {
                            SettingsDivider()
                            Menu {
                                Picker(tr("settings.organize"), selection: Binding(get: { media.organizePref }, set: { media.setOrganizePref($0) })) {
                                    ForEach(OrganizePref.allCases, id: \.self) { Text($0.title).tag($0) }
                                }
                            } label: {
                                SettingsRow(value: media.organizePref.title, trailing: "chevron.up.chevron.down") { Text(tr("settings.organize")).font(.role(.body)).foregroundStyle(Theme.text) }
                            }
                            .accessibilityIdentifier("organizePref")
                        }
                    }
                    // one sentence, always in view (a popover in a list header was cut off)
                    Text(tr("settings.photos_info")).font(.role(.footnote)).foregroundStyle(Theme.textSecondary).fixedSize(horizontal: false, vertical: true).padding(.horizontal, Theme.Space.xs).accessibilityIdentifier("photosInfo")
                }

                SettingsCard {
                    Button { showFeedback = true } label: { SettingsRow(symbol: "bubble.left", trailing: "chevron.right") { Text(tr("feedback.title")).font(.role(.body)).foregroundStyle(Theme.text) } }
                        .buttonStyle(.plain).accessibilityIdentifier("sendFeedbackRow")
                    SettingsDivider()
                    link(tr("settings.support"), "lifepreserver", "mailto:hello@videomk.com", id: "supportLink")
                    SettingsDivider()
                    link(tr("legal.terms"), "doc.text", tr("legal.terms_url"), id: "termsLink")
                    SettingsDivider()
                    link(tr("legal.privacy"), "hand.raised", tr("legal.privacy_url"), id: "privacyLink")
                    SettingsDivider()
                    SettingsRow(symbol: "info.circle", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "") { Text(tr("settings.about")).font(.role(.body)).foregroundStyle(Theme.text) }
                        .accessibilityElement(children: .combine)
                }

                SettingsCard {
                    Button { showDelete = true } label: { SettingsRow(symbol: "trash", tint: Theme.danger) { Text(tr("settings.delete_account")).font(.role(.body)).foregroundStyle(Theme.danger) } }
                        .buttonStyle(.plain).accessibilityIdentifier("deleteAccountButton")
                }
            }
            .padding(.horizontal, Theme.gutter).padding(.bottom, Theme.Space.xxl)
            .frame(maxWidth: 640).frame(maxWidth: .infinity)
        }
        .presentationBackground(Theme.background).presentationDragIndicator(.visible)
        .sheet(isPresented: $showDelete) { DeleteAccountView() }
        .sheet(isPresented: $showFeedback) { FeedbackSheet(composer: model.makeFeedback(.settings)) }
        #if DEBUG
        .onAppear { if ProcessInfo.processInfo.environment["VMK_DEBUG_SHEET"] == "delete" { showDelete = true }
            if ProcessInfo.processInfo.environment["VMK_DEBUG_SHEET"] == "feedback" { showFeedback = true } }
        #endif
        .task { if model.media?.summary == nil { await model.media?.loadSummary() } }
    }

    private var languageValue: String {
        switch Localization.shared.choice { case .system: tr("settings.language_system"); case .en: AppLanguage.en.nativeName; case .es: AppLanguage.es.nativeName }
    }

    private func link(_ title: String, _ symbol: String, _ url: String, id: String) -> some View {
        Button { if let u = URL(string: url) { openURL(u) } } label: { SettingsRow(symbol: symbol, trailing: "arrow.up.right") { Text(title).font(.role(.body)).foregroundStyle(Theme.text) } }
            .buttonStyle(.plain).accessibilityAddTraits(.isLink).accessibilityIdentifier(id)
    }
}

/// An opaque card that holds rows.
struct SettingsCard<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        VStack(spacing: 0) { content }
            .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.Radii.card, style: .continuous))
    }
}

struct SettingsDivider: View {
    var body: some View { Rectangle().fill(Theme.outline).frame(height: 0.5).padding(.leading, Theme.Space.l) }
}

/// The one row: an optional glyph, the label in the text colour, an optional value and an optional trailing glyph (a chevron for "opens here",
/// an arrow for "opens elsewhere"). At the largest text sizes the value goes under the label.
struct SettingsRow<Label: View>: View {
    var symbol: String?
    var tint: Color = Theme.textSecondary
    var value: String?
    var trailing: String?
    @ViewBuilder var label: Label
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        HStack(spacing: Theme.Space.m) {
            if let symbol { Image(systemName: symbol).font(.role(.body)).foregroundStyle(tint).frame(width: 28).accessibilityHidden(true) }
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 2) { label; if let value { Text(value).font(.role(.subhead)).foregroundStyle(Theme.textSecondary) } }
                Spacer(minLength: Theme.Space.s)
            } else {
                label
                Spacer(minLength: Theme.Space.s)
                if let value { Text(value).font(.role(.subhead)).foregroundStyle(Theme.textSecondary).lineLimit(1) }
            }
            if let trailing { Image(systemName: trailing).font(.role(.footnote, weight: .semibold)).foregroundStyle(Theme.textSecondary).accessibilityHidden(true) }
        }
        .padding(.horizontal, Theme.Space.l).padding(.vertical, Theme.Space.s).frame(minHeight: 52).contentShape(Rectangle())
    }
}
