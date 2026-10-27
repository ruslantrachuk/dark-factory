import ServiceManagement
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
                SummaryTiles(state: model.state, feed: model.feed, now: model.checkedAt)
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
            NoDataView(reason: model.connected ? "Live changes still arrive; the 15-minute update is missing."
                                               : "Reconnecting automatically.",
                       lastGood: lastGood)
        default:
            if model.feed == nil {
                Tile { Text("Connecting…").font(.system(size: 12)).foregroundStyle(.secondary) }
            }
            if let feed = model.feed {
                ScrollView {
                    StatusList(feed: feed, now: model.checkedAt, linkRows: false, expanded: $model.expanded)
                }
                .scrollBounceBehavior(.basedOnSize)
                .frame(maxHeight: 520)
                .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private var footer: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 1) {
                if let feed = model.feed { Text(updatedText(feed)) }
                Text(connectionText(connected: model.connected, everReceived: model.everReceived, feed: model.feed))
            }
            .font(.system(size: 11)).foregroundStyle(.secondary)
            Spacer()
            if model.refreshing {
                ProgressView().controlSize(.small).frame(width: 16, height: 16)
            } else {
                Button { model.refreshNow() } label: { Image(systemName: "arrow.clockwise") }
                    .frame(width: 16, height: 16)
                    .help("Refresh")
            }
            Menu {
                Button("Feed URL…") { editingURL = true }
                Toggle("Launch at Login", isOn: Binding(get: launchesAtLogin, set: setLaunchAtLogin))
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

/// Login item through ServiceManagement: no helper app, works sandboxed. The system lists it in
/// System Settings → General → Login Items, where it can also be turned off.
private func launchesAtLogin() -> Bool { SMAppService.mainApp.status == .enabled }

private func setLaunchAtLogin(_ on: Bool) {
    do {
        if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
    } catch {
        NSLog("FactoryBar: launch at login: \(error.localizedDescription)")
    }
}
