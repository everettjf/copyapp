import SwiftUI
import UIKit

final class HomeViewController: UIViewController {
    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Copy APP Fixture"
        view.backgroundColor = .systemBackground

        let actions: [(String, Selector)] = [
            ("Counter · UserDefaults", #selector(showCounter)),
            ("Notes · SQLite", #selector(showNotes)),
            ("Catalog · Framework", #selector(showCatalog)),
        ]
        let stack = UIStackView()
        stack.axis = .vertical
        stack.alignment = .leading
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false
        for (name, action) in actions {
            let button = UIButton(type: .system)
            button.setTitle(name, for: .normal)
            button.titleLabel?.font = .systemFont(ofSize: 20)
            button.contentHorizontalAlignment = .leading
            button.addTarget(self, action: action, for: .touchUpInside)
            button.heightAnchor.constraint(equalToConstant: 50).isActive = true
            stack.addArrangedSubview(button)
        }
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24),
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 30),
        ])
    }

    @objc private func showCounter() {
        let controller = UIHostingController(rootView: CounterPage())
        controller.title = "Counter"
        navigationController?.pushViewController(controller, animated: true)
    }

    @objc private func showNotes() {
        navigationController?.pushViewController(NotesViewController(), animated: true)
    }

    @objc private func showCatalog() {
        navigationController?.pushViewController(CatalogViewController(), animated: true)
    }
}
