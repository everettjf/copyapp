#ifndef ICTRL_H
#define ICTRL_H

#include <stddef.h>
#include <stdint.h>

// ── SHA-256 / HMAC ──────────────────────────────────────────────────────────

typedef struct {
    uint32_t h[8];
    uint64_t len;
    uint8_t buf[64];
    size_t buflen;
} sha256_ctx;

void sha256_init(sha256_ctx *c);
void sha256_update(sha256_ctx *c, const uint8_t *data, size_t n);
void sha256_final(sha256_ctx *c, uint8_t out[32]);
void sha256(const uint8_t *data, size_t n, uint8_t out[32]);

/// Split so the keystream loop can precompute the key schedule once and clone
/// the inner/outer state per block instead of re-deriving the pads each time.
typedef struct {
    sha256_ctx inner;
    sha256_ctx outer;
} hmac_ctx;

void hmac_init(hmac_ctx *c, const uint8_t *key, size_t keylen);
void hmac_update(hmac_ctx *c, const uint8_t *msg, size_t msglen);
void hmac_final(hmac_ctx *c, uint8_t out[32]);
void hmac_sha256(const uint8_t *key, size_t keylen,
                 const uint8_t *msg, size_t msglen, uint8_t out[32]);

// ── X25519 ──────────────────────────────────────────────────────────────────

void x25519(uint8_t out[32], const uint8_t scalar[32], const uint8_t point[32]);
void x25519_base(uint8_t out[32], const uint8_t scalar[32]);

// ── Growable byte buffer ────────────────────────────────────────────────────

typedef struct {
    uint8_t *data;
    size_t len;
    size_t cap;
} buf;

void buf_init(buf *b);
void buf_free(buf *b);
int buf_append(buf *b, const void *data, size_t n);
int buf_appendf(buf *b, const char *fmt, ...);

// ── Encoding ────────────────────────────────────────────────────────────────

void hex_encode(const uint8_t *in, size_t n, char *out);
int hex_decode(const char *in, uint8_t *out, size_t outlen);
size_t base64_encode(const uint8_t *in, size_t n, char *out);
size_t base64_decode(const char *in, size_t n, uint8_t *out);

#endif
