import SwiftUI
import WebKit

/// Renders the self-contained HTML the server sends. No network access is needed by the
/// content (see API.md), so we load it as a string with a nil base URL.
struct MockupWebView: UIViewRepresentable {
    let html: String
    /// The width the server composed for (draft/final events). Pinning the layout viewport
    /// to it means WebKit scales the page to whatever width the view has instead of
    /// laying out at some other width and clipping.
    var designWidth: Int = 1180

    private static func fitViewport(_ designWidth: Int) -> String { """
    (function() {
      var m = document.querySelector('meta[name=viewport]');
      if (!m) {
        m = document.createElement('meta');
        m.setAttribute('name', 'viewport');
        (document.head || document.documentElement).appendChild(m);
      }
      m.setAttribute('content', 'width=\(designWidth), shrink-to-fit=yes');
    })();
    """ }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.defaultWebpagePreferences.allowsContentJavaScript = true
        // Runs for every load, so server HTML and the sample page size the same way.
        config.userContentController.addUserScript(
            WKUserScript(source: Self.fitViewport(designWidth), injectionTime: .atDocumentEnd, forMainFrameOnly: true)
        )
        let view = WKWebView(frame: .zero, configuration: config)
        view.isOpaque = false
        view.backgroundColor = .white
        view.scrollView.bounces = false
        view.scrollView.contentInsetAdjustmentBehavior = .never
        return view
    }

    func updateUIView(_ view: WKWebView, context: Context) {
        guard context.coordinator.lastHTML != html || context.coordinator.lastWidth != designWidth else { return }
        context.coordinator.lastHTML = html
        context.coordinator.lastWidth = designWidth
        view.configuration.userContentController.removeAllUserScripts()
        view.configuration.userContentController.addUserScript(
            WKUserScript(source: Self.fitViewport(designWidth), injectionTime: .atDocumentEnd, forMainFrameOnly: true)
        )
        view.loadHTMLString(html, baseURL: nil)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    final class Coordinator {
        var lastHTML: String?
        var lastWidth: Int?
    }
}
