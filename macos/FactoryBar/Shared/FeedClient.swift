import Foundation

actor FeedClient {
    private let url: URL
    private let token: String?
    private let session: URLSession

    init(url: URL, token: String? = nil, session: URLSession? = nil) {
        self.url = url
        self.token = token
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
            var request = URLRequest(url: url)
            authorize(&request, token: token)
            (data, response) = try await session.data(for: request)
        } catch {
            return .failure(FeedError.unreachable(error.localizedDescription))
        }
        let code = (response as? HTTPURLResponse)?.statusCode ?? 0
        if code == 503 { return .failure(FeedError.notWrittenYet) }
        if code == 401 { return .failure(FeedError.unauthorized(hadToken: !(token ?? "").isEmpty)) }
        guard code == 200 else { return .failure(FeedError.http(code)) }
        do {
            return .success(try Feed.decode(data))
        } catch {
            return .failure(FeedError.undecodable)
        }
    }
}
