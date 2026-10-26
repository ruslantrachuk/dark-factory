import Foundation

/// A feed older than this is "no data": the server stopped writing it.
let staleAfter: TimeInterval = 2700

enum IconState: Equatable {
    case working(agents: Int)
    case idle
    case noData(reason: String, lastGood: Date?)
}

enum FeedError: Error, Equatable, LocalizedError {
    case notConfigured
    case notWrittenYet
    case http(Int)
    case undecodable
    case unreachable(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: "feed URL not set"
        case .notWrittenYet: "feed not written yet"
        case let .http(code): "server answered \(code)"
        case .undecodable: "feed unreadable"
        case let .unreachable(why): "server unreachable: \(why)"
        }
    }
}

/// `lastGood` is when the last fresh feed was generated; a stale feed reports its own time instead.
func iconState(feed: Result<Feed, Error>, now: Date, lastGood: Date?) -> IconState {
    switch feed {
    case let .failure(error):
        return .noData(reason: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription,
                       lastGood: lastGood)
    case let .success(feed):
        // A generated_at ahead of the Mac's clock counts as fresh.
        let age = now.timeIntervalSince(feed.generatedAt)
        if age > staleAfter {
            return .noData(reason: "feed is \(Int(age / 60)) min old", lastGood: feed.generatedAt)
        }
        // A project that only waits for quota is listed under "Working now" but leaves the icon idle.
        guard feed.projects.contains(where: \.working) else { return .idle }
        return .working(agents: feed.projects.reduce(0) { $0 + $1.agents })
    }
}

enum RowStatus: Equatable {
    case building(agents: Int)
    case waitingQuota(until: Date?, queued: Int)
    case lastWorked(Date?)
}

func rowStatus(_ p: ProjectStatus, quota: Quota?) -> RowStatus {
    if p.working { return .building(agents: p.agents) }
    if p.waitingQuota { return .waitingQuota(until: quota?.resetsAt, queued: p.queueReady) }
    return .lastWorked(p.lastWorkedAt)
}

/// The "Working now" section: doing something, or held back only by quota.
func isWorkingNow(_ p: ProjectStatus) -> Bool { p.working || p.waitingQuota }

func statusText(_ status: RowStatus, now: Date) -> String {
    switch status {
    case let .building(agents) where agents > 0: "Building · \(agents) agent\(agents == 1 ? "" : "s")"
    case .building: "Building"
    case let .waitingQuota(until?, queued): "Waiting for quota until \(clock(until)) · \(queued) queued"
    case let .waitingQuota(nil, queued): "Waiting for quota · \(queued) queued"
    case let .lastWorked(when?): "Last worked \(ago(when, now: now))"
    case .lastWorked(nil): "Not worked yet"
    }
}

/// "On-call wrote N min ago" within the last hour, else nil.
func oncallLine(_ p: ProjectStatus, now: Date) -> String? {
    guard p.oncall.installed, let said = p.oncall.lastMessageAt else { return nil }
    let age = max(0, now.timeIntervalSince(said))
    guard age <= 3600 else { return nil }
    return "On-call wrote \(Int(age / 60)) min ago"
}

func quotaText(_ quota: Quota?) -> String {
    guard let q = quota else { return "quota unknown" }
    return "5h \(Int(q.fiveHour.rounded()))% · 7d \(Int(q.sevenDay.rounded()))%"
}

/// HH:MM in the Mac's local time.
func clock(_ date: Date) -> String {
    let f = DateFormatter()
    f.dateFormat = "HH:mm"
    return f.string(from: date)
}

func ago(_ date: Date, now: Date) -> String {
    let minutes = max(0, Int(now.timeIntervalSince(date) / 60))
    if minutes < 1 { return "just now" }
    if minutes < 60 { return "\(minutes) min ago" }
    if minutes < 48 * 60 { return "\(minutes / 60) h ago" }
    return "\(minutes / 1440) d ago"
}

/// An http(s) URL with a host, from what the owner typed.
func validFeedURL(_ text: String) -> URL? {
    guard let url = URL(string: text.trimmingCharacters(in: .whitespaces)),
          ["http", "https"].contains(url.scheme ?? ""), url.host != nil else { return nil }
    return url
}
