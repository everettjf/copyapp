import SQLite3
import UIKit

@objc(FixtureNotesViewController)
final class NotesViewController: UIViewController {
    private let status = UILabel()
    private let store = NoteStore()

    override func viewDidLoad() {
        super.viewDidLoad()
        title = "Notes"
        view.backgroundColor = .systemBackground
        let button = UIButton(type: .system)
        button.setTitle("Add sample note", for: .normal)
        button.addTarget(self, action: #selector(addNote), for: .touchUpInside)
        let stack = UIStackView(arrangedSubviews: [status, button])
        stack.axis = .vertical
        stack.spacing = 24
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.centerXAnchor.constraint(equalTo: view.centerXAnchor),
            stack.centerYAnchor.constraint(equalTo: view.centerYAnchor),
        ])
        refresh()
    }

    @objc private func addNote() {
        do { try store.addSampleNote(); refresh() }
        catch { status.text = "SQLite error: \(error.localizedDescription)" }
    }

    private func refresh() {
        do { status.text = "Saved notes: \(try store.count())" }
        catch { status.text = "SQLite error: \(error.localizedDescription)" }
    }
}

final class NoteStore {
    private let path: String

    init() {
        let directory = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        path = directory.appendingPathComponent("fixture-notes.sqlite").path
    }

    private func withDatabase<T>(_ body: (OpaquePointer) throws -> T) throws -> T {
        var handle: OpaquePointer?
        guard sqlite3_open(path, &handle) == SQLITE_OK, let db = handle else {
            if handle != nil { sqlite3_close(handle) }
            throw NSError(domain: "CopyAppFixture.SQLite", code: 1)
        }
        defer { sqlite3_close(db) }
        guard sqlite3_exec(db, "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)",
                           nil, nil, nil) == SQLITE_OK else {
            throw NSError(domain: "CopyAppFixture.SQLite", code: 2)
        }
        return try body(db)
    }

    func addSampleNote() throws {
        try withDatabase { db in
            var statement: OpaquePointer?
            guard sqlite3_prepare_v2(db, "INSERT INTO notes (text) VALUES (?)", -1,
                                     &statement, nil) == SQLITE_OK else {
                throw NSError(domain: "CopyAppFixture.SQLite", code: 3)
            }
            defer { sqlite3_finalize(statement) }
            let note = "Sample note \(Int(Date().timeIntervalSince1970))"
            let result = note.withCString { pointer in
                sqlite3_bind_text(statement, 1, pointer, -1, unsafeBitCast(-1, to: sqlite3_destructor_type.self))
                return sqlite3_step(statement)
            }
            guard result == SQLITE_DONE else {
                throw NSError(domain: "CopyAppFixture.SQLite", code: 4)
            }
        }
    }

    func count() throws -> Int {
        try withDatabase { db in
            var statement: OpaquePointer?
            guard sqlite3_prepare_v2(db, "SELECT COUNT(*) FROM notes", -1,
                                     &statement, nil) == SQLITE_OK else {
                throw NSError(domain: "CopyAppFixture.SQLite", code: 5)
            }
            defer { sqlite3_finalize(statement) }
            guard sqlite3_step(statement) == SQLITE_ROW else {
                throw NSError(domain: "CopyAppFixture.SQLite", code: 6)
            }
            return Int(sqlite3_column_int(statement, 0))
        }
    }
}
