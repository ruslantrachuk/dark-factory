import SwiftUI

/// The project list shared by the drop-down and the widget.
/// `linkRows`: rows are `Link`s (the widget); otherwise buttons that open the link through `openTarget`.
struct StatusList: View {
    let feed: Feed
    let now: Date
    let linkRows: Bool

    var body: some View {
        let working = feed.projects.filter(isWorkingNow)
        let idle = feed.projects.filter { !isWorkingNow($0) }
        VStack(alignment: .leading, spacing: 8) {
            if feed.projects.isEmpty {
                Text("No projects in the feed").foregroundStyle(.secondary)
            }
            if !working.isEmpty { section("Working now", working) }
            if !idle.isEmpty { section("Idle", idle) }
        }
    }

    private func section(_ title: String, _ projects: [ProjectStatus]) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased()).font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
            ForEach(projects) { row($0) }
        }
    }

    @ViewBuilder
    private func row(_ p: ProjectStatus) -> some View {
        let content = ProjectRow(project: p, quota: feed.quota, now: now)
        if let url = p.link {
            if linkRows {
                Link(destination: openTarget(url)) { content }
            } else {
                Button { NSWorkspace.shared.open(openTarget(url)) } label: { content }
                    .buttonStyle(.plain)
                    .help("Open the session in Claude")
            }
        } else {
            content
        }
    }
}

struct ProjectRow: View {
    let project: ProjectStatus
    let quota: Quota?
    let now: Date

    var body: some View {
        VStack(alignment: .leading, spacing: 1) {
            HStack(spacing: 6) {
                Text(project.name)
                    .fontWeight(.medium)
                    .foregroundStyle(project.link == nil ? Color.primary : Color.accentColor)
                ModuleIcons(project: project)
                Spacer(minLength: 0)
                if project.link != nil {
                    Image(systemName: "arrow.up.forward").font(.caption2).foregroundStyle(.secondary)
                }
            }
            Text(statusText(rowStatus(project, quota: quota), now: now))
                .font(.caption).foregroundStyle(.secondary)
            if let line = oncallLine(project, now: now) {
                Text(line).font(.caption).foregroundStyle(.blue)
            }
            if let error = project.error {
                Text(error).font(.caption).foregroundStyle(.orange).lineLimit(1)
            }
        }
        .contentShape(Rectangle())
    }
}

/// "updated HH:MM · next at HH:MM" — the server writes the feed every 15 minutes.
func footerText(_ feed: Feed) -> String {
    "updated \(clock(feed.generatedAt)) · next at \(clock(feed.generatedAt.addingTimeInterval(900)))"
}
