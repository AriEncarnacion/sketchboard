import SwiftUI
import PencilKit
import WebKit

struct ContentView: View {
    @State private var strokeCount = 0
    @State private var mockupHTML = ContentView.sampleHTML

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Text("Hello, Sketchboard — strokes: \(strokeCount)")
                    .padding(8)
                HStack(spacing: 0) {
                    Canvas(strokeCount: $strokeCount)
                        .frame(maxWidth: .infinity)
                    HTMLPreview(html: mockupHTML)
                        .frame(maxWidth: .infinity)
                }
            }
            .toolbar {
                ToolbarItemGroup(placement: .topBarTrailing) {
                    Button("Load sample") { mockupHTML = ContentView.sampleHTML }
                    Button("Clear") { mockupHTML = "" }
                }
            }
        }
    }

    /// Self-contained iOS-styled login mockup. Inline CSS/JS only, no external resources.
    /// The button's inline script mutates its own label so we can confirm the rendered
    /// HTML is actually interactive.
    static let sampleHTML = """
    <!DOCTYPE html>
    <html>
    <head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      * { box-sizing: border-box; }
      body {
        font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif;
        background: #f2f2f7;
        margin: 0;
        padding: 24px;
        color: #1c1c1e;
      }
      .card {
        background: #ffffff;
        border-radius: 12px;
        padding: 24px;
        max-width: 360px;
        margin: 40px auto;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
      }
      h1 {
        font-size: 24px;
        font-weight: 700;
        text-align: center;
        margin: 0 0 24px;
      }
      input {
        width: 100%;
        padding: 12px;
        margin-bottom: 12px;
        border: 1px solid #d1d1d6;
        border-radius: 12px;
        font-size: 16px;
        background: #f2f2f7;
      }
      .toggle-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin: 16px 0;
        font-size: 16px;
      }
      .switch { position: relative; width: 51px; height: 31px; }
      .switch input { opacity: 0; width: 0; height: 0; margin: 0; }
      .slider {
        position: absolute;
        inset: 0;
        background: #d1d1d6;
        border-radius: 31px;
        transition: background 0.2s;
      }
      .slider::before {
        content: "";
        position: absolute;
        height: 27px;
        width: 27px;
        left: 2px;
        top: 2px;
        background: #ffffff;
        border-radius: 50%;
        transition: transform 0.2s;
        box-shadow: 0 1px 3px rgba(0,0,0,0.2);
      }
      .switch input:checked + .slider { background: #34c759; }
      .switch input:checked + .slider::before { transform: translateX(20px); }
      button {
        width: 100%;
        padding: 14px;
        border: none;
        border-radius: 12px;
        background: #007aff;
        color: #ffffff;
        font-size: 17px;
        font-weight: 600;
        cursor: pointer;
      }
      button:active { background: #0062cc; }
    </style>
    </head>
    <body>
      <div class="card">
        <h1>Sign In</h1>
        <input type="email" placeholder="Email">
        <input type="password" placeholder="Password">
        <div class="toggle-row">
          <span>Remember me</span>
          <label class="switch">
            <input type="checkbox">
            <span class="slider"></span>
          </label>
        </div>
        <button id="signInButton" onclick="this.textContent = 'Tapped!'">Sign In</button>
      </div>
    </body>
    </html>
    """
}

/// Wraps a WKWebView so a hardcoded HTML string can be rendered natively. Reloads only
/// when the html string actually changes, so ordinary SwiftUI redraws don't reset the page.
struct HTMLPreview: UIViewRepresentable {
    let html: String

    func makeUIView(context: Context) -> WKWebView {
        let configuration = WKWebViewConfiguration()
        let webView = WKWebView(frame: .zero, configuration: configuration)
        webView.scrollView.bounces = false
        return webView
    }

    func updateUIView(_ webView: WKWebView, context: Context) {
        guard context.coordinator.loadedHTML != html else { return }
        context.coordinator.loadedHTML = html
        webView.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    class Coordinator {
        var loadedHTML: String?
    }
}

struct Canvas: UIViewRepresentable {
    @Binding var strokeCount: Int
    private let toolPicker = PKToolPicker()

    func makeUIView(context: Context) -> PKCanvasView {
        let view = PKCanvasView()
        view.drawingPolicy = .anyInput
        view.tool = PKInkingTool(.pen, color: .black, width: 4)
        view.delegate = context.coordinator

        // Deferred: view isn't in the window yet, so becomeFirstResponder() would no-op here.
        DispatchQueue.main.async {
            toolPicker.setVisible(true, forFirstResponder: view)
            toolPicker.addObserver(view)
            view.becomeFirstResponder()
        }
        return view
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, PKCanvasViewDelegate {
        let parent: Canvas
        init(_ parent: Canvas) { self.parent = parent }

        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            parent.strokeCount = canvasView.drawing.strokes.count
        }
    }
}
