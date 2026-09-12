# Sketchboard (iPad, SwiftUI + PencilKit)

- Project file is generated: edit `project.yml`, never `Sketchboard.xcodeproj`. After adding/removing files run `xcodegen generate`.
- Build: `xcodebuild -scheme Sketchboard -destination 'platform=iOS Simulator,name=iPad Pro 11-inch (M5)' CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO build 2>&1 | xcbeautify`
- Run in simulator: open `Sketchboard.xcodeproj` in Xcode and press Run, or use the Xcode MCP tools.
- Min iOS 18, iPad only. Prefer stdlib/Apple frameworks; no new dependencies without asking.
- Backend: Gemma 4 via Ollama, OpenAI-compatible endpoint. App sends a JPEG of the hand-drawn sketch; server returns a UI mockup (SwiftUI/HTML description); app renders it in place. Think Claude Design, but native on the iPad.
