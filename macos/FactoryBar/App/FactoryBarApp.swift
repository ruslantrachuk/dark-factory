import SwiftUI
import WidgetKit

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

/// Holds one `/events` connection (no polling) and keeps the last feed; re-evaluates the state only at the moments it
/// can change without a message — ten seconds after a drop, or when the heavy facts turn 45 minutes old.
@MainActor
final class FeedModel: ObservableObject {
    static let urlKey = "feedURL"

    @Published private(set) var feed: Feed?
    @Published private(set) var everReceived = false
    @Published private(set) var connected = false
    /// Since when there is no connection; nil while connected.
    @Published private(set) var lostAt: Date?
    @Published private(set) var checkedAt = Date()
    @Published private(set) var refreshing = false
    @Published var feedURL: String {
        didSet {
            UserDefaults.standard.set(feedURL, forKey: Self.urlKey)
            restart()
        }
    }

    /// The low point of the blink when work starts (off with Reduce motion).
    @Published private(set) var dim = false

    private var stream: FeedStream?
    private var deadline: Task<Void, Never>?
    private var blinker: Task<Void, Never>?

    init() {
        feedURL = UserDefaults.standard.string(forKey: Self.urlKey) ?? ""
        restart()
    }

    var state: IconState { liveState(feed: feed, everReceived: everReceived, lostAt: lostAt, now: checkedAt) }

    func restart() {
        stream?.stop()
        feed = nil
        everReceived = false
        connected = false
        lostAt = Date()
        guard let url = validFeedURL(feedURL) else { return }
        stream = FeedStream(feedURL: url) { [weak self] event in self?.handle(event) }
        stream?.start()
        rearm()
    }

    private func handle(_ event: FeedStream.Event) {
        let before = state
        let firstMessage = !everReceived
        switch event {
        case .connected:
            connected = true
            lostAt = nil
        case let .message(feed):
            self.feed = feed
            reloadWidget(for: feed)
            everReceived = true
            connected = true
            lostAt = nil
            endRefresh()
        case .disconnected:
            connected = false
            if lostAt == nil { lostAt = Date() }
            endRefresh()
        }
        checkedAt = Date()
        if !firstMessage, shouldBlink(from: before, to: state) { blink() }
        rearm()
    }

    /// Wakes once, at the next moment the state can change on its own; nothing runs in between.
    private func rearm() {
        deadline?.cancel()
        guard let at = stateDeadline(feed: feed, lostAt: lostAt, now: Date()) else { return }
        deadline = Task { [weak self] in
            try? await Task.sleep(for: .seconds(max(0, at.timeIntervalSinceNow) + 0.1))
            guard let self, !Task.isCancelled else { return }
            self.checkedAt = Date()
            self.rearm()
        }
    }

    private var widgetThrottle = WidgetThrottle()
    private var widgetReload: Task<Void, Never>?

    /// macOS decides when the widget actually redraws; this only asks, when its rows change, at most every 30 s.
    private func reloadWidget(for feed: Feed) {
        switch widgetThrottle.offer(widgetSignature(feed), now: Date()) {
        case .none:
            return
        case .now:
            WidgetCenter.shared.reloadAllTimelines()
        case let .at(date):
            guard widgetReload == nil else { return }
            widgetReload = Task { [weak self] in
                try? await Task.sleep(for: .seconds(max(0, date.timeIntervalSinceNow)))
                guard let self, !Task.isCancelled else { return }
                self.widgetThrottle.fired(at: Date())
                self.widgetReload = nil
                WidgetCenter.shared.reloadAllTimelines()
            }
        }
    }

    private var refreshStarted: Date?

    /// The Refresh button: drop the connection and open a new one at once (the back-off starts over).
    func refreshNow() {
        refreshing = true
        refreshStarted = Date()
        stream?.start()
    }

    /// The spinner stays at least half a second: a private-network reconnect is too fast to see.
    private func endRefresh() {
        guard refreshing, let started = refreshStarted else { return }
        refreshStarted = nil
        let left = 0.5 - Date().timeIntervalSince(started)
        Task { [weak self] in
            if left > 0 { try? await Task.sleep(for: .seconds(left)) }
            self?.refreshing = false
        }
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
