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
    var mockupSize = CGSize(width: 1180, height: 820)   // from the server's draft/final events
    var sessionId: String?
    var isBusy = false
    var backendOnline: Bool?      // nil = not checked yet
    var lastProblems: String?
    var errorMessage: String?

    // Sign in with GitHub (via Nango). authURL non-nil = Safari sheet is up.
    var githubUser: GitHubUser?
    var authURL: URL?
    let userId: String = {
        let key = "SKETCHBOARD_USER_ID"
        if let id = UserDefaults.standard.string(forKey: key), id.count >= 20 { return id }  // re-mint short ids from early builds
        // Full UUID (128 bits): the id doubles as the lookup key for this device's GitHub
        // profile on the server, so it must not be guessable by another token holder.
        let id = "ipad-" + UUID().uuidString.lowercased()
        UserDefaults.standard.set(id, forKey: key)
        return id
    }()

    private var task: Task<Void, Never>?
    private var authTask: Task<Void, Never>?

    var isConfigured: Bool { BackendConfig.current != nil }
    var canEdit: Bool { sessionId != nil && html != nil && !isBusy }

    func checkBackend() {
        guard let config = BackendConfig.current else { backendOnline = false; return }
        Task { backendOnline = await MockupClient(config: config).isReady() }
        refreshGitHubUser()
    }

    // MARK: GitHub sign-in

    func signInWithGitHub() {
        guard let config = BackendConfig.current else { errorMessage = MockupClientError.notConfigured.localizedDescription; return }
        let client = MockupClient(config: config)
        authTask?.cancel()
        authTask = Task { [weak self] in
            guard let self else { return }
            do {
                authURL = try await client.authSession(userId: userId)
                // Poll while the sheet is up; Nango has no way to call back into a native app.
                for _ in 0..<150 {   // ponytail: 150 × 2 s = 5 min, then give up quietly
                    try await Task.sleep(for: .seconds(2))
                    guard authURL != nil else { return }
                    if let user = try? await client.authStatus(userId: userId) {
                        githubUser = user
                        authURL = nil
                        return
                    }
                }
            } catch is CancellationError {
            } catch {
                errorMessage = error.localizedDescription
                authURL = nil
            }
        }
    }

    /// Restores a previous sign-in without opening the sheet.
    func refreshGitHubUser() {
        guard let config = BackendConfig.current else { return }
        Task { githubUser = try? await MockupClient(config: config).authStatus(userId: userId) }
    }

    func signOut() {
        githubUser = nil   // ponytail: forgets locally; the Nango connection stays. Delete it via Nango if needed.
    }

    func cancelSignIn() {
        authTask?.cancel()
        authURL = nil
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
        run(client.mockup(sketch: jpeg, description: description, sessionId: sid), verb: "Thinking")
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
            if let w = e.width, let h = e.height { mockupSize = CGSize(width: w, height: h) }
            status = "Draft \(e.iteration ?? 0) in \(Int(e.seconds ?? 0)) s"
        case .checks:
            lastProblems = (e.clean ?? true) ? nil : e.problems
            status = "Validating…"
        case .verdict:
            lastProblems = e.problems
            status = "Revising…"
        case .approved:
            lastProblems = nil
            status = "Approved."
        case .final:
            if let h = e.html { html = h }
            if let w = e.width, let h = e.height { mockupSize = CGSize(width: w, height: h) }
            status = (e.approved ?? false) ? "Done (approved)." : "Done (best of \((e.iterations ?? 0) + 1) drafts)."
        case .error:
            errorMessage = e.message ?? "Server error"
            status = "Failed."
        case .unknown:
            break
        }
    }
}
