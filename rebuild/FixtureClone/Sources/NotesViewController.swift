import UIKit

final class NotesViewController: UIViewController {
    private let store = NoteStore()
    private let countLabel = UILabel()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Notes"
        view.backgroundColor = .systemBackground

        countLabel.font = .systemFont(ofSize: 17)
        countLabel.textAlignment = .center
        countLabel.text = "Saved notes: \(store.count())"

        let addButton = UIButton(type: .system)
        addButton.setTitle("Add sample note", for: .normal)
        addButton.titleLabel?.font = .systemFont(ofSize: 17)
        addButton.addTarget(self, action: #selector(addNote), for: .touchUpInside)

        let stack = UIStackView(arrangedSubviews: [countLabel, addButton])
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 20
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
    }

    @objc private func addNote() {
        if store.addSample() {
            countLabel.text = "Saved notes: \(store.count())"
        }
    }
}
