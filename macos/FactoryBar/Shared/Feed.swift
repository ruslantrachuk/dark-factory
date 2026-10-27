import AppKit

/// `status.json` as written by `fleet.py feed` (schema version 1).
struct Feed: Decodable, Equatable {
    let version: Int
    let generatedAt: Date
    let quota: Quota?
    let projects: [ProjectStatus]
    /// Version 2: when the heavy facts (On-call, watchdog, queue) were built; `generatedAt` moves on every push.
    var fullAt: Date? = nil

    /// The age that matters for "no data": the heavy facts' time, or the whole document's in version 1.
    var heavyAt: Date { fullAt ?? generatedAt }

    static func decode(_ data: Data) throws -> Feed {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { d in
            let text = try d.singleValueContainer().decode(String.self)
            guard let date = parseISO(text) else {
                throw DecodingError.dataCorrupted(.init(codingPath: d.codingPath, debugDescription: "not ISO 8601: \(text)"))
            }
            return date
        }
        return try decoder.decode(Feed.self, from: data)
    }
}

struct Quota: Decodable, Equatable {
    let fiveHour: Double
    let sevenDay: Double
    let noNewWork: Bool
    let resetsAt: Date?
    let asOf: Date?
    /// When each window resets; nil from a server that does not report them.
    var resets: Resets? = nil

    struct Resets: Decodable, Equatable {
        let fiveHour: Date?
        let sevenDay: Date?
    }
}

struct ProjectStatus: Decodable, Equatable, Identifiable {
    struct Oncall: Decodable, Equatable {
        let installed: Bool
        let running: Bool
        let lastMessageAt: Date?
        /// The On-call's own Claude session; nil from a server that does not report it.
        var sessionUrl: String? = nil

        var link: URL? { claudeLink(sessionUrl) }
    }

    struct Watchdog: Decodable, Equatable {
        let installed: Bool
        let ok: Bool
    }

    let name: String
    let working: Bool
    let agents: Int
    let waitingQuota: Bool
    let queueReady: Int
    let lastWorkedAt: Date?
    let sessionUrl: String?
    let oncall: Oncall
    let watchdog: Watchdog
    let error: String?
    /// Version 2: live sessions of the project that are mid-turn; nil without the server's session registry.
    var busySessions: Int? = nil
    /// The project's dev stands from `scripts/stands.json`; nil from a server that does not report them.
    var stands: [Stand]? = nil
    /// Where the project stands on the level ladder (`level.py status`); nil from a server that does not report it.
    var level: Level? = nil

    var id: String { name }

    /// The link a click opens.
    var link: URL? { claudeLink(sessionUrl) }
}

/// Only Claude's own https links: the app never opens whatever else a feed may carry.
private func claudeLink(_ text: String?) -> URL? {
    guard let text, let url = URL(string: text), url.scheme == "https", url.host == "claude.ai" else { return nil }
    return url
}

/// The project's rung on the level ladder, its fence and which canon modules it has.
struct Level: Decodable, Equatable {
    struct Module: Decodable, Equatable {
        let name: String
        let installed: Bool
    }

    let level: Int
    let name: String
    /// FENCE_LEVEL: solo, standard or team.
    var fence: String? = nil
    var modules: [Module] = []
    /// What the next rung lacks, in a few words.
    var next: String? = nil
}

/// A dev stand: whether it answers its health check, its address and how its checkout relates to origin/main.
struct Stand: Decodable, Equatable, Identifiable {
    let name: String
    /// "running" or "stopped".
    let state: String
    let url: String?
    /// The checkout's branch; "main" when it follows origin/main.
    var ref: String? = nil
    var sha: String? = nil
    /// Commits origin/main has that the checkout lacks, and the other way round.
    var behind: Int? = nil
    var ahead: Int? = nil
    var at: Date? = nil

    var id: String { name }
    var running: Bool { state == "running" }

    /// Only https addresses, like session links.
    var link: URL? {
        guard let text = url, let url = URL(string: text), url.scheme == "https", url.host != nil else { return nil }
        return url
    }
}

private func parseISO(_ text: String) -> Date? {
    let plain = ISO8601DateFormatter()
    if let date = plain.date(from: text) { return date }
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    return fractional.date(from: text)
}

/// The widget's link to a project: the app opens its drop-down with the project unfolded.
func projectLink(_ name: String) -> URL {
    var c = URLComponents()
    c.scheme = "factorybar"
    c.host = "project"
    c.path = "/" + name
    return c.url ?? URL(string: "factorybar://project")!
}

/// The project a `projectLink` names; nil for any other URL.
func projectName(in url: URL) -> String? {
    guard url.scheme == "factorybar", url.host == "project" else { return nil }
    let name = String(url.path.dropFirst())
    return name.isEmpty ? nil : name
}

/// Where a click goes. A session link opens in the Claude desktop app through its `claude://code/<id>` scheme when
/// the app is installed; https links to claude.ai open in the default browser, which is the fallback.
func openTarget(_ link: URL, desktopAppInstalled: Bool = desktopAppHandlesClaudeLinks()) -> URL {
    let parts = link.pathComponents  // ["/", "code", "<id>"]
    guard desktopAppInstalled, link.host == "claude.ai", parts.count == 3, parts[1] == "code",
          parts[2].hasPrefix("session_") || parts[2].hasPrefix("cse_")
    else { return link }
    return URL(string: "claude://code/\(parts[2])") ?? link
}

func desktopAppHandlesClaudeLinks() -> Bool {
    guard let probe = URL(string: "claude://code") else { return false }
    return NSWorkspace.shared.urlForApplication(toOpen: probe) != nil
}
