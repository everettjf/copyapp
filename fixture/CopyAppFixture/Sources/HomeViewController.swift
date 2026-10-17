import FixtureCore
import SwiftUI
import UIKit

@objc(FixtureHomeViewController)
final class HomeViewController: UIViewController {
    private let stack = UIStackView()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Copy APP Fixture"
        view.backgroundColor = .systemBackground
        stack.axis = .vertical
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 30),
        ])
        addButton("Counter · UserDefaults", action: #selector(showCounter))
        addButton("Notes · SQLite", action: #selector(showNotes))
        addButton("Catalog · Framework", action: #selector(showCatalog))
        addButton("Share sample text", action: #selector(shareSampleText))
    }

    private func addButton(_ title: String, action: Selector) {
        let button = UIButton(type: .system)
        button.setTitle(title, for: .normal)
        button.contentHorizontalAlignment = .leading
        button.titleLabel?.font = .preferredFont(forTextStyle: .title3)
        button.heightAnchor.constraint(greaterThanOrEqualToConstant: 54).isActive = true
        button.addTarget(self, action: action, for: .touchUpInside)
        stack.addArrangedSubview(button)
    }

    @objc private func showCounter() {
        navigationController?.pushViewController(UIHostingController(rootView: CounterView()), animated: true)
    }

    @objc private func showNotes() {
        navigationController?.pushViewController(NotesViewController(), animated: true)
    }

    @objc private func showCatalog() {
        navigationController?.pushViewController(CatalogViewController(), animated: true)
    }

    @objc private func shareSampleText(_ sender: UIButton) {
        let sheet = UIActivityViewController(activityItems: ["Copy APP fixture sample text"], applicationActivities: nil)
        if let popover = sheet.popoverPresentationController {
            popover.sourceView = sender
            popover.sourceRect = sender.bounds
        }
        present(sheet, animated: true)
    }
}
