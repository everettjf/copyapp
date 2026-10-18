import UIKit

private let accent = UIColor(red: 0.48, green: 0.11, blue: 0.85, alpha: 1)

final class PodcastsTabController: UITabBarController {
    override func viewDidLoad() {
        super.viewDidLoad()
        overrideUserInterfaceStyle = .light
        tabBar.tintColor = accent
        tabBar.backgroundColor = UIColor.systemBackground

        let pages: [(UIViewController, String, String)] = [
            (ListenNowController(), "Listen Now", "play.circle.fill"),
            (BrowseController(), "Browse", "square.grid.2x2.fill"),
            (LibraryController(), "Library", "square.stack.fill"),
            (SearchController(), "Search", "magnifyingglass")
        ]
        viewControllers = pages.map { page, title, symbol in
            let navigation = UINavigationController(rootViewController: page)
            navigation.navigationBar.prefersLargeTitles = true
            navigation.tabBarItem = UITabBarItem(title: title, image: UIImage(systemName: symbol), tag: 0)
            return navigation
        }
        selectedIndex = 1
        installMiniPlayer()
    }

    private func installMiniPlayer() {
        let bar = UIView()
        bar.translatesAutoresizingMaskIntoConstraints = false
        bar.backgroundColor = UIColor.systemGray6.withAlphaComponent(0.97)
        bar.layer.borderWidth = 0.5
        bar.layer.borderColor = UIColor.systemGray4.cgColor
        view.addSubview(bar)

        let artwork = UIImageView(image: UIImage(systemName: "dot.radiowaves.left.and.right"))
        artwork.tintColor = UIColor.systemGray2
        artwork.backgroundColor = UIColor.systemGray5
        artwork.contentMode = .center
        artwork.layer.cornerRadius = 4
        artwork.translatesAutoresizingMaskIntoConstraints = false
        bar.addSubview(artwork)

        let label = UILabel()
        label.text = "Not Playing"
        label.font = .systemFont(ofSize: 14)
        label.translatesAutoresizingMaskIntoConstraints = false
        bar.addSubview(label)

        let play = UIButton(type: .system)
        play.setImage(UIImage(systemName: "play.fill"), for: .normal)
        play.tintColor = .black
        play.accessibilityLabel = "Play"
        play.translatesAutoresizingMaskIntoConstraints = false
        bar.addSubview(play)

        NSLayoutConstraint.activate([
            bar.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            bar.bottomAnchor.constraint(equalTo: tabBar.topAnchor),
            bar.heightAnchor.constraint(equalToConstant: 58),
            artwork.leadingAnchor.constraint(equalTo: bar.leadingAnchor, constant: 20),
            artwork.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
            artwork.widthAnchor.constraint(equalToConstant: 44),
            artwork.heightAnchor.constraint(equalToConstant: 44),
            label.leadingAnchor.constraint(equalTo: artwork.trailingAnchor, constant: 14),
            label.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
            play.trailingAnchor.constraint(equalTo: bar.trailingAnchor, constant: -22),
            play.centerYAnchor.constraint(equalTo: bar.centerYAnchor),
            play.widthAnchor.constraint(equalToConstant: 36),
            play.heightAnchor.constraint(equalToConstant: 36)
        ])
    }
}

class BasePage: UIViewController {
    init(title: String) {
        super.init(nibName: nil, bundle: nil)
        self.title = title
        navigationItem.largeTitleDisplayMode = .always
    }

    required init?(coder: NSCoder) { fatalError("Storyboard is unused") }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemBackground
    }

    func addEmptyState() {
        let stack = UIStackView()
        stack.axis = .vertical
        stack.alignment = .center
        stack.spacing = 12
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        let headline = UILabel()
        headline.text = "No Shows Yet?"
        headline.font = .boldSystemFont(ofSize: 21)
        headline.textAlignment = .center
        stack.addArrangedSubview(headline)
        let detail = UILabel()
        detail.text = "Use the Browse tab to discover new stories, or search for a favorite show."
        detail.font = .systemFont(ofSize: 14)
        detail.textColor = .secondaryLabel
        detail.textAlignment = .center
        detail.numberOfLines = 0
        stack.addArrangedSubview(detail)
        for title in ["Search For a Podcast", "Follow a Show by URL"] {
            let button = UIButton(type: .system)
            button.setTitle(title, for: .normal)
            button.tintColor = accent
            button.titleLabel?.font = .systemFont(ofSize: 15)
            stack.addArrangedSubview(button)
        }
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 34),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -34),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor, constant: -64)
        ])
    }

    func addSectionList(_ titles: [String]) {
        let stack = UIStackView()
        stack.axis = .vertical
        stack.spacing = 0
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        for title in titles {
            let row = UILabel()
            row.text = "   " + title + "    ›"
            row.font = .systemFont(ofSize: 18)
            row.heightAnchor.constraint(equalToConstant: 48).isActive = true
            stack.addArrangedSubview(row)
            let line = UIView()
            line.backgroundColor = .systemGray5
            line.heightAnchor.constraint(equalToConstant: 0.5).isActive = true
            stack.addArrangedSubview(line)
        }
        NSLayoutConstraint.activate([
            stack.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 12),
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -20)
        ])
    }
}

final class LibraryController: BasePage {
    init() { super.init(title: "Library") }
    required init?(coder: NSCoder) { fatalError("Storyboard is unused") }

    override func viewDidLoad() {
        super.viewDidLoad()
        if ProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 17 {
            addSectionList(["Shows", "Channels", "Saved", "Downloaded", "Latest Episodes"])
            let recent = UILabel()
            recent.text = "Recently Updated"
            recent.font = .boldSystemFont(ofSize: 21)
            recent.translatesAutoresizingMaskIntoConstraints = false
            view.addSubview(recent)
            NSLayoutConstraint.activate([
                recent.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 20),
                recent.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor, constant: 278)
            ])
        } else {
            addEmptyState()
        }
    }
}

final class ListenNowController: BasePage {
    init() { super.init(title: "Listen Now") }
    required init?(coder: NSCoder) { fatalError("Storyboard is unused") }

    override func viewDidLoad() {
        super.viewDidLoad()
        navigationItem.rightBarButtonItem = UIBarButtonItem(
            image: UIImage(systemName: "person.crop.circle"), style: .plain,
            target: self, action: #selector(showAccount))
        navigationItem.rightBarButtonItem?.accessibilityLabel = "Account Settings"
        if ProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 17 {
            addSectionList(["Up Next", "Recently Played"])
        } else {
            addEmptyState()
        }
    }

    @objc private func showAccount() {
        let alert = UIAlertController(title: "Account Settings", message: nil, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Done", style: .cancel))
        present(alert, animated: true)
    }
}

final class BrowseController: BasePage {
    init() { super.init(title: "Browse") }
    required init?(coder: NSCoder) { fatalError("Storyboard is unused") }

    override func viewDidLoad() {
        super.viewDidLoad()
        addSectionList(["New Shows", "Featured", "Top Charts", "Categories"])
    }
}

final class SearchController: BasePage, UISearchBarDelegate {
    private let categories: [(String, String, UIColor)] = [
        ("Top Charts", "chart.bar.fill", UIColor(red: 0.56, green: 0.54, blue: 0.00, alpha: 1)),
        ("Audiobooks", "books.vertical.fill", UIColor(red: 0.96, green: 0.22, blue: 0.32, alpha: 1)),
        ("Horror & Supernatural", "moon.stars.fill", UIColor(red: 0.68, green: 0.20, blue: 0.70, alpha: 1)),
        ("Sleep", "moon.fill", UIColor(red: 0.02, green: 0.49, blue: 0.95, alpha: 1)),
        ("Comedy", "face.smiling.fill", UIColor(red: 0.94, green: 0.42, blue: 0.01, alpha: 1)),
        ("Business", "briefcase.fill", UIColor(red: 0.02, green: 0.36, blue: 0.84, alpha: 1)),
        ("Education", "graduationcap.fill", UIColor(red: 0.04, green: 0.66, blue: 0.62, alpha: 1)),
        ("Society & Culture", "person.2.fill", UIColor(red: 0.93, green: 0.37, blue: 0.02, alpha: 1))
    ]

    init() { super.init(title: "Search") }
    required init?(coder: NSCoder) { fatalError("Storyboard is unused") }

    override func viewDidLoad() {
        super.viewDidLoad()
        let scroll = UIScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(scroll)
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: view.safeAreaLayoutGuide.topAnchor),
            scroll.leadingAnchor.constraint(equalTo: view.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: view.trailingAnchor),
            scroll.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor)
        ])
        let content = UIStackView()
        content.axis = .vertical
        content.spacing = 10
        content.translatesAutoresizingMaskIntoConstraints = false
        scroll.addSubview(content)
        NSLayoutConstraint.activate([
            content.topAnchor.constraint(equalTo: scroll.contentLayoutGuide.topAnchor, constant: 4),
            content.leadingAnchor.constraint(equalTo: scroll.frameLayoutGuide.leadingAnchor, constant: 20),
            content.trailingAnchor.constraint(equalTo: scroll.frameLayoutGuide.trailingAnchor, constant: -20),
            content.bottomAnchor.constraint(equalTo: scroll.contentLayoutGuide.bottomAnchor),
        ])
        let search = UISearchBar()
        search.placeholder = ProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 17
            ? "Shows, Episodes, and More" : "All Podcasts"
        search.searchBarStyle = .minimal
        search.delegate = self
        content.addArrangedSubview(search)
        for start in stride(from: 0, to: categories.count, by: 2) {
            let row = UIStackView()
            row.axis = .horizontal
            row.spacing = 10
            row.distribution = .fillEqually
            for index in start..<min(start + 2, categories.count) {
                row.addArrangedSubview(categoryCard(categories[index]))
            }
            content.addArrangedSubview(row)
        }
    }

    private func categoryCard(_ category: (String, String, UIColor)) -> UIView {
        let card = UIView()
        card.backgroundColor = category.2
        card.layer.cornerRadius = 7
        card.clipsToBounds = true
        card.heightAnchor.constraint(equalToConstant: 126).isActive = true
        card.isAccessibilityElement = true
        card.accessibilityLabel = category.0
        let symbol = UIImageView(image: UIImage(systemName: category.1))
        symbol.tintColor = UIColor.white.withAlphaComponent(0.4)
        symbol.contentMode = .scaleAspectFit
        symbol.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(symbol)
        let label = UILabel()
        label.text = category.0
        label.textColor = .white
        label.font = .boldSystemFont(ofSize: 14)
        label.numberOfLines = 2
        label.translatesAutoresizingMaskIntoConstraints = false
        card.addSubview(label)
        NSLayoutConstraint.activate([
            symbol.topAnchor.constraint(equalTo: card.topAnchor, constant: 15),
            symbol.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -14),
            symbol.widthAnchor.constraint(equalToConstant: 58),
            symbol.heightAnchor.constraint(equalToConstant: 60),
            label.leadingAnchor.constraint(equalTo: card.leadingAnchor, constant: 11),
            label.trailingAnchor.constraint(equalTo: card.trailingAnchor, constant: -6),
            label.bottomAnchor.constraint(equalTo: card.bottomAnchor, constant: -9)
        ])
        return card
    }

    func searchBarSearchButtonClicked(_ searchBar: UISearchBar) {
        searchBar.resignFirstResponder()
    }
}
