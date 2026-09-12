import SwiftUI
import SafariServices

/// In-app Safari for the Nango Connect UI. Shares Safari's cookies, so a user already logged
/// into GitHub skips the password step.
struct SafariView: UIViewControllerRepresentable {
    let url: URL

    func makeUIViewController(context: Context) -> SFSafariViewController {
        let vc = SFSafariViewController(url: url)
        vc.dismissButtonStyle = .close
        return vc
    }

    func updateUIViewController(_ vc: SFSafariViewController, context: Context) {}
}
