import SwiftUI

/// "Factory" and the quota, as in the sketch.
struct FeedHeader: View {
    let quota: Quota?

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text("Factory").font(.system(size: 13, weight: .semibold))
            Spacer()
            Text(quotaText(quota)).font(.system(size: 10.5, design: .monospaced)).foregroundStyle(Color(nsColor: Palette.mute))
        }
    }
}

/// "updated HH:MM" on the left, "next at HH:MM" on the right; the server writes the feed every 15 minutes.
struct FeedFooter: View {
    let feed: Feed

    var body: some View {
        VStack(spacing: 6) {
            Hairline()
            HStack {
                Text("updated \(clock(feed.generatedAt))")
                Spacer()
                Text("next at \(clock(feed.generatedAt.addingTimeInterval(900)))")
            }
            .font(.system(size: 10, design: .monospaced))
            .foregroundStyle(Color(nsColor: Palette.faint))
        }
    }
}

struct Hairline: View {
    var body: some View { Rectangle().fill(Color(nsColor: Palette.line)).frame(height: 0.5) }
}

/// The project list shared by the drop-down and the widget.
/// `linkRows`: rows are `Link`s (the widget); otherwise buttons that open the link through `openTarget`.
struct StatusList: View {
    let feed: Feed
    let now: Date
    let linkRows: Bool

    var body: some View {
        let working = feed.projects.filter(isWorkingNow)
        let idle = feed.projects.filter { !isWorkingNow($0) }
        VStack(alignment: .leading, spacing: 0) {
            if feed.projects.isEmpty {
                Text("No projects in the feed").font(.system(size: 12)).foregroundStyle(Color(nsColor: Palette.mute))
                    .padding(.vertical, 8)
            }
            if !working.isEmpty { section("Working now", working) }
            if !idle.isEmpty { section("Idle", idle) }
        }
    }

    private func section(_ title: String, _ projects: [ProjectStatus]) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title.uppercased())
                .font(.system(size: 10)).tracking(0.8).foregroundStyle(Color(nsColor: Palette.mute))
                .padding(.top, 10).padding(.bottom, 4).padding(.horizontal, 2)
            ForEach(Array(projects.enumerated()), id: \.element.id) { index, project in
                if index > 0 { Hairline() }
                row(project)
            }
        }
    }

    @ViewBuilder
    private func row(_ p: ProjectStatus) -> some View {
        let content = ProjectRow(project: p, quota: feed.quota, now: now)
        if let url = p.link {
            if linkRows {
                Link(destination: openTarget(url)) { content }
            } else {
                HoverRow(url: openTarget(url)) { content }
            }
        } else {
            content
        }
    }
}

/// A clickable row in the drop-down: plain like the sketch, highlighted under the pointer.
private struct HoverRow<Content: View>: View {
    let url: URL
    @ViewBuilder let content: Content
    @State private var hovering = false

    var body: some View {
        Button { NSWorkspace.shared.open(url) } label: { content }
            .buttonStyle(.plain)
            .background(RoundedRectangle(cornerRadius: 5).fill(Color(nsColor: Palette.line)).opacity(hovering ? 1 : 0))
            .onHover { inside in
                hovering = inside
                if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() }
            }
            .help("Open the session in Claude")
    }
}

struct ProjectRow: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date

    var body: some View {
        let status = rowStatus(project, quota: quota)
        let (main, tail) = statusParts(status, now: now)
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline) {
                Text(project.name).font(.system(size: 12.5, weight: .semibold)).lineLimit(1)
                Spacer(minLength: 8)
                ModuleIcons(project: project)
            }
            HStack(spacing: 6) {
                Circle().fill(Color(nsColor: dotColor(status))).frame(width: 7, height: 7)
                Group {
                    if case .lastWorked = status {
                        Text(main).foregroundStyle(Color(nsColor: Palette.mute))
                    } else if let tail {
                        Text(main) + Text(" · \(tail)").foregroundColor(Color(nsColor: Palette.mute))
                    } else {
                        Text(main)
                    }
                }
                .font(.system(size: 11.5)).lineLimit(1)
            }
            if let line = oncallLine(project, now: now) {
                Text(line).font(.system(size: 10.5)).foregroundStyle(Color(nsColor: Palette.accent))
            }
            if let error = project.error {
                Text(error).font(.system(size: 10.5)).foregroundStyle(Color(nsColor: Palette.warn)).lineLimit(1)
            }
        }
        .padding(.vertical, 7).padding(.horizontal, 2)
        .contentShape(Rectangle())
    }

    private func dotColor(_ status: RowStatus) -> NSColor {
        switch status {
        case .building: Palette.ok
        case .waitingQuota: Palette.warn
        case .lastWorked: Palette.off
        }
    }
}

/// Why there is no data and when the last good feed was.
struct NoDataView: View {
    let reason: String
    let lastGood: Date?

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                FactoryShape(filled: false).stroke(Color(nsColor: Palette.bad), lineWidth: 1.2).frame(width: 14, height: 14)
                Text("No data").font(.system(size: 12.5, weight: .semibold)).foregroundStyle(Color(nsColor: Palette.bad))
            }
            Text(reason).font(.system(size: 11.5))
            Text(lastGood.map { "last update \(clock($0))" } ?? "no update yet")
                .font(.system(size: 10, design: .monospaced)).foregroundStyle(Color(nsColor: Palette.faint))
        }
        .padding(.top, 10)
    }
}
