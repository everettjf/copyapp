import CryptoKit
import Foundation

/// Protocol v1 crypto primitives + envelope sealing/opening.
///
/// Wire-compatible with MinisApp's debug server (same labels, same construction),
/// so one client implementation drives both. All crypto on the request path is
/// HMAC-SHA256 only — implementable anywhere with an HMAC primitive (Python
/// stdlib, Node crypto, WebCrypto, `openssl` CLI). X25519 appears only in the
/// optional pairing mode A.
///
///     K          = 32B token key
///     tok        = first 4 bytes of SHA256(K), 8 hex chars (lookup id only)
///     nonce      = 16 random bytes per request
///     ts         = unix seconds (server accepts |ts - now| <= 120)
///
///     K_enc_req  = HMAC(K, "ictrl-v1|enc-req"  || nonce)
///     K_enc_resp = HMAC(K, "ictrl-v1|enc-resp" || nonce)
///     K_mac      = HMAC(K, "ictrl-v1|mac"      || nonce)
///
///     keystream(Kx) = HMAC(Kx, nonce || be32(0)) || HMAC(Kx, nonce || be32(1)) || ...
///     ct  = plaintext XOR keystream(K_enc_req)
///     tag = HMAC(K_mac, "v1" || tok_4B || be64(ts) || nonce || ct)
///
/// Encrypt-then-MAC: the tag covers the ciphertext, so a forged body is rejected
/// before any decryption happens.
enum SecureEnvelope {

    /// Domain-separation labels. Changing these breaks the wire protocol.
    static let labelMac = "ictrl-v1|mac"
    static let labelEncRequest = "ictrl-v1|enc-req"
    static let labelEncResponse = "ictrl-v1|enc-resp"
    static let labelPair = "ictrl-pair"
    static let labelWrap = "ictrl-wrap"

    /// Requests older/newer than this are rejected (replay + clock-skew bound).
    static let timestampWindow: TimeInterval = 120

    struct Failure: Error {
        let code: String
        let message: String
    }

    // MARK: - Primitives

    static func hmac(_ key: Data, _ data: Data) -> Data {
        Data(HMAC<SHA256>.authenticationCode(for: data, using: SymmetricKey(data: key)))
    }

    static func tagMatches(_ tag: Data, message: Data, key: Data) -> Bool {
        HMAC<SHA256>.isValidAuthenticationCode(tag, authenticating: message,
                                               using: SymmetricKey(data: key))
    }

    /// PRF-CTR stream cipher: keystream_i = HMAC-SHA256(key, nonce || be32(i)).
    static func keystreamXOR(key: Data, nonce: Data, data: Data) -> Data {
        var stream = Data(capacity: data.count + 32)
        var counter: UInt32 = 0
        while stream.count < data.count {
            var be = counter.bigEndian
            stream.append(hmac(key, nonce + Data(bytes: &be, count: 4)))
            counter += 1
        }
        return Data(zip(data, stream).map { $0 ^ $1 })
    }

    static func be64(_ value: UInt64) -> Data {
        var be = value.bigEndian
        return Data(bytes: &be, count: 8)
    }

    /// The lookup id derived from a key: first 4 bytes of SHA256(K), hex.
    static func tokenId(for key: Data) -> String {
        Data(SHA256.hash(data: key)).prefix(4).hexString
    }

    static func randomBytes(_ count: Int) -> Data? {
        var bytes = [UInt8](repeating: 0, count: count)
        guard SecRandomCopyBytes(kSecRandomDefault, count, &bytes) == errSecSuccess else { return nil }
        return Data(bytes)
    }

    // MARK: - Envelope shape

    /// True if the JSON object looks like a v1 request envelope.
    static func looksLikeEnvelope(_ obj: [String: Any]) -> Bool {
        (obj["v"] as? Int) == 1 && obj["tok"] is String && obj["ct"] is String
    }

    /// Parsed, still-unverified envelope fields.
    struct Parsed {
        let tokId: String
        let ts: Int
        let nonceHex: String
        let nonce: Data
        let ct: Data
        let tag: Data
        let tok4: Data
    }

    static func parse(_ obj: [String: Any]) throws -> Parsed {
        guard let tokId = obj["tok"] as? String,
              let ts = obj["ts"] as? Int, ts >= 0,   // negative would trap in UInt64(ts)
              let nonceHex = obj["nonce"] as? String,
              let ctB64 = obj["ct"] as? String,
              let tagHex = obj["tag"] as? String,
              let nonce = Data(hexString: nonceHex), nonce.count == 16,
              let ct = Data(base64Encoded: ctB64),
              let tag = Data(hexString: tagHex), tag.count == 32,
              let tok4 = Data(hexString: tokId), tok4.count == 4 else {
            throw Failure(code: "bad_envelope", message: "Malformed envelope fields")
        }
        return Parsed(tokId: tokId, ts: ts, nonceHex: nonceHex, nonce: nonce,
                      ct: ct, tag: tag, tok4: tok4)
    }

    // MARK: - Open / seal

    /// Verifies the tag and decrypts the request body. Throws on any mismatch.
    static func open(_ p: Parsed, key: Data) throws -> String {
        let kMac = hmac(key, Data(labelMac.utf8) + p.nonce)
        let signed = Data("v1".utf8) + p.tok4 + be64(UInt64(p.ts)) + p.nonce + p.ct
        guard tagMatches(p.tag, message: signed, key: kMac) else {
            throw Failure(code: "bad_tag", message: "MAC verification failed")
        }
        let kEncReq = hmac(key, Data(labelEncRequest.utf8) + p.nonce)
        let plaintextData = keystreamXOR(key: kEncReq, nonce: p.nonce, data: p.ct)
        guard let plaintext = String(data: plaintextData, encoding: .utf8) else {
            throw Failure(code: "bad_tag", message: "Decrypted payload is not UTF-8")
        }
        return plaintext
    }

    /// Encrypts a response under the same nonce with the response-direction key.
    static func seal(responseJSON: String, key: Data, nonce: Data, nonceHex: String) -> String {
        let kMac = hmac(key, Data(labelMac.utf8) + nonce)
        let kEncResp = hmac(key, Data(labelEncResponse.utf8) + nonce)
        let respCt = keystreamXOR(key: kEncResp, nonce: nonce, data: Data(responseJSON.utf8))
        let respTag = hmac(kMac, Data("resp".utf8) + nonce + respCt)
        let envelope: [String: Any] = [
            "v": 1,
            "nonce": nonceHex,
            "ct": respCt.base64EncodedString(),
            "tag": respTag.hexString,
        ]
        let data = (try? JSONSerialization.data(withJSONObject: envelope,
                                                options: .withoutEscapingSlashes)) ?? Data("{}".utf8)
        return String(data: data, encoding: .utf8) ?? "{}"
    }
}

// MARK: - Hex helpers

extension Data {
    init?(hexString hex: String) {
        guard hex.count % 2 == 0 else { return nil }
        var bytes = [UInt8]()
        bytes.reserveCapacity(hex.count / 2)
        var index = hex.startIndex
        while index < hex.endIndex {
            let next = hex.index(index, offsetBy: 2)
            guard let byte = UInt8(hex[index..<next], radix: 16) else { return nil }
            bytes.append(byte)
            index = next
        }
        self.init(bytes)
    }

    var hexString: String {
        map { String(format: "%02x", $0) }.joined()
    }
}
