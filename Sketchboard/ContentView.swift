import SwiftUI
import PencilKit

struct ContentView: View {
    @State private var model = MockupViewModel()
    @State private var drawing = PKDrawing()
    @State private var canvasSize = CGSize(width: 1180, height: 820)
    @State private var showSettings = false

    var body: some View {
        HStack(spacing: 0) {
            // Left: sketch
            VStack(spacing: 0) {
                HStack(spacing: 12) {
                    TextField("Describe the screen (optional)", text: $model.description)
                        .textFieldStyle(.roundedBorder)
                    Button { drawing = PKDrawing() } label: { Label("Clear", systemImage: "trash") }
                        .disabled(drawing.strokes.isEmpty || model.isBusy)
                    if model.isBusy {
                        Button("Cancel", role: .cancel) { model.cancel() }
                    } else {
                        Button { model.generate(drawing: drawing, canvasSize: canvasSize) } label: {
                            Label("Generate", systemImage: "sparkles")
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(drawing.strokes.isEmpty || !model.isConfigured)
                    }
                }
                .padding(10)
                GeometryReader { geo in
                    Canvas(drawing: $drawing)
                        .onAppear { canvasSize = geo.size }
                        .onChange(of: geo.size) { _, new in canvasSize = new }
                }
                .background(Color.white)
            }
            .frame(maxWidth: .infinity)

            Divider()

            // Right: mockup
            VStack(spacing: 0) {
                HStack(spacing: 12) {
                    statusDot
                    Text(model.status).lineLimit(1).truncationMode(.tail)
                    Spacer()
                    Button { showSettings = true } label: { Image(systemName: "gearshape") }
                }
                .padding(10)
                // Edit row lives at the top so the keyboard (or its accessory bar) can never cover it.
                HStack(spacing: 12) {
                    TextField("Change something… e.g. make the button green", text: $model.editText)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { model.edit() }
                        .disabled(!model.canEdit)
                    Button("Apply") { model.edit() }
                        .buttonStyle(.bordered)
                        .disabled(!model.canEdit || model.editText.trimmingCharacters(in: .whitespaces).isEmpty)
                }
                .padding(.horizontal, 10).padding(.bottom, 8)
                ZStack {
                    if let html = model.html {
                        MockupWebView(html: html)
                    } else {
                        ContentUnavailableView(
                            model.isConfigured ? "No mockup yet" : "Backend not configured",
                            systemImage: model.isConfigured ? "rectangle.dashed" : "network.slash",
                            description: Text(model.isConfigured ? "Sketch a screen on the left and tap Generate." : "Tap the gear and enter the server URL and token.")
                        )
                    }
                    if model.isBusy {
                        ProgressView().controlSize(.large).padding(20)
                            .background(.thinMaterial, in: RoundedRectangle(cornerRadius: 12))
                    }
                }
                if let problems = model.lastProblems, !problems.isEmpty {
                    Text(problems).font(.caption).foregroundStyle(.secondary).lineLimit(3)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).padding(.vertical, 6)
                }
                if let err = model.errorMessage {
                    Text(err).font(.caption).foregroundStyle(.red)
                        .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).padding(.vertical, 6)
                }
            }
            .frame(maxWidth: .infinity)
        }
        .onAppear { model.checkBackend() }
        .sheet(isPresented: $showSettings, onDismiss: { model.checkBackend() }) { BackendSettingsView() }
    }

    private var statusDot: some View {
        Circle()
            .fill(model.backendOnline == true ? .green : (model.backendOnline == false ? .red : .gray))
            .frame(width: 10, height: 10)
            .help(model.backendOnline == true ? "Backend online" : "Backend unreachable")
    }
}

/// Lets a teammate point the app at the box without rebuilding. Values live in UserDefaults
/// and override whatever Secrets.xcconfig baked in.
struct BackendSettingsView: View {
    @Environment(\.dismiss) private var dismiss
    @State private var url = UserDefaults.standard.string(forKey: BackendConfig.defaultsURLKey)
        ?? (Bundle.main.infoDictionary?["GemmaBaseURL"] as? String ?? "")
    @State private var token = UserDefaults.standard.string(forKey: BackendConfig.defaultsTokenKey)
        ?? (Bundle.main.infoDictionary?["GemmaToken"] as? String ?? "")

    var body: some View {
        NavigationStack {
            Form {
                Section("Harness server") {
                    TextField("http://1.2.3.4:8080", text: $url)
                        .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    SecureField("Bearer token", text: $token)
                }
                Section {
                    Button("Use build-time values", role: .destructive) {
                        BackendConfig.clearOverride(); dismiss()
                    }
                } footer: {
                    Text("Get both from whoever ran `lambda/lambdactl.sh wait`. The IP changes every launch.")
                }
            }
            .navigationTitle("Backend")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { BackendConfig.saveOverride(urlString: url, token: token); dismiss() }
                        .disabled(URL(string: url)?.host == nil || token.isEmpty)
                }
            }
        }
        .frame(minWidth: 480, minHeight: 320)
    }
}

// Wraps Apple's PencilKit canvas for SwiftUI.
struct Canvas: UIViewRepresentable {
    @Binding var drawing: PKDrawing

    func makeUIView(context: Context) -> PKCanvasView {
        let view = PKCanvasView()
        view.drawingPolicy = .anyInput // ponytail: lets mouse/finger draw in Simulator; .pencilOnly for the real demo
        view.tool = PKInkingTool(.pen, color: .black, width: 4)
        view.delegate = context.coordinator
        view.drawing = drawing
        return view
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {
        // Only push the binding into the view when it changed elsewhere (e.g. Clear).
        if uiView.drawing != drawing && !context.coordinator.isUpdatingFromView {
            uiView.drawing = drawing
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, PKCanvasViewDelegate {
        let parent: Canvas
        var isUpdatingFromView = false
        init(_ parent: Canvas) { self.parent = parent }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            isUpdatingFromView = true
            parent.drawing = canvasView.drawing
            isUpdatingFromView = false
        }
    }
}
