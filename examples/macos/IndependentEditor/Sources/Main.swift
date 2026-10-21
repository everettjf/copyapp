import AppKit
import UniformTypeIdentifiers

// Independent implementation of the selected, observed fixture contract.
// The source fixture's package and data are never loaded by this application.
final class EditorSession: NSObject, NSWindowDelegate, NSTextViewDelegate {
    let index: Int
    unowned let workspace: EditorWorkspace
    let window: NSWindow
    let textView = NSTextView()
    let caption = NSTextField(labelWithString: "")
    let viewport = NSScrollView()
    var inspector: NSWindow?
    var readout: NSTextField?

    var wordCount: Int { textView.string.split(whereSeparator: { $0.isWhitespace }).count }

    init(index: Int, workspace: EditorWorkspace, text: String) {
        self.index = index
        self.workspace = workspace
        window = NSWindow(contentRect: NSRect(x: 180 + index * 24, y: 180 + index * 24,
                                              width: 720, height: 480),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable],
                          backing: .buffered, defer: false)
        super.init()
        window.title = "Fixture Document \(index)"
        window.identifier = NSUserInterfaceItemIdentifier("fixture.document.\(index)")
        window.delegate = self
        window.isReleasedWhenClosed = false
        window.minSize = NSSize(width: 480, height: 320)
        viewport.frame = NSRect(x: 16, y: 42, width: 688, height: 422)
        viewport.autoresizingMask = [.width, .height]
        viewport.borderType = .bezelBorder
        viewport.hasVerticalScroller = true
        textView.frame = NSRect(x: 0, y: 0, width: 669, height: 421)
        textView.isRichText = false
        textView.allowsUndo = true
        textView.font = .monospacedSystemFont(ofSize: 16, weight: .regular)
        textView.textContainerInset = NSSize(width: 12, height: 12)
        textView.minSize = .zero
        textView.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        textView.isVerticallyResizable = true
        textView.autoresizingMask = [.width]
        textView.setAccessibilityIdentifier("fixture.editor")
        textView.delegate = self
        textView.string = text
        viewport.documentView = textView
        caption.frame.origin = NSPoint(x: 16, y: 14)
        caption.font = .systemFont(ofSize: 12)
        caption.setAccessibilityIdentifier("fixture.status")
        window.contentView!.addSubview(viewport)
        window.contentView!.addSubview(caption)
        updateWrapping()
    }

    func focus() {
        window.makeKeyAndOrderFront(nil)
        window.makeFirstResponder(textView)
    }

    func updateWrapping() {
        textView.isHorizontallyResizable = !workspace.wrapping
        textView.textContainer?.widthTracksTextView = workspace.wrapping
        textView.textContainer?.containerSize = NSSize(
            width: workspace.wrapping ? max(100, window.contentView!.bounds.width - 58) : 100_000,
            height: CGFloat.greatestFiniteMagnitude)
        viewport.hasHorizontalScroller = !workspace.wrapping
        refresh()
    }

    func refresh() {
        let count = textView.string.count
        caption.stringValue = "Wrapping: \(workspace.wrapping ? "On" : "Off") | Characters: \(count) | Words: \(wordCount)"
        caption.sizeToFit()
        readout?.stringValue = "Characters: \(count)\nWords: \(wordCount)\nUTF-8 bytes: \(textView.string.utf8.count)"
    }

    func inspect() {
        if inspector == nil {
            let panel = NSWindow(contentRect: NSRect(x: 970, y: 310, width: 300, height: 170),
                                 styleMask: [.titled, .closable], backing: .buffered, defer: false)
            panel.title = "Fixture Inspector \(index)"
            panel.isReleasedWhenClosed = false
            let label = NSTextField(wrappingLabelWithString: "")
            label.frame = NSRect(x: 24, y: 26, width: 252, height: 112)
            label.font = .monospacedSystemFont(ofSize: 16, weight: .regular)
            label.setAccessibilityIdentifier("fixture.statistics")
            panel.contentView!.addSubview(label)
            inspector = panel
            readout = label
        }
        refresh()
        inspector!.makeKeyAndOrderFront(nil)
    }

    func textDidChange(_ notification: Notification) { refresh() }
    func windowDidBecomeKey(_ notification: Notification) { workspace.selected = self }
    func windowWillClose(_ notification: Notification) {
        inspector?.close()
        workspace.sessions.removeAll { $0 === self }
        if workspace.selected === self { workspace.selected = workspace.sessions.last }
    }
}

final class EditorWorkspace: NSObject, NSApplicationDelegate {
    var sessions: [EditorSession] = []
    weak var selected: EditorSession?
    var nextIndex = 0
    var wrapping: Bool {
        get { UserDefaults.standard.object(forKey: "editor.wrapping") as? Bool ?? true }
        set {
            UserDefaults.standard.set(newValue, forKey: "editor.wrapping")
            sessions.forEach { $0.updateWrapping() }
        }
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        installMenus()
        NSApp.setActivationPolicy(.regular)
        addDocument("")
        NSApp.activate(ignoringOtherApps: true)
    }

    func addDocument(_ text: String) {
        nextIndex += 1
        let session = EditorSession(index: nextIndex, workspace: self, text: text)
        sessions.append(session)
        session.focus()
    }

    func installMenus() {
        let bar = NSMenu()
        func group(_ title: String) -> NSMenu {
            let heading = NSMenuItem(title: title, action: nil, keyEquivalent: "")
            let menu = NSMenu(title: title)
            heading.submenu = menu
            bar.addItem(heading)
            return menu
        }
        func command(_ menu: NSMenu, _ title: String, _ action: Selector, _ key: String = "", shifted: Bool = false) {
            let entry = NSMenuItem(title: title, action: action, keyEquivalent: key)
            entry.target = self
            entry.keyEquivalentModifierMask = shifted ? [.command, .shift] : [.command]
            menu.addItem(entry)
        }
        let app = group("Copy APP Editor")
        let quit = NSMenuItem(title: "Quit Copy APP Editor", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApp
        app.addItem(quit)
        let file = group("File")
        command(file, "New", #selector(newDocument(_:)), "n")
        command(file, "Open…", #selector(openDocument(_:)), "o")
        command(file, "Save As…", #selector(saveDocument(_:)), "s")
        command(file, "Export Summary…", #selector(exportSummary(_:)), "e", shifted: true)
        let edit = group("Edit")
        for (title, selector, key) in [("Undo", "undo:", "z"), ("Cut", "cut:", "x"), ("Copy", "copy:", "c"),
                                       ("Paste", "paste:", "v"), ("Select All", "selectAll:", "a")] {
            edit.addItem(NSMenuItem(title: title, action: NSSelectorFromString(selector), keyEquivalent: key))
        }
        let tools = group("Tools")
        command(tools, "Toggle Wrapping", #selector(toggleWrapping(_:)), "w", shifted: true)
        command(tools, "Show Inspector", #selector(showInspector(_:)), "i", shifted: true)
        tools.addItem(.separator())
        command(tools, "Reset Fixture Settings", #selector(resetSettings(_:)))
        let windows = group("Window")
        windows.addItem(NSMenuItem(title: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w"))
        windows.addItem(NSMenuItem(title: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m"))
        windows.addItem(.separator())
        let front = NSMenuItem(title: "Bring All to Front", action: #selector(NSApplication.arrangeInFront(_:)), keyEquivalent: "")
        front.target = NSApp
        windows.addItem(front)
        NSApp.windowsMenu = windows
        // Attach the completed menu tree so AppKit can add its standard window
        // commands before the application becomes active.
        NSApp.mainMenu = bar
    }

    @objc func newDocument(_ sender: Any?) { addDocument("") }
    @objc func toggleWrapping(_ sender: Any?) { wrapping.toggle() }
    @objc func resetSettings(_ sender: Any?) { wrapping = true }
    @objc func showInspector(_ sender: Any?) { selected?.inspect() }

    @objc func openDocument(_ sender: Any?) {
        let chooser = NSOpenPanel()
        chooser.allowedContentTypes = [.plainText]
        chooser.canChooseDirectories = false
        chooser.allowsMultipleSelection = false
        guard chooser.runModal() == .OK, let file = chooser.url else { return }
        do { addDocument(try String(contentsOf: file, encoding: .utf8)) }
        catch { NSAlert(error: error).runModal() }
    }

    func write(using type: UTType, name: String, payload: () throws -> Data) {
        let chooser = NSSavePanel()
        chooser.allowedContentTypes = [type]
        chooser.nameFieldStringValue = name
        guard chooser.runModal() == .OK, let file = chooser.url else { return }
        do { try payload().write(to: file, options: .atomic) }
        catch { NSAlert(error: error).runModal() }
    }

    @objc func saveDocument(_ sender: Any?) {
        guard let session = selected else { return }
        write(using: .plainText, name: "fixture.txt") { Data(session.textView.string.utf8) }
    }

    @objc func exportSummary(_ sender: Any?) {
        guard let session = selected else { return }
        let text = session.textView.string
        let summary: [String: Any] = ["text": text, "characters": text.count, "words": session.wordCount,
                                     "utf8_bytes": text.utf8.count, "wrapping": wrapping]
        write(using: .json, name: "summary.json") {
            try JSONSerialization.data(withJSONObject: summary, options: [.prettyPrinted, .sortedKeys])
        }
    }
}

@main enum CopyAppEditor {
    static func main() {
        let app = NSApplication.shared
        let workspace = EditorWorkspace()
        app.delegate = workspace
        app.run()
    }
}
