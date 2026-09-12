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
