import XCTest

final class FeedStateTests: XCTestCase {
    private func fixture() throws -> Feed {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "status", withExtension: "json"))
        return try Feed.decode(Data(contentsOf: url))
    }

    private func project(_ name: String = "project-x", working: Bool = false, agents: Int = 0,
                         waitingQuota: Bool = false, queueReady: Int = 0, lastWorkedAt: Date? = nil,
                         sessionUrl: String? = nil, oncallAt: Date? = nil) -> ProjectStatus {
        ProjectStatus(name: name, working: working, agents: agents, waitingQuota: waitingQuota,
                      queueReady: queueReady, lastWorkedAt: lastWorkedAt, sessionUrl: sessionUrl,
                      oncall: .init(installed: true, running: true, lastMessageAt: oncallAt),
                      watchdog: .init(installed: false, ok: false), error: nil)
    }

    private func feed(_ projects: [ProjectStatus], at generated: Date, quota: Quota? = nil) -> Feed {
        Feed(version: 1, generatedAt: generated, quota: quota, projects: projects)
    }

    private let now = Date(timeIntervalSince1970: 1_800_000_000)

    // MARK: decoding

    func testFixtureDecodes() throws {
        let f = try fixture()
        XCTAssertEqual(f.version, 1)
        XCTAssertEqual(f.generatedAt, ISO8601DateFormatter().date(from: "2026-10-26T19:45:00Z"))
        XCTAssertEqual(f.quota?.fiveHour, 28)
        XCTAssertNil(f.quota?.resetsAt)
        XCTAssertEqual(f.projects.map(\.name), ["project-a", "project-b"])
        let a = f.projects[0], b = f.projects[1]
        XCTAssertEqual(a.agents, 3)
        XCTAssertNotNil(a.link)
        XCTAssertNotNil(a.oncall.lastMessageAt)
        XCTAssertNil(b.link)
        XCTAssertFalse(b.oncall.installed)
        XCTAssertEqual(b.error, "watchdog: state file unreadable")
    }

    func testFractionalSecondsAndNullQuotaDecode() throws {
        let json = #"{"version":1,"generated_at":"2026-10-26T19:45:00.250Z","quota":null,"projects":[]}"#
        let f = try Feed.decode(Data(json.utf8))
        XCTAssertNil(f.quota)
        XCTAssertTrue(f.projects.isEmpty)
    }

    func testOnlyClaudeLinksAreClickable() {
        XCTAssertNotNil(project(sessionUrl: "https://claude.ai/code/session_01").link)
        XCTAssertNil(project(sessionUrl: "file:///etc/passwd").link)
        XCTAssertNil(project(sessionUrl: "https://example.com/code").link)
    }

    // MARK: icon state

    func testWorkingWithAgents() {
        let f = feed([project(working: true, agents: 3), project()], at: now)
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .working(agents: 3))
    }

    func testAgentsAreTotalledAcrossProjects() {
        let f = feed([project(working: true, agents: 3), project(working: true, agents: 2)], at: now)
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .working(agents: 5))
    }

    func testWorkingWithoutAgentsShowsNoNumber() {
        let f = feed([project(working: true)], at: now)
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .working(agents: 0))
    }

    func testOnlyWaitingForQuotaIsWaitingQuota() {
        let f = feed([project(waitingQuota: true, queueReady: 4), project()], at: now)
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .waitingQuota)
    }

    func testWorkingWinsOverWaitingForQuota() {
        let f = feed([project(waitingQuota: true), project(working: true, agents: 2)], at: now)
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .working(agents: 2))
    }

    func testWaitingForQuotaIsAFilledOrangeFactoryWithoutBadge() {
        XCTAssertTrue(IconState.waitingQuota.isFilled)
        XCTAssertTrue(IconState.working(agents: 1).isFilled)
        XCTAssertFalse(IconState.idle.isFilled)
        XCTAssertEqual(IconState.waitingQuota.nsColor, Palette.quota)
        XCTAssertNil(IconState.waitingQuota.badge)
    }

    func testFetchErrorIsNoData() {
        let last = now.addingTimeInterval(-600)
        guard case let .noData(reason, lastGood) = iconState(feed: .failure(FeedError.notWrittenYet), now: now,
                                                            lastGood: last) else { return XCTFail() }
        XCTAssertEqual(reason, "feed not written yet")
        XCTAssertEqual(lastGood, last)
    }

    func testStaleFeedIsNoData() {
        let generated = now.addingTimeInterval(-2701)
        guard case let .noData(_, lastGood) = iconState(feed: .success(feed([project(working: true)], at: generated)),
                                                        now: now, lastGood: nil) else { return XCTFail() }
        XCTAssertEqual(lastGood, generated)
    }

    func testFeedAtTheThresholdIsFresh() {
        let f = feed([project()], at: now.addingTimeInterval(-2700))
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .idle)
    }

    func testFeedFromTheFutureIsFresh() {
        let f = feed([project()], at: now.addingTimeInterval(300))
        XCTAssertEqual(iconState(feed: .success(f), now: now, lastGood: nil), .idle)
    }

    func testBlinkOnlyWhenWorkStarts() {
        XCTAssertTrue(shouldBlink(from: .idle, to: .working(agents: 0)))
        XCTAssertTrue(shouldBlink(from: .noData(reason: "x", lastGood: now), to: .working(agents: 2)))
        XCTAssertFalse(shouldBlink(from: .working(agents: 1), to: .working(agents: 3)))
        XCTAssertFalse(shouldBlink(from: .noData(reason: "feed URL not set", lastGood: nil), to: .working(agents: 1)))
        XCTAssertFalse(shouldBlink(from: .working(agents: 1), to: .idle))
        XCTAssertTrue(shouldBlink(from: .waitingQuota, to: .working(agents: 1)))
        XCTAssertFalse(shouldBlink(from: .idle, to: .waitingQuota))
    }

    // MARK: rows

    func testRowBuilding() {
        XCTAssertEqual(rowStatus(project(working: true, agents: 2), quota: nil), .building(agents: 2))
        XCTAssertEqual(statusText(.building(agents: 2), now: now), "Building · 2 agents")
        XCTAssertEqual(statusText(.building(agents: 1), now: now), "Building · 1 agent")
        XCTAssertEqual(statusText(.building(agents: 0), now: now), "Building")
    }

    func testRowWaitingForQuota() {
        let resets = now.addingTimeInterval(3600)
        let q = Quota(fiveHour: 96, sevenDay: 40, noNewWork: true, resetsAt: resets, asOf: now)
        let p = project(waitingQuota: true, queueReady: 4)
        XCTAssertEqual(rowStatus(p, quota: q), .waitingQuota(until: resets, queued: 4))
        XCTAssertEqual(statusText(.waitingQuota(until: resets, queued: 4), now: now),
                       "Waiting for quota until \(clock(resets)) · 4 queued")
        XCTAssertEqual(statusText(.waitingQuota(until: nil, queued: 4), now: now), "Waiting for quota · 4 queued")
    }

    func testRowLastWorked() {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let now = ISO8601DateFormatter().date(from: "2026-10-26T19:45:00Z")!
        let at = { ISO8601DateFormatter().date(from: $0)! }
        XCTAssertEqual(rowStatus(project(lastWorkedAt: at("2026-10-26T14:02:00Z")), quota: nil),
                       .lastWorked(at("2026-10-26T14:02:00Z")))
        XCTAssertEqual(statusText(.lastWorked(at("2026-10-26T14:02:00Z")), now: now, calendar: utc), "Last worked today 14:02")
        XCTAssertEqual(statusText(.lastWorked(at("2026-10-25T22:10:00Z")), now: now, calendar: utc),
                       "Last worked yesterday 22:10")
        XCTAssertEqual(statusText(.lastWorked(at("2026-10-24T06:11:00Z")), now: now, calendar: utc),
                       "Last worked 24 Oct 06:11")
        XCTAssertEqual(statusText(.lastWorked(nil), now: now), "Not worked yet")
    }

    func testWaitingForQuotaTailIsSeparate() {
        let (main, tail) = statusParts(.waitingQuota(until: nil, queued: 5), now: now)
        XCTAssertEqual(main, "Waiting for quota")
        XCTAssertEqual(tail, "5 queued")
    }

    func testWorkingNowSection() {
        XCTAssertTrue(isWorkingNow(project(working: true)))
        XCTAssertTrue(isWorkingNow(project(waitingQuota: true)))
        XCTAssertFalse(isWorkingNow(project()))
    }

    func testSummaryText() {
        let busy = feed([project(working: true, agents: 3), project(working: true), project()], at: now)
        XCTAssertEqual(summaryText(state: .working(agents: 3), feed: busy), "2 working · 3 agents")
        XCTAssertEqual(summaryText(state: .working(agents: 0), feed: feed([project(working: true)], at: now)), "1 working")
        XCTAssertEqual(summaryText(state: .idle, feed: feed([project(waitingQuota: true)], at: now)), "Waiting for quota")
        XCTAssertEqual(summaryText(state: .idle, feed: feed([project()], at: now)), "Idle")
        XCTAssertEqual(summaryText(state: .noData(reason: "feed not written yet", lastGood: nil), feed: nil),
                       "feed not written yet")
    }

    func testConnectionText() {
        let f = feed([project()], at: now)
        XCTAssertEqual(connectionText(connected: true, everReceived: true, feed: f), "Live · last change \(clock(now))")
        XCTAssertEqual(connectionText(connected: false, everReceived: true, feed: f), "Reconnecting…")
        XCTAssertEqual(connectionText(connected: false, everReceived: false, feed: nil), "Connecting…")
    }

    // MARK: On-call line

    func testOncallLineWithinTheHour() {
        XCTAssertEqual(oncallLine(project(oncallAt: now.addingTimeInterval(-59 * 60)), now: now),
                       "On-call wrote 59 min ago")
    }

    func testOncallLineAfterTheHour() {
        XCTAssertNil(oncallLine(project(oncallAt: now.addingTimeInterval(-61 * 60)), now: now))
    }

    func testOncallLineWithoutMessage() {
        XCTAssertNil(oncallLine(project(oncallAt: nil), now: now))
    }
}

final class OpenTargetTests: XCTestCase {
    func testSessionLinkOpensInTheDesktopApp() {
        let link = URL(string: "https://claude.ai/code/session_01AbC")!
        XCTAssertEqual(openTarget(link, desktopAppInstalled: true), URL(string: "claude://code/session_01AbC"))
        XCTAssertEqual(openTarget(URL(string: "https://claude.ai/code/cse_01x")!, desktopAppInstalled: true),
                       URL(string: "claude://code/cse_01x"))
    }

    func testWithoutTheDesktopAppTheLinkStaysHttps() {
        let link = URL(string: "https://claude.ai/code/session_01AbC")!
        XCTAssertEqual(openTarget(link, desktopAppInstalled: false), link)
    }

    func testEnvironmentLinkStaysHttps() {
        let link = URL(string: "https://claude.ai/code?environment=env_01x")!
        XCTAssertEqual(openTarget(link, desktopAppInstalled: true), link)
    }
}
