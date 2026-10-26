import SwiftUI

// Layout in the style of Control Center: a summary tile and a quota tile on top, one rounded tile per project.

/// A rounded Control Center tile; `active` tints it with the accent color.
struct Tile<Content: View>: View {
    var active = false
    var highlighted = false
    var padding: CGFloat = 10
    @ViewBuilder let content: Content

    var body: some View {
        content
            .padding(padding)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(fill))
    }

    private var fill: Color {
        if active { return Color.accentColor.opacity(highlighted ? 0.2 : 0.12) }
        return Color.primary.opacity(highlighted ? 0.1 : 0.05)
    }
}

/// The two top tiles: the factory (state and what runs) and the quota gauges.
struct SummaryTiles: View {
    let state: IconState
    let feed: Feed?

    var body: some View {
        HStack(spacing: 8) {
            Tile {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Image(nsImage: menuBarImage(state, dim: false, showBadge: false))
                        Text(state.isNoData ? "No data" : "Factory").font(.system(size: 12, weight: .semibold))
                            .foregroundStyle(Color(nsColor: state.nsColor))
                    }
                    Text(summaryText(state: state, feed: feed)).font(.system(size: 11)).foregroundStyle(.secondary)
                        .lineLimit(2)
                }
            }
            if !state.isNoData { Tile {
                if let q = feed?.quota {
                    VStack(alignment: .leading, spacing: 5) {
                        Gauge(label: "5h", value: q.fiveHour)
                        Gauge(label: "7d", value: q.sevenDay)
                    }
                } else {
                    Text("Quota unknown").font(.system(size: 11)).foregroundStyle(.secondary)
                        .frame(maxHeight: .infinity, alignment: .leading)
                }
            } }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// A quota bar; orange from 80 %, where the factory stops taking new work.
struct Gauge: View {
    let label: String
    let value: Double

    var body: some View {
        HStack(spacing: 6) {
            Text(label).font(.system(size: 10, weight: .medium)).foregroundStyle(.secondary).frame(width: 16, alignment: .leading)
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(Color.primary.opacity(0.1))
                    Capsule().fill(value >= 80 ? Color.orange : Color.accentColor)
                        .frame(width: g.size.width * min(max(value, 0), 100) / 100)
                }
            }
            .frame(height: 5)
            Text("\(Int(value.rounded()))%").font(.system(size: 10).monospacedDigit()).foregroundStyle(.secondary)
                .frame(width: 30, alignment: .trailing)
        }
    }
}

/// The project tiles shared by the drop-down and the widget: working and waiting first, then idle.
/// `linkRows`: tiles are `Link`s (the widget); otherwise buttons that open the link through `openTarget`.
/// `limit`: the widget shows as many as fit and a "+N more" line.
struct StatusList: View {
    let feed: Feed
    let now: Date
    let linkRows: Bool
    var compact = false
    var limit: Int? = nil

    var body: some View {
        let ordered = feed.projects.filter(isWorkingNow) + feed.projects.filter { !isWorkingNow($0) }
        let shown = limit.map { Array(ordered.prefix($0)) } ?? ordered
        VStack(alignment: .leading, spacing: compact ? 6 : 8) {
            if ordered.isEmpty {
                Tile { Text("No projects in the feed").font(.system(size: 12)).foregroundStyle(.secondary) }
            }
            ForEach(shown) { tile($0) }
            if shown.count < ordered.count {
                Text("+\(ordered.count - shown.count) more").font(.system(size: 11)).foregroundStyle(.secondary)
                    .padding(.leading, 4)
            }
        }
    }

    @ViewBuilder
    private func tile(_ p: ProjectStatus) -> some View {
        if let url = p.link {
            if linkRows {
                Link(destination: openTarget(url)) { ProjectTile(project: p, quota: feed.quota, now: now, compact: compact) }
            } else {
                HoverTile(project: p, quota: feed.quota, now: now, url: openTarget(url))
            }
        } else {
            ProjectTile(project: p, quota: feed.quota, now: now, compact: compact)
        }
    }
}

/// A clickable tile in the drop-down: it darkens under the pointer.
private struct HoverTile: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date
    let url: URL
    @State private var hovering = false

    var body: some View {
        Button { NSWorkspace.shared.open(url) } label: {
            ProjectTile(project: project, quota: quota, now: now, highlighted: hovering)
        }
        .buttonStyle(.plain)
        .onHover { inside in
            hovering = inside
            if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
        }
        .help("Open the session in Claude")
    }
}

struct ProjectTile: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date
    var compact = false
    var highlighted = false

    var body: some View {
        let status = rowStatus(project, quota: quota)
        Tile(active: project.working, highlighted: highlighted, padding: compact ? 7 : 10) {
            HStack(spacing: compact ? 8 : 10) {
                StatusBadge(status: status, size: compact ? 24 : 30)
                VStack(alignment: .leading, spacing: 1) {
                    Text(project.name).font(.system(size: compact ? 12 : 13, weight: .semibold)).lineLimit(1)
                    Text(statusText(status, now: now)).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(compact ? 1 : 2)
                    if !compact, let line = oncallLine(project, now: now) {
                        Text(line).font(.system(size: 11)).foregroundStyle(.secondary)
                    }
                    if !compact, let error = project.error {
                        Text(error).font(.system(size: 11)).foregroundStyle(.orange).lineLimit(1)
                    }
                }
                Spacer(minLength: 4)
                ModuleIcons(project: project)
            }
        }
        .contentShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

/// The round icon of a project tile: hammer on the accent color while building, hourglass while waiting for quota,
/// moon when idle.
struct StatusBadge: View {
    let status: RowStatus
    let size: CGFloat

    var body: some View {
        ZStack {
            Circle().fill(background)
            Image(systemName: symbol).font(.system(size: size * 0.43, weight: .semibold)).foregroundStyle(foreground)
        }
        .frame(width: size, height: size)
    }

    private var symbol: String {
        switch status {
        case .building: "hammer.fill"
        case .waitingQuota: "hourglass"
        case .lastWorked: "moon.zzz.fill"
        }
    }

    private var background: Color {
        if case .building = status { return .accentColor }
        return Color.primary.opacity(0.1)
    }

    private var foreground: Color {
        switch status {
        case .building: .white
        case .waitingQuota: .orange
        case .lastWorked: .secondary
        }
    }
}

/// Why there is no data and when the last good feed was.
struct NoDataView: View {
    let reason: String
    let lastGood: Date?

    var body: some View {
        Tile {
            VStack(alignment: .leading, spacing: 3) {
                Text(reason).font(.system(size: 12))
                Text(lastGood.map { "Last update \(clock($0))" } ?? "No update yet")
                    .font(.system(size: 11)).foregroundStyle(.secondary)
            }
        }
    }
}

/// "Updated HH:MM · next at HH:MM": the heavy facts, which the server rebuilds every 15 minutes.
func updatedText(_ feed: Feed) -> String {
    "Updated \(clock(feed.heavyAt)) · next at \(clock(feed.heavyAt.addingTimeInterval(900)))"
}

/// The connection line: "Live · last change HH:MM" while the stream is open, else what the app is doing about it.
func connectionText(connected: Bool, everReceived: Bool, feed: Feed?) -> String {
    if connected, let feed { return "Live · last change \(clock(feed.generatedAt))" }
    if connected { return "Live" }
    return everReceived ? "Reconnecting…" : "Connecting…"
}
