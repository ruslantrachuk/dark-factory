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
    let now: Date

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
                        Gauge(label: "5h", value: q.fiveHour, resets: q.resets?.fiveHour.flatMap { untilText($0, now: now) })
                        Gauge(label: "7d", value: q.sevenDay, resets: q.resets?.sevenDay.flatMap { untilText($0, now: now) })
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

/// A quota bar; orange from 80 %, where the factory stops taking new work. `resets`: "2h 10m" under the bar.
struct Gauge: View {
    let label: String
    let value: Double
    var resets: String? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            bar
            if let resets {
                Text("resets in \(resets)").font(.system(size: 9)).foregroundStyle(.secondary).padding(.leading, 22)
            }
        }
    }

    private var bar: some View {
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
/// `linkRows`: tiles are `Link`s that open the drop-down at the project (the widget); otherwise an accordion: a
/// click opens the project's details under its row and closes the one open before.
/// `limit`: the widget shows as many as fit and a "+N more" line.
struct StatusList: View {
    let feed: Feed
    let now: Date
    let linkRows: Bool
    var compact = false
    var limit: Int? = nil
    /// The unfolded project, kept by the app so the widget can open the drop-down at one.
    var expanded: Binding<String?> = .constant(nil)

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
        if linkRows {
            Link(destination: projectLink(p.name)) { ProjectTile(project: p, quota: feed.quota, now: now, compact: compact) }
        } else {
            AccordionTile(project: p, quota: feed.quota, now: now, expanded: Binding(
                get: { expanded.wrappedValue == p.id },
                set: { open in withAnimation(.easeInOut(duration: 0.15)) { expanded.wrappedValue = open ? p.id : nil } }))
        }
    }
}

/// A project in the drop-down: the row with a chevron; a click unfolds the details below it.
struct AccordionTile: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date
    @Binding var expanded: Bool
    @State private var hovering = false

    var body: some View {
        Tile(active: project.working, highlighted: hovering) {
            VStack(alignment: .leading, spacing: 8) {
                Button { expanded.toggle() } label: {
                    ProjectRow(project: project, quota: quota, now: now, compact: false, chevron: expanded)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .onHover { inside in
                    hovering = inside
                    if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
                }
                if expanded {
                    Divider()
                    ProjectDetails(project: project, now: now)
                }
            }
        }
    }
}

/// The widget's tile: the row alone.
struct ProjectTile: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date
    var compact = false

    var body: some View {
        Tile(active: project.working, padding: compact ? 7 : 10) {
            ProjectRow(project: project, quota: quota, now: now, compact: compact, chevron: nil)
        }
        .contentShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
    }
}

/// Badge, name, status line, module icons; `chevron` (nil: none) points down while the details are open.
struct ProjectRow: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date
    let compact: Bool
    let chevron: Bool?

    var body: some View {
        let status = rowStatus(project, quota: quota)
        HStack(spacing: compact ? 8 : 10) {
            StatusBadge(status: status, size: compact ? 24 : 30)
            VStack(alignment: .leading, spacing: 1) {
                Text(project.name).font(.system(size: compact ? 12 : 13, weight: .semibold)).lineLimit(1)
                Text(statusText(status, now: now)).font(.system(size: 11)).foregroundStyle(.secondary).lineLimit(compact ? 1 : 2)
                if !compact, let error = project.error {
                    Text(error).font(.system(size: 11)).foregroundStyle(.orange).lineLimit(1)
                }
            }
            Spacer(minLength: 4)
            ModuleIcons(project: project)
            if let open = chevron {
                Image(systemName: "chevron.right").font(.system(size: 11, weight: .semibold)).foregroundStyle(.secondary)
                    .rotationEffect(.degrees(open ? 90 : 0))
            }
        }
    }
}

/// The second layer: the session, each stand, On-call, watchdog and queue — whatever the project has.
private struct ProjectDetails: View {
    let project: ProjectStatus
    let now: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let url = project.link {
                DetailRow(symbol: "bubble.left.and.text.bubble.right", title: "Session", value: "Open in Claude",
                          url: openTarget(url))
            }
            ForEach(project.stands ?? []) { stand in
                DetailRow(symbol: "display", title: stand.name,
                          value: ([stand.running ? "running" : "stopped"] + [standFreshness(stand)].compactMap { $0 })
                              .joined(separator: " · "),
                          tint: stand.running ? .green : nil,
                          url: stand.running ? stand.link : nil)
            }
            if project.oncall.installed {
                DetailRow(symbol: "person.bubble", title: "On-call",
                          value: ([project.oncall.running ? "running" : "not running"]
                                  + [project.oncall.lastMessageAt.map { "wrote \(dayAndTime($0, now: now))" }].compactMap { $0 })
                              .joined(separator: " · "),
                          tint: project.oncall.running ? .green : nil,
                          url: project.oncall.link.map { openTarget($0) })
            }
            if project.watchdog.installed {
                DetailRow(symbol: "checkmark.shield.fill", title: "Watchdog", value: project.watchdog.ok ? "on" : "off",
                          tint: project.watchdog.ok ? .green : nil)
            }
            if let level = project.level {
                DetailRow(symbol: "stairs", title: "Level", value: levelText(level))
                if let modules = modulesText(level) {
                    ModulesRow(summary: modules, modules: level.modules)
                }
            }
            DetailRow(symbol: "tray.full", title: "Queue",
                      value: project.queueReady > 0 ? "\(project.queueReady) ready" : "empty")
        }
    }
}

/// The Modules line folds once more: a click lists every canon module and whether the project has it.
struct ModulesRow: View {
    let summary: String
    let modules: [Level.Module]
    @State var open = false

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button { withAnimation(.easeInOut(duration: 0.15)) { open.toggle() } } label: {
                HStack(spacing: 6) {
                    Image(systemName: "square.stack.3d.up").foregroundStyle(.secondary).frame(width: 16)
                    Text("Modules").foregroundStyle(.primary)
                    Text(summary).foregroundStyle(.secondary)
                    Spacer(minLength: 4)
                    Image(systemName: "chevron.right").font(.system(size: 9, weight: .semibold)).foregroundStyle(.secondary)
                        .rotationEffect(.degrees(open ? 90 : 0))
                }
                .font(.system(size: 11))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if open {
                ForEach(modules, id: \.name) { m in
                    HStack(spacing: 6) {
                        Image(systemName: m.installed ? "checkmark.circle.fill" : "circle")
                            .foregroundStyle(m.installed ? Color.green : Color.secondary.opacity(0.6)).frame(width: 16)
                        Text(m.name).foregroundStyle(m.installed ? .primary : .secondary)
                        Spacer(minLength: 4)
                        Text(m.installed ? "installed" : "not installed").foregroundStyle(.secondary)
                    }
                    .font(.system(size: 11))
                    .padding(.leading, 22)
                }
            }
        }
    }
}

/// One detail line; with `url` it is a link and shows an arrow.
private struct DetailRow: View {
    let symbol: String
    let title: String
    let value: String
    var tint: Color? = nil
    var url: URL? = nil

    var body: some View {
        if let url {
            Button { NSWorkspace.shared.open(url) } label: { line(linked: true) }
                .buttonStyle(.plain)
                .onHover { inside in if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() } }
                .help(url.absoluteString)
        } else {
            line(linked: false)
        }
    }

    private func line(linked: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: symbol).foregroundStyle(tint ?? Color.secondary).frame(width: 16)
            Text(title).foregroundStyle(.primary)
            Text(value).foregroundStyle(.secondary).lineLimit(2).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 4)
            if linked { Image(systemName: "arrow.up.right").foregroundStyle(Color.accentColor) }
        }
        .font(.system(size: 11))
        .contentShape(Rectangle())
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
