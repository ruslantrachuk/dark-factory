import Foundation

/// Server-Sent Events, the part the feed uses: `data:` lines make a message (several join with "\n"), a blank line
/// ends it, `:` lines are comments (keep-alives), other fields are ignored. Fed raw bytes in any chunking.
struct SSEParser {
    private var line: [UInt8] = []
    private var data: [String] = []

    mutating func consume(_ chunk: Data) -> [String] {
        var messages: [String] = []
        for byte in chunk {
            guard byte == 0x0A else {
                line.append(byte)
                continue
            }
            if line.last == 0x0D { line.removeLast() }
            if let message = take(String(decoding: line, as: UTF8.self)) { messages.append(message) }
            line.removeAll(keepingCapacity: true)
        }
        return messages
    }

    private mutating func take(_ text: String) -> String? {
        if text.isEmpty {
            defer { data.removeAll() }
            return data.isEmpty ? nil : data.joined(separator: "\n")
        }
        guard text.hasPrefix("data:") else { return nil }  // comments and event/id/retry fields
        var value = text.dropFirst(5)
        if value.first == " " { value = value.dropFirst() }
        data.append(String(value))
        return nil
    }
}

/// `…/status.json` → `…/events`; any other URL gets `/events` appended.
func eventsURL(for feedURL: URL) -> URL {
    if feedURL.lastPathComponent == "status.json" {
        return feedURL.deletingLastPathComponent().appendingPathComponent("events")
    }
    return feedURL.appendingPathComponent("events")
}

/// Seconds to wait before reconnect attempt `n` (0-based): 1, 2, 5, 10, then 30.
func backoffDelay(_ attempt: Int) -> TimeInterval {
    let steps: [TimeInterval] = [1, 2, 5, 10, 30]
    return steps[min(max(attempt, 0), steps.count - 1)]
}

/// One `/events` connection, reconnected with back-off. A server without `/events` (feed version 1, 404) is read
/// from `status.json` once a minute instead.
final class FeedStream {
    enum Event {
        case connected
        case message(Feed)
        case disconnected
    }

    private let feedURL: URL
    private let session: URLSession
    private let onEvent: @MainActor (Event) -> Void
    private var task: Task<Void, Never>?

    init(feedURL: URL, session: URLSession? = nil, onEvent: @escaping @MainActor (Event) -> Void) {
        self.feedURL = feedURL
        self.onEvent = onEvent
        if let session {
            self.session = session
        } else {
            let config = URLSessionConfiguration.ephemeral
            // The server sends a keep-alive every 20 s; silence longer than this means the connection is gone.
            config.timeoutIntervalForRequest = 30
            config.timeoutIntervalForResource = .infinity
            config.requestCachePolicy = .reloadIgnoringLocalCacheData
            self.session = URLSession(configuration: config)
        }
    }

    func start() {
        task?.cancel()
        task = Task { [weak self] in await self?.run() }
    }

    func stop() {
        task?.cancel()
        task = nil
    }

    private func run() async {
        var attempt = 0
        while !Task.isCancelled {
            var request = URLRequest(url: eventsURL(for: feedURL))
            request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
            do {
                let (bytes, response) = try await session.bytes(for: request)
                let code = (response as? HTTPURLResponse)?.statusCode ?? 0
                if code == 404 {
                    await legacyPoll()
                    attempt = 0
                    continue
                }
                guard code == 200 else { throw FeedError.http(code) }
                await onEvent(.connected)
                var parser = SSEParser()
                var chunk = Data()
                for try await byte in bytes {
                    chunk.append(byte)
                    guard byte == 0x0A else { continue }
                    for text in parser.consume(chunk) {
                        guard let feed = try? Feed.decode(Data(text.utf8)) else { continue }
                        attempt = 0
                        await onEvent(.message(feed))
                    }
                    chunk.removeAll(keepingCapacity: true)
                }
            } catch {}
            if Task.isCancelled { return }
            await onEvent(.disconnected)
            try? await Task.sleep(for: .seconds(backoffDelay(attempt)))
            attempt += 1
        }
    }

    /// A version-1 server: one fetch of `status.json`, then a minute before trying `/events` again.
    private func legacyPoll() async {
        switch await FeedClient(url: feedURL, session: session).fetch() {
        case let .success(feed):
            await onEvent(.connected)
            await onEvent(.message(feed))
        case .failure:
            await onEvent(.disconnected)
        }
        try? await Task.sleep(for: .seconds(60))
    }
}
