import AppKit
import SwiftUI

/// Colors of the agreed sketch, light and dark.
enum Palette {
    static let ok = dynamic(0x2F9E5B, 0x45C27A)
    static let warn = dynamic(0xC98A12, 0xE2A93A)
    static let quota = dynamic(0xE06A1B, 0xF5893A)
    static let off = dynamic(0xB9C0C9, 0x4A5361)
    static let bad = dynamic(0xC94A3A, 0xE46B5B)
    static let accent = dynamic(0x3B6FD8, 0x7AA2F0)
    static let mute = dynamic(0x6A7686, 0x98A3B2)
    static let faint = dynamic(0xA4ADB8, 0x5F6A78)
    static let line = NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
            ? NSColor.white.withAlphaComponent(0.08) : NSColor(red: 30 / 255, green: 40 / 255, blue: 55 / 255, alpha: 0.09)
    }

    private static func dynamic(_ light: Int, _ dark: Int) -> NSColor {
        NSColor(name: nil) { appearance in
            rgb(appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua ? dark : light)
        }
    }

    private static func rgb(_ hex: Int) -> NSColor {
        NSColor(srgbRed: CGFloat(hex >> 16 & 0xFF) / 255, green: CGFloat(hex >> 8 & 0xFF) / 255,
                blue: CGFloat(hex & 0xFF) / 255, alpha: 1)
    }
}

extension IconState {
    var isNoData: Bool {
        if case .noData = self { return true }
        return false
    }

    /// Filled like the app icon while work runs or waits for quota; outlined otherwise.
    var isFilled: Bool {
        switch self {
        case .working, .waitingQuota: true
        case .idle, .noData: false
        }
    }

    var nsColor: NSColor {
        switch self {
        case .working: Palette.ok
        case .waitingQuota: Palette.quota
        case .idle: Palette.mute
        case .noData: Palette.bad
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

/// The factory glyph of the sketch (two sheds and a chimney) in a 24×24 box, y down: filled when work is running or
/// waits for quota, outlined otherwise.
enum FactoryGlyph {
    static func path(filled: Bool) -> CGPath {
        let p = CGMutablePath()
        if filled {
            p.addLines(between: [(2, 21), (2, 10), (7, 13), (7, 10), (12, 13), (12, 10), (17, 13), (17, 4), (21, 4),
                                 (21, 21)].map { CGPoint(x: $0.0, y: $0.1) })
        } else {
            p.addLines(between: [(2.9, 20.1), (2.9, 11.6), (7.9, 14.6), (7.9, 11.6), (12.9, 14.6), (12.9, 11.6),
                                 (17.9, 14.6), (17.9, 4.9), (20.1, 4.9), (20.1, 20.1)].map { CGPoint(x: $0.0, y: $0.1) })
        }
        p.closeSubpath()
        return p
    }

    static func draw(in ctx: CGContext, rect: CGRect, filled: Bool, color: NSColor) {
        ctx.saveGState()
        ctx.translateBy(x: rect.minX, y: rect.minY)
        ctx.scaleBy(x: rect.width / 24, y: rect.height / 24)
        ctx.addPath(path(filled: filled))
        if filled {
            ctx.setFillColor(color.cgColor)
            ctx.fillPath()
        } else {
            ctx.setStrokeColor(color.cgColor)
            ctx.setLineWidth(1.8)
            ctx.setLineJoin(.round)
            ctx.strokePath()
        }
        ctx.restoreGState()
    }
}

/// The menu bar draws SwiftUI images and text as templates (monochrome); one non-template NSImage keeps the glyph
/// and its badge in the state's color. `dim` is the low point of the slow pulse while work is running.
func menuBarImage(_ state: IconState, dim: Bool = false) -> NSImage {
    menuBarImage(state, dim: dim, showBadge: true)
}

func menuBarImage(_ state: IconState, dim: Bool, showBadge: Bool) -> NSImage {
    let font = NSFont.monospacedSystemFont(ofSize: 13, weight: .semibold)
    let badge = (showBadge ? state.badge : nil).map { NSAttributedString(string: $0, attributes: [.font: font]) }
    let glyph: CGFloat = 19, gap: CGFloat = 3, height: CGFloat = 22
    let width = glyph + (badge.map { gap + ceil($0.size().width) } ?? 0)
    let image = NSImage(size: NSSize(width: width, height: height), flipped: true) { _ in
        guard let ctx = NSGraphicsContext.current?.cgContext else { return false }
        // Drawn at display time, so the dynamic color resolves against the menu bar's own appearance.
        let color = state.nsColor.withAlphaComponent(dim ? 0.35 : 1)
        FactoryGlyph.draw(in: ctx, rect: CGRect(x: 0, y: (height - glyph) / 2, width: glyph, height: glyph),
                          filled: state.isFilled, color: color)
        if let badge {
            let text = NSAttributedString(string: badge.string, attributes: [.font: font, .foregroundColor: color])
            text.draw(at: NSPoint(x: glyph + gap, y: (height - text.size().height) / 2))
        }
        return true
    }
    image.isTemplate = false
    image.accessibilityDescription = "Factory"
    return image
}

/// The glyph as a SwiftUI shape, for the widget's no-data line.
struct FactoryShape: Shape {
    let filled: Bool

    func path(in rect: CGRect) -> Path {
        Path(FactoryGlyph.path(filled: filled))
            .applying(CGAffineTransform(scaleX: rect.width / 24, y: rect.height / 24))
    }
}

/// Person-bubble for the On-call, check-shield for the watchdog, display for the dev stands: green when on (a stand:
/// at least one running), grey when off, absent when not installed or no stand is declared.
struct ModuleIcons: View {
    let project: ProjectStatus

    var body: some View {
        HStack(spacing: 4) {
            if project.oncall.installed {
                Image(systemName: "person.bubble")
                    .foregroundStyle(project.oncall.running ? Color.green : Color.secondary.opacity(0.5))
                    .help(project.oncall.running ? "On-call running" : "On-call not running")
            }
            if project.watchdog.installed {
                Image(systemName: "checkmark.shield.fill")
                    .foregroundStyle(project.watchdog.ok ? Color.green : Color.secondary.opacity(0.5))
                    .help(project.watchdog.ok ? "Watchdog on" : "Watchdog off")
            }
            if let stands = project.stands, !stands.isEmpty {
                let running = stands.filter(\.running).count
                Image(systemName: "display")
                    .foregroundStyle(running > 0 ? Color.green : Color.secondary.opacity(0.5))
                    .help("Stands: \(running) of \(stands.count) running")
            }
        }
        .font(.system(size: 12))
    }
}
