import XCTest

final class SSEParserTests: XCTestCase {
    private func messages(_ chunks: [String]) -> [String] {
        var parser = SSEParser()
        return chunks.flatMap { parser.consume(Data($0.utf8)) }
    }

    func testOneMessage() {
        XCTAssertEqual(messages(["data: {\"version\":2}\n\n"]), [#"{"version":2}"#])
    }

    func testChunksSplitAnywhere() {
        let whole = "data: {\"a\":1}\n\ndata: {\"b\":2}\n\n"
        for cut in whole.indices.dropFirst() {
            XCTAssertEqual(messages([String(whole[..<cut]), String(whole[cut...])]), [#"{"a":1}"#, #"{"b":2}"#],
                           "cut at \(whole.distance(from: whole.startIndex, to: cut))")
        }
    }

    func testCommentsAndOtherFieldsAreIgnored() {
        XCTAssertEqual(messages([": keep-alive\n\n", "event: feed\nid: 7\nretry: 5000\ndata: x\n\n"]), ["x"])
    }

    func testKeepAliveAloneYieldsNothing() {
        XCTAssertEqual(messages([": keep-alive\n\n", ": keep-alive\n\n"]), [])
    }

    func testMultiLineDataJoinsWithNewline() {
        XCTAssertEqual(messages(["data: {\"a\":\ndata: 1}\n\n"]), ["{\"a\":\n1}"])
    }

    func testCRLFAndNoSpaceAfterColon() {
        XCTAssertEqual(messages(["data:x\r\n\r\n"]), ["x"])
    }

    func testUnfinishedMessageIsHeldBack() {
        var parser = SSEParser()
        XCTAssertEqual(parser.consume(Data("data: x\n".utf8)), [])
        XCTAssertEqual(parser.consume(Data("\n".utf8)), ["x"])
    }

    func testMultiByteCharacterSplitAcrossChunks() {
        let bytes = Array("data: ü\n\n".utf8)
        var parser = SSEParser()
        XCTAssertEqual(parser.consume(Data(bytes[..<7])), [])
        XCTAssertEqual(parser.consume(Data(bytes[7...])), ["ü"])
    }
}

final class FeedStreamTests: XCTestCase {
    func testEventsURLReplacesStatusJSON() {
        XCTAssertEqual(eventsURL(for: URL(string: "http://100.64.0.1:8765/status.json")!),
                       URL(string: "http://100.64.0.1:8765/events"))
        XCTAssertEqual(eventsURL(for: URL(string: "http://host:8765/feed/status.json")!),
                       URL(string: "http://host:8765/feed/events"))
    }

    func testEventsURLAppendsWhenNotStatusJSON() {
        XCTAssertEqual(eventsURL(for: URL(string: "http://host:8765")!), URL(string: "http://host:8765/events"))
        XCTAssertEqual(eventsURL(for: URL(string: "http://host:8765/")!), URL(string: "http://host:8765/events"))
    }

    func testBackoffSteps() {
        XCTAssertEqual((0..<7).map(backoffDelay), [1, 2, 5, 10, 30, 30, 30])
    }
}

/// Answers by path: `routes[path] = (status, body)`.
final class RouteStub: URLProtocol {
    nonisolated(unsafe) static var routes: [String: (Int, String)] = [:]

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let (status, body) = Self.routes[request.url!.path] ?? (404, "")
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class FeedStreamConnectionTests: XCTestCase {
    private let v2 = #"{"version":2,"generated_at":"2026-10-26T19:45:00Z","full_at":"2026-10-26T19:40:00Z","quota":null,"projects":[{"name":"project-a","working":true,"agents":0,"busy_sessions":1,"waiting_quota":false,"queue_ready":0,"last_worked_at":null,"session_url":null,"oncall":{"installed":false,"running":false,"last_message_at":null},"watchdog":{"installed":false,"ok":false}}]}"#
    private let v1 = #"{"version":1,"generated_at":"2026-10-26T19:45:00Z","quota":null,"projects":[]}"#

    private func run(_ routes: [String: (Int, String)], until count: Int) async -> [String] {
        RouteStub.routes = routes
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [RouteStub.self]
        var seen: [String] = []
        let done = expectation(description: "events")
        let stream = FeedStream(feedURL: URL(string: "http://100.64.0.1:8765/status.json")!,
                                session: URLSession(configuration: config)) { event in
            switch event {
            case .connected: seen.append("connected")
            case let .message(feed): seen.append("message v\(feed.version) \(feed.projects.first?.busySessions.map(String.init) ?? "-")")
            case .disconnected: seen.append("disconnected")
            }
            if seen.count == count { done.fulfill() }
        }
        stream.start()
        await fulfillment(of: [done], timeout: 5)
        stream.stop()
        return Array(seen.prefix(count))
    }

    func testMessageFromEvents() async {
        let events = await run(["/events": (200, ": keep-alive\n\ndata: \(v2)\n\n")], until: 3)
        XCTAssertEqual(events, ["connected", "message v2 1", "disconnected"])
    }

    func testVersionOneServerFallsBackToStatusJSON() async {
        let events = await run(["/status.json": (200, v1)], until: 2)
        XCTAssertEqual(events, ["connected", "message v1 -"])
    }

    func testServerErrorIsADisconnect() async {
        let events = await run(["/events": (503, "")], until: 1)
        XCTAssertEqual(events, ["disconnected"])
    }
}
