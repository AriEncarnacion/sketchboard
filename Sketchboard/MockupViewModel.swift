import Foundation
import PencilKit
import Observation

/// Drives one sketch → mockup session and exposes state for the UI.
@MainActor
@Observable
final class MockupViewModel {
    var description = ""
    var editText = ""
    var status = "Draw a screen, then tap Generate."
    var html: String?
    var sessionId: String?
    var isBusy = false
    var backendOnline: Bool?      // nil = not checked yet
    var lastProblems: String?
    var errorMessage: String?

    private var task: Task<Void, Never>?

    var isConfigured: Bool { BackendConfig.current != nil }
    var canEdit: Bool { sessionId != nil && html != nil && !isBusy }

    func checkBackend() {
        guard let config = BackendConfig.current else { backendOnline = false; return }
        Task { backendOnline = await MockupClient(config: config).isReady() }
    }

    func generate(drawing: PKDrawing, canvasSize: CGSize) {
        guard let config = BackendConfig.current else { errorMessage = MockupClientError.notConfigured.localizedDescription; return }
        guard !drawing.strokes.isEmpty else { status = "Draw something first."; return }
        guard let jpeg = drawing.sketchJPEG(canvasSize: canvasSize) else { errorMessage = "Could not export the sketch."; return }

        let client = MockupClient(config: config)
        let sid = "ipad-" + UUID().uuidString.prefix(8)
        sessionId = sid
        html = nil
        lastProblems = nil
        run(client.mockup(sketch: jpeg, description: description, sessionId: sid), verb: "Generating")
    }

    func edit() {
        let instruction = editText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let config = BackendConfig.current, let sid = sessionId, !instruction.isEmpty else { return }
        editText = ""
        run(MockupClient(config: config).edit(sessionId: sid, instruction: instruction), verb: "Editing")
    }

    func cancel() {
        task?.cancel()
        task = nil
        isBusy = false
        status = "Cancelled."
    }

    private func run(_ stream: AsyncThrowingStream<MockupEvent, Error>, verb: String) {
        task?.cancel()
        isBusy = true
        errorMessage = nil
        status = "\(verb)…"
        task = Task { [weak self] in
            do {
                for try await event in stream {
                    guard let self, !Task.isCancelled else { return }
                    self.apply(event)
                }
            } catch is CancellationError {
                return
            } catch {
                self?.errorMessage = error.localizedDescription
                self?.status = "Failed."
            }
            self?.isBusy = false
        }
    }

    private func apply(_ e: MockupEvent) {
        switch e.kind {
        case .session:
            if let id = e.sessionId { sessionId = id }
        case .status:
            status = e.message ?? status
        case .draft:
            if let h = e.html { html = h }
            status = "Draft \(e.iteration ?? 0) in \(Int(e.seconds ?? 0)) s"
        case .checks:
            lastProblems = (e.clean ?? true) ? nil : e.problems
        case .verdict:
            lastProblems = e.problems
            status = "Judge found problems, revising…"
        case .approved:
            lastProblems = nil
            status = "Approved."
        case .final:
            if let h = e.html { html = h }
            status = (e.approved ?? false) ? "Done (approved)." : "Done (best of \((e.iterations ?? 0) + 1) drafts)."
        case .error:
            errorMessage = e.message ?? "Server error"
            status = "Failed."
        case .unknown:
            break
        }
    }
}
