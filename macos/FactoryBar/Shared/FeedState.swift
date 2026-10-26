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

/// The status line in two parts: the sketch shows the second one muted ("Waiting for quota until 20:40 · 5 queued").
func statusParts(_ status: RowStatus, now: Date, calendar: Calendar = .current) -> (String, String?) {
    switch status {
    case let .building(agents) where agents > 0: ("Building · \(agents) agent\(agents == 1 ? "" : "s")", nil)
    case .building: ("Building", nil)
    case let .waitingQuota(until?, queued): ("Waiting for quota until \(clock(until, calendar: calendar))", "\(queued) queued")
    case let .waitingQuota(nil, queued): ("Waiting for quota", "\(queued) queued")
    case let .lastWorked(when?): ("Last worked \(dayAndTime(when, now: now, calendar: calendar))", nil)
    case .lastWorked(nil): ("Not worked yet", nil)
    }
}

func statusText(_ status: RowStatus, now: Date, calendar: Calendar = .current) -> String {
    let (main, tail) = statusParts(status, now: now, calendar: calendar)
    return tail.map { "\(main) · \($0)" } ?? main
}

/// The summary tile's second line: "2 working · 3 agents", "Waiting for quota", "Idle", or the no-data reason.
func summaryText(state: IconState, feed: Feed?) -> String {
    if case let .noData(reason, _) = state { return reason }
    guard let feed else { return "" }
    let working = feed.projects.filter(\.working).count
    let agents = feed.projects.reduce(0) { $0 + $1.agents }
    if working > 0 { return agents > 0 ? "\(working) working · \(agents) agent\(agents == 1 ? "" : "s")" : "\(working) working" }
    return feed.projects.contains(where: \.waitingQuota) ? "Waiting for quota" : "Idle"
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
func clock(_ date: Date, calendar: Calendar = .current) -> String {
    let f = DateFormatter()
    f.timeZone = calendar.timeZone
    f.dateFormat = "HH:mm"
    return f.string(from: date)
}

/// "today 14:02", "yesterday 22:10", "24 Oct 06:11".
func dayAndTime(_ date: Date, now: Date, calendar: Calendar = .current) -> String {
    if calendar.isDate(date, inSameDayAs: now) { return "today \(clock(date, calendar: calendar))" }
    if let yesterday = calendar.date(byAdding: .day, value: -1, to: now), calendar.isDate(date, inSameDayAs: yesterday) {
        return "yesterday \(clock(date, calendar: calendar))"
    }
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.timeZone = calendar.timeZone
    f.dateFormat = "d MMM HH:mm"
    return f.string(from: date)
}

/// An http(s) URL with a host, from what the owner typed.
func validFeedURL(_ text: String) -> URL? {
    guard let url = URL(string: text.trimmingCharacters(in: .whitespaces)),
          ["http", "https"].contains(url.scheme ?? ""), url.host != nil else { return nil }
    return url
}
