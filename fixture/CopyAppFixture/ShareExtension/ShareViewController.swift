import UIKit
import UniformTypeIdentifiers

@objc(FixtureShareViewController)
final class ShareViewController: UIViewController {
    private let payloadLabel = UILabel()

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground

        let titleLabel = UILabel()
        titleLabel.text = "Copy APP Fixture Share Extension"
        titleLabel.textAlignment = .center
        payloadLabel.text = "Loading shared text…"
        payloadLabel.textAlignment = .center
        payloadLabel.numberOfLines = 0

        let stack = UIStackView(arrangedSubviews: [titleLabel, payloadLabel])
        stack.axis = .vertical
        stack.spacing = 16
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
            stack.leadingAnchor.constraint(greaterThanOrEqualTo: view.safeAreaLayoutGuide.leadingAnchor, constant: 24),
            stack.trailingAnchor.constraint(lessThanOrEqualTo: view.safeAreaLayoutGuide.trailingAnchor, constant: -24),
        ])
        loadSharedText()
    }

    private func loadSharedText() {
        let providers = (extensionContext?.inputItems ?? [])
            .compactMap { $0 as? NSExtensionItem }
            .flatMap { $0.attachments ?? [] }
        guard let pair = providers.compactMap({ provider -> (NSItemProvider, String)? in
            guard let type = provider.registeredTypeIdentifiers.first(where: {
                UTType($0)?.conforms(to: .text) == true
            }) else { return nil }
            return (provider, type)
        }).first else {
            payloadLabel.text = "No shared text"
            return
        }

        pair.0.loadItem(forTypeIdentifier: pair.1, options: nil) { [weak self] item, _ in
            let text: String?
            if let value = item as? String {
                text = value
            } else if let data = item as? Data {
                text = String(data: data, encoding: .utf8)
            } else {
                text = nil
            }
            DispatchQueue.main.async {
                self?.payloadLabel.text = text.map { "Received: " + String($0.prefix(200)) }
                    ?? "Unable to read shared text"
            }
        }
    }
}
