// X25519 (RFC 7748) — needed only for LAN pairing, where the device wraps the
// session key against an ephemeral shared secret.
//
// Public-domain-style compact implementation using 64-bit limbs. Constant-time
// with respect to the scalar: the ladder swaps via a mask rather than branching,
// so a private key never steers control flow.

#include "ictrl.h"
#include <string.h>

typedef uint64_t fe[5];   // radix 2^51

static void fe_zero(fe h) { for (int i = 0; i < 5; i++) h[i] = 0; }
static void fe_one(fe h) { fe_zero(h); h[0] = 1; }
static void fe_copy(fe h, const fe f) { for (int i = 0; i < 5; i++) h[i] = f[i]; }

static void fe_add(fe h, const fe f, const fe g) {
    for (int i = 0; i < 5; i++) h[i] = f[i] + g[i];
}

static void fe_sub(fe h, const fe f, const fe g) {
    // Add 2p before subtracting so no limb underflows.
    static const uint64_t twop[5] = {0xfffffffffffda, 0xffffffffffffe,
                                     0xffffffffffffe, 0xffffffffffffe,
                                     0xffffffffffffe};
    for (int i = 0; i < 5; i++) h[i] = f[i] + twop[i] - g[i];
}

static void fe_carry(fe h) {
    const uint64_t MASK = 0x7ffffffffffffULL;
    uint64_t c;
    c = h[0] >> 51; h[0] &= MASK; h[1] += c;
    c = h[1] >> 51; h[1] &= MASK; h[2] += c;
    c = h[2] >> 51; h[2] &= MASK; h[3] += c;
    c = h[3] >> 51; h[3] &= MASK; h[4] += c;
    c = h[4] >> 51; h[4] &= MASK; h[0] += c * 19;
    c = h[0] >> 51; h[0] &= MASK; h[1] += c;
}

static void fe_mul(fe h, const fe f, const fe g) {
    const uint64_t MASK = 0x7ffffffffffffULL;
    __uint128_t r0, r1, r2, r3, r4;
    uint64_t g1_19 = 19 * g[1], g2_19 = 19 * g[2],
             g3_19 = 19 * g[3], g4_19 = 19 * g[4];

    r0 = (__uint128_t)f[0] * g[0] + (__uint128_t)f[1] * g4_19 +
         (__uint128_t)f[2] * g3_19 + (__uint128_t)f[3] * g2_19 +
         (__uint128_t)f[4] * g1_19;
    r1 = (__uint128_t)f[0] * g[1] + (__uint128_t)f[1] * g[0] +
         (__uint128_t)f[2] * g4_19 + (__uint128_t)f[3] * g3_19 +
         (__uint128_t)f[4] * g2_19;
    r2 = (__uint128_t)f[0] * g[2] + (__uint128_t)f[1] * g[1] +
         (__uint128_t)f[2] * g[0] + (__uint128_t)f[3] * g4_19 +
         (__uint128_t)f[4] * g3_19;
    r3 = (__uint128_t)f[0] * g[3] + (__uint128_t)f[1] * g[2] +
         (__uint128_t)f[2] * g[1] + (__uint128_t)f[3] * g[0] +
         (__uint128_t)f[4] * g4_19;
    r4 = (__uint128_t)f[0] * g[4] + (__uint128_t)f[1] * g[3] +
         (__uint128_t)f[2] * g[2] + (__uint128_t)f[3] * g[1] +
         (__uint128_t)f[4] * g[0];

    uint64_t c;
    h[0] = (uint64_t)r0 & MASK; c = (uint64_t)(r0 >> 51); r1 += c;
    h[1] = (uint64_t)r1 & MASK; c = (uint64_t)(r1 >> 51); r2 += c;
    h[2] = (uint64_t)r2 & MASK; c = (uint64_t)(r2 >> 51); r3 += c;
    h[3] = (uint64_t)r3 & MASK; c = (uint64_t)(r3 >> 51); r4 += c;
    h[4] = (uint64_t)r4 & MASK; c = (uint64_t)(r4 >> 51);
    h[0] += c * 19;
    c = h[0] >> 51; h[0] &= MASK; h[1] += c;
}

static void fe_sq(fe h, const fe f) { fe_mul(h, f, f); }

static void fe_mul121666(fe h, const fe f) {
    const uint64_t MASK = 0x7ffffffffffffULL;
    __uint128_t r;
    uint64_t c = 0;
    for (int i = 0; i < 5; i++) {
        r = (__uint128_t)f[i] * 121666 + c;
        h[i] = (uint64_t)r & MASK;
        c = (uint64_t)(r >> 51);
    }
    h[0] += c * 19;
    c = h[0] >> 51; h[0] &= MASK; h[1] += c;
}

/// Swap f and g iff b == 1, without branching on b.
static void fe_cswap(fe f, fe g, uint64_t b) {
    uint64_t mask = 0 - b;
    for (int i = 0; i < 5; i++) {
        uint64_t t = mask & (f[i] ^ g[i]);
        f[i] ^= t;
        g[i] ^= t;
    }
}

static void fe_frombytes(fe h, const uint8_t s[32]) {
    const uint64_t MASK = 0x7ffffffffffffULL;
    uint64_t w[4];
    for (int i = 0; i < 4; i++) {
        w[i] = 0;
        for (int j = 0; j < 8; j++) w[i] |= (uint64_t)s[i * 8 + j] << (8 * j);
    }
    h[0] = w[0] & MASK;
    h[1] = ((w[0] >> 51) | (w[1] << 13)) & MASK;
    h[2] = ((w[1] >> 38) | (w[2] << 26)) & MASK;
    h[3] = ((w[2] >> 25) | (w[3] << 39)) & MASK;
    h[4] = (w[3] >> 12) & MASK;   // top bit ignored, per RFC 7748
}

static void fe_tobytes(uint8_t s[32], const fe f) {
    const uint64_t MASK = 0x7ffffffffffffULL;
    fe t;
    fe_copy(t, f);
    fe_carry(t);
    fe_carry(t);
    // Conditionally subtract p to get the canonical representative.
    uint64_t q = (t[0] + 19) >> 51;
    q = (t[1] + q) >> 51;
    q = (t[2] + q) >> 51;
    q = (t[3] + q) >> 51;
    q = (t[4] + q) >> 51;
    t[0] += 19 * q;
    uint64_t c;
    c = t[0] >> 51; t[0] &= MASK; t[1] += c;
    c = t[1] >> 51; t[1] &= MASK; t[2] += c;
    c = t[2] >> 51; t[2] &= MASK; t[3] += c;
    c = t[3] >> 51; t[3] &= MASK; t[4] += c;
    t[4] &= MASK;

    uint64_t w0 = t[0] | (t[1] << 51);
    uint64_t w1 = (t[1] >> 13) | (t[2] << 38);
    uint64_t w2 = (t[2] >> 26) | (t[3] << 25);
    uint64_t w3 = (t[3] >> 39) | (t[4] << 12);
    uint64_t w[4] = {w0, w1, w2, w3};
    for (int i = 0; i < 4; i++)
        for (int j = 0; j < 8; j++) s[i * 8 + j] = (uint8_t)(w[i] >> (8 * j));
}

void x25519(uint8_t out[32], const uint8_t scalar[32], const uint8_t point[32]) {
    uint8_t e[32];
    memcpy(e, scalar, 32);
    e[0] &= 248;            // clamp, RFC 7748 §5
    e[31] &= 127;
    e[31] |= 64;

    fe x1, x2, z2, x3, z3, tmp0, tmp1;
    fe_frombytes(x1, point);
    fe_one(x2); fe_zero(z2);
    fe_copy(x3, x1); fe_one(z3);

    uint64_t swap = 0;
    for (int pos = 254; pos >= 0; pos--) {
        uint64_t b = (e[pos / 8] >> (pos & 7)) & 1;
        swap ^= b;
        fe_cswap(x2, x3, swap);
        fe_cswap(z2, z3, swap);
        swap = b;

        fe_sub(tmp0, x3, z3);
        fe_sub(tmp1, x2, z2);
        fe_add(x2, x2, z2);
        fe_add(z2, x3, z3);
        fe_mul(z3, tmp0, x2);
        fe_mul(z2, z2, tmp1);
        fe_sq(tmp0, tmp1);
        fe_sq(tmp1, x2);
        fe_add(x3, z3, z2);
        fe_sub(z2, z3, z2);
        fe_mul(x2, tmp1, tmp0);
        fe_sub(tmp1, tmp1, tmp0);
        fe_sq(z2, z2);
        fe_mul121666(z3, tmp1);
        fe_sq(x3, x3);
        fe_add(tmp0, tmp0, z3);
        fe_mul(z3, x1, z2);
        fe_mul(z2, tmp1, tmp0);
    }
    fe_cswap(x2, x3, swap);
    fe_cswap(z2, z3, swap);

    // Invert z2 via Fermat: z^(p-2), p = 2^255 - 19.
    fe z, t0, t1, t2;
    fe_copy(z, z2);
    fe_sq(t0, z);
    fe_sq(t1, t0); fe_sq(t1, t1);
    fe_mul(t1, z, t1);
    fe_mul(t0, t0, t1);
    fe_sq(t2, t0);
    fe_mul(t1, t1, t2);
    fe_sq(t2, t1); for (int i = 1; i < 5; i++) fe_sq(t2, t2);
    fe_mul(t1, t2, t1);
    fe_sq(t2, t1); for (int i = 1; i < 10; i++) fe_sq(t2, t2);
    fe_mul(t2, t2, t1);
    fe c;
    fe_sq(c, t2); for (int i = 1; i < 20; i++) fe_sq(c, c);
    fe_mul(t2, c, t2);
    fe_sq(t2, t2); for (int i = 1; i < 10; i++) fe_sq(t2, t2);
    fe_mul(t1, t2, t1);
    fe_sq(t2, t1); for (int i = 1; i < 50; i++) fe_sq(t2, t2);
    fe_mul(t2, t2, t1);
    fe_sq(c, t2); for (int i = 1; i < 100; i++) fe_sq(c, c);
    fe_mul(t2, c, t2);
    fe_sq(t2, t2); for (int i = 1; i < 50; i++) fe_sq(t2, t2);
    fe_mul(t1, t2, t1);
    fe_sq(t1, t1); for (int i = 1; i < 5; i++) fe_sq(t1, t1);
    fe_mul(t0, t1, t0);

    fe_mul(x2, x2, t0);
    fe_tobytes(out, x2);
}

void x25519_base(uint8_t out[32], const uint8_t scalar[32]) {
    static const uint8_t basepoint[32] = {9};
    x25519(out, scalar, basepoint);
}
