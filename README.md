# Sketchboard

iPad app: sketch a UI with Apple Pencil, Gemma 4 turns it into a rendered mockup. Claude Design, but native on the iPad.

## Setup (every Mac, ~10 min after Xcode is installed)

1. Install Xcode 26 from the Mac App Store. Open it once and let it finish installing components.
2. `brew install xcodegen xcbeautify`
3. Clone this repo, then in it: `xcodegen generate` (creates `Sketchboard.xcodeproj`, which is gitignored).
4. `open Sketchboard.xcodeproj`
5. Top bar: pick an iPad simulator (e.g. iPad Pro 11-inch) and press Run (⌘R). You should see "Hello, Sketchboard" and be able to draw with the mouse.

## Rules

- Edit `project.yml` and files in `Sketchboard/`. Never edit `Sketchboard.xcodeproj` by hand.
- Added or removed a file? Run `xcodegen generate` again. Pulled? Run it again.
- Terminal build (what the AI agents use):
  `xcodebuild -scheme Sketchboard -destination 'platform=iOS Simulator,name=iPad Pro 11-inch (M5)' CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO build 2>&1 | xcbeautify`

## Real iPad (one person only)

1. Xcode → Settings → Accounts → + → sign in with Apple ID (creates a free Personal Team).
2. Project → Sketchboard target → Signing & Capabilities → check "Automatically manage signing", pick your Personal Team.
3. Plug in the iPad, tap Trust on it. iPad: Settings → Privacy & Security → Developer Mode → on, reboot.
4. Pick the iPad in the scheme dropdown, Run. On first launch: iPad Settings → General → VPN & Device Management → trust your Apple ID. Run again.
5. Free signing expires after 7 days; just Run from Xcode again.

## Agents

Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`. To let them drive Xcode, enable Xcode → Settings → Intelligence → Model Context Protocol → Xcode Tools, then follow Apple's docs to register `xcrun mcpbridge` with your agent.
