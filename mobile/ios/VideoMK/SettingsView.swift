import SwiftUI
import VideoMKCore

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmSignOut = false
    @State private var showDelete = false
    @State private var showFeedback = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @AppStorage(PhotoMetaSettings.datesKey) private var useDates = true
    @AppStorage(PhotoMetaSettings.locationsKey) private var useLocations = true

    var body: some View {
        NavigationStack {
            List {
                Section {
                    if case .signedIn(let email) = model.phase, let email {
                        Label { Text(email).font(.vmk(17)).foregroundStyle(Theme.text).lineLimit(1).truncationMode(.middle) } icon: { Image(systemName: "person.crop.circle").foregroundStyle(Theme.textSecondary) }
                            .frame(minHeight: Theme.minTouch).accessibilityIdentifier("accountEmail")
                    }
                    Button(tr("settings.sign_out")) { confirmSignOut = true }.foregroundStyle(Theme.primary).frame(minHeight: Theme.minTouch).accessibilityIdentifier("signOutButton")      // not destructive: primary colour, not red
                }
                Section {
                    Picker(tr("settings.language"), selection: Binding(get: { Localization.shared.choice }, set: { model.setLanguage($0) })) {
                        Text(tr("settings.language_system")).tag(LanguageChoice.system)
                        Text(AppLanguage.en.nativeName).tag(LanguageChoice.en)
                        Text(AppLanguage.es.nativeName).tag(LanguageChoice.es)
                    }
                    .frame(minHeight: Theme.minTouch).accessibilityIdentifier("languagePicker")
                }
                Section {
                    Toggle(tr("settings.photo_dates"), isOn: $useDates).frame(minHeight: Theme.minTouch).accessibilityIdentifier("usePhotoDates")
                    Toggle(tr("settings.photo_locations"), isOn: $useLocations).frame(minHeight: Theme.minTouch).accessibilityIdentifier("usePhotoLocations")
                    if let media = model.media {
                        Picker(tr("settings.organize"), selection: Binding(get: { media.organizePref }, set: { media.setOrganizePref($0) })) {
                            ForEach(OrganizePref.allCases, id: \.self) { Text($0.title).tag($0) }
                        }
                        .frame(minHeight: Theme.minTouch).accessibilityIdentifier("organizePref")
                    }
                } header: {
                    HStack(spacing: 0) { Text(tr("settings.photos")); InfoPopover(text: tr("settings.photos_info"), spoken: tr("settings.photos"), identifier: "photosInfo").offset(y: -2) }
                }
                Section {
                    Button { showFeedback = true } label: {
                        HStack { Label(tr("feedback.title"), systemImage: "bubble.left").foregroundStyle(Theme.text); Spacer(minLength: 4); Image(systemName: "chevron.right").font(.vmk(13, weight: .semibold)).foregroundStyle(Theme.textTertiary).accessibilityHidden(true) }
                            .frame(minHeight: Theme.minTouch).contentShape(Rectangle())
                    }
                    .accessibilityIdentifier("sendFeedbackRow")
                    Link(destination: URL(string: "mailto:hello@videomk.com")!) {
                        HStack { Label(tr("settings.support"), systemImage: "lifepreserver").foregroundStyle(Theme.text); Spacer(minLength: 4); Image(systemName: "arrow.up.right").font(.vmk(13, weight: .semibold)).foregroundStyle(Theme.textTertiary).accessibilityHidden(true) }.frame(minHeight: Theme.minTouch)
                    }
                    .accessibilityIdentifier("supportLink")
                    Link(tr("legal.terms"), destination: URL(string: tr("legal.terms_url"))!).frame(minHeight: Theme.minTouch).accessibilityIdentifier("termsLink")
                    Link(tr("legal.privacy"), destination: URL(string: tr("legal.privacy_url"))!).frame(minHeight: Theme.minTouch)
                    LabeledContent(tr("settings.about"), value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "").frame(minHeight: Theme.minTouch)
                }
                Section {
                    Button(role: .destructive) { showDelete = true } label: { Text(tr("settings.delete_account")).frame(minHeight: Theme.minTouch, alignment: .leading) }
                        .accessibilityIdentifier("deleteAccountButton")
                }
            }
            .sheet(isPresented: $showDelete) { DeleteAccountView() }
            .sheet(isPresented: $showFeedback) { FeedbackSheet(composer: model.makeFeedback(.settings)) }
            #if DEBUG
            .onAppear { if ProcessInfo.processInfo.environment["VMK_DEBUG_SHEET"] == "delete" { showDelete = true }
                if ProcessInfo.processInfo.environment["VMK_DEBUG_SHEET"] == "feedback" { showFeedback = true } }
            #endif
            .task { if model.media?.summary == nil { await model.media?.loadSummary() } }
            .navigationTitle(tr("settings.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button(tr("common.done")) { dismiss() } } }
            .confirmationDialog(tr("settings.sign_out_confirm"), isPresented: $confirmSignOut, titleVisibility: .visible) {
                Button(tr("settings.sign_out"), role: .destructive) { dismiss(); Task { await model.signOut() } }
            }
        }
    }
}
