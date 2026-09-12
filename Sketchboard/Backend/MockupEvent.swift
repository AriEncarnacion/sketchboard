import Foundation

/// One line of the NDJSON stream from `/api/v1/mockup` or `/api/v1/edit`. See API.md.
///
/// Modelled as one struct with optional fields rather than an enum so that new event
/// types or new fields from the server never fail decoding on an older app build.
struct MockupEvent: Decodable, Sendable {
    enum Kind: String, Sendable {
        case session, status, draft, checks, verdict, approved, final, error
        case unknown
    }

    let type: String
    var kind: Kind { Kind(rawValue: type) ?? .unknown }

    // session
    let sessionId: String?
    // status / error
    let message: String?
    // draft / checks / verdict / approved / final
    let iteration: Int?
    let html: String?
    let notes: String?
    let seconds: Double?
    let tokens: Int?
    let clean: Bool?
    let problems: String?
    let score: Int?
    let approved: Bool?
    let chosen: Int?
    let iterations: Int?
    let pngBase64: String?
    // draft / final: the screen format the server composed for
    let format: String?
    let width: Int?
    let height: Int?

    enum CodingKeys: String, CodingKey {
        case type, message, iteration, html, notes, seconds, tokens, clean, problems, score, approved, chosen, iterations, format, width, height
        case sessionId = "session_id"
        case pngBase64 = "png_base64"
    }
}
