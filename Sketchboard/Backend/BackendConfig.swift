import Foundation

/// Where the harness lives and how to authenticate. See API.md at the repo root.
///
/// Resolution order: in-app override (Settings sheet, stored in UserDefaults), then the
/// values baked in at build time from `Sketchboard/Config/Secrets.xcconfig`.
struct BackendConfig: Equatable {
    var baseURL: URL
    var token: String

    static let defaultsURLKey = "GEMMA_BASE_URL"
    static let defaultsTokenKey = "GEMMA_TOKEN"

    /// nil until someone configures a URL and token.
    static var current: BackendConfig? {
        let defaults = UserDefaults.standard
        let info = Bundle.main.infoDictionary ?? [:]
        let urlString = nonEmpty(defaults.string(forKey: defaultsURLKey)) ?? nonEmpty(info["GemmaBaseURL"] as? String)
        let token = nonEmpty(defaults.string(forKey: defaultsTokenKey)) ?? nonEmpty(info["GemmaToken"] as? String)
        guard let urlString, let token, let url = URL(string: urlString), url.host != nil else { return nil }
        return BackendConfig(baseURL: url, token: token)
    }

    static func saveOverride(urlString: String, token: String) {
        let defaults = UserDefaults.standard
        defaults.set(urlString.trimmingCharacters(in: .whitespacesAndNewlines), forKey: defaultsURLKey)
        defaults.set(token.trimmingCharacters(in: .whitespacesAndNewlines), forKey: defaultsTokenKey)
    }

    static func clearOverride() {
        UserDefaults.standard.removeObject(forKey: defaultsURLKey)
        UserDefaults.standard.removeObject(forKey: defaultsTokenKey)
    }

    private static func nonEmpty(_ s: String?) -> String? {
        guard let s = s?.trimmingCharacters(in: .whitespacesAndNewlines), !s.isEmpty else { return nil }
        return s
    }
}
