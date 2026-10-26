import SwiftUI

struct MenuContent: View {
    @ObservedObject var model: FeedModel
    @State private var editingURL = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if model.feedURL.isEmpty || editingURL {
                SettingsView(url: model.feedURL) { url in
                    model.feedURL = url
                    editingURL = false
                }
            } else {
                header
                Divider()
                content
            }
            Divider()
            HStack {
                Button("Feed URL…") { editingURL.toggle() }
                Button("Refresh") { Task { await model.refresh() } }
                Spacer()
                Button("Quit") { NSApplication.shared.terminate(nil) }
            }
            .buttonStyle(.borderless)
            .font(.caption)
        }
        .padding(12)
        .frame(width: 320)
    }

    private var header: some View {
        HStack {
            StateGlyph(state: model.state)
            Text("Factory").font(.headline)
            Spacer()
            Text(quotaText(model.feed?.quota)).font(.caption).foregroundStyle(.secondary).monospacedDigit()
        }
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case let .noData(reason, lastGood):
            VStack(alignment: .leading, spacing: 4) {
                Text("No data").font(.subheadline.weight(.semibold)).foregroundStyle(.red)
                Text(reason).font(.caption)
                Text(lastGood.map { "last update \(clock($0))" } ?? "no update yet")
                    .font(.caption).foregroundStyle(.secondary)
            }
        default:
            if let feed = model.feed {
                StatusList(feed: feed, now: model.checkedAt, linkRows: false)
                Text(footerText(feed)).font(.caption2).foregroundStyle(.secondary)
            }
        }
    }
}
