# Sketchboard: teammate setup

Two values you'll need from Justin (Slack, not the repo): the **server URL** and the
**bearer token**. The URL changes every time the GPU box is relaunched.

## 1. Run the iPad app (everyone, ~10 min)

1. Install Xcode 26 from the Mac App Store. Open it once so it finishes installing components.
2. `brew install xcodegen xcbeautify`
3. Clone the repo and, inside it:
   ```bash
   xcodegen generate
   ```
   Re-run this after every pull and whenever a Swift file is added or removed.
4. Point the app at the server:
   ```bash
   cp Sketchboard/Config/Secrets.xcconfig.example Sketchboard/Config/Secrets.xcconfig
   ```
   Edit `Secrets.xcconfig` with the URL and token. Keep the odd `http:/$()/` spelling;
   xcconfig treats `//` as a comment. The file is git-ignored.
   (Skip this step if you prefer: the gear icon in the app lets you type both in at runtime.)
5. `open Sketchboard.xcodeproj`, pick an iPad simulator (iPad Pro 11-inch), press Run.
6. Draw a screen, optionally type a description, tap **Generate**. The green dot next to
   the status text means the server is reachable. Type a change like "make the button
   green" and tap **Apply** to edit the result.

Terminal build, same thing the AI agents run:
```bash
xcodebuild -scheme Sketchboard -destination 'platform=iOS Simulator,name=iPad Pro 11-inch (M4)' CODE_SIGN_IDENTITY="" CODE_SIGNING_REQUIRED=NO build 2>&1 | xcbeautify
```
Use whatever iPad simulator `xcrun simctl list devices available` shows on your Mac.

## 2. Work on the server (only if you're touching `server/`)

```bash
brew install jq uv
cd server
uv venv -p 3.12 && uv pip install -r requirements.txt
.venv/bin/playwright install chromium     # for the render/judge tests
.venv/bin/python -m pytest -q
```

The harness runs on the GPU box, not locally. To push a change to the box you need the
Lambda tooling below, then `lambda/lambdactl.sh deploy`. It's an rsync plus restart,
about 30 seconds, no relaunch of the GPU.

Read `server/DESIGN.md` before changing prompts or the loop. `API.md` is the contract
with the app: change both sides together.

## 3. Drive the GPU box (only if you'll deploy or restart it)

```bash
cp lambda/.env.example lambda/.env
```
Fill in `LAMBDA_API_KEY` (from Justin) and set `LAMBDA_SSH_KEY_FILE` to a public key you
own. Then:

```bash
lambda/lambdactl.sh check      # API key works?
lambda/lambdactl.sh status     # is the box up, what's its IP
lambda/lambdactl.sh deploy     # push server/ to the box
lambda/lambdactl.sh mockup server/samples/login.png "login screen"   # end-to-end test from the CLI
```

`lambda/lambdactl.sh` with no arguments lists every command. Full notes in `lambda/README.md`.

Note: SSH access to the box (needed by `deploy`, `ssh`, `logs`) currently works only for
the key the box was launched with. Ask Justin to add yours, or to relaunch with it.

## Rules of the road

- The box bills by the hour. Whoever is last to use it for the day runs
  `lambda/lambdactl.sh terminate`. Relaunch is `launch` then `wait`, about 5 minutes, and
  produces a new URL that everyone needs.
- Never commit `lambda/.env`, `Sketchboard/Config/Secrets.xcconfig`, or the token.
  They're git-ignored; keep it that way.
- Edit `project.yml`, never `Sketchboard.xcodeproj`.
- Branch from `main`, open a PR. `ContentView.swift` is where merges collide; pull `main`
  into your branch early if you touch it.
