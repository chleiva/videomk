import SwiftUI
import VideoMKCore

struct CreateView: View {
    @Environment(AppModel.self) private var model
    @Environment(\.dismiss) private var dismiss
    @State private var brief: String
    @State private var requestID = UUID().uuidString
    @State private var options = CreateOptions()
    @State private var sending = false
    @State private var error: String?
    @FocusState private var focused: Bool
    let onCreated: (String) -> Void

    init(initialBrief: String = "", onCreated: @escaping (String) -> Void) {
        _brief = State(initialValue: initialBrief)
        self.onCreated = onCreated
    }

    private var count: Int { Brief.normalized(brief).count }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("What should the video be about?").font(.title3.bold()).foregroundStyle(Theme.text)
                    TextEditor(text: $brief)
                        .focused($focused)
                        .scrollContentBackground(.hidden)
                        .frame(minHeight: 160)
                        .padding(12)
                        .background(Theme.surface, in: RoundedRectangle(cornerRadius: Theme.radius, style: .continuous))
                        .overlay(alignment: .topLeading) {
                            if brief.isEmpty { Text("A topic, a question, or a story you want told…").foregroundStyle(Theme.textSecondary).padding(18).allowsHitTesting(false) }
                        }
                        .accessibilityIdentifier("briefField")
                        .onChange(of: brief) { error = nil; requestID = UUID().uuidString }  // new text = new attempt; retries of the same text reuse the id
                    HStack {
                        Text(counterText).font(.footnote).foregroundStyle(counterColor)
                        Spacer()
                    }
                    optionsSection
                    if let error { Text(error).font(.callout).foregroundStyle(Theme.danger).accessibilityIdentifier("createError") }
                    if brief.isEmpty {
                        Text("Try one of these").font(.footnote.weight(.semibold)).foregroundStyle(Theme.textSecondary)
                        ForEach(ExampleBriefs.all, id: \.self) { e in
                            Button(e) { brief = e }.font(.callout).foregroundStyle(Theme.primary).multilineTextAlignment(.leading)
                        }
                    }
                }
                .padding(20)
            }
            .background(Theme.background.ignoresSafeArea())
            .navigationTitle("New video")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .safeAreaInset(edge: .bottom) {
                Button { Task { await submit() } } label: {
                    if sending { ProgressView().tint(.white) } else { Text("Create video") }
                }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(!Brief.isValid(brief) || sending)
                .accessibilityIdentifier("createButton")
                .padding(.horizontal, 20).padding(.vertical, 12)
                .background(.bar)
            }
        }
        .onAppear { focused = true }
    }

    private var optionsSection: some View {
        Card {
            VStack(alignment: .leading, spacing: 14) {
                Picker("Length", selection: $options.minutes) {
                    ForEach(CreateOptions.lengths, id: \.self) { Text("\(Int($0)) min").tag($0) }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("lengthPicker")
                Divider()
                Picker("Look", selection: $options.look) {
                    Text("Producer decides").tag(VideoLook?.none)
                    ForEach(VideoLook.allCases) { Text($0.title).tag(VideoLook?.some($0)) }
                }
                .pickerStyle(.menu)
                .accessibilityIdentifier("lookPicker")
                Text("A \(Int(options.minutes)) minute video takes a few minutes to make.").font(.footnote).foregroundStyle(Theme.textSecondary)
            }
        }
        .onChange(of: options) { requestID = UUID().uuidString }  // different options = a different request
    }

    private var counterText: String {
        if count == 0 { return "At least \(Brief.minLength) characters" }
        if count < Brief.minLength { return "\(Brief.minLength - count) more characters needed" }
        return "\(count) / \(Brief.maxLength)"
    }
    private var counterColor: Color { count > Brief.maxLength ? Theme.danger : Theme.textSecondary }

    private func submit() async {
        guard !sending else { return }  // a double tap never starts two videos
        sending = true; error = nil
        defer { sending = false }
        do {
            let id = try await model.create(brief: brief, requestID: requestID, options: options)
            onCreated(id)
        } catch let e as APIError {
            error = e.message  // the draft stays in place so nothing is lost
        } catch {
            self.error = APIError.server.message
        }
    }
}
