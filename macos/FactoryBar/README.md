# FactoryBar

The factory at a glance on the Mac: a menu bar icon, a drop-down and a large desktop widget, all read from the
`status.json` feed that `fleet.py serve` publishes on a private address (see
`openspec/changes/menu-bar-status/design.md`). The app only reads; it never changes anything on the server.

## Prerequisites

- Xcode (15 or newer) and macOS 14 or newer.
- XcodeGen: `brew install xcodegen`.
- A free Apple ID added in Xcode → Settings → Accounts (a paid membership is not needed).
- The server serves the feed: `FLEET_FEED_ADDR` set in the server's `fleet.env` and `fleet.py provision` run.

## Build and run

```bash
cd macos/FactoryBar
xcodegen
open FactoryBar.xcodeproj
```

Once: select each target (`FactoryBar`, `FactoryBarWidget`) → Signing & Capabilities → Team → your personal team.
Then Run. The `.xcodeproj` is generated — after pulling changes to `project.yml`, run `xcodegen` again.

Later builds and the tests from the command line:

```bash
xcodebuild -scheme FactoryBar build
xcodebuild test -scheme FactoryBar -destination 'platform=macOS'
```

If `xcodebuild` says the active developer directory is the command line tools, prefix the command with
`DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` (or switch it once with `sudo xcode-select -s`).

## Start at login

Copy the built app to `/Applications` first (Xcode: Product → Show Build Folder, or `build/Build/Products/Debug/`
after `xcodebuild`): a login item points at the app's path, and the build folder can be cleaned. Launch the copy, then
in the drop-down: gear → **Launch at Login**. It appears in System Settings → General → Login Items and can be turned
off there too.

## The feed URL

- **Menu bar:** on first launch the drop-down asks for the feed URL, e.g. `http://100.x.y.z:8765/status.json`
  (the server's Tailscale address and the port from `FLEET_FEED_ADDR`). Change it later with "Feed URL…" in the
  drop-down.
- **Widget:** right-click the widget → Edit "Factory" → Feed URL. The widget does not share settings with the app.

## What it shows

- Icon: filled green with the number of running agents — work is running; outlined grey — nothing running;
  outlined red with "?" — no data (the server is unreachable, answers with an error, or the feed is older than
  45 minutes).
- Drop-down and widget: quota, projects working now and idle, On-call (headset) and watchdog (shield) icons, the
  status line per project, when the feed was updated. A click on a project opens its session link in Claude.
