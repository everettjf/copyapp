import CryptoKit
import Foundation

/// An authenticated connection from this app to the runner on the same device.
///
/// The runner owns the authorized clients and its log; this app is a separate
/// process and can only reach them over the runner's encrypted `/rpc`, like any
/// other client. So it pairs once — the user approves it in the runner's
/// notification, exactly as for a computer — and keeps the key in its own
/// Keychain. Nothing here bypasses that approval: an app that could manage the
/// runner's clients without it could also have granted itself access.
///
/// Calls go to 127.0.0.1 only. Pairing uses the X25519 mode so the key never
/// crosses even the loopback interface in the clear.
final class RunnerClient {
    enum Failure: LocalizedError, Equatable {
        /// Nothing answers on the port: the runner isn't running.
        case notRunning
        /// No key yet; `pair()` first.
        case notPaired
        /// The runner no longer accepts our key (revoked, expired, reinstalled).
        case keyRejected
        case pairDenied
        /// Another request is waiting, or one was just refused.
        case pairUnavailable(retryAfter: Int, busy: Bool)
        case server(String)

        var errorDescription: String? {
            switch self {
            case .notRunning: return "The runner is not running."
            case .notPaired: return "Not connected to the runner."
            case .keyRejected: return "The runner no longer accepts this app's key."
            case .pairDenied: return "The request was refused or not answered in time."
            case .pairUnavailable(let s, let busy):
                return busy ? "Another request is waiting for approval (retry in \(s)s)."
                            : "A request was just refused; retry in \(s)s."
            case .server(let m): return m
            }
        }
    }

    /// What the runner shows in its approval prompt and client list.
    static let clientName = "iCTRL App"
    private static let keychainAccount = "runner-admin"

    private struct Record: Codable {
        var key: String   // hex, 32 bytes
        var tok: String   // hex, 4 bytes: the session id on the runner
    }

    let port: Int
    private var record: Record?

    init(port: Int) {
        self.port = port
        if let data = KeychainStore.load(account: Self.keychainAccount) {
            record = try? JSONDecoder().decode(Record.self, from: data)
        }
    }

    var isPaired: Bool { record != nil }
    /// This app's own session id on the runner, so the client list can mark it.
    var sessionID: String? { record?.tok }

    func forget() {
        record = nil
        KeychainStore.clear(account: Self.keychainAccount)
    }

    // MARK: - Pairing

    /// Ask the runner for a key. Blocks until the user answers the runner's
    /// notification or it times out (60 s on the runner side).
    func pair() async throws {
        let priv = Curve25519.KeyAgreement.PrivateKey()
        let pub = priv.publicKey.rawRepresentation
        let (status, body) = try await post("/pair", json: [
            "client_name": Self.clientName,
            "pub": pub.base64EncodedString(),
        ], timeout: 90)

        switch status {
        case 200: break
        case 403: throw Failure.pairDenied
        case 429:
            let error = body["error"] as? [String: Any]
            let wait = error?["retry_after"] as? Int ?? body["retry_after"] as? Int ?? 15
            let busy = error?["code"] as? String == "pair_busy"
            throw Failure.pairUnavailable(retryAfter: wait, busy: busy)
        default: throw Failure.server(Self.message(body, status: status))
        }

        guard let devicePubB64 = body["pub"] as? String,
              let devicePub = Data(base64Encoded: devicePubB64),
              let wrappedHex = body["token_ct"] as? String,
              let wrapped = Data(hexString: wrappedHex), wrapped.count == 32 else {
            throw Failure.server("Malformed pairing response")
        }
        let peer = try Curve25519.KeyAgreement.PublicKey(rawRepresentation: devicePub)
        let shared = try priv.sharedSecretFromKeyAgreement(with: peer).withUnsafeBytes { Data($0) }
        let kWrap = SecureEnvelope.hmac(shared, Data(SecureEnvelope.labelPair.utf8) + pub + devicePub)
        let pad = SecureEnvelope.hmac(kWrap, Data(SecureEnvelope.labelWrap.utf8))
        let key = Data(zip(wrapped, pad).map { $0 ^ $1 })

        let rec = Record(key: key.hexString, tok: SecureEnvelope.tokenId(for: key))
        record = rec
        if let data = try? JSONEncoder().encode(rec) {
            KeychainStore.save(data, account: Self.keychainAccount)
        }
    }

    // MARK: - RPC

    /// One enveloped JSON-RPC call; returns its `result` object.
    func call(_ method: String, _ params: [String: Any] = [:], timeout: TimeInterval = 15) async throws -> [String: Any] {
        guard let record, let key = Data(hexString: record.key), let tok4 = Data(hexString: record.tok),
              let nonce = SecureEnvelope.randomBytes(16) else { throw Failure.notPaired }

        let request: [String: Any] = ["jsonrpc": "2.0", "method": method, "params": params, "id": 1]
        let plaintext = try JSONSerialization.data(withJSONObject: request)
        let ts = UInt64(Date().timeIntervalSince1970)
        let kEnc = SecureEnvelope.hmac(key, Data(SecureEnvelope.labelEncRequest.utf8) + nonce)
        let kMac = SecureEnvelope.hmac(key, Data(SecureEnvelope.labelMac.utf8) + nonce)
        let ct = SecureEnvelope.keystreamXOR(key: kEnc, nonce: nonce, data: plaintext)
        let tag = SecureEnvelope.hmac(kMac, Data("v1".utf8) + tok4 + SecureEnvelope.be64(ts) + nonce + ct)

        let (status, body) = try await post("/rpc", json: [
            "v": 1, "tok": record.tok, "ts": Int(ts), "nonce": nonce.hexString,
            "ct": ct.base64EncodedString(), "tag": tag.hexString,
        ], timeout: timeout)

        if status == 401 {
            // Revoked from elsewhere, expired, or the runner was reinstalled:
            // the key is dead for good, so drop it rather than retry with it.
            forget()
            throw Failure.keyRejected
        }
        guard status == 200 else { throw Failure.server(Self.message(body, status: status)) }

        guard let respCtB64 = body["ct"] as? String, let respCt = Data(base64Encoded: respCtB64),
              let respTagHex = body["tag"] as? String, let respTag = Data(hexString: respTagHex),
              SecureEnvelope.tagMatches(respTag, message: Data("resp".utf8) + nonce + respCt, key: kMac) else {
            throw Failure.server("Response failed verification")
        }
        let kEncResp = SecureEnvelope.hmac(key, Data(SecureEnvelope.labelEncResponse.utf8) + nonce)
        let decoded = SecureEnvelope.keystreamXOR(key: kEncResp, nonce: nonce, data: respCt)
        guard let reply = try JSONSerialization.jsonObject(with: decoded) as? [String: Any] else {
            throw Failure.server("Malformed response")
        }
        if let error = reply["error"] as? [String: Any] {
            throw Failure.server(error["message"] as? String ?? "RPC error")
        }
        return reply["result"] as? [String: Any] ?? [:]
    }

    // MARK: - HTTP

    private func post(_ path: String, json: [String: Any], timeout: TimeInterval) async throws -> (Int, [String: Any]) {
        var request = URLRequest(url: URL(string: "http://127.0.0.1:\(port)\(path)")!)
        request.httpMethod = "POST"
        request.timeoutInterval = timeout
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: json)
        do {
            let (data, response) = try await URLSession.shared.data(for: request)
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            let body = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
            return (status, body)
        } catch let error as URLError where [.cannotConnectToHost, .networkConnectionLost,
                                             .cannotFindHost, .notConnectedToInternet].contains(error.code) {
            throw Failure.notRunning
        }
    }

    private static func message(_ body: [String: Any], status: Int) -> String {
        if let error = body["error"] as? [String: Any], let message = error["message"] as? String { return message }
        return "HTTP \(status)"
    }
}
