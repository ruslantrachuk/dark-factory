import XCTest

/// Answers every request with the status code and body set on the class.
final class StubProtocol: URLProtocol {
    nonisolated(unsafe) static var status = 200
    nonisolated(unsafe) static var body = Data()

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Self.body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class FeedClientTests: XCTestCase {
    private func client() -> FeedClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        return FeedClient(url: URL(string: "http://100.64.0.1:8765/status.json")!, session: URLSession(configuration: config))
    }

    func testOK() async throws {
        StubProtocol.status = 200
        StubProtocol.body = Data(#"{"version":1,"generated_at":"2026-10-26T19:45:00Z","quota":null,"projects":[]}"#.utf8)
        let feed = try await client().fetch().get()
        XCTAssertEqual(feed.version, 1)
    }

    func testNotWrittenYet() async {
        StubProtocol.status = 503
        StubProtocol.body = Data()
        guard case let .failure(e) = await client().fetch() else { return XCTFail() }
        XCTAssertEqual(e as? FeedError, .notWrittenYet)
    }

    func testOtherStatus() async {
        StubProtocol.status = 404
        guard case let .failure(e) = await client().fetch() else { return XCTFail() }
        XCTAssertEqual(e as? FeedError, .http(404))
    }

    func testUndecodable() async {
        StubProtocol.status = 200
        StubProtocol.body = Data("<html>".utf8)
        guard case let .failure(e) = await client().fetch() else { return XCTFail() }
        XCTAssertEqual(e as? FeedError, .undecodable)
    }
}
