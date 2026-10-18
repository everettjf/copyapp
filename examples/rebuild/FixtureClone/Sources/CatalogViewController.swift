import CloneCatalogCore
import UIKit

final class CatalogViewController: UITableViewController {
    private let items = CatalogItems.localSamples()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Catalog"
        tableView.register(UITableViewCell.self, forCellReuseIdentifier: "item")
        tableView.tableFooterView = UIView()
        tableView.rowHeight = 60
    }

    override func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int {
        items.count
    }

    override func tableView(_ tableView: UITableView,
                            cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = UITableViewCell(style: .subtitle, reuseIdentifier: "item")
        let item = items[indexPath.row]
        cell.textLabel?.text = item.title
        cell.detailTextLabel?.text = item.detail
        cell.selectionStyle = .none
        return cell
    }
}
