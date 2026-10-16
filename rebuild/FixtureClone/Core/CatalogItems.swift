import Foundation

public struct CatalogItem {
    public let title: String
    public let detail: String

    public init(title: String, detail: String) {
        self.title = title
        self.detail = detail
    }
}

public enum CatalogItems {
    public static func localSamples() -> [CatalogItem] {
        [CatalogItem(title: "Alpha", detail: "Local sample A"),
         CatalogItem(title: "Beta", detail: "Local sample B")]
    }
}
