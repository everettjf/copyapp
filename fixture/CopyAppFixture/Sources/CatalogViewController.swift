import FixtureCore
import UIKit

@objc(FixtureCatalogViewController)
final class CatalogViewController: UITableViewController {
    private let cards = FixtureCatalog.mockResponse()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Catalog"
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "card")
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        cards.count
    }

    override func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = tableView.dequeueReusableCell(withIdentifier: "card", for: indexPath)
        let card = cards[indexPath.row]
        var content = cell.defaultContentConfiguration()
        content.text = card.title
        content.secondaryText = card.detail
        cell.contentConfiguration = content
        return cell
    }
}
