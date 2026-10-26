import SwiftUI

@main
struct FactoryBarApp: App {
    var body: some Scene {
        MenuBarExtra("Factory", systemImage: "building.2") { Text("Factory") }
    }
}
