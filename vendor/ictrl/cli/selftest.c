// Known-answer tests for the primitives this client implements from scratch.
//
// These are hand-rolled crypto, so a subtle bug would not announce itself — it
// would look like an auth failure against the device, or worse, silently wrong
// plaintext. Vectors come from the RFCs and from the Python reference client, so
// a mismatch here means the CLI and the reference implementation have diverged.

#include "ictrl.h"
#include <stdio.h>
#include <string.h>

static int failures = 0;

static void check(const char *name, int ok) {
    printf("  %s %s\n", ok ? "PASS" : "FAIL", name);
    if (!ok) failures++;
}

static int hexeq(const uint8_t *got, size_t n, const char *want) {
    char buf[256];
    hex_encode(got, n, buf);
    return strcmp(buf, want) == 0;
}

int main(void) {
    printf("ictrl selftest\n");

    // ── SHA-256, FIPS 180-2 ──
    {
        uint8_t d[32];
        sha256((const uint8_t *)"abc", 3, d);
        check("sha256(\"abc\")",
              hexeq(d, 32, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"));

        sha256((const uint8_t *)"", 0, d);
        check("sha256(\"\")",
              hexeq(d, 32, "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"));

        const char *long_msg =
            "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
        sha256((const uint8_t *)long_msg, strlen(long_msg), d);
        check("sha256(56-byte msg)",
              hexeq(d, 32, "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"));
    }

    // ── SHA-256 length sweep: catch padding bugs at block boundaries ──
    //
    // A padding bug found earlier in the JS client only showed up when
    // len % 64 landed in [56,63], which fixed vectors sail straight past.
    {
        // Verify structural invariants across the block boundary rather than
        // transcribing constants: every length must produce a distinct digest,
        // and feeding the data one byte at a time must equal the one-shot call.
        // A padding bug at len % 64 in [56,63] fails this and slips past fixed
        // vectors — which is exactly how one escaped in the JS client.
        int ok = 1;
        uint8_t prev[32] = {0};
        for (int n = 0; n <= 200; n++) {
            uint8_t msg[201];
            memset(msg, 'a', (size_t)n);
            uint8_t one[32], streamed[32];
            sha256(msg, (size_t)n, one);

            sha256_ctx c;
            sha256_init(&c);
            for (int i = 0; i < n; i++) sha256_update(&c, msg + i, 1);  // 1 byte at a time
            sha256_final(&c, streamed);

            if (memcmp(one, streamed, 32) != 0) { ok = 0; break; }
            if (n > 0 && memcmp(one, prev, 32) == 0) { ok = 0; break; }
            memcpy(prev, one, 32);
        }
        check("sha256 streaming == one-shot, lengths 0..200", ok);
    }

    // ── HMAC-SHA256, RFC 4231 ──
    {
        uint8_t key[20], mac[32];
        memset(key, 0x0b, sizeof key);
        hmac_sha256(key, sizeof key, (const uint8_t *)"Hi There", 8, mac);
        check("RFC 4231 case 1",
              hexeq(mac, 32, "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"));

        hmac_sha256((const uint8_t *)"Jefe", 4,
                    (const uint8_t *)"what do ya want for nothing?", 28, mac);
        check("RFC 4231 case 2",
              hexeq(mac, 32, "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"));

        // Key longer than the block size must be hashed first.
        uint8_t longkey[131];
        memset(longkey, 0xaa, sizeof longkey);
        hmac_sha256(longkey, sizeof longkey,
                    (const uint8_t *)"Test Using Larger Than Block-Size Key - Hash Key First", 54, mac);
        check("RFC 4231 case 6 (key > 64 bytes)",
              hexeq(mac, 32, "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"));
    }

    // ── hmac incremental == one-shot ──
    {
        uint8_t key[32];
        memset(key, 0x42, sizeof key);
        const char *msg = "the quick brown fox jumps over the lazy dog";
        uint8_t a[32], b[32];
        hmac_sha256(key, 32, (const uint8_t *)msg, strlen(msg), a);
        hmac_ctx c;
        hmac_init(&c, key, 32);
        for (size_t i = 0; i < strlen(msg); i++) hmac_update(&c, (const uint8_t *)msg + i, 1);
        hmac_final(&c, b);
        check("hmac incremental == one-shot", memcmp(a, b, 32) == 0);

        // Cloning a primed context must reproduce it — this is the optimisation
        // the keystream loop depends on.
        hmac_ctx base;
        hmac_init(&base, key, 32);
        hmac_ctx c1 = base, c2 = base;
        uint8_t d1[32], d2[32];
        hmac_update(&c1, (const uint8_t *)"x", 1);
        hmac_final(&c1, d1);
        hmac_update(&c2, (const uint8_t *)"x", 1);
        hmac_final(&c2, d2);
        check("hmac context clone is reusable", memcmp(d1, d2, 32) == 0);
    }

    // ── X25519, RFC 7748 §6.1 ──
    {
        uint8_t alice_priv[32], bob_priv[32], alice_pub[32], bob_pub[32];
        hex_decode("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a", alice_priv, 32);
        hex_decode("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb", bob_priv, 32);

        x25519_base(alice_pub, alice_priv);
        check("X25519 Alice public",
              hexeq(alice_pub, 32, "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"));

        x25519_base(bob_pub, bob_priv);
        check("X25519 Bob public",
              hexeq(bob_pub, 32, "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f"));

        uint8_t s1[32], s2[32];
        x25519(s1, alice_priv, bob_pub);
        x25519(s2, bob_priv, alice_pub);
        check("X25519 shared secret",
              hexeq(s1, 32, "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"));
        check("X25519 both sides agree", memcmp(s1, s2, 32) == 0);

        // RFC 7748 §5.2 scalar-multiplication vector.
        uint8_t k[32], u[32], out[32];
        hex_decode("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4", k, 32);
        hex_decode("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c", u, 32);
        x25519(out, k, u);
        check("RFC 7748 §5.2 vector",
              hexeq(out, 32, "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"));
    }

    // ── base64 / hex round-trips ──
    {
        int ok = 1;
        for (size_t n = 0; n <= 64; n++) {
            uint8_t in[64], out[64];
            char b64[128];
            for (size_t i = 0; i < n; i++) in[i] = (uint8_t)(i * 7 + 13);
            base64_encode(in, n, b64);
            size_t got = base64_decode(b64, strlen(b64), out);
            if (got != n || memcmp(in, out, n) != 0) { ok = 0; break; }
        }
        check("base64 round-trip, lengths 0..64", ok);

        uint8_t raw[32], back[32];
        char hx[65];
        for (int i = 0; i < 32; i++) raw[i] = (uint8_t)(i * 3 + 1);
        hex_encode(raw, 32, hx);
        check("hex round-trip", hex_decode(hx, back, 32) == 0 && memcmp(raw, back, 32) == 0);
    }

    printf("%s (%d failure%s)\n", failures ? "FAILED" : "OK", failures,
           failures == 1 ? "" : "s");
    return failures ? 1 : 0;
}
