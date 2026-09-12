import SwiftUI
import PencilKit

/// Side by side, or one pane at a time filling the screen.
enum PaneLayout {
    case split, full
}

// MARK: - Design tokens
//
// Warm near-white ground, ink-black primary action, hairline borders, one mono face for
// labels and status. Mirrors the Sketchboard redesign; keep changes here rather than
// sprinkling colors through the views.

private extension Color {
    init(hex: UInt) {
        self.init(.sRGB,
                  red: Double((hex >> 16) & 0xFF) / 255,
                  green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255,
                  opacity: 1)
    }
    static let ink = Color(hex: 0x2E2C2A)
    static let inkSoft = Color(hex: 0x6E6A66)
    static let inkFaint = Color(hex: 0x9E9A95)
    static let paper = Color(hex: 0xFBFAF9)
    static let paperAlt = Color(hex: 0xF7F6F4)
    static let hairline = Color(hex: 0xE7E5E2)
    static let dot = Color(hex: 0xE3E1DE)
}

private extension Font {
    /// Label / status face. Space Grotesk isn't on iOS, so the UI face stays system
    /// (SF) and the small caps-y labels go monospaced, which is what the mock leans on.
    static func mono(_ size: CGFloat, _ weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight, design: .monospaced)
    }
}

private let cardRadius: CGFloat = 16
private let fieldRadius: CGFloat = 12
private let controlHeight: CGFloat = 44

private struct CardSurface: ViewModifier {
    var fill: Color = .white
    func body(content: Content) -> some View {
        content
            .background(fill)
            .clipShape(RoundedRectangle(cornerRadius: cardRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: cardRadius, style: .continuous)
                    .strokeBorder(Color.hairline, lineWidth: 1)
            )
    }
}

private struct PrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15, weight: .medium))
            .foregroundStyle(.white)
            .padding(.horizontal, 22)
            .frame(height: controlHeight)
            .background(Color.ink.opacity(isEnabled ? (configuration.isPressed ? 0.8 : 1) : 0.25))
            .clipShape(RoundedRectangle(cornerRadius: fieldRadius, style: .continuous))
    }
}

private struct QuietButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var height: CGFloat = controlHeight
    var horizontal: CGFloat = 18
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15))
            .foregroundStyle(isEnabled ? Color.ink : Color.inkFaint)
            .padding(.horizontal, horizontal)
            .frame(height: height)
            .background(configuration.isPressed ? Color.paperAlt : .white)
            .clipShape(RoundedRectangle(cornerRadius: fieldRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: fieldRadius, style: .continuous)
                    .strokeBorder(Color.hairline, lineWidth: 1)
            )
    }
}

private struct IconButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var side: CGFloat = 38
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 15))
            .foregroundStyle(isEnabled ? Color.inkSoft : Color.inkFaint)
            .frame(width: side, height: side)
            .background(configuration.isPressed ? Color.paperAlt : .white)
            .clipShape(RoundedRectangle(cornerRadius: fieldRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: fieldRadius, style: .continuous)
                    .strokeBorder(Color.hairline, lineWidth: 1)
            )
    }
}

/// Bordered box the text field sits in, so it matches the height and border of the
/// buttons beside it.
private struct FieldBox<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        HStack(spacing: 8) {
            content
        }
        .padding(.horizontal, 14)
        .frame(height: controlHeight)
        .background(.white)
        .clipShape(RoundedRectangle(cornerRadius: fieldRadius, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: fieldRadius, style: .continuous)
                .strokeBorder(Color.hairline, lineWidth: 1)
        )
    }
}

private func paneLabel(_ text: String) -> some View {
    Text(text)
        .font(.mono(11, .medium))
        .tracking(1.4)
        .foregroundStyle(Color.inkFaint)
}

// MARK: - Root

struct ContentView: View {
    @State private var model = MockupViewModel()
    @State private var drawing = PKDrawing()
    @State private var canvasSize = CGSize(width: 1180, height: 820)
    @State private var showSettings = false
    @State private var dictation = Dictation()
    @State private var layout: PaneLayout = .split
    @State private var visiblePane = 0

    // Custom pen dock state (replaces the system PKToolPicker bar).
    @State private var tool: SketchTool = .pen
    @State private var colorIndex = 0
    @State private var canvas = CanvasController()

    var body: some View {
        VStack(spacing: 0) {
            topBar
            busyHairline
            if layout == .split {
                HStack(spacing: 0) {
                    sketchPane
                    Rectangle().fill(Color.hairline).frame(width: 1)
                    mockupPane
                }
            } else if visiblePane == 0 {
                sketchPane
            } else {
                mockupPane
            }
        }
        .background(Color.paper)
        .tint(Color.ink)
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

    // MARK: Top bar

    private var topBar: some View {
        HStack(spacing: 12) {
            Text("Sketchboard")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Color.ink)
                .kerning(-0.2)

            Spacer(minLength: 12)

            if layout == .full {
                Picker("Pane", selection: $visiblePane) {
                    Text("Sketch").tag(0)
                    Text("Mockup").tag(1)
                }
                .pickerStyle(.segmented)
                .frame(width: 200)
            }

            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    layout = layout == .split ? .full : .split
                }
            } label: {
                Image(systemName: layout == .split ? "rectangle.split.2x1" : "rectangle")
            }
            .buttonStyle(IconButtonStyle())
            .accessibilityLabel(layout == .split ? "Full screen pane" : "Split panes")

            githubButton

            Button { showSettings = true } label: { Image(systemName: "gearshape") }
                .buttonStyle(IconButtonStyle())
                .accessibilityLabel("Backend settings")
        }
        .padding(.horizontal, 22)
        .frame(height: 62)
        .overlay(alignment: .bottom) { Rectangle().fill(Color.hairline).frame(height: 1) }
    }

    /// Indeterminate 2px line under the header: progress stays visible in either layout,
    /// including while the sketch pane is the one on screen.
    @ViewBuilder
    private var busyHairline: some View {
        if model.isBusy {
            ProgressView()
                .progressViewStyle(.linear)
                .tint(Color.ink)
                .frame(height: 2)
                .transition(.opacity)
        }
    }

    @ViewBuilder
    private var githubButton: some View {
        if let user = model.githubUser {
            HStack(spacing: 8) {
                AsyncImage(url: user.avatarURL) { $0.resizable() } placeholder: { Color.paperAlt }
                    .frame(width: 24, height: 24)
                    .clipShape(Circle())
                Text("@\(user.login)")
                    .font(.system(size: 14))
                    .foregroundStyle(Color.ink)
            }
            .padding(.horizontal, 12)
            .frame(height: 38)
            .background(.white)
            .clipShape(RoundedRectangle(cornerRadius: fieldRadius, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: fieldRadius, style: .continuous)
                    .strokeBorder(Color.hairline, lineWidth: 1)
            )
            .contextMenu { Button("Sign out", role: .destructive) { model.signOut() } }
        } else {
            Button { model.signInWithGitHub() } label: {
                HStack(spacing: 8) {
                    Image(systemName: "person.crop.circle")
                    Text("Sign in with GitHub").font(.system(size: 14))
                }
            }
            .buttonStyle(QuietButtonStyle(height: 38, horizontal: 14))
            .disabled(!model.isConfigured)
        }
    }

    // MARK: Sketch pane

    private var sketchPane: some View {
        VStack(spacing: 0) {
            HStack {
                paneLabel("CANVAS")
                Spacer()
                Button("Clear") {
                    drawing = PKDrawing()
                    canvas.clear()
                }
                .font(.system(size: 14))
                .foregroundStyle(drawing.strokes.isEmpty ? Color.inkFaint : Color.inkSoft)
                .disabled(drawing.strokes.isEmpty || model.isBusy)
            }
            .padding(.horizontal, 22)
            .padding(.top, 16)
            .padding(.bottom, 10)

            GeometryReader { geo in
                ZStack {
                    DotGrid()
                    SketchCanvas(drawing: $drawing,
                                 tool: tool,
                                 color: SketchTool.palette[colorIndex],
                                 controller: canvas)
                    if drawing.strokes.isEmpty {
                        VStack(spacing: 8) {
                            Text("Draw a screen with your Pencil")
                                .font(.system(size: 16))
                                .foregroundStyle(Color.inkSoft)
                            Text("boxes, lines, labels — rough is fine")
                                .font(.mono(11))
                                .foregroundStyle(Color.inkFaint)
                        }
                        .allowsHitTesting(false)
                    }
                    VStack {
                        Spacer()
                        PenDock(tool: $tool, colorIndex: $colorIndex, controller: canvas)
                            .padding(.bottom, 18)
                    }
                }
                .modifier(CardSurface())
                .onAppear { canvasSize = geo.size }
                .onChange(of: geo.size) { _, new in canvasSize = new }
            }
            .padding(.horizontal, 22)

            HStack(spacing: 10) {
                FieldBox {
                    TextField("Describe the screen (optional)", text: $model.description)
                        .textFieldStyle(.plain)
                        .font(.system(size: 15))
                }
                DictationButton(dictation: dictation, field: "describe",
                                text: $model.description, isEnabled: !model.isBusy)
                if model.isBusy {
                    Button("Cancel") { model.cancel() }
                        .buttonStyle(QuietButtonStyle())
                } else {
                    Button("Generate") { model.generate(drawing: drawing, canvasSize: canvasSize) }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(drawing.strokes.isEmpty || !model.isConfigured)
                }
            }
            .padding(.horizontal, 22)
            .padding(.top, 16)
            .padding(.bottom, 18)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: Mockup pane

    private var mockupPane: some View {
        VStack(spacing: 0) {
            HStack(spacing: 10) {
                paneLabel("MOCKUP")
                Spacer()
                statusDot
                Text(model.status)
                    .font(.mono(11))
                    .foregroundStyle(Color.inkFaint)
                    .lineLimit(1)
                    .truncationMode(.tail)
            }
            .padding(.horizontal, 22)
            .padding(.top, 16)
            .padding(.bottom, 10)

            ZStack {
                if let html = model.html {
                    // Phone mockups stay phone-shaped; the web view scales to fit whichever side binds.
                    MockupWebView(html: html, designWidth: Int(model.mockupSize.width))
                        .aspectRatio(model.mockupSize.width / model.mockupSize.height, contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                } else if model.isBusy {
                    BusyState(status: model.status)
                } else {
                    EmptyState(configured: model.isConfigured)
                }
                if model.isBusy, model.html != nil {
                    VStack {
                        Spacer()
                        Text(model.status)
                            .font(.mono(11))
                            .foregroundStyle(Color.inkSoft)
                            .padding(.horizontal, 14)
                            .frame(height: 32)
                            .background(.ultraThinMaterial, in: Capsule())
                            .overlay(Capsule().strokeBorder(Color.hairline, lineWidth: 1))
                            .padding(.bottom, 16)
                    }
                }
            }
            .modifier(CardSurface())
            .padding(.horizontal, 22)

            // Edit row sits below the card but above the safe area; the keyboard's accessory
            // bar can't cover it because the pane scrolls nothing.
            HStack(spacing: 10) {
                FieldBox {
                    TextField("Refine… e.g. make the button full width", text: $model.editText)
                        .textFieldStyle(.plain)
                        .font(.system(size: 15))
                        .onSubmit { model.edit() }
                        .disabled(!model.canEdit)
                }
                DictationButton(dictation: dictation, field: "edit",
                                text: $model.editText, isEnabled: model.canEdit)
                Button("Apply") { model.edit() }
                    .buttonStyle(QuietButtonStyle())
                    .disabled(!model.canEdit || model.editText.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 22)
            .padding(.top, 16)
            .padding(.bottom, 18)

            if let problems = model.lastProblems, !problems.isEmpty {
                footnote(problems, color: .inkFaint)
            }
            if let err = model.errorMessage ?? dictation.errorMessage {
                footnote(err, color: Color(hex: 0xB4462F))
            }
        }
        .frame(maxWidth: .infinity)
        .background(Color.paperAlt)
    }

    private func footnote(_ text: String, color: Color) -> some View {
        Text(text)
            .font(.mono(11))
            .foregroundStyle(color)
            .lineLimit(3)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 22)
            .padding(.bottom, 14)
    }

    private var statusDot: some View {
        Circle()
            .fill(model.backendOnline == true ? Color(hex: 0x3FA96B)
                  : (model.backendOnline == false ? Color(hex: 0xC2553C) : Color.inkFaint))
            .frame(width: 6, height: 6)
            .help(model.backendOnline == true ? "Backend online" : "Backend unreachable")
    }
}

// MARK: - Pane states

private struct EmptyState: View {
    let configured: Bool
    var body: some View {
        VStack(spacing: 14) {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(Color(hex: 0xD2CFCB), style: StrokeStyle(lineWidth: 2, dash: [6, 5]))
                .frame(width: 64, height: 46)
            Text(configured ? "No mockup yet" : "Backend not configured")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Color.ink)
            Text(configured ? "Sketch a screen on the left, then tap Generate."
                 : "Tap the gear and enter the server URL and token.")
                .font(.system(size: 14))
                .foregroundStyle(Color.inkSoft)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 280)
        }
        .padding(24)
    }
}

private struct BusyState: View {
    let status: String
    @State private var slide = false
    var body: some View {
        VStack(spacing: 16) {
            Capsule()
                .fill(Color(hex: 0xEDEBE8))
                .frame(width: 220, height: 3)
                .overlay(alignment: .leading) {
                    Capsule()
                        .fill(Color.ink)
                        .frame(width: 55, height: 3)
                        .offset(x: slide ? 165 : 0)
                        .animation(.easeInOut(duration: 1.1).repeatForever(autoreverses: true), value: slide)
                }
            Text(status)
                .font(.mono(12))
                .foregroundStyle(Color.inkSoft)
                .lineLimit(1)
        }
        .onAppear { slide = true }
    }
}

/// Faint dot grid behind the canvas, matching the sketch surface in the design.
private struct DotGrid: View {
    var body: some View {
        Canvas { ctx, size in
            let step: CGFloat = 22
            let r: CGFloat = 1
            var y: CGFloat = step / 2
            while y < size.height {
                var x: CGFloat = step / 2
                while x < size.width {
                    ctx.fill(Path(ellipseIn: CGRect(x: x - r, y: y - r, width: r * 2, height: r * 2)),
                             with: .color(.dot))
                    x += step
                }
                y += step
            }
        }
        .background(.white)
        .allowsHitTesting(false)
    }
}

// MARK: - Pen dock

enum SketchTool: String, CaseIterable, Identifiable {
    case pen, marker, pencil, erase
    var id: String { rawValue }
    var label: String {
        switch self {
        case .pen: "PEN"
        case .marker: "MARKER"
        case .pencil: "PENCIL"
        case .erase: "ERASE"
        }
    }
    func pkTool(color: UIColor) -> PKTool {
        switch self {
        case .pen: PKInkingTool(.pen, color: color, width: 4)
        case .marker: PKInkingTool(.marker, color: color.withAlphaComponent(0.55), width: 18)
        case .pencil: PKInkingTool(.pencil, color: color, width: 6)
        case .erase: PKEraserTool(.bitmap)
        }
    }
    /// Ink, blue, green, amber — the four the design exposes; the system picker is hidden.
    static let palette: [UIColor] = [
        UIColor(Color(hex: 0x2E2C2A)),
        UIColor(Color(hex: 0x3A6BD6)),
        UIColor(Color(hex: 0x2E9E6B)),
        UIColor(Color(hex: 0xD08A2C))
    ]
}

/// Floating pill above the canvas: undo/redo, four tools, four inks.
private struct PenDock: View {
    @Binding var tool: SketchTool
    @Binding var colorIndex: Int
    let controller: CanvasController

    var body: some View {
        HStack(spacing: 6) {
            dockIcon("arrow.uturn.backward", enabled: controller.canUndo) { controller.undo() }
            dockIcon("arrow.uturn.forward", enabled: controller.canRedo) { controller.redo() }
            separator
            ForEach(SketchTool.allCases) { t in
                Button { tool = t } label: {
                    Text(t.label)
                        .font(.mono(11, .medium))
                        .tracking(0.4)
                        .foregroundStyle(tool == t ? Color.ink : Color.inkSoft)
                        .padding(.horizontal, 12)
                        .frame(height: 34)
                        .background(tool == t ? Color(hex: 0xEFEDEA) : .clear, in: Capsule())
                }
                .buttonStyle(.plain)
            }
            separator
            ForEach(Array(SketchTool.palette.enumerated()), id: \.offset) { i, ink in
                Button { colorIndex = i } label: {
                    Circle()
                        .fill(Color(ink))
                        .frame(width: 22, height: 22)
                        .overlay(
                            Circle().strokeBorder(colorIndex == i ? Color.ink : .white, lineWidth: 2)
                                .padding(-2)
                        )
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Ink \(i + 1)")
            }
        }
        .padding(8)
        .background(.ultraThinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(Color.hairline, lineWidth: 1))
        .shadow(color: .black.opacity(0.06), radius: 14, y: 6)
    }

    private var separator: some View {
        Rectangle().fill(Color.hairline).frame(width: 1, height: 20).padding(.horizontal, 4)
    }

    private func dockIcon(_ name: String, enabled: Bool, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: name)
                .font(.system(size: 14))
                .foregroundStyle(enabled ? Color.inkSoft : Color.inkFaint.opacity(0.6))
                .frame(width: 34, height: 34)
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
    }
}

// MARK: - Canvas

/// Exposes PKCanvasView's undo stack to the dock, since the system tool picker (which
/// normally owns those buttons) is no longer shown.
@Observable
final class CanvasController {
    weak var canvas: PKCanvasView?
    var canUndo = false
    var canRedo = false

    func undo() { canvas?.undoManager?.undo(); sync() }
    func redo() { canvas?.undoManager?.redo(); sync() }
    func clear() {
        canvas?.drawing = PKDrawing()
        canvas?.undoManager?.removeAllActions()
        sync()
    }
    func sync() {
        canUndo = canvas?.undoManager?.canUndo ?? false
        canRedo = canvas?.undoManager?.canRedo ?? false
    }
}

/// Apple's PencilKit canvas, transparent so the dot grid shows through, with the system
/// tool picker suppressed in favour of the custom dock.
struct SketchCanvas: UIViewRepresentable {
    @Binding var drawing: PKDrawing
    let tool: SketchTool
    let color: UIColor
    let controller: CanvasController

    func makeUIView(context: Context) -> PKCanvasView {
        let view = PKCanvasView()
        view.drawingPolicy = .anyInput // lets mouse/finger draw in Simulator; .pencilOnly for the real demo
        view.tool = tool.pkTool(color: color)
        view.delegate = context.coordinator
        view.drawing = drawing
        view.backgroundColor = .clear
        view.isOpaque = false
        controller.canvas = view
        DispatchQueue.main.async { controller.sync() }
        return view
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {
        if controller.canvas !== uiView { controller.canvas = uiView }
        uiView.tool = tool.pkTool(color: color)
        // Only push the binding into the view when it changed elsewhere (e.g. Clear).
        if uiView.drawing != drawing && !context.coordinator.isUpdatingFromView {
            uiView.drawing = drawing
        }
    }

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, PKCanvasViewDelegate {
        let parent: SketchCanvas
        var isUpdatingFromView = false
        init(_ parent: SketchCanvas) { self.parent = parent }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            isUpdatingFromView = true
            parent.drawing = canvasView.drawing
            isUpdatingFromView = false
            parent.controller.sync()
        }
    }
}

// MARK: - Settings

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
