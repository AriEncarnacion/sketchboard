import SwiftUI
import PencilKit

struct ContentView: View {
    @State private var strokeCount = 0

    var body: some View {
        VStack(spacing: 0) {
            Text("Hello, Sketchboard — strokes: \(strokeCount)")
                .padding(8)
            Canvas(strokeCount: $strokeCount)
        }
    }
}

// Wraps Apple's PencilKit canvas for SwiftUI.
struct Canvas: UIViewRepresentable {
    @Binding var strokeCount: Int

    func makeUIView(context: Context) -> PKCanvasView {
        let view = PKCanvasView()
        view.drawingPolicy = .anyInput // ponytail: lets mouse/finger draw in Simulator; .pencilOnly for the real demo
        view.tool = PKInkingTool(.pen, color: .black, width: 4)
        view.delegate = context.coordinator
        return view
    }

    func updateUIView(_ uiView: PKCanvasView, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, PKCanvasViewDelegate {
        let parent: Canvas
        init(_ parent: Canvas) { self.parent = parent }

        // Fires after every stroke. Tomorrow: debounce here, snapshot, POST to Gemma for a UI mockup.
        func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
            parent.strokeCount = canvasView.drawing.strokes.count
        }
    }
}
