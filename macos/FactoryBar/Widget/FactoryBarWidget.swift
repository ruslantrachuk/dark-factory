import SwiftUI
import WidgetKit

struct FactoryEntry: TimelineEntry {
    let date: Date
    let feed: Feed?
    let state: IconState
}

struct Provider: AppIntentTimelineProvider {
    func placeholder(in context: Context) -> FactoryEntry {
        FactoryEntry(date: Date(), feed: nil, state: .idle)
    }

    func snapshot(for configuration: FeedURLIntent, in context: Context) async -> FactoryEntry {
        await entry(for: configuration)
    }

    /// One entry; the system is asked to reload in 15 minutes and picks the exact moment.
    func timeline(for configuration: FeedURLIntent, in context: Context) async -> Timeline<FactoryEntry> {
        let entry = await entry(for: configuration)
        return Timeline(entries: [entry], policy: .after(entry.date.addingTimeInterval(900)))
    }

    private func entry(for configuration: FeedURLIntent) async -> FactoryEntry {
        let result: Result<Feed, Error>
        if let url = validFeedURL(configuration.feedURL) {
            result = await FeedClient(url: url).fetch()
        } else {
            result = .failure(FeedError.notConfigured)
        }
        let now = Date()
        // The widget keeps no history, so a fetch error has no last good time to show.
        return FactoryEntry(date: now, feed: try? result.get(), state: iconState(feed: result, now: now, lastGood: nil))
    }
}

struct FactoryWidgetView: View {
    let entry: FactoryEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                StateGlyph(state: entry.state)
                Text("Factory").font(.headline)
                Spacer()
                Text(quotaText(entry.feed?.quota)).font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
            Divider()
            if case let .noData(reason, lastGood) = entry.state {
                VStack(alignment: .leading, spacing: 4) {
                    Text("No data").font(.subheadline.weight(.semibold)).foregroundStyle(.red)
                    Text(reason).font(.caption)
                    if let lastGood { Text("last update \(clock(lastGood))").font(.caption).foregroundStyle(.secondary) }
                }
            } else if let feed = entry.feed {
                StatusList(feed: feed, now: entry.date, linkRows: true)
                Spacer(minLength: 0)
                Text(footerText(feed)).font(.caption2).foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .containerBackground(.background, for: .widget)
    }
}

@main
struct FactoryBarWidget: Widget {
    var body: some WidgetConfiguration {
        AppIntentConfiguration(kind: "FactoryBarWidget", intent: FeedURLIntent.self, provider: Provider()) { entry in
            FactoryWidgetView(entry: entry)
        }
        .configurationDisplayName("Factory")
        .description("Projects working now, idle projects, On-call and watchdog.")
        .supportedFamilies([.systemLarge])
    }
}
