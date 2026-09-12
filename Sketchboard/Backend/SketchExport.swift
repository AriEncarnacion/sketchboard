import PencilKit
import UIKit

extension PKDrawing {
    /// The drawing flattened onto a white background as JPEG, at the given canvas size.
    /// The server expects roughly 1180×820 for an iPad landscape canvas; larger is fine.
    func sketchJPEG(canvasSize: CGSize, scale: CGFloat = 1, quality: CGFloat = 0.85) -> Data? {
        let size = CGSize(width: max(canvasSize.width, 16), height: max(canvasSize.height, 16))
        let rect = CGRect(origin: .zero, size: size)
        let format = UIGraphicsImageRendererFormat()
        format.scale = scale
        format.opaque = true
        let strokes = image(from: rect, scale: scale)
        let flattened = UIGraphicsImageRenderer(size: size, format: format).image { ctx in
            UIColor.white.setFill()
            ctx.fill(rect)
            strokes.draw(in: rect)
        }
        return flattened.jpegData(compressionQuality: quality)
    }
}
