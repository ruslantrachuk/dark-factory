import XCTest

final class FeedStateTests: XCTestCase {
    private func fixture() throws -> Feed {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "status", withExtension: "json"))
        return try Feed.decode(Data(contentsOf: url))
    }

    private func project(_ name: String = "project-x", working: Bool = false, agents: Int = 0,
                         waitingQuota: Bool = false, queueReady: Int = 0, lastWorkedAt: Date? = nil,
                         sessionUrl: String? = nil, oncallAt: Date? = nil, sessions: Int? = nil) -> ProjectStatus {
        ProjectStatus(name: name, working: working, agents: agents, waitingQuota: waitingQuota,
                      queueReady: queueReady, lastWorkedAt: lastWorkedAt, sessionUrl: sessionUrl,
                      oncall: .init(installed: true, running: true, lastMessageAt: oncallAt),
                      watchdog: .init(installed: false, ok: false), error: nil, busySessions: sessions)
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
        XCTAssertEqual(rowStatus(project(working: true, agents: 2, sessions: 1), quota: nil),
                       .building(sessions: 1, agents: 2))
        XCTAssertEqual(statusText(.building(sessions: 1, agents: 3), now: now), "Building · 1 session · 3 agents")
        XCTAssertEqual(statusText(.building(sessions: 2, agents: 0), now: now), "Building · 2 sessions")
        XCTAssertEqual(statusText(.building(sessions: nil, agents: 1), now: now), "Building · 1 agent")
        XCTAssertEqual(statusText(.building(sessions: 0, agents: 0), now: now), "Building")
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
        let withSessions = feed([project(working: true, agents: 3, sessions: 1), project(working: true, sessions: 1)], at: now)
        XCTAssertEqual(summaryText(state: .working(agents: 3), feed: withSessions), "2 working · 2 sessions · 3 agents")
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

    // MARK: stands

    func testStandsDecode() throws {
        let json = #"{"version":2,"generated_at":"2026-10-26T19:45:00Z","quota":null,"projects":[{"name":"project-b","working":false,"agents":0,"waiting_quota":false,"queue_ready":0,"last_worked_at":null,"session_url":null,"oncall":{"installed":false,"running":false,"last_message_at":null},"watchdog":{"installed":false,"ok":false},"stands":[{"name":"main","state":"running","url":"https://a.trycloudflare.com","ref":"main","sha":"8f6569a4","behind":0,"ahead":0,"at":"2026-10-26T19:44:00Z"},{"name":"fast","state":"stopped","url":"http://127.0.0.1:8101"}]}]}"#
        let stands = try XCTUnwrap(Feed.decode(Data(json.utf8)).projects[0].stands)
        XCTAssertEqual(stands.map(\.running), [true, false])
        XCTAssertEqual(stands[0].link, URL(string: "https://a.trycloudflare.com"))
        XCTAssertNil(stands[1].link)
        XCTAssertNil(try fixture().projects[0].stands)
    }

    func testUntilText() {
        XCTAssertEqual(untilText(now.addingTimeInterval(45 * 60), now: now), "45m")
        XCTAssertEqual(untilText(now.addingTimeInterval(130 * 60), now: now), "2h 10m")
        XCTAssertEqual(untilText(now.addingTimeInterval(3 * 3600), now: now), "3h")
        XCTAssertEqual(untilText(now.addingTimeInterval(76 * 3600), now: now), "3d 4h")
        XCTAssertNil(untilText(now.addingTimeInterval(-60), now: now))
    }

    func testLevelTexts() {
        let l = Level(level: 3, name: "client modules", fence: "standard",
                      modules: [.init(name: "feedback-desk", installed: true), .init(name: "release-tag", installed: true),
                                .init(name: "feature-pipeline", installed: false)])
        XCTAssertEqual(levelText(l), "3 · client modules · fence standard")
        XCTAssertEqual(modulesText(l), "2 of 3 installed")
        XCTAssertNil(modulesText(Level(level: 0, name: "bare")))
    }

    func testFeedV3FieldsDecode() throws {
        let json = #"{"version":2,"generated_at":"2026-10-26T19:45:00Z","quota":{"five_hour":8,"seven_day":33,"no_new_work":false,"resets_at":null,"as_of":null,"resets":{"five_hour":"2026-10-26T16:50:00Z","seven_day":"2026-11-01T22:00:00Z"}},"projects":[{"name":"p","working":false,"agents":0,"waiting_quota":false,"queue_ready":0,"last_worked_at":null,"session_url":null,"oncall":{"installed":true,"running":true,"last_message_at":null,"session_url":"https://claude.ai/code/session_01x"},"watchdog":{"installed":false,"ok":false},"level":{"level":3,"name":"client modules","fence":"standard","modules":[{"name":"feature-pipeline","installed":false}],"next":null}}]}"#
        let f = try Feed.decode(Data(json.utf8))
        XCTAssertEqual(f.quota?.resets?.sevenDay, ISO8601DateFormatter().date(from: "2026-11-01T22:00:00Z"))
        XCTAssertEqual(f.projects[0].oncall.link, URL(string: "https://claude.ai/code/session_01x"))
        XCTAssertEqual(f.projects[0].level?.modules.first?.installed, false)
    }

    func testStandFreshness() {
        func stand(_ ref: String?, behind: Int = 0, ahead: Int = 0) -> Stand {
            Stand(name: "s", state: "running", url: nil, ref: ref, behind: behind, ahead: ahead)
        }
        XCTAssertEqual(standFreshness(stand("main")), "on main")
        XCTAssertEqual(standFreshness(stand("main", behind: 3)), "3 behind main")
        XCTAssertEqual(standFreshness(stand("dev-session", behind: 1, ahead: 2)), "dev-session · +2 to main · 1 behind")
        XCTAssertNil(standFreshness(stand(nil)))
    }
}

final class OpenTargetTests: XCTestCase {
    func testProjectLinkRoundTrips() {
        XCTAssertEqual(projectLink("dark.factory").absoluteString, "factorybar://project/dark.factory")
        XCTAssertEqual(projectName(in: projectLink("my project")), "my project")
        XCTAssertNil(projectName(in: URL(string: "factorybar://project")!))
        XCTAssertNil(projectName(in: URL(string: "https://claude.ai/code/session_01x")!))
    }

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
