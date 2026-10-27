import SwiftUI

/// Where the feed is served, e.g. http://100.x.y.z:8765/status.json, and its token when the server asks for one.
struct SettingsView: View {
    @State var url: String
    @State var token: String
    let save: (String, String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Feed URL").font(.headline)
            TextField("http://100.x.y.z:8765/status.json", text: $url)
                .textFieldStyle(.roundedBorder)
                .onSubmit(submit)
            Text("The address `fleet.py serve` listens on (FLEET_FEED_ADDR on the server), or its Funnel address.")
                .font(.caption).foregroundStyle(.secondary)
            Text("Token").font(.headline).padding(.top, 4)
            SecureField("Empty when the server has no token", text: $token)
                .textFieldStyle(.roundedBorder)
                .onSubmit(submit)
            Text("FLEET_FEED_TOKEN from the server's fleet.env. Kept in the Keychain.")
                .font(.caption).foregroundStyle(.secondary)
            Button("Save", action: submit)
                .keyboardShortcut(.defaultAction)
                .disabled(validFeedURL(url) == nil)
        }
    }

    private func submit() {
        guard validFeedURL(url) != nil else { return }
        save(url.trimmingCharacters(in: .whitespaces), token.trimmingCharacters(in: .whitespacesAndNewlines))
    }
}
