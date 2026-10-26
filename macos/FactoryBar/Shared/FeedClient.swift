import Foundation

actor FeedClient {
    private let url: URL
    private let session: URLSession

    init(url: URL, session: URLSession? = nil) {
        self.url = url
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.ephemeral
            config.timeoutIntervalForRequest = 10
            config.timeoutIntervalForResource = 10
            config.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.session = URLSession(configuration: config)
        }
    }

    func fetch() async -> Result<Feed, Error> {
        let data: Data, response: URLResponse
        do {
            (data, response) = try await session.data(from: url)
        } catch {
            return .failure(FeedError.unreachable(error.localizedDescription))
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        if code == 503 { return .failure(FeedError.notWrittenYet) }
        guard code == 200 else { return .failure(FeedError.http(code)) }
        do {
            return .success(try Feed.decode(data))
        } catch {
            return .failure(FeedError.undecodable)
        }
    }
}
