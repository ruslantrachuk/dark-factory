import Foundation

/// A feed older than this is "no data": the server stopped writing it.
let staleAfter: TimeInterval = 2700

enum IconState: Equatable {
    case working(agents: Int)
    case waitingQuota
    case idle
    case noData(reason: String, lastGood: Date?)
}

enum FeedError: Error, Equatable, LocalizedError {
    case notConfigured
    case notWrittenYet
    case http(Int)
    /// 401: the server wants a token (FLEET_FEED_TOKEN) and got none, or a wrong one.
    case unauthorized(hadToken: Bool)
    case undecodable
    case unreachable(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured: "feed URL not set"
        case .notWrittenYet: "feed not written yet"
        case let .http(code): "server answered \(code)"
        case .unauthorized(true): "Feed token rejected"
        case .unauthorized(false): "Feed token missing"
        case .undecodable: "feed unreadable"
        case let .unreachable(why): "server unreachable: \(why)"
        }
    }
}

/// No connection for this long is "no data".
let lostAfter: TimeInterval = 10

/// The widget's one-shot fetch. `lastGood` is when the last fresh feed was generated; a stale feed reports its own
/// time instead.
func iconState(feed: Result<Feed, Error>, now: Date, lastGood: Date?) -> IconState {
    switch feed {
    case let .failure(error):
        return .noData(reason: (error as? LocalizedError)?.errorDescription ?? error.localizedDescription,
                       lastGood: lastGood)
    case let .success(feed):
        return feedState(feed, now: now)
    }
}

/// The menu bar on its `/events` connection: the last feed received, whether one ever arrived, and since when the
/// connection is down (nil while connected). Before ten seconds without a connection the last state stands.
func liveState(feed: Feed?, everReceived: Bool, lostAt: Date?, now: Date) -> IconState {
    if let lostAt, now.timeIntervalSince(lostAt) >= lostAfter {
        return .noData(reason: everReceived ? "Connection lost" : "Server unreachable", lastGood: feed?.heavyAt)
    }
    guard let feed else { return .idle }  // connecting: the drop-down says so, the icon stays neutral
    return feedState(feed, now: now)
}

/// When `liveState` can change without a message: ten seconds after the connection dropped, or when the heavy facts
/// turn 45 minutes old. Nil when neither is ahead.
func stateDeadline(feed: Feed?, lostAt: Date?, now: Date) -> Date? {
    let candidates = [lostAt?.addingTimeInterval(lostAfter), feed.map { $0.heavyAt.addingTimeInterval(staleAfter) }]
    return candidates.compactMap { $0 }.filter { $0 > now }.min()
}

private func feedState(_ feed: Feed, now: Date) -> IconState {
    // A time ahead of the Mac's clock counts as fresh.
    if now.timeIntervalSince(feed.heavyAt) > staleAfter {
        return .noData(reason: "Status not updated since \(clock(feed.heavyAt))", lastGood: feed.heavyAt)
    }
    guard feed.projects.contains(where: \.working) else {
        return feed.projects.contains(where: \.waitingQuota) ? .waitingQuota : .idle
    }
    return .working(agents: feed.projects.reduce(0) { $0 + $1.agents })
}

/// The icon blinks once when work starts — not on launch, not while it keeps running.
func shouldBlink(from before: IconState, to after: IconState) -> Bool {
    guard case .working = after else { return false }
    switch before {
    case .working: return false
    case .noData(_, nil): return false  // the first fetch after launch
    default: return true
    }
}

enum RowStatus: Equatable {
    case building(sessions: Int?, agents: Int)
    case waitingQuota(until: Date?, queued: Int)
    case lastWorked(Date?)
}

func rowStatus(_ p: ProjectStatus, quota: Quota?) -> RowStatus {
    if p.working { return .building(sessions: p.busySessions, agents: p.agents) }
    if p.waitingQuota { return .waitingQuota(until: quota?.resetsAt, queued: p.queueReady) }
    return .lastWorked(p.lastWorkedAt)
}

/// The "Working now" section: doing something, or held back only by quota.
func isWorkingNow(_ p: ProjectStatus) -> Bool { p.working || p.waitingQuota }

/// The status line in two parts: the sketch shows the second one muted ("Waiting for quota until 20:40 · 5 queued").
func statusParts(_ status: RowStatus, now: Date, calendar: Calendar = .current) -> (String, String?) {
    switch status {
    case let .building(sessions, agents): ((["Building"] + counts(sessions: sessions, agents: agents)).joined(separator: " · "), nil)
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

/// The summary tile's second line: "2 working · 2 sessions · 3 agents", "Waiting for quota", "Idle", or the no-data
/// reason.
func summaryText(state: IconState, feed: Feed?) -> String {
    if case let .noData(reason, _) = state { return reason }
    guard let feed else { return "" }
    let working = feed.projects.filter(\.working).count
    let agents = feed.projects.reduce(0) { $0 + $1.agents }
    let known = feed.projects.compactMap(\.busySessions)
    let sessions = known.isEmpty ? nil : known.reduce(0, +)
    if working > 0 { return (["\(working) working"] + counts(sessions: sessions, agents: agents)).joined(separator: " · ") }
    return feed.projects.contains(where: \.waitingQuota) ? "Waiting for quota" : "Idle"
}

/// "1 session", "3 agents": each only when above zero; sub-agents are rare, so a zero is noise.
func counts(sessions: Int?, agents: Int) -> [String] {
    var parts: [String] = []
    if let sessions, sessions > 0 { parts.append("\(sessions) session\(sessions == 1 ? "" : "s")") }
    if agents > 0 { parts.append("\(agents) agent\(agents == 1 ? "" : "s")") }
    return parts
}

/// How a stand's checkout relates to origin/main: "on main", "3 behind main", "feat/x · +2 to main · 1 behind".
/// Nil when the server does not know the checkout.
func standFreshness(_ s: Stand) -> String? {
    guard let ref = s.ref else { return nil }
    let behind = s.behind ?? 0, ahead = s.ahead ?? 0
    if ref == "main" && ahead == 0 { return behind > 0 ? "\(behind) behind main" : "on main" }
    var parts = [ref]
    if ahead > 0 { parts.append("+\(ahead) to main") }
    if behind > 0 { parts.append("\(behind) behind") }
    return parts.joined(separator: " · ")
}

/// "2h 10m", "45m", "3d 4h" until `date`; nil once it is past.
func untilText(_ date: Date, now: Date) -> String? {
    let minutes = Int(date.timeIntervalSince(now) / 60)
    guard minutes > 0 else { return nil }
    if minutes < 60 { return "\(minutes)m" }
    if minutes < 24 * 60 { return minutes % 60 == 0 ? "\(minutes / 60)h" : "\(minutes / 60)h \(minutes % 60)m" }
    let hours = minutes / 60
    return hours % 24 == 0 ? "\(hours / 24)d" : "\(hours / 24)d \(hours % 24)h"
}

/// "3 · client modules · fence standard".
func levelText(_ l: Level) -> String {
    (["\(l.level) · \(l.name)"] + [l.fence.map { "fence \($0)" }].compactMap { $0 }).joined(separator: " · ")
}

/// The folded Modules line: "4 of 5 installed"; nil when the server lists none.
func modulesText(_ l: Level) -> String? {
    l.modules.isEmpty ? nil : "\(l.modules.filter(\.installed).count) of \(l.modules.count) installed"
}

/// The factory needs a look: a server job failed, is not installed or is off, or an enabled routine failed.
/// A routine turned off on purpose is not a problem.
func scheduledNeedsAttention(_ s: Scheduled?) -> Bool {
    let server = s?.server ?? []
    let cloud = s?.cloud?.routines ?? []
    return server.contains { $0.result == "failed" || $0.notRunning }
        || cloud.contains { $0.enabled && $0.result == "failed" }
}

/// A job's name for people; an unknown one falls back to the server's title.
func jobLabel(_ j: Job) -> String {
    let known = ["janitor": "Janitor", "analytics": "Analytics", "watch": "Watcher", "feed": "Feed",
                 "routines": "Cloud check", "stand": "Stand", "desk-watch": "On-call guard"]
    return known[j.name] ?? j.title ?? j.name
}

/// When it runs: "every 15min" as is; a calendar one by its next run, "next 06:30" or "next 1 Nov 06:30".
func whenText(schedule: String?, nextAt: Date?, now: Date, calendar: Calendar = .current) -> String? {
    if let schedule, schedule.hasPrefix("every ") { return schedule }
    guard let next = nextAt else { return nil }
    if calendar.isDate(next, inSameDayAs: now) { return "next \(clock(next, calendar: calendar))" }
    if let tomorrow = calendar.date(byAdding: .day, value: 1, to: now), calendar.isDate(next, inSameDayAs: tomorrow) {
        return "next tomorrow \(clock(next, calendar: calendar))"
    }
    return "next \(dayAndTime(next, now: now, calendar: calendar))"
}

/// The job's state after its schedule: "not installed", "off", "failed", "running"; nil when all is well.
func jobProblem(_ j: Job) -> String? {
    if j.installed == false { return "not installed" }
    if j.enabled == false { return "off" }
    if j.result == "failed" { return "failed" }
    if j.result == "running" { return "running" }
    return nil
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
