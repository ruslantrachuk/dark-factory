import AppIntents
import WidgetKit

/// The widget's own setting: no shared container with the app (a free personal team has no reliable App Group).
struct FeedURLIntent: WidgetConfigurationIntent {
    static var title: LocalizedStringResource = "Factory feed"
    static var description = IntentDescription("Where fleet.py serve publishes status.json.")

    @Parameter(title: "Feed URL", default: "http://100.x.y.z:8765/status.json")
    var feedURL: String
}
