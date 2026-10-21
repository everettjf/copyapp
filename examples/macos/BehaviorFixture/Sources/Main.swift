import AppKit
import UniformTypeIdentifiers

final class DocumentWindow: NSObject, NSWindowDelegate, NSTextViewDelegate {
    let window: NSWindow
    let editor = NSTextView()
    let status = NSTextField(labelWithString: "")
    let number: Int
    var url: URL?
    var inspector: NSWindow?
    var statistics: NSTextField?
    weak var owner: FixtureApp?

    init(number: Int, owner: FixtureApp) {
        self.number = number
        self.owner = owner
        window = NSWindow(contentRect: NSRect(x: 180 + number * 24, y: 180 + number * 24, width: 720, height: 480),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        super.init()
        window.title = "Fixture Document \(number)"
        window.identifier = NSUserInterfaceItemIdentifier("fixture.document.\(number)")
        window.isReleasedWhenClosed = false
        window.delegate = self
        window.minSize = NSSize(width: 480, height: 320)
        let content = window.contentView!
        let scroll = NSScrollView()
        scroll.translatesAutoresizingMaskIntoConstraints = false
        scroll.hasVerticalScroller = true
        scroll.borderType = .bezelBorder
        editor.isRichText = false
        editor.allowsUndo = true
        editor.font = .monospacedSystemFont(ofSize: 16, weight: .regular)
        editor.textContainerInset = NSSize(width: 12, height: 12)
        editor.isVerticallyResizable = true
        editor.autoresizingMask = [.width]
        editor.setAccessibilityIdentifier("fixture.editor")
        editor.delegate = self
        editor.frame = NSRect(x: 0, y: 0, width: 660, height: 380)
        scroll.documentView = editor
        status.translatesAutoresizingMaskIntoConstraints = false
        status.font = .systemFont(ofSize: 12)
        status.setAccessibilityIdentifier("fixture.status")
        content.addSubview(scroll)
        content.addSubview(status)
        NSLayoutConstraint.activate([
            scroll.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 16),
            scroll.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -16),
            scroll.topAnchor.constraint(equalTo: content.topAnchor, constant: 16),
            scroll.bottomAnchor.constraint(equalTo: status.topAnchor, constant: -12),
            status.leadingAnchor.constraint(equalTo: scroll.leadingAnchor),
            status.trailingAnchor.constraint(lessThanOrEqualTo: scroll.trailingAnchor),
            status.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -14)
        ])
        editor.minSize = NSSize(width: 0, height: 0)
        editor.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        editor.textContainer?.containerSize = NSSize(width: 660, height: CGFloat.greatestFiniteMagnitude)
        applyWrapping()
    }

    var text: String { editor.string }
    var words: Int { text.split(whereSeparator: { $0.isWhitespace }).count }

    func applyWrapping() {
        let enabled = owner?.wrap ?? true
        editor.isHorizontallyResizable = !enabled
        editor.textContainer?.widthTracksTextView = enabled
        editor.enclosingScrollView?.hasHorizontalScroller = !enabled
        editor.textContainer?.containerSize = NSSize(width: enabled ? max(100, window.contentView!.bounds.width - 58) : 100_000,
                                                    height: CGFloat.greatestFiniteMagnitude)
        refresh()
    }

    func refresh() {
        status.stringValue = "Wrapping: \((owner?.wrap ?? true) ? "On" : "Off") | Characters: \(text.count) | Words: \(words)"
        statistics?.stringValue = "Characters: \(text.count)\nWords: \(words)\nUTF-8 bytes: \(text.utf8.count)"
    }

    func show() {
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(editor)
    }

    func textDidChange(_ notification: Notification) { refresh() }
    func windowDidBecomeKey(_ notification: Notification) { owner?.active = self }
    func windowWillClose(_ notification: Notification) {
        inspector?.close()
        owner?.documents.removeAll { $0 === self }
        if owner?.active === self { owner?.active = owner?.documents.last }
    }

    func showInspector() {
        if inspector == nil {
            let panel = NSWindow(contentRect: NSRect(x: 970, y: 310, width: 300, height: 170),
                                 styleMask: [.titled, .closable], backing: .buffered, defer: false)
            panel.title = "Fixture Inspector \(number)"
            panel.isReleasedWhenClosed = false
            let label = NSTextField(wrappingLabelWithString: "")
            label.frame = NSRect(x: 24, y: 26, width: 252, height: 112)
            label.font = .monospacedSystemFont(ofSize: 16, weight: .regular)
            label.setAccessibilityIdentifier("fixture.statistics")
            panel.contentView!.addSubview(label)
            inspector = panel
            statistics = label
        }
        refresh()
        inspector?.makeKeyAndOrderFront(nil)
    }
}

final class FixtureApp: NSObject, NSApplicationDelegate {
    var documents: [DocumentWindow] = []
    weak var active: DocumentWindow?
    var counter = 0
    var wrap: Bool {
        get { UserDefaults.standard.bool(forKey: "fixture.wrap") }
        set {
            UserDefaults.standard.set(newValue, forKey: "fixture.wrap")
            for document in documents { document.applyWrapping() }
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        UserDefaults.standard.register(defaults: ["fixture.wrap": true])
        NSApplication.shared.mainMenu = menus()
        NSApplication.shared.setActivationPolicy(.regular)
        newDocument(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }

    func item(_ title: String, _ action: Selector, _ key: String = "", shift: Bool = false) -> NSMenuItem {
        let result = NSMenuItem(title: title, action: action, keyEquivalent: key)
        result.target = self
        result.keyEquivalentModifierMask = shift ? [.command, .shift] : [.command]
        return result
    }

    func menus() -> NSMenu {
        let bar = NSMenu()
        func menu(_ title: String) -> NSMenu {
            let heading = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let menu = NSMenu(title: title)
            heading.submenu = menu
            bar.addItem(heading)
            return menu
        }
        let app = menu("Behavior Fixture")
        let quit = NSMenuItem(title: "Quit Behavior Fixture", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApplication.shared
        app.addItem(quit)
        let file = menu("File")
        file.addItem(item("New", #selector(newDocument(_:)), "n"))
        file.addItem(item("Open…", #selector(openDocument(_:)), "o"))
        file.addItem(item("Save As…", #selector(saveDocument(_:)), "s"))
        file.addItem(item("Export Summary…", #selector(exportSummary(_:)), "e", shift: true))
        let edit = menu("Edit")
        for (title, selector, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"),
                                       ("Copy", "copy:", "c"), ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(NSMenuItem(title: title, action: NSSelectorFromString(selector), keyEquivalent: key))
        }
        let tools = menu("Tools")
        tools.addItem(item("Toggle Wrapping", #selector(toggleWrapping(_:)), "w", shift: true))
        tools.addItem(item("Show Inspector", #selector(showInspector(_:)), "i", shift: true))
        tools.addItem(.separator())
        tools.addItem(item("Reset Fixture Settings", #selector(resetSettings(_:))))
        let windows = menu("Window")
        windows.addItem(NSMenuItem(title: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"))
        windows.addItem(NSMenuItem(title: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m"))
        windows.addItem(.separator())
        let all = NSMenuItem(title: "Bring All to Front", action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        all.target = NSApplication.shared
        windows.addItem(all)
        NSApplication.shared.windowsMenu = windows
        return bar
    }

    @objc func newDocument(_ sender: Any?) {
        counter += 1
        let document = DocumentWindow(number: counter, owner: self)
        documents.append(document)
        document.show()
    }

    func selected() -> DocumentWindow? {
        if let active { return active }
        newDocument(nil)
        return active ?? documents.last
    }

    func fail(_ error: Error) { NSAlert(error: error).runModal() }

    @objc func openDocument(_ sender: Any?) {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.plainText]
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = false
        if panel.runModal() == .OK, let url = panel.url {
            do {
                let text = try String(contentsOf: url, encoding: .utf8)
                newDocument(nil)
                let document = documents.last!
                document.url = url
                document.editor.string = text
                document.refresh()
            } catch { fail(error) }
        }
    }

    @objc func saveDocument(_ sender: Any?) {
        guard let document = selected() else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.plainText]
        panel.nameFieldStringValue = "fixture.txt"
        if panel.runModal() == .OK, let url = panel.url {
            do {
                try Data(document.text.utf8).write(to: url, options: .atomic)
                document.url = url
                document.refresh()
            } catch { fail(error) }
        }
    }

    @objc func exportSummary(_ sender: Any?) {
        guard let document = selected() else { return }
        let panel = NSSavePanel()
        panel.allowedContentTypes = [.json]
        panel.nameFieldStringValue = "summary.json"
        if panel.runModal() == .OK, let url = panel.url {
            do {
                let value: [String: Any] = ["text": document.text, "characters": document.text.count,
                                           "words": document.words, "utf8_bytes": document.text.utf8.count,
                                           "wrapping": wrap]
                try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .prettyPrinted]).write(to: url, options: .atomic)
            } catch { fail(error) }
        }
    }

    @objc func toggleWrapping(_ sender: Any?) { wrap.toggle() }
    @objc func resetSettings(_ sender: Any?) { wrap = true }
    @objc func showInspector(_ sender: Any?) { selected()?.showInspector() }
}

let application = NSApplication.shared
let delegate = FixtureApp()
application.delegate = delegate
application.run()
