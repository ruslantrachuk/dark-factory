import XCTest

final class LiveStateTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func feed(full: TimeInterval?, generated: TimeInterval = 0, working: Bool = false) -> Feed {
        let p = ProjectStatus(name: "project-a", working: working, agents: working ? 2 : 0, waitingQuota: false,
                              queueReady: 0, lastWorkedAt: nil, sessionUrl: nil,
                              oncall: .init(installed: false, running: false, lastMessageAt: nil),
                              watchdog: .init(installed: false, ok: false), error: nil, busySessions: working ? 1 : 0)
        return Feed(version: full == nil ? 1 : 2, generatedAt: now.addingTimeInterval(-generated), quota: nil,
                    projects: [p], fullAt: full.map { now.addingTimeInterval(-$0) })
    }

    func testConnectedFreshFeed() {
        XCTAssertEqual(liveState(feed: feed(full: 600, working: true), everReceived: true, lostAt: nil, now: now),
                       .working(agents: 2))
        XCTAssertEqual(liveState(feed: feed(full: 600), everReceived: true, lostAt: nil, now: now), .idle)
    }

    func testConnectingBeforeTheFirstMessageIsNotNoDataYet() {
        XCTAssertEqual(liveState(feed: nil, everReceived: false, lostAt: nil, now: now), .idle)
    }

    func testNeverConnectedForTenSecondsIsServerUnreachable() {
        let lost = now.addingTimeInterval(-10)
        XCTAssertEqual(liveState(feed: nil, everReceived: false, lostAt: lost, now: now),
                       .noData(reason: "Server unreachable", lastGood: nil))
        XCTAssertEqual(liveState(feed: nil, everReceived: false, lostAt: now.addingTimeInterval(-9), now: now), .idle)
    }

    func testLostForTenSecondsIsConnectionLost() {
        let f = feed(full: 600, working: true)
        XCTAssertEqual(liveState(feed: f, everReceived: true, lostAt: now.addingTimeInterval(-10), now: now),
                       .noData(reason: "Connection lost", lastGood: f.heavyAt))
    }

    func testBrieflyLostKeepsTheLastState() {
        XCTAssertEqual(liveState(feed: feed(full: 600, working: true), everReceived: true,
                                 lostAt: now.addingTimeInterval(-3), now: now), .working(agents: 2))
    }

    func testStaleHeavyFactsAreNoDataEvenWithFreshPushes() {
        let f = feed(full: 2701, generated: 1)
        XCTAssertEqual(liveState(feed: f, everReceived: true, lostAt: nil, now: now),
                       .noData(reason: "Status not updated since \(clock(f.heavyAt))", lastGood: f.heavyAt))
        XCTAssertEqual(liveState(feed: feed(full: 2700), everReceived: true, lostAt: nil, now: now), .idle)
    }

    func testVersionOneUsesGeneratedAt() {
        let f = feed(full: nil, generated: 2701)
        XCTAssertEqual(f.heavyAt, f.generatedAt)
        guard case .noData = liveState(feed: f, everReceived: true, lostAt: nil, now: now) else { return XCTFail() }
    }

    func testOneShotFetchUsesTheSameStaleRule() {
        let f = feed(full: 2701, generated: 1)
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil),
                       .noData(reason: "Status not updated since \(clock(f.heavyAt))", lastGood: f.heavyAt))
    }

    func testNextDeadline() {
        let f = feed(full: 600)
        XCTAssertEqual(stateDeadline(feed: f, lostAt: now.addingTimeInterval(-4), now: now), now.addingTimeInterval(6))
        XCTAssertEqual(stateDeadline(feed: f, lostAt: nil, now: now), f.heavyAt.addingTimeInterval(2700))
        XCTAssertNil(stateDeadline(feed: feed(full: 3000), lostAt: nil, now: now))
    }

    func testVersionTwoDecodes() throws {
        let json = #"{"version":2,"generated_at":"2026-10-26T19:45:00Z","full_at":"2026-10-26T19:40:00Z","quota":null,"projects":[{"name":"project-b","working":false,"agents":0,"busy_sessions":null,"waiting_quota":false,"queue_ready":0,"last_worked_at":null,"session_url":null,"oncall":{"installed":false,"running":false,"last_message_at":null},"watchdog":{"installed":false,"ok":false}}]}"#
        let f = try Feed.decode(Data(json.utf8))
        XCTAssertEqual(f.fullAt, ISO8601DateFormatter().date(from: "2026-10-26T19:40:00Z"))
        XCTAssertNil(f.projects[0].busySessions)
    }
}
