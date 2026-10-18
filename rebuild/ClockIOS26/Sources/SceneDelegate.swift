import UIKit

final class ClockTabsController: UITabBarController {
    private let tray = UIView()
    private var controls: [UIControl] = []
    private let names = ["World Clock", "Alarms", "Stopwatch", "Timers"]
    private let icons = ["globe", "alarm", "stopwatch", "timer"]

    override func viewDidLoad() {
        super.viewDidLoad()
        tabBar.isHidden = true
        tray.backgroundColor = UIColor(white: 0.12, alpha: 1)
        tray.layer.cornerRadius = 30
        tray.layer.borderWidth = 0.5
        tray.layer.borderColor = UIColor(white: 0.27, alpha: 1).cgColor
        view.addSubview(tray)
        for index in names.indices {
            let control = UIControl()
            control.tag = index
            control.isAccessibilityElement = true
            control.accessibilityLabel = names[index]
            control.accessibilityTraits = .button
            control.layer.cornerRadius = 27
            control.addTarget(self, action: #selector(selectPage(_:)), for: .touchUpInside)
            let icon = UIImageView(image: UIImage(systemName: icons[index]))
            icon.contentMode = .scaleAspectFit
            icon.tag = 100
            let title = UILabel()
            title.text = names[index]
            title.font = .systemFont(ofSize: 10)
            title.textAlignment = .center
            title.tag = 101
            control.addSubview(icon)
            control.addSubview(title)
            tray.addSubview(control)
            controls.append(control)
        }
        updateSelectedPage()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        tray.frame = CGRect(x: 21, y: view.bounds.height - 82,
                            width: view.bounds.width - 42, height: 61)
        let itemWidth = tray.bounds.width / CGFloat(controls.count)
        for (index, control) in controls.enumerated() {
            control.frame = CGRect(x: CGFloat(index) * itemWidth, y: 3,
                                   width: itemWidth, height: 55)
            control.viewWithTag(100)?.frame = CGRect(x: (itemWidth - 24) / 2,
                                                     y: 7, width: 24, height: 24)
            control.viewWithTag(101)?.frame = CGRect(x: 0, y: 35,
                                                     width: itemWidth, height: 15)
        }
        view.bringSubviewToFront(tray)
    }

    @objc private func selectPage(_ sender: UIControl) {
        selectedIndex = sender.tag
        updateSelectedPage()
    }

    private func updateSelectedPage() {
        for (index, control) in controls.enumerated() {
            let selected = index == selectedIndex
            control.backgroundColor = selected ? UIColor(white: 0.22, alpha: 1) : .clear
            let color = selected ? UIColor.systemOrange : UIColor.white
            (control.viewWithTag(100) as? UIImageView)?.tintColor = color
            (control.viewWithTag(101) as? UILabel)?.textColor = color
        }
    }
}

final class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession,
               options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }
        let world = UINavigationController(rootViewController: WorldClockController())
        let alarm = UINavigationController(rootViewController: AlarmController())
        let stopwatch = UINavigationController(rootViewController: StopwatchController())
        let timer = UINavigationController(rootViewController: TimerController())
        let pages = [world, alarm, stopwatch, timer]
        for page in pages { page.navigationBar.prefersLargeTitles = true }
        world.tabBarItem = UITabBarItem(title: "World Clock", image: UIImage(systemName: "globe"), tag: 0)
        alarm.tabBarItem = UITabBarItem(title: "Alarms", image: UIImage(systemName: "alarm"), tag: 1)
        stopwatch.tabBarItem = UITabBarItem(title: "Stopwatch", image: UIImage(systemName: "stopwatch"), tag: 2)
        timer.tabBarItem = UITabBarItem(title: "Timers", image: UIImage(systemName: "timer"), tag: 3)

        let tabs = ClockTabsController()
        tabs.viewControllers = pages
        tabs.selectedIndex = 0
        tabs.tabBar.tintColor = .systemOrange
        tabs.tabBar.unselectedItemTintColor = UIColor(white: 0.55, alpha: 1)
        tabs.tabBar.backgroundColor = .black
        let window = UIWindow(windowScene: windowScene)
        window.overrideUserInterfaceStyle = .dark
        window.rootViewController = tabs
        window.makeKeyAndVisible()
        self.window = window
    }
}
