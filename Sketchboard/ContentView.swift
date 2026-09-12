import SwiftUI
import PencilKit

/// Side by side, or one pane at a time filling the screen.
enum PaneLayout {
    case split, full
}

struct ContentView: View {
    @State private var model = MockupViewModel()
    @State private var drawing = PKDrawing()
    @State private var canvasSize = CGSize(width: 1180, height: 820)
    @State private var showSettings = false
    @State private var dictation = Dictation()
    @State private var layout: PaneLayout = .split
    @State private var visiblePane = 0

    var body: some View {
        VStack(spacing: 0) {
            topBar
            if model.isBusy { progressBar }
            Divider()
            if layout == .split {
                HStack(spacing: 0) {
                    sketchPane
                    Divider()
                    mockupPane
                }
            } else if visiblePane == 0 {
                sketchPane
            } else {
                mockupPane
            }
        }
        .onAppear { model.checkBackend() }
        .onChange(of: model.isBusy) { _, busy in
            // Full screen hides whichever pane you aren't on, so surface the result when
            // the run ends. Nothing to show after a cancel with no mockup yet.
            guard !busy, layout == .full, model.html != nil || model.errorMessage != nil else { return }
            withAnimation(.easeInOut(duration: 0.2)) { visiblePane = 1 }
        }
        .sheet(isPresented: $showSettings, onDismiss: { model.checkBackend() }) { BackendSettingsView() }
        .sheet(isPresented: Binding(get: { model.authURL != nil }, set: { if !$0 { model.cancelSignIn() } })) {
            if let url = model.authURL { SafariView(url: url).ignoresSafeArea() }
        }
    }

    @ViewBuilder
    private var githubButton: some View {
        if let user = model.githubUser {
            HStack(spacing: 6) {
                AsyncImage(url: user.avatarURL) { $0.resizable() } placeholder: { Color.secondary.opacity(0.3) }
                    .frame(width: 24, height: 24).clipShape(Circle())
                Text("@\(user.login)").font(.callout)
            }
            .contextMenu { Button("Sign out", role: .destructive) { model.signOut() } }
        } else {
            Button { model.signInWithGitHub() } label: { Label("Sign in with GitHub", systemImage: "person.crop.circle") }
                .buttonStyle(.bordered)
                .disabled(!model.isConfigured)
        }
    }

    /// Sits under the top bar so progress is visible in either layout, including while the
    /// sketch pane is the one on screen.
    private var progressBar: some View {
        VStack(alignment: .leading, spacing: 3) {
            ProgressView().progressViewStyle(.linear)
            Text(model.status)
                .font(.caption).foregroundStyle(.secondary)
                .lineLimit(1).truncationMode(.tail)
        }
        .padding(.horizontal, 10)
        .padding(.bottom, 6)
    }

    /// Layout switch, plus a pane picker when one pane fills the screen. Deliberately a
    /// picker rather than a swipe: PKCanvasView and WKWebView are both scroll views, so a
    /// horizontal drag over their content is swallowed before any pager could see it.
    private var topBar: some View {
        HStack(spacing: 12) {
            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    layout = layout == .split ? .full : .split
                }
            } label: {
                Label(layout == .split ? "Split" : "Full",
                      systemImage: layout == .split ? "rectangle.split.2x1" : "rectangle")
            }
            .buttonStyle(.bordered)

            if layout == .full {
                Picker("Pane", selection: $visiblePane) {
                    Text("Sketch").tag(0)
                    Text("Mockup").tag(1)
                }
                .pickerStyle(.segmented)
                .frame(width: 220)
            }
            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }

    // Left when split, whole screen when full: sketch
    private var sketchPane: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                TextField("Describe the screen (optional)", text: $model.description)
                    .textFieldStyle(.roundedBorder)
                DictationButton(dictation: dictation, field: "describe",
                                text: $model.description, isEnabled: !model.isBusy)
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
    }

    // Right when split, whole screen when full: mockup
    private var mockupPane: some View {
        VStack(spacing: 0) {
            HStack(spacing: 12) {
                statusDot
                Text(model.status).lineLimit(1).truncationMode(.tail)
                Spacer()
                githubButton
                Button { showSettings = true } label: { Image(systemName: "gearshape") }
            }
            .padding(10)
            // Edit row lives at the top so the keyboard (or its accessory bar) can never cover it.
            HStack(spacing: 12) {
                TextField("Change something… e.g. make the button green", text: $model.editText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { model.edit() }
                    .disabled(!model.canEdit)
                DictationButton(dictation: dictation, field: "edit",
                                text: $model.editText, isEnabled: model.canEdit)
                Button("Apply") { model.edit() }
                    .buttonStyle(.bordered)
                    .disabled(!model.canEdit || model.editText.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 10).padding(.bottom, 8)
            ZStack {
                if let html = model.html {
                    // Phone mockups stay phone-shaped; the web view scales to fit whichever side binds.
                    MockupWebView(html: html, designWidth: Int(model.mockupSize.width))
                        .aspectRatio(model.mockupSize.width / model.mockupSize.height, contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    ContentUnavailableView(
                        model.isConfigured ? "No mockup yet" : "Backend not configured",
                        systemImage: model.isConfigured ? "rectangle.dashed" : "network.slash",
                        description: Text(model.isConfigured ? "Sketch a screen and tap Generate." : "Tap the gear and enter the server URL and token.")
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
            if let err = model.errorMessage ?? dictation.errorMessage {
                Text(err).font(.caption).foregroundStyle(.red)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 10).padding(.vertical, 6)
            }
        }
        .frame(maxWidth: .infinity)
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

        // System tool picker (pen sizes, eraser, undo). Deferred: the view isn't in the
        // window yet, so becomeFirstResponder() would no-op if called synchronously.
        let picker = context.coordinator.toolPicker
        DispatchQueue.main.async {
            picker.setVisible(true, forFirstResponder: view)
            picker.addObserver(view)
            view.becomeFirstResponder()
        }
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
        let toolPicker = PKToolPicker()   // owned here so it outlives SwiftUI's struct re-creation
        var isUpdatingFromView = false
        init(_ parent: Canvas) { self.parent = parent }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            isUpdatingFromView = true
            parent.drawing = canvasView.drawing
            isUpdatingFromView = false
        }
    }
}
