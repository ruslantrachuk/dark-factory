import SwiftUI

struct MenuContent: View {
    @ObservedObject var model: FeedModel
    @State private var editingURL = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if model.feedURL.isEmpty || editingURL {
                Tile {
                    SettingsView(url: model.feedURL) { url in
                        model.feedURL = url
                        editingURL = false
                    }
                }
            } else {
                SummaryTiles(state: model.state, feed: model.feed)
                content
            }
            footer
        }
        .padding(10)
        .frame(width: 320)
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case let .noData(_, lastGood):
            NoDataView(reason: "The menu bar keeps trying every minute.", lastGood: lastGood)
        default:
            if let feed = model.feed {
                ScrollView {
                    StatusList(feed: feed, now: model.checkedAt, linkRows: false)
                }
                .scrollBounceBehavior(.basedOnSize)
                .frame(maxHeight: 520)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 12) {
            Text(model.feed.map(updatedText) ?? "").font(.system(size: 11)).foregroundStyle(.secondary)
            Spacer()
            Button { Task { await model.refresh() } } label: { Image(systemName: "arrow.clockwise") }
                .help("Refresh")
            Menu {
                Button("Feed URL…") { editingURL = true }
                Divider()
                Button("Quit FactoryBar") { NSApplication.shared.terminate(nil) }
            } label: { Image(systemName: "gearshape") }
                .menuIndicator(.hidden)
                .fixedSize()
                .help("Settings")
        }
        .buttonStyle(.borderless)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 4)
    }
}
