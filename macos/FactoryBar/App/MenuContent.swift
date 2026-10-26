import SwiftUI

struct MenuContent: View {
    @ObservedObject var model: FeedModel
    @State private var editingURL = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if model.feedURL.isEmpty || editingURL {
                SettingsView(url: model.feedURL) { url in
                    model.feedURL = url
                    editingURL = false
                }
            } else {
                FeedHeader(quota: model.feed?.quota)
                content
            }
            HStack(spacing: 12) {
                Button("Feed URL…") { editingURL.toggle() }
                Button("Refresh") { Task { await model.refresh() } }
                Spacer()
                Button("Quit") { NSApplication.shared.terminate(nil) }
            }
            .buttonStyle(.borderless)
            .font(.system(size: 10.5))
            .foregroundStyle(Color(nsColor: Palette.mute))
            .padding(.top, 6)
        }
        .padding(EdgeInsets(top: 12, leading: 12, bottom: 8, trailing: 12))
        .frame(width: 340)
    }

    @ViewBuilder
    private var content: some View {
        switch model.state {
        case let .noData(reason, lastGood):
            NoDataView(reason: reason, lastGood: lastGood)
        default:
            if let feed = model.feed {
                StatusList(feed: feed, now: model.checkedAt, linkRows: false)
                FeedFooter(feed: feed).padding(.top, 6)
            }
        }
    }
}
