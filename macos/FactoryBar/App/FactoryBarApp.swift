import SwiftUI

@main
struct FactoryBarApp: App {
    @StateObject private var model = FeedModel()

    var body: some Scene {
        MenuBarExtra {
            MenuContent(model: model)
        } label: {
            Image(nsImage: menuBarImage(model.state, dim: model.dim))
        }
        .menuBarExtraStyle(.window)
    }
}

/// Polls the feed every 60 s and keeps the last good feed for the no-data footer.
@MainActor
final class FeedModel: ObservableObject {
    static let urlKey = "feedURL"

    @Published private(set) var result: Result<Feed, Error> = .failure(FeedError.notConfigured)
    @Published private(set) var lastGood: Date?
    @Published private(set) var checkedAt = Date()
    @Published var feedURL: String {
        didSet {
            UserDefaults.standard.set(feedURL, forKey: Self.urlKey)
            restart()
        }
    }

    /// The low point of the blink when work starts (off with Reduce motion).
    @Published private(set) var dim = false

    private var poller: Task<Void, Never>?
    private var blinker: Task<Void, Never>?

    init() {
        feedURL = UserDefaults.standard.string(forKey: Self.urlKey) ?? ""
        restart()
    }

    var state: IconState { iconState(feed: result, now: checkedAt, lastGood: lastGood) }
    var feed: Feed? { try? result.get() }

    func restart() {
        poller?.cancel()
        poller = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refresh()
                try? await Task.sleep(for: .seconds(60))
            }
        }
    }

    func refresh() async {
        guard let url = validFeedURL(feedURL) else {
            result = .failure(FeedError.notConfigured)
            return
        }
        let fetched = await FeedClient(url: url).fetch()
        let now = Date()
        if case let .success(feed) = fetched, now.timeIntervalSince(feed.generatedAt) <= staleAfter {
            lastGood = feed.generatedAt
        }
        let before = state
        result = fetched
        checkedAt = now
        if shouldBlink(from: before, to: state) { blink() }
    }

    /// Three slow blinks, then a steady icon: a continuous pulse kept the app awake and cost ~1 % CPU.
    private func blink() {
        guard !NSWorkspace.shared.accessibilityDisplayShouldReduceMotion else { return }
        blinker?.cancel()
        blinker = Task { [weak self] in
            for _ in 0..<6 {
                try? await Task.sleep(for: .milliseconds(600))
                guard let self, !Task.isCancelled else { return }
                self.dim.toggle()
            }
            self?.dim = false
        }
    }
}
