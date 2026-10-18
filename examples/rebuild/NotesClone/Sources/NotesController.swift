import UIKit

private struct LocalNote: Codable {
    let id: UUID
    var text: String
    var modified: Date
    var title: String { text.components(separatedBy: .newlines).first ?? "" }
    var body: String { text.components(separatedBy: .newlines).dropFirst().joined(separator: "\n") }
}

private final class NoteStore {
    static let shared = NoteStore()
    private let file: URL
    private(set) var notes: [LocalNote] = []

    private init() {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        file = documents.appendingPathComponent("local-notes.json")
        if let data = try? Data(contentsOf: file),
           let saved = try? JSONDecoder().decode([LocalNote].self, from: data) {
            notes = saved
        }
    }

    func add() -> UUID {
        let note = LocalNote(id: UUID(), text: "", modified: Date())
        notes.insert(note, at: 0)
        save()
        return note.id
    }

    func update(_ id: UUID, text: String) {
        guard let index = notes.firstIndex(where: { $0.id == id }) else { return }
        notes[index].text = text
        notes[index].modified = Date()
        save()
    }

    func note(_ id: UUID) -> LocalNote? { notes.first { $0.id == id } }

    private func save() {
        if let data = try? JSONEncoder().encode(notes) {
            try? data.write(to: file, options: .atomic)
        }
    }
}

final class NotesController: UIViewController, UITextViewDelegate, UITextFieldDelegate {
    private enum Page: String { case folders, list, editor, search }
    private let ink = UIColor(red: 0.85, green: 0.67, blue: 0.11, alpha: 1)
    private let paper = UIColor(red: 0.95, green: 0.95, blue: 0.97, alpha: 1)
    private let store = NoteStore.shared
    private var page: Page = Page(rawValue: UserDefaults.standard.string(forKey: "page") ?? "folders") ?? .folders
    private var activeNoteID: UUID?
    private var searchField: UITextField?

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = paper
        show(page)
    }

    private func show(_ next: Page) {
        page = next
        UserDefaults.standard.set(next.rawValue, forKey: "page")
        view.endEditing(true)
        view.subviews.forEach { $0.removeFromSuperview() }
        searchField = nil
        switch next {
        case .folders: folders()
        case .list: list()
        case .editor: editor()
        case .search: search()
        }
    }

    private func label(_ text: String, size: CGFloat, weight: UIFont.Weight = .regular,
                       color: UIColor = .label) -> UILabel {
        let item = UILabel()
        item.text = text
        item.font = .systemFont(ofSize: size, weight: weight)
        item.textColor = color
        item.isAccessibilityElement = true
        return item
    }

    private func button(_ title: String, frame: CGRect, action: Selector,
                        systemImage: String? = nil) -> UIButton {
        let item = UIButton(type: .system)
        item.frame = frame
        if let systemImage = systemImage { item.setImage(UIImage(systemName: systemImage), for: .normal) }
        else { item.setTitle(title, for: .normal) }
        item.tintColor = ink
        item.setTitleColor(ink, for: .normal)
        item.accessibilityLabel = title
        item.addTarget(self, action: action, for: .touchUpInside)
        view.addSubview(item)
        return item
    }

    private var width: CGFloat { view.bounds.width }
    private var height: CGFloat { view.bounds.height }
    private func shortTime(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }
    private func title(_ text: String) {
        let header = label(text, size: 34, weight: .bold)
        header.frame = CGRect(x: 20, y: 96, width: width - 40, height: 44)
        view.addSubview(header)
    }

    private func backButton(_ text: String, action: Selector) {
        let item = button(text, frame: CGRect(x: 8, y: 48, width: 110, height: 44), action: action)
        item.setTitle("‹  " + text, for: .normal)
        item.titleLabel?.font = .systemFont(ofSize: 18)
        item.contentHorizontalAlignment = .left
    }

    private func searchButton() {
        let item = button("Search", frame: CGRect(x: 20, y: 145, width: width - 40, height: 36),
                          action: #selector(openSearch))
        item.backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1)
        item.layer.cornerRadius = 10
        item.setTitle("⌕  Search", for: .normal)
        item.setTitleColor(.secondaryLabel, for: .normal)
        item.contentHorizontalAlignment = .left
        item.contentEdgeInsets = UIEdgeInsets(top: 0, left: 9, bottom: 0, right: 0)
    }

    private func bottomNewNote() {
        button("New note", frame: CGRect(x: width - 59, y: height - 80, width: 52, height: 44),
               action: #selector(newNote), systemImage: "square.and.pencil")
    }

    private func folders() {
        view.backgroundColor = paper
        title("Folders")
        button("Edit", frame: CGRect(x: width - 64, y: 48, width: 50, height: 44), action: #selector(noop))
        searchButton()
        let account = label("On My iPhone", size: 21, weight: .bold)
        account.frame = CGRect(x: 20, y: 196, width: width - 40, height: 46)
        view.addSubview(account)
        button("Notes", frame: CGRect(x: 20, y: 242, width: width - 40, height: 44),
               action: #selector(openList)).contentHorizontalAlignment = .left
        button("New folder", frame: CGRect(x: 4, y: height - 80, width: 70, height: 44),
               action: #selector(noop), systemImage: "folder.badge.plus")
        bottomNewNote()
    }

    private func list() {
        view.backgroundColor = paper
        backButton("Folders", action: #selector(openFolders))
        button("Folder Actions", frame: CGRect(x: width - 58, y: 48, width: 44, height: 44),
               action: #selector(noop), systemImage: "ellipsis.circle")
        title("Notes")
        searchButton()
        let entries = store.notes.filter { !$0.text.isEmpty }
        if entries.isEmpty {
            let empty = label("No Notes", size: 12)
            empty.textAlignment = .center
            empty.frame = CGRect(x: 0, y: height - 79, width: width, height: 30)
            view.addSubview(empty)
        } else {
            let today = label("Today", size: 20, weight: .semibold)
            today.frame = CGRect(x: 40, y: 207, width: 180, height: 27)
            view.addSubview(today)
            let card = UIView(frame: CGRect(x: 20, y: 242, width: width - 40,
                                            height: CGFloat(min(entries.count, 9)) * 60))
            card.backgroundColor = .white
            card.layer.cornerRadius = 10
            card.clipsToBounds = true
            view.addSubview(card)
            for (index, note) in entries.prefix(9).enumerated() {
                let row = UIButton(type: .system)
                row.frame = CGRect(x: 28, y: CGFloat(index) * 60 + 6,
                                   width: card.bounds.width - 56, height: 26)
                row.setTitle(note.title, for: .normal)
                row.setTitleColor(.label, for: .normal)
                row.titleLabel?.font = .systemFont(ofSize: 16, weight: .semibold)
                row.contentHorizontalAlignment = .left
                row.tag = index
                row.accessibilityLabel = note.title
                row.addTarget(self, action: #selector(openFirstNote), for: .touchUpInside)
                card.addSubview(row)
                let subtitle = label("\(shortTime(note.modified))  \(note.body)",
                                     size: 14, color: .secondaryLabel)
                subtitle.frame = CGRect(x: 28, y: CGFloat(index) * 60 + 31,
                                        width: card.bounds.width - 56, height: 20)
                card.addSubview(subtitle)
                if index > 0 {
                    let line = UIView(frame: CGRect(x: 28, y: CGFloat(index) * 60,
                                                    width: card.bounds.width - 28, height: 0.5))
                    line.backgroundColor = .separator
                    card.addSubview(line)
                }
            }
            let count = label("\(entries.count) Notes", size: 12)
            count.textAlignment = .center
            count.frame = CGRect(x: 0, y: height - 79, width: width, height: 30)
            view.addSubview(count)
        }
        bottomNewNote()
    }

    private func editor() {
        view.backgroundColor = .white
        backButton("Folders", action: #selector(openFolders))
        button("Share", frame: CGRect(x: width - 113, y: 48, width: 42, height: 44),
               action: #selector(noop), systemImage: "square.and.arrow.up")
        button("Note Actions", frame: CGRect(x: width - 60, y: 48, width: 42, height: 44),
               action: #selector(noop), systemImage: "ellipsis.circle")

        guard let id = activeNoteID ?? store.notes.first?.id else { show(.list); return }
        activeNoteID = id
        let noteText = store.note(id)?.text ?? ""
        if noteText.isEmpty {
            let editor = UITextView(frame: CGRect(x: 21, y: 102, width: width - 42,
                                                  height: height - 192))
            editor.font = .systemFont(ofSize: 18)
            editor.text = noteText
            editor.delegate = self
            editor.accessibilityLabel = "Note"
            editor.textContainerInset = .zero
            view.addSubview(editor)
            button("Done", frame: CGRect(x: width - 76, y: 92, width: 64, height: 42), action: #selector(done))
            editor.becomeFirstResponder()
        } else {
            let title = label(store.note(id)?.title ?? "", size: 28, weight: .bold,
                              color: UIColor(white: 0.26, alpha: 1))
            title.frame = CGRect(x: 27, y: 102, width: width - 54, height: 36)
            view.addSubview(title)
            let body = label(store.note(id)?.body ?? "", size: 17,
                             color: UIColor(white: 0.27, alpha: 1))
            body.numberOfLines = 0
            body.frame = CGRect(x: 27, y: 139, width: width - 54, height: 28)
            view.addSubview(body)
        }
        let tools = ["checklist", "camera", "pencil.tip", "square.and.pencil"]
        for (index, symbol) in tools.enumerated() {
            button(symbol, frame: CGRect(x: CGFloat(index) * width / 4 + 12,
                                         y: height - 80, width: 48, height: 44),
                   action: symbol == "square.and.pencil" ? #selector(newNote) : #selector(noop),
                   systemImage: symbol)
        }
    }

    private func search() {
        view.backgroundColor = paper
        let field = UITextField(frame: CGRect(x: 20, y: 56, width: width - 105, height: 37))
        field.borderStyle = .roundedRect
        field.backgroundColor = UIColor(red: 0.89, green: 0.89, blue: 0.91, alpha: 1)
        field.placeholder = "Search"
        field.accessibilityLabel = "Search"
        let glass = UIImageView(image: UIImage(systemName: "magnifyingglass"))
        glass.tintColor = .secondaryLabel
        glass.contentMode = .center
        glass.frame = CGRect(x: 0, y: 0, width: 28, height: 37)
        field.leftView = glass
        field.leftViewMode = .always
        field.returnKeyType = .search
        field.autocorrectionType = .no
        field.spellCheckingType = .no
        field.delegate = self
        field.addTarget(self, action: #selector(queryChanged), for: .editingChanged)
        view.addSubview(field)
        searchField = field
        button("Cancel", frame: CGRect(x: width - 79, y: 56, width: 70, height: 37),
               action: #selector(openFolders))
        field.becomeFirstResponder()
    }

    @objc private func queryChanged() {
        view.subviews.filter { $0.tag == 900 }.forEach { $0.removeFromSuperview() }
        guard let query = searchField?.text, !query.isEmpty else { return }
        let matching = store.notes.filter { $0.text.localizedCaseInsensitiveContains(query) }
        let top = Array(matching.prefix(2))
        let rest = Array(matching.dropFirst(2))
        let notesY = CGFloat(112 + top.count * 81 + 65)
        let attachmentsY = notesY + CGFloat(rest.count * 81 + 63)
        let headings = [("Top Hits", top.isEmpty ? "None Found" : "\(top.count) Found", CGFloat(112)),
                        ("Notes", rest.isEmpty ? "None Found" : "\(rest.count) Found", notesY),
                        ("Attachments", "None Found", attachmentsY)]
        for (heading, count, y) in headings {
            let left = label(heading, size: 20, weight: .semibold)
            left.frame = CGRect(x: 36, y: y, width: 230, height: 30)
            left.tag = 900
            view.addSubview(left)
            let right = label(count, size: 16, color: .secondaryLabel)
            right.textAlignment = .right
            right.frame = CGRect(x: width - 150, y: y, width: 113, height: 30)
            right.tag = 900
            view.addSubview(right)
        }
        for (index, first) in matching.prefix(4).enumerated() {
            let y = index < 2 ? CGFloat(146 + index * 81) : notesY + 34 + CGFloat(index - 2) * 81
            let card = UIView(frame: CGRect(x: 20, y: y, width: width - 40, height: 81))
            card.backgroundColor = .white
            card.layer.cornerRadius = 10
            card.tag = 900
            view.addSubview(card)
            let item = label(first.title, size: 16, weight: .semibold, color: ink)
            item.frame = CGRect(x: 28, y: 9, width: card.bounds.width - 56, height: 22)
            card.addSubview(item)
            let subtitle = label("\(shortTime(first.modified))  \(first.body)",
                                 size: 14, color: .secondaryLabel)
            subtitle.frame = CGRect(x: 28, y: 31, width: card.bounds.width - 56, height: 20)
            card.addSubview(subtitle)
            let folder = label("Notes — On My iPhone", size: 14, color: .secondaryLabel)
            folder.frame = CGRect(x: 28, y: 51, width: card.bounds.width - 56, height: 20)
            card.addSubview(folder)
        }
    }

    func textViewDidChange(_ textView: UITextView) {
        if let id = activeNoteID { store.update(id, text: textView.text) }
    }

    @objc private func noop() {}
    @objc private func openFolders() { show(.folders) }
    @objc private func openList() { show(.list) }
    @objc private func openSearch() { show(.search) }
    @objc private func newNote() { activeNoteID = store.add(); show(.editor) }
    @objc private func done() {
        view.endEditing(true)
        show(.editor)
    }
    @objc private func openFirstNote(_ sender: UIButton) {
        let notes = store.notes.filter { !$0.text.isEmpty }
        guard sender.tag < notes.count else { return }
        activeNoteID = notes[sender.tag].id
        show(.editor)
    }
}
