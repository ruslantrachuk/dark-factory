import XCTest

final class WidgetReloadTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    private func feed(working: Bool = false, agents: Int = 0, generated: TimeInterval = 0, five: Double = 20) -> Feed {
        let p = ProjectStatus(name: "project-a", working: working, agents: agents, waitingQuota: false, queueReady: 0,
                              lastWorkedAt: nil, sessionUrl: nil,
                              oncall: .init(installed: true, running: true, lastMessageAt: nil),
                              watchdog: .init(installed: false, ok: false), error: nil, busySessions: working ? 1 : 0)
        return Feed(version: 2, generatedAt: now.addingTimeInterval(generated),
                    quota: Quota(fiveHour: five, sevenDay: 10, noNewWork: false, resetsAt: nil, asOf: now),
                    projects: [p], fullAt: now)
    }

    func testSignatureIgnoresGeneratedAt() {
        XCTAssertEqual(widgetSignature(feed(generated: 0)), widgetSignature(feed(generated: 30)))
    }

    func testSignatureFollowsWhatTheWidgetShows() {
        XCTAssertNotEqual(widgetSignature(feed()), widgetSignature(feed(working: true)))
        XCTAssertNotEqual(widgetSignature(feed(working: true, agents: 1)), widgetSignature(feed(working: true, agents: 2)))
        XCTAssertNotEqual(widgetSignature(feed(five: 20)), widgetSignature(feed(five: 21)))
    }

    func testFirstChangeReloadsAtOnce() {
        var t = WidgetThrottle()
        XCTAssertEqual(t.offer("a", now: now), .now)
    }

    func testSameRowsDoNotReload() {
        var t = WidgetThrottle()
        _ = t.offer("a", now: now)
        XCTAssertEqual(t.offer("a", now: now.addingTimeInterval(60)), .none)
    }

    func testChangeWithinThirtySecondsWaits() {
        var t = WidgetThrottle()
        _ = t.offer("a", now: now)
        XCTAssertEqual(t.offer("b", now: now.addingTimeInterval(10)), .at(now.addingTimeInterval(30)))
        XCTAssertEqual(t.offer("c", now: now.addingTimeInterval(20)), .at(now.addingTimeInterval(30)))
        t.fired(at: now.addingTimeInterval(30))
        XCTAssertEqual(t.offer("d", now: now.addingTimeInterval(40)), .at(now.addingTimeInterval(60)))
        XCTAssertEqual(t.offer("e", now: now.addingTimeInterval(61)), .now)
    }

    func testChangeAfterThirtySecondsReloadsAtOnce() {
        var t = WidgetThrottle()
        _ = t.offer("a", now: now)
        XCTAssertEqual(t.offer("b", now: now.addingTimeInterval(30)), .now)
    }
}
