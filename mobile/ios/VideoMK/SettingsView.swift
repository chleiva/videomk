import SwiftUI
import VideoMKCore

struct SettingsView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var confirmSignOut = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @AppStorage(PhotoMetaSettings.datesKey) private var useDates = true
    @AppStorage(PhotoMetaSettings.locationsKey) private var useLocations = true

    var body: some View {
        NavigationStack {
            List {
                Section("Account") {
                    if case .signedIn(let email) = model.phase, let email { LabeledContent("Signed in as", value: email) }
                    Button("Sign out", role: .destructive) { confirmSignOut = true }.accessibilityIdentifier("signOutButton")
                }
                Section {
                    Toggle("Use photo dates", isOn: $useDates).accessibilityIdentifier("usePhotoDates")
                    Toggle("Use photo locations", isOn: $useLocations).accessibilityIdentifier("usePhotoLocations")
                } header: { Text("Photos") } footer: {
                    Text("Use photo dates: puts your photos in the order they were taken and groups them by day.\n\nUse photo locations: names the places in your story. An approximate location (about 1 km) is sent, never the exact spot, and it is not kept after your video is planned. Location is always removed from the photo files themselves.")
                }
                if let media = model.media {
                    Section {
                        VStack(alignment: .leading, spacing: 10) {
                            Label("Organize new uploads", systemImage: "sparkles").font(.system(size: 16, weight: .semibold))
                            Picker("Organize new uploads", selection: Binding(get: { media.organizePref }, set: { media.setOrganizePref($0) })) {
                                ForEach(OrganizePref.allCases, id: \.self) { Text($0.title).tag($0) }
                            }
                            .pickerStyle(.segmented).labelsHidden().accessibilityIdentifier("organizePref")
                        }
                        .padding(.vertical, 4)
                    } footer: {
                        Text("Ask offers after a big upload. Always groups photos by place and month, and adds later uploads to matching collections. Never leaves everything as it is.")
                    }
                }
                Section("My media") {
                    Text(MediaCopy.privacy).font(.footnote).foregroundStyle(Theme.textSecondary)
                }
                Section("About") {
                    LabeledContent("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "")
                    Link("Privacy Policy", destination: URL(string: "https://videomk.com/privacy")!)
                }
            }
            .task { if model.media?.summary == nil { await model.media?.loadSummary() } }
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } } }
            .confirmationDialog("Sign out of videomk?", isPresented: $confirmSignOut, titleVisibility: .visible) {
                Button("Sign out", role: .destructive) { dismiss(); Task { await model.signOut() } }
            }
        }
    }
}
