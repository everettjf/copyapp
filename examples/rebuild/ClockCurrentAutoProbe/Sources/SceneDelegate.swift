import UIKit

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
        alarm.tabBarItem = UITabBarItem(title: "Alarm", image: UIImage(systemName: "alarm"), tag: 1)
        stopwatch.tabBarItem = UITabBarItem(title: "Stopwatch", image: UIImage(systemName: "stopwatch"), tag: 2)
        timer.tabBarItem = UITabBarItem(title: "Timer", image: UIImage(systemName: "timer"), tag: 3)

        let tabs = UITabBarController()
        tabs.viewControllers = pages
        tabs.selectedIndex = 1
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
