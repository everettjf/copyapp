import Foundation

public struct FixtureCard {
    public let title: String
    public let detail: String

    public init(title: String, detail: String) {
        self.title = title
        self.detail = detail
    }
}

public enum FixtureCatalog {
    public static func mockResponse() -> [FixtureCard] {
        [FixtureCard(title: "Alpha", detail: "Local sample A"),
         FixtureCard(title: "Beta", detail: "Local sample B")]
    }
}
