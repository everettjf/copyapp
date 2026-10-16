import Foundation

// MARK: - JSON-RPC 2.0 Types

struct JSONRPCRequest: Codable {
    let jsonrpc: String
    let method: String
    let params: [String: JSONValue]?
    let id: JSONValue?
}

struct JSONRPCResponse: Encodable {
    let jsonrpc: String = "2.0"
    let result: [String: JSONValue]?
    let error: JSONRPCError?
    let id: JSONValue?
}

struct JSONRPCError: Encodable {
    let code: Int
    let message: String
    let data: [String: JSONValue]?

    static let parseError = JSONRPCError(code: -32700, message: "Parse error", data: nil)
    static let invalidRequest = JSONRPCError(code: -32600, message: "Invalid Request", data: nil)
    static let methodNotFound = JSONRPCError(code: -32601, message: "Method not found", data: nil)
    static let invalidParams = JSONRPCError(code: -32602, message: "Invalid params", data: nil)
    static let internalError = JSONRPCError(code: -32603, message: "Internal error", data: nil)
    /// Auth failure. Distinct code (-32099) so the HTTP layer can map ONLY this to
    /// 401 — business errors use serverError(-32000) and must return HTTP 200 with
    /// the failure in the JSON-RPC error body (otherwise a slow/timed-out action
    /// looks like "unauthorized" to clients).
    static let unauthorizedCode = -32099
    static let unauthorized = JSONRPCError(code: unauthorizedCode, message: "Unauthorized: valid auth token required", data: nil)

    static func serverError(_ msg: String) -> JSONRPCError {
        JSONRPCError(code: -32000, message: msg, data: nil)
    }
}

// MARK: - JSON Value (heterogeneous)

enum JSONValue: Codable, Equatable {
    case string(String)
    case int(Int)
    case double(Double)
    case bool(Bool)
    case null
    case array([JSONValue])
    case object([String: JSONValue])

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let v = try? container.decode(Bool.self) {
            self = .bool(v)
        } else if let v = try? container.decode(Int.self) {
            self = .int(v)
        } else if let v = try? container.decode(Double.self) {
            self = .double(v)
        } else if let v = try? container.decode(String.self) {
            self = .string(v)
        } else if let v = try? container.decode([JSONValue].self) {
            self = .array(v)
        } else if let v = try? container.decode([String: JSONValue].self) {
            self = .object(v)
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Unsupported JSON value")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let v): try container.encode(v)
        case .int(let v): try container.encode(v)
        case .double(let v): try container.encode(v)
        case .bool(let v): try container.encode(v)
        case .null: try container.encodeNil()
        case .array(let v): try container.encode(v)
        case .object(let v): try container.encode(v)
        }
    }

    var stringValue: String? {
        if case .string(let v) = self { return v }
        return nil
    }

    var doubleValue: Double? {
        switch self {
        case .double(let v): return v
        case .int(let v): return Double(v)
        default: return nil
        }
    }

    var boolValue: Bool? {
        if case .bool(let v) = self { return v }
        return nil
    }

    var intValue: Int? {
        switch self {
        case .int(let v): return v
        case .double(let v): return Int(v)      // JSON numbers often parse as double
        default: return nil
        }
    }

    var objectValue: [String: JSONValue]? {
        if case .object(let v) = self { return v }
        return nil
    }

    func toAny() -> Any {
        switch self {
        case .string(let v): return v
        case .int(let v): return v
        case .double(let v): return v
        case .bool(let v): return v
        case .null: return NSNull()
        case .array(let v): return v.map { $0.toAny() }
        case .object(let v): return v.mapValues { $0.toAny() }
        }
    }
}

// MARK: - Auth Types

struct AuthRequest: Codable {
    let clientName: String

    enum CodingKeys: String, CodingKey {
        case clientName = "client_name"
    }
}

struct AuthResponse: Encodable {
    let token: String
    let expiresIn: Int?

    enum CodingKeys: String, CodingKey {
        case token
        case expiresIn = "expires_in"
    }
}

/// One paired client. `id` is the token id (first 4 bytes of SHA256(K), hex) —
/// it is what the wire sends as `tok` and is a lookup handle only, never a
/// secret. `keyHex` is the actual 32-byte key K used to derive the per-request
/// MAC/encryption keys; it never leaves the device after pairing.
///
/// Expiry is idle-based: a session dies only after `inactivityWindow` of no use.
/// Every authenticated request slides `lastActiveAt` forward, so a token in
/// regular use never expires.
struct AuthSession: Identifiable, Codable {
    let id: String
    let keyHex: String
    let clientName: String
    let grantedAt: Date
    var lastActiveAt: Date
    /// Where the last authenticated request came from: the peer address
    /// (no port) and how it arrived — see `PeerSource`. Nil for sessions not
    /// used since this was recorded.
    var lastAddress: String?
    var lastVia: String?

    /// The 32-byte key, or nil if the stored record is corrupt.
    var key: Data? { Data(hexString: keyHex) }

    /// "Expiry if never used again" — informational, recomputed from last use.
    var expiresAt: Date { lastActiveAt.addingTimeInterval(AuthManager.inactivityWindow) }

    var isExpired: Bool { Date() >= expiresAt }

    enum CodingKeys: String, CodingKey {
        case id
        case keyHex = "key"
        case clientName = "client_name"
        case grantedAt = "granted_at"
        case lastActiveAt = "last_active_at"
        case lastAddress = "last_address"
        case lastVia = "last_via"
    }
}

/// How a request reached the server, judged by the interface it arrived on.
enum PeerSource: String {
    /// Loopback: an app on this device, or a computer over USB (usbmuxd
    /// forwards to the device's loopback, so the two look the same).
    case local
    /// Wi-Fi, Ethernet or the Personal Hotspot bridge.
    case lan
    /// Apple peer-to-peer Wi-Fi (AWDL): nearby discovery.
    case nearby
    /// A VPN or proxy tunnel (utun, ipsec, ppp).
    case vpn
    case cellular
    case other
}
