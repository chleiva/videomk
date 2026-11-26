import SwiftUI
import VideoMKCore

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmSignOut = false
    @State private var showDelete = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @AppStorage(PhotoMetaSettings.datesKey) private var useDates = true
    @AppStorage(PhotoMetaSettings.locationsKey) private var useLocations = true

    var body: some View {
        NavigationStack {
            List {
                Section(tr("settings.account")) {
                    if case .signedIn(let email) = model.phase, let email { LabeledContent(tr("settings.signed_in_as"), value: email) }
                    Button(tr("settings.sign_out"), role: .destructive) { confirmSignOut = true }.accessibilityIdentifier("signOutButton")
                }
                Section {
                    Button(role: .destructive) { showDelete = true } label: { Label { Text(tr("settings.delete_account")) } icon: { Image(systemName: "trash").foregroundStyle(.red) } }
                        .accessibilityIdentifier("deleteAccountButton")
                } footer: {
                    Text(tr("settings.delete_footer"))
                }
                Section {
                    Picker(tr("settings.language"), selection: Binding(get: { Localization.shared.choice }, set: { model.setLanguage($0) })) {
                        Text(tr("settings.language_system")).tag(LanguageChoice.system)
                        Text(AppLanguage.en.nativeName).tag(LanguageChoice.en)
                        Text(AppLanguage.es.nativeName).tag(LanguageChoice.es)
                    }
                    .accessibilityIdentifier("languagePicker")
                } header: { Text(tr("settings.language")) } footer: { Text(tr("settings.language_footer")) }
                Section {
                    Toggle(tr("settings.photo_dates"), isOn: $useDates).accessibilityIdentifier("usePhotoDates")
                    Toggle(tr("settings.photo_locations"), isOn: $useLocations).accessibilityIdentifier("usePhotoLocations")
                } header: { Text(tr("settings.photos")) } footer: {
                    Text(tr("settings.photos_footer"))
                }
                if let media = model.media {
                    Section {
                        VStack(alignment: .leading, spacing: 10) {
                            Label(tr("settings.organize"), systemImage: "sparkles").font(.system(size: 16, weight: .semibold))
                            Picker(tr("settings.organize"), selection: Binding(get: { media.organizePref }, set: { media.setOrganizePref($0) })) {
                                ForEach(OrganizePref.allCases, id: \.self) { Text($0.title).tag($0) }
                            }
                            .pickerStyle(.segmented).labelsHidden().accessibilityIdentifier("organizePref")
                        }
                        .padding(.vertical, 4)
                    } footer: {
                        Text(tr("settings.organize_footer"))
                    }
                }
                Section(tr("media.title")) {
                    Text(MediaCopy.privacy).font(.footnote).foregroundStyle(Theme.textSecondary)
                }
                Section(tr("settings.about")) {
                    LabeledContent(tr("settings.version"), value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")
                    Link(tr("legal.privacy"), destination: URL(string: tr("legal.privacy_url"))!)
                }
            }
            .sheet(isPresented: $showDelete) { DeleteAccountView() }
            #if DEBUG
            .onAppear { if ProcessInfo.processInfo.environment["VMK_DEBUG_SHEET"] == "delete" { showDelete = true } }
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
