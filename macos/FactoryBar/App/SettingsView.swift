import SwiftUI

/// The one setting: where the feed is served, e.g. http://100.x.y.z:8765/status.json.
struct SettingsView: View {
    @State var url: String
    let save: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Feed URL").font(.headline)
            TextField("http://100.x.y.z:8765/status.json", text: $url)
                .textFieldStyle(.roundedBorder)
                .onSubmit(submit)
            Text("The address `fleet.py serve` listens on (FLEET_FEED_ADDR on the server).")
                .font(.caption).foregroundStyle(.secondary)
            Button("Save", action: submit)
                .keyboardShortcut(.defaultAction)
                .disabled(validFeedURL(url) == nil)
        }
    }

    private func submit() {
        guard validFeedURL(url) != nil else { return }
        save(url.trimmingCharacters(in: .whitespaces))
    }
}
