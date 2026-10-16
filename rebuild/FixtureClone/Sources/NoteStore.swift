import Foundation
import SQLite3

final class NoteStore {
    private let fileURL: URL

    init() {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
        fileURL = documents.appendingPathComponent("fixture-notes.sqlite")
    }

    private func withDatabase<T>(_ work: (OpaquePointer) -> T?) -> T? {
        var database: OpaquePointer?
        guard sqlite3_open(fileURL.path, &database) == SQLITE_OK,
              let database = database else {
            if let database = database { sqlite3_close(database) }
            return nil
        }
        defer { sqlite3_close(database) }
        guard sqlite3_exec(database,
                           "CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY, text TEXT NOT NULL)",
                           nil, nil, nil) == SQLITE_OK else { return nil }
        return work(database)
    }

    func count() -> Int {
        withDatabase { database in
            var statement: OpaquePointer?
            guard sqlite3_prepare_v2(database, "SELECT COUNT(*) FROM notes", -1,
                                     &statement, nil) == SQLITE_OK else { return nil }
            defer { sqlite3_finalize(statement) }
            guard sqlite3_step(statement) == SQLITE_ROW else { return nil }
            return Int(sqlite3_column_int(statement, 0))
        } ?? 0
    }

    @discardableResult
    func addSample() -> Bool {
        withDatabase { database in
            var statement: OpaquePointer?
            guard sqlite3_prepare_v2(database, "INSERT INTO notes (text) VALUES (?)", -1,
                                     &statement, nil) == SQLITE_OK else { return nil }
            defer { sqlite3_finalize(statement) }
            guard sqlite3_bind_text(statement, 1, "Sample note", -1,
                                    unsafeBitCast(-1, to: sqlite3_destructor_type.self)) == SQLITE_OK else {
                return nil
            }
            return sqlite3_step(statement) == SQLITE_DONE
        } ?? false
    }
}
