import Foundation

enum MockupClientError: LocalizedError {
    case http(status: Int, body: String)
    case notConfigured

    var errorDescription: String? {
        switch self {
        case .http(let status, let body):
            return "Server returned \(status): \(body.prefix(200))"
        case .notConfigured:
            return "Backend not configured. Set the server URL and token in Settings."
        }
    }
}

/// Async client for the harness API. Each call returns a stream of `MockupEvent`s that
/// ends after the `final` or `error` event. Cancel the consuming task to abort.
final class MockupClient: Sendable {
    let config: BackendConfig
    private let session: URLSession

    init(config: BackendConfig) {
        self.config = config
        let c = URLSessionConfiguration.default
        c.timeoutIntervalForRequest = 600   // idle gap between bytes; events arrive every < 70 s
        c.timeoutIntervalForResource = 1800
        c.waitsForConnectivity = true
        self.session = URLSession(configuration: c)
    }

    // MARK: Requests (field names match API.md)

    struct MockupRequest: Encodable {
        var imageBase64: String
        var mime = "image/jpeg"
        var description = ""
        var sessionId: String?
        var maxIterations: Int?
        var model: String?
        var debug = false

        enum CodingKeys: String, CodingKey {
            case mime, description, model, debug
            case imageBase64 = "image_base64"
            case sessionId = "session_id"
            case maxIterations = "max_iterations"
        }
    }

    struct EditRequest: Encodable {
        var sessionId: String
        var instruction: String
        var model: String?

        enum CodingKeys: String, CodingKey {
            case instruction, model
            case sessionId = "session_id"
        }
    }

    struct AuthSessionRequest: Encodable {
        var userId: String
        enum CodingKeys: String, CodingKey { case userId = "user_id" }
    }

    private struct AuthSessionResponse: Decodable {
        var connectLink: URL
        enum CodingKeys: String, CodingKey { case connectLink = "connect_link" }
    }

    private struct AuthMeResponse: Decodable {
        var connected: Bool
        var login: String?
        var avatarUrl: URL?
        var name: String?
        enum CodingKeys: String, CodingKey { case connected, login, name; case avatarUrl = "avatar_url" }
    }

    // MARK: Calls

    func mockup(sketch: Data, mime: String = "image/jpeg", description: String,
                sessionId: String? = nil, maxIterations: Int? = nil) -> AsyncThrowingStream<MockupEvent, Error> {
        let body = MockupRequest(imageBase64: sketch.base64EncodedString(), mime: mime, description: description,
                                 sessionId: sessionId, maxIterations: maxIterations)
        return stream(path: "api/v1/mockup", body: body)
    }

    func edit(sessionId: String, instruction: String) -> AsyncThrowingStream<MockupEvent, Error> {
        stream(path: "api/v1/edit", body: EditRequest(sessionId: sessionId, instruction: instruction))
    }

    /// Nango Connect UI link for this device's user. Open it in SafariView, then poll `authStatus`.
    func authSession(userId: String) async throws -> URL {
        let r: AuthSessionResponse = try await json("POST", path: "api/v1/auth/github/session",
                                                    body: AuthSessionRequest(userId: userId))
        return r.connectLink
    }

    /// The signed-in GitHub user, or nil if this device hasn't connected yet.
    func authStatus(userId: String) async throws -> GitHubUser? {
        let r: AuthMeResponse = try await json("GET", path: "api/v1/auth/github/me", query: ["user_id": userId])
        guard r.connected, let login = r.login else { return nil }
        return GitHubUser(login: login, avatarURL: r.avatarUrl, name: r.name)
    }

    /// True when the box is up and the model is loaded.
    func isReady() async -> Bool {
        var req = URLRequest(url: config.baseURL.appending(path: "readyz"))
        req.timeoutInterval = 5
        guard let (_, resp) = try? await session.data(for: req) else { return false }
        return (resp as? HTTPURLResponse)?.statusCode == 200
    }

    // MARK: Plain JSON

    private func json<T: Decodable>(_ method: String, path: String, query: [String: String] = [:],
                                    body: (any Encodable)? = nil) async throws -> T {
        var url = config.baseURL.appending(path: path)
        if !query.isEmpty { url.append(queryItems: query.map { URLQueryItem(name: $0.key, value: $0.value) }) }
        var req = URLRequest(url: url)
        req.httpMethod = method
        req.timeoutInterval = 20
        req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONEncoder().encode(body)
        }
        let (data, response) = try await session.data(for: req)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(status) else {
            throw MockupClientError.http(status: status, body: String(decoding: data, as: UTF8.self))
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    // MARK: Streaming

    private func stream<Body: Encodable>(path: String, body: Body) -> AsyncThrowingStream<MockupEvent, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var req = URLRequest(url: config.baseURL.appending(path: path))
                    req.httpMethod = "POST"
                    req.setValue("Bearer \(config.token)", forHTTPHeaderField: "Authorization")
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.setValue("application/x-ndjson", forHTTPHeaderField: "Accept")
                    req.httpBody = try JSONEncoder().encode(body)

                    let (bytes, response) = try await session.bytes(for: req)
                    let status = (response as? HTTPURLResponse)?.statusCode ?? 0
                    guard (200..<300).contains(status) else {
                        var text = ""
                        for try await line in bytes.lines { text += line + "\n"; if text.count > 2000 { break } }
                        throw MockupClientError.http(status: status, body: text)
                    }

                    let decoder = JSONDecoder()
                    for try await line in bytes.lines {
                        guard !line.isEmpty else { continue }
                        // A malformed line shouldn't kill the stream; skip it.
                        guard let event = try? decoder.decode(MockupEvent.self, from: Data(line.utf8)) else { continue }
                        continuation.yield(event)
                        if event.kind == .final || event.kind == .error { break }
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

struct GitHubUser: Equatable {
    var login: String
    var avatarURL: URL?
    var name: String?
}
