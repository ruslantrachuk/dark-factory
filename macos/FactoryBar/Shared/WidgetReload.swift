import Foundation

/// What the widget shows, as one string: the summary, quota, its five project tiles and the 15-minute update time.
/// `generated_at`, which moves on every push, is left out, so a push that changes nothing visible reloads nothing.
func widgetSignature(_ feed: Feed) -> String {
    let ordered = feed.projects.filter(isWorkingNow) + feed.projects.filter { !isWorkingNow($0) }
    let tiles = ordered.prefix(5).map { p in
        [p.name, "\(rowStatus(p, quota: feed.quota))", "\(p.oncall.installed)\(p.oncall.running)",
         "\(p.watchdog.installed)\(p.watchdog.ok)", p.link?.absoluteString ?? ""].joined(separator: "|")
    }
    let quota = feed.quota.map { "\(Int($0.fiveHour.rounded()))/\(Int($0.sevenDay.rounded()))" } ?? "-"
    let state = feedStateSummary(feed)
    return ([state, quota, "\(ordered.count)", "\(feed.heavyAt.timeIntervalSince1970)"] + tiles).joined(separator: "\n")
}

private func feedStateSummary(_ feed: Feed) -> String {
    "\(feed.projects.filter(\.working).count)·\(feed.projects.reduce(0) { $0 + $1.agents })"
}

/// At most one widget reload per 30 s: a change inside the window is reloaded when it ends.
struct WidgetThrottle {
    enum Decision: Equatable {
        case none
        case now
        case at(Date)
    }

    static let interval: TimeInterval = 30
    private var lastReload: Date?
    private var lastSignature: String?

    mutating func offer(_ signature: String, now: Date) -> Decision {
        guard signature != lastSignature else { return .none }
        lastSignature = signature
        guard let last = lastReload, now.timeIntervalSince(last) < Self.interval else {
            lastReload = now
            return .now
        }
        return .at(last.addingTimeInterval(Self.interval))
    }

    mutating func fired(at date: Date) { lastReload = date }
}
