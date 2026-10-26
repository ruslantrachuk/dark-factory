import AppKit
import SwiftUI

extension IconState {
    var symbol: String {
        if case .working = self { return "building.2.fill" }
        return "building.2"
    }

    var color: Color {
        switch self {
        case .working: .green
        case .idle: .secondary
        case .noData: .red
        }
    }

    var nsColor: NSColor {
        switch self {
        case .working: .systemGreen
        case .idle: .secondaryLabelColor
        case .noData: .systemRed
        }
    }

    /// Next to the glyph: the agent count when > 0, "?" in no data, else nothing.
    var badge: String? {
        switch self {
        case let .working(agents) where agents > 0: "\(agents)"
        case .noData: "?"
        default: nil
        }
    }
}

/// The glyph with its badge, for the drop-down header and the widget.
struct StateGlyph: View {
    let state: IconState

    var body: some View {
        HStack(spacing: 2) {
            Image(systemName: state.symbol)
            if let badge = state.badge { Text(badge).fontWeight(.semibold).monospacedDigit() }
        }
        .foregroundStyle(state.color)
    }
}

/// The menu bar draws SwiftUI images as templates (monochrome); a non-template NSImage keeps the state's color.
func menuBarImage(_ state: IconState) -> NSImage {
    let config = NSImage.SymbolConfiguration(pointSize: 14, weight: .regular)
        .applying(.init(paletteColors: [state.nsColor]))
    let image = NSImage(systemSymbolName: state.symbol, accessibilityDescription: "Factory")?
        .withSymbolConfiguration(config) ?? NSImage()
    image.isTemplate = false
    return image
}

/// Headset for the On-call, shield for the watchdog: colored when on, grey when off, absent when not installed.
struct ModuleIcons: View {
    let project: ProjectStatus

    var body: some View {
        HStack(spacing: 4) {
            if project.oncall.installed {
                Image(systemName: "headphones")
                    .foregroundStyle(project.oncall.running ? Color.blue : Color.gray)
                    .help(project.oncall.running ? "On-call running" : "On-call not running")
            }
            if project.watchdog.installed {
                Image(systemName: "shield.fill")
                    .foregroundStyle(project.watchdog.ok ? Color.green : Color.gray)
                    .help(project.watchdog.ok ? "Watchdog on" : "Watchdog off")
            }
        }
        .font(.caption)
    }
}
