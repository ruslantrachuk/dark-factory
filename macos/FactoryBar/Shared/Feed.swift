import AppKit

/// `status.json` as written by `fleet.py feed` (schema version 1).
struct Feed: Decodable, Equatable {
    let version: Int
    let generatedAt: Date
    let quota: Quota?
    let projects: [ProjectStatus]

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
}

struct ProjectStatus: Decodable, Equatable, Identifiable {
    struct Oncall: Decodable, Equatable {
        let installed: Bool
        let running: Bool
        let lastMessageAt: Date?
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

    var id: String { name }

    /// The link a click opens. Only Claude's own https links: the app never opens whatever else a feed may carry.
    var link: URL? {
        guard let text = sessionUrl, let url = URL(string: text), url.scheme == "https", url.host == "claude.ai"
        else { return nil }
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
