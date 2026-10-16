// ictrl — a static CLI for the iCTRL encrypted JSON-RPC protocol (v1).
//
// Exists because the Python reference client is a poor fit for the Minis
// sandbox: that Alpine minirootfs has no python3, so using it costs an `apk add`
// (network round-trip + ~50MB) before the first command, and every subsequent
// run pays interpreter startup through an emulated syscall layer over a
// SQLite-backed filesystem. This is one static file with no runtime deps.
//
// Protocol: every /rpc body is an encrypted envelope. The request path is
// HMAC-SHA256 only; X25519 appears solely in LAN pairing.

#include "ictrl.h"
#ifdef __APPLE__
#include "nearby.h"
#endif

#include <errno.h>
#include <stdarg.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#ifdef __APPLE__
#include <poll.h>
#include <signal.h>
#endif
#include <time.h>
#include <unistd.h>

#define LABEL_MAC      "ictrl-v1|mac"
#define LABEL_ENC_REQ  "ictrl-v1|enc-req"
#define LABEL_ENC_RESP "ictrl-v1|enc-resp"
#define LABEL_PAIR     "ictrl-pair"
#define LABEL_WRAP     "ictrl-wrap"

/// Key-store entry to use when it differs from the host: nearby devices are
/// keyed by "nearby:<device id>" because their link-local address changes.
static const char *g_store_key = NULL;
/// Set when the key in use was found under an older name: after a call with
/// it succeeds, it is saved under this device's name too.
static const char *g_adopt_to = NULL;
/// Set while pairing implicitly before a call: progress goes to stderr so the
/// call's JSON stays alone on stdout.
static int g_pair_implicit = 0;
#define STORE_KEY(hostport) (g_store_key ? g_store_key : (hostport))

static void die(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    fprintf(stderr, "ictrl: ");
    vfprintf(stderr, fmt, ap);
    fprintf(stderr, "\n");
    va_end(ap);
    exit(1);
}

// ── Random ──────────────────────────────────────────────────────────────────

/// Nonce uniqueness is what keeps the stream cipher safe, so a weak source here
/// would be a real break, not a nit. /dev/urandom only — never a PRNG fallback.
static void random_bytes(uint8_t *out, size_t n) {
    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) die("cannot open /dev/urandom: %s", strerror(errno));
    size_t got = 0;
    while (got < n) {
        ssize_t r = read(fd, out + got, n - got);
        if (r <= 0) die("short read from /dev/urandom");
        got += (size_t)r;
    }
    close(fd);
}

// ── Envelope crypto ─────────────────────────────────────────────────────────

/// keystream_i = HMAC(key, nonce || be32(i)), XORed over the data.
///
/// The key schedule is derived once and the inner/outer states copied per block.
/// Re-deriving it for each 32-byte block is what made the Python client spend
/// seconds decrypting a screenshot.
static void keystream_xor(const uint8_t key[32], const uint8_t nonce[16],
                          uint8_t *data, size_t len) {
    hmac_ctx base;
    hmac_init(&base, key, 32);
    uint8_t block[32];
    uint32_t counter = 0;
    for (size_t off = 0; off < len; off += 32, counter++) {
        hmac_ctx c = base;   // clone the precomputed pads
        uint8_t ctr[4] = {(uint8_t)(counter >> 24), (uint8_t)(counter >> 16),
                          (uint8_t)(counter >> 8), (uint8_t)counter};
        hmac_update(&c, nonce, 16);
        hmac_update(&c, ctr, 4);
        hmac_final(&c, block);
        size_t n = len - off < 32 ? len - off : 32;
        for (size_t i = 0; i < n; i++) data[off + i] ^= block[i];
    }
}

/// Compare MACs without leaking where they diverge.
static int ct_equal(const uint8_t *a, const uint8_t *b, size_t n) {
    uint8_t d = 0;
    for (size_t i = 0; i < n; i++) d |= (uint8_t)(a[i] ^ b[i]);
    return d == 0;
}

// ── HTTP ────────────────────────────────────────────────────────────────────

#ifdef __APPLE__
#define SO_RECV_ANYIF_OPT 0x1104   // <sys/socket.h> (private): accept input on a restricted interface
#define NC_PATH "/usr/bin/nc"

// Connect with a deadline: a peer whose reply is dropped would otherwise hold
// a blocking connect for over a minute.
static int connect_within(int fd, const struct sockaddr *sa, socklen_t len, int ms) {
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    int rc = connect(fd, sa, len);
    if (rc != 0 && errno == EINPROGRESS) {
        struct pollfd pfd = { fd, POLLOUT, 0 };
        rc = poll(&pfd, 1, ms);
        if (rc == 0) { errno = ETIMEDOUT; rc = -1; }
        else if (rc > 0) {
            int err = 0;
            socklen_t el = sizeof err;
            getsockopt(fd, SOL_SOCKET, SO_ERROR, &err, &el);
            if (err) { errno = err; rc = -1; } else rc = 0;
        }
    }
    fcntl(fd, F_SETFL, flags);
    return rc;
}

// Reach a zoned link-local peer through Apple's /usr/bin/nc with
// SO_RECV_ANYIF (-A). macOS Local Network privacy can refuse this process
// outright (an instant EHOSTUNREACH, e.g. for a locally built binary run
// from a context never granted access); the platform nc is not subject to
// it. Returns one end of a socketpair wired to nc's stdin and stdout.
static int nc_relay(const char *host, const char *port) {
    int sv[2], errp[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, sv) != 0 || pipe(errp) != 0) return -1;
    signal(SIGCHLD, SIG_IGN);   // nc outlives the call; let the kernel reap it
    pid_t pid = fork();
    if (pid < 0) return -1;
    if (pid == 0) {
        dup2(sv[1], 0);
        dup2(sv[1], 1);
        dup2(errp[1], 2);
        close(sv[0]); close(sv[1]); close(errp[0]); close(errp[1]);
        // -G: connect timeout; -w: idle timeout; -v: report "succeeded!".
        // -w outlasts a pairing request, which waits up to 60 s for the
        // user's answer with nothing on the wire.
        execl(NC_PATH, "nc", "-6", "-A", "-v", "-G", "10", "-w", "120", host, port, (char *)NULL);
        _exit(127);
    }
    close(sv[1]);
    close(errp[1]);
    char line[512];
    size_t n = 0;
    struct pollfd pfd = { errp[0], POLLIN, 0 };
    while (n < sizeof line - 1 && !memchr(line, '\n', n) && poll(&pfd, 1, 12000) > 0) {
        ssize_t r = read(errp[0], line + n, sizeof line - 1 - n);
        if (r <= 0) break;
        n += (size_t)r;
    }
    line[n] = 0;
    close(errp[0]);
    if (!strstr(line, "succeeded")) {
        close(sv[0]);
        kill(pid, SIGKILL);
        errno = EHOSTUNREACH;
        return -1;
    }
    return sv[0];
}
#endif

static int tcp_connect(const char *host, const char *port) {
    struct addrinfo hints, *res, *rp;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;
    int rc = getaddrinfo(host, port, &hints, &res);
    if (rc != 0) die("cannot resolve %s:%s (%s)", host, port, gai_strerror(rc));

    int fd = -1;
    for (rp = res; rp; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd < 0) continue;
#ifdef __APPLE__
        // A zoned link-local peer (fe80::…%awdl0) is reachable only with the
        // socket bound to that interface; SO_RECV_ANYIF also lets its reply in
        // through the restricted interface. Refused or silent: relay via nc.
        unsigned int idx = rp->ai_family == AF_INET6 ? ((struct sockaddr_in6 *)rp->ai_addr)->sin6_scope_id : 0;
        if (idx) {
            int one = 1;
            setsockopt(fd, IPPROTO_IPV6, IPV6_BOUND_IF, &idx, sizeof idx);
            setsockopt(fd, SOL_SOCKET, SO_RECV_ANYIF_OPT, &one, sizeof one);
            if (connect_within(fd, rp->ai_addr, rp->ai_addrlen, 4000) == 0) break;
            int saved = errno;
            close(fd);
            fd = access(NC_PATH, X_OK) == 0 ? nc_relay(host, port) : -1;
            if (fd >= 0) { freeaddrinfo(res); return fd; }
            errno = saved;
            continue;
        }
#endif
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) == 0) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    if (fd < 0) {
#ifdef __APPLE__
        if (errno == EHOSTUNREACH && strchr(host, '%'))
            die("cannot connect to %s:%s (%s) — allow Local Network access for the app running "
                "this client (System Settings › Privacy & Security › Local Network)",
                host, port, strerror(errno));
#endif
        die("cannot connect to %s:%s (%s)", host, port, strerror(errno));
    }
    int one = 1;
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    return fd;
}

static int write_all(int fd, const uint8_t *p, size_t n) {
    while (n > 0) {
        ssize_t w = write(fd, p, n);
        if (w <= 0) return -1;
        p += w;
        n -= (size_t)w;
    }
    return 0;
}

/// POST `body` to `path`, returning the response body. `*status` gets the code.
static int http_post(const char *host, const char *port, const char *path,
                     const char *body, size_t bodylen, buf *out, int *status) {
    int fd = tcp_connect(host, port);
    buf req;
    buf_init(&req);
    buf_appendf(&req,
                "POST %s HTTP/1.1\r\nHost: %s:%s\r\nContent-Type: application/json\r\n"
                "Content-Length: %zu\r\nConnection: close\r\n\r\n",
                path, host, port, bodylen);
    buf_append(&req, body, bodylen);
    int rc = write_all(fd, req.data, req.len);
    buf_free(&req);
    if (rc != 0) { close(fd); die("write failed: %s", strerror(errno)); }

    buf resp;
    buf_init(&resp);
    uint8_t chunk[65536];
    for (;;) {
        ssize_t r = read(fd, chunk, sizeof chunk);
        if (r < 0) { close(fd); buf_free(&resp); die("read failed: %s", strerror(errno)); }
        if (r == 0) break;
        buf_append(&resp, chunk, (size_t)r);
    }
    close(fd);

    // Status line, then split on the header terminator.
    if (resp.len < 12 || memcmp(resp.data, "HTTP/1.", 7) != 0) {
        buf_free(&resp);
        die("malformed HTTP response");
    }
    *status = atoi((const char *)resp.data + 9);
    const char *sep = strstr((const char *)resp.data, "\r\n\r\n");
    if (!sep) { buf_free(&resp); die("no HTTP header terminator"); }
    const uint8_t *bodyp = (const uint8_t *)sep + 4;
    size_t blen = resp.len - (size_t)(bodyp - resp.data);
    buf_init(out);
    buf_append(out, bodyp, blen);
    buf_free(&resp);
    return 0;
}

/// GET `path`, returning the response body.
static int http_get(const char *host, const char *port, const char *path,
                    buf *out, int *status) {
    int fd = tcp_connect(host, port);
    buf req;
    buf_init(&req);
    buf_appendf(&req, "GET %s HTTP/1.1\r\nHost: %s:%s\r\nConnection: close\r\n\r\n",
                path, host, port);
    int rc = write_all(fd, req.data, req.len);
    buf_free(&req);
    if (rc != 0) { close(fd); die("write failed: %s", strerror(errno)); }

    buf resp;
    buf_init(&resp);
    uint8_t chunk[65536];
    for (;;) {
        ssize_t r = read(fd, chunk, sizeof chunk);
        if (r <= 0) break;
        buf_append(&resp, chunk, (size_t)r);
    }
    close(fd);
    if (resp.len < 12) { buf_free(&resp); die("empty HTTP response"); }
    *status = atoi((const char *)resp.data + 9);
    const char *sep = strstr((const char *)resp.data, "\r\n\r\n");
    if (!sep) { buf_free(&resp); die("no HTTP header terminator"); }
    const uint8_t *bodyp = (const uint8_t *)sep + 4;
    buf_init(out);
    buf_append(out, bodyp, resp.len - (size_t)(bodyp - resp.data));
    buf_free(&resp);
    return 0;
}

// ── Minimal JSON scraping ───────────────────────────────────────────────────
//
// Only ever applied to this server's own envelope fields, which are flat
// strings — so a full parser would be weight without benefit. The RPC payload
// itself is passed through verbatim to the caller, never parsed here.

static int json_str(const char *json, const char *key, char *out, size_t outsz) {
    char pat[64];
    snprintf(pat, sizeof pat, "\"%s\"", key);
    const char *p = strstr(json, pat);
    if (!p) return -1;
    p = strchr(p + strlen(pat), ':');
    if (!p) return -1;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r') p++;
    if (*p != '"') return -1;
    p++;
    size_t i = 0;
    while (*p && *p != '"' && i + 1 < outsz) {
        if (*p == '\\' && p[1]) p++;   // envelope fields are hex/base64, no escapes expected
        out[i++] = *p++;
    }
    out[i] = 0;
    return 0;
}

// ── Token store ─────────────────────────────────────────────────────────────
//
// ~/.ictrl/token.json, same file and shape the Python client uses, so the two
// are interchangeable on one machine.

static void store_path(char *out, size_t n) {
    const char *home = getenv("HOME");
    if (!home) home = "/root";
    snprintf(out, n, "%s/.ictrl/token.json", home);
}

static char *read_file(const char *path, size_t *len) {
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    if (sz < 0) { fclose(f); return NULL; }
    char *p = malloc((size_t)sz + 1);
    if (!p) { fclose(f); return NULL; }
    size_t got = fread(p, 1, (size_t)sz, f);
    fclose(f);
    p[got] = 0;
    if (len) *len = got;
    return p;
}

/// Find the record for `host` and pull out its 32-byte key + token id.
static int load_token(const char *host, uint8_t key[32], char tok[9]) {
    char path[512];
    store_path(path, sizeof path);
    size_t n;
    char *js = read_file(path, &n);
    if (!js) return -1;

    // Records are keyed by name ("device:<id>", or an older "host:port" /
    // "nearby:<id>"); scan to that object, then read its fields from the
    // following text. Match the name only as a key ("name": {) — the same
    // string could appear as a value elsewhere in the file.
    char pat[256];
    snprintf(pat, sizeof pat, "\"%s\"", host);
    const char *p = js;
    for (;;) {
        p = strstr(p, pat);
        if (!p) { free(js); return -1; }
        const char *q = p + strlen(pat);
        while (*q == ' ' || *q == '\t' || *q == '\n' || *q == '\r') q++;
        if (*q == ':') {
            q++;
            while (*q == ' ' || *q == '\t' || *q == '\n' || *q == '\r') q++;
            if (*q == '{') break;
        }
        p += strlen(pat);
    }

    char keyhex[80] = {0};
    if (json_str(p, "key", keyhex, sizeof keyhex) != 0 ||
        strlen(keyhex) != 64 ||
        json_str(p, "tok", tok, 9) != 0) {
        free(js);
        return -1;
    }
    int rc = hex_decode(keyhex, key, 32);
    free(js);
    return rc;
}

static void save_token(const char *host, const uint8_t key[32], const char *tok,
                       const char *client_name) {
    const char *home = getenv("HOME");
    if (!home) home = "/root";
    char dir[512];
    snprintf(dir, sizeof dir, "%s/.ictrl", home);
    mkdir(dir, 0700);

    char path[512];
    store_path(path, sizeof path);

    // Preserve other hosts' records: read what's there, drop any entry for this
    // host, and write the rest back alongside the new one.
    size_t n = 0;
    char *old = read_file(path, &n);
    buf out;
    buf_init(&out);
    buf_append(&out, "{\n", 2);

    int wrote = 0;
    if (old) {
        const char *p = old;
        while ((p = strchr(p, '"')) != NULL) {
            const char *keystart = p + 1;
            const char *keyend = strchr(keystart, '"');
            if (!keyend) break;
            size_t klen = (size_t)(keyend - keystart);
            const char *objstart = strchr(keyend, '{');
            if (!objstart) break;
            // Copy this record verbatim unless it's the host we're replacing.
            int depth = 0;
            const char *q = objstart;
            for (; *q; q++) {
                if (*q == '{') depth++;
                else if (*q == '}') { depth--; if (depth == 0) { q++; break; } }
            }
            if (!(klen == strlen(host) && memcmp(keystart, host, klen) == 0)) {
                if (wrote) buf_append(&out, ",\n", 2);
                buf_appendf(&out, "  \"%.*s\": ", (int)klen, keystart);
                buf_append(&out, objstart, (size_t)(q - objstart));
                wrote = 1;
            }
            p = q;
        }
        free(old);
    }

    char keyhex[65];
    hex_encode(key, 32, keyhex);
    if (wrote) buf_append(&out, ",\n", 2);
    buf_appendf(&out,
                "  \"%s\": {\n    \"tok\": \"%s\",\n    \"key\": \"%s\",\n"
                "    \"client_name\": \"%s\"\n  }",
                host, tok, keyhex, client_name);
    buf_append(&out, "\n}\n", 3);

    // 0600 from the start — this file is the device's session key.
    int fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0600);
    if (fd < 0) die("cannot write %s: %s", path, strerror(errno));
    write_all(fd, out.data, out.len);
    close(fd);
    buf_free(&out);
}

// ── RPC ─────────────────────────────────────────────────────────────────────

static void split_host(const char *hostport, char *host, size_t hn, char *port, size_t pn) {
    if (hostport[0] == '[') {                 // [v6addr%zone]:port
        const char *end = strchr(hostport, ']');
        size_t hl = end ? (size_t)(end - hostport - 1) : strlen(hostport + 1);
        if (hl >= hn) hl = hn - 1;
        memcpy(host, hostport + 1, hl);
        host[hl] = 0;
        snprintf(port, pn, "%s", end && end[1] == ':' ? end + 2 : "8200");
        return;
    }
    const char *colon = strrchr(hostport, ':');
    if (colon && strchr(hostport, ':') == colon) {
        size_t hl = (size_t)(colon - hostport);
        if (hl >= hn) hl = hn - 1;
        memcpy(host, hostport, hl);
        host[hl] = 0;
        snprintf(port, pn, "%s", colon + 1);
    } else {
        snprintf(host, hn, "%s", hostport);
        snprintf(port, pn, "8200");
    }
}

/// One enveloped call. Prints the decrypted JSON-RPC response to stdout.
static int rpc_call(const char *hostport, const char *method, const char *params) {
    uint8_t key[32];
    char tok[9];
    if (load_token(STORE_KEY(hostport), key, tok) != 0)
        die("no key for %s — run: ictrl --host %s pair", STORE_KEY(hostport), hostport);

    char host[256], port[16];
    split_host(hostport, host, sizeof host, port, sizeof port);

    buf body;
    buf_init(&body);
    buf_appendf(&body, "{\"jsonrpc\":\"2.0\",\"method\":\"%s\",\"params\":%s,\"id\":1}",
                method, params && *params ? params : "{}");

    uint8_t nonce[16];
    random_bytes(nonce, sizeof nonce);
    int64_t ts = (int64_t)time(NULL);

    uint8_t k_enc[32], k_mac[32];
    uint8_t lbl[64];
    size_t l;
    l = strlen(LABEL_ENC_REQ);
    memcpy(lbl, LABEL_ENC_REQ, l);
    memcpy(lbl + l, nonce, 16);
    hmac_sha256(key, 32, lbl, l + 16, k_enc);
    l = strlen(LABEL_MAC);
    memcpy(lbl, LABEL_MAC, l);
    memcpy(lbl + l, nonce, 16);
    hmac_sha256(key, 32, lbl, l + 16, k_mac);

    keystream_xor(k_enc, nonce, body.data, body.len);   // in-place → ciphertext

    // tag = HMAC(k_mac, "v1" || tok4 || be64(ts) || nonce || ct)
    uint8_t tok4[4];
    if (hex_decode(tok, tok4, 4) != 0) die("corrupt token id in store");
    hmac_ctx tc;
    hmac_init(&tc, k_mac, 32);
    hmac_update(&tc, (const uint8_t *)"v1", 2);
    hmac_update(&tc, tok4, 4);
    uint8_t tsbe[8];
    for (int i = 0; i < 8; i++) tsbe[i] = (uint8_t)((uint64_t)ts >> (56 - i * 8));
    hmac_update(&tc, tsbe, 8);
    hmac_update(&tc, nonce, 16);
    hmac_update(&tc, body.data, body.len);
    uint8_t tag[32];
    hmac_final(&tc, tag);

    char *ct_b64 = malloc(((body.len + 2) / 3) * 4 + 8);
    if (!ct_b64) die("out of memory");
    base64_encode(body.data, body.len, ct_b64);
    char noncehex[33], taghex[65];
    hex_encode(nonce, 16, noncehex);
    hex_encode(tag, 32, taghex);

    buf env;
    buf_init(&env);
    buf_appendf(&env,
                "{\"v\":1,\"tok\":\"%s\",\"ts\":%lld,\"nonce\":\"%s\",\"ct\":\"%s\",\"tag\":\"%s\"}",
                tok, (long long)ts, noncehex, ct_b64, taghex);
    free(ct_b64);
    buf_free(&body);

    buf resp;
    int status = 0;
    http_post(host, port, "/rpc", (const char *)env.data, env.len, &resp, &status);
    buf_free(&env);

    if (status != 200) {
        fprintf(stderr, "ictrl: rpc failed (HTTP %d): %s\n", status,
                resp.data ? (const char *)resp.data : "");
        buf_free(&resp);
        return 1;
    }
    char rct[64], rtag[80];
    // ct can be megabytes (a screenshot), so pull it out by locating the field
    // rather than copying into a fixed buffer.
    const char *ctp = strstr((const char *)resp.data, "\"ct\"");
    if (!ctp || json_str((const char *)resp.data, "tag", rtag, sizeof rtag) != 0)
        die("malformed response envelope");
    ctp = strchr(ctp, ':');
    while (*ctp && *ctp != '"') ctp++;
    ctp++;
    const char *ctend = strchr(ctp, '"');
    if (!ctend) die("malformed response ct");

    size_t ct_b64_len = (size_t)(ctend - ctp);
    uint8_t *ct = malloc(ct_b64_len);
    if (!ct) die("out of memory");
    size_t ctlen = base64_decode(ctp, ct_b64_len, ct);
    (void)rct;

    // Verify before decrypting: tag = HMAC(k_mac, "resp" || nonce || ct)
    hmac_ctx rc2;
    hmac_init(&rc2, k_mac, 32);
    hmac_update(&rc2, (const uint8_t *)"resp", 4);
    hmac_update(&rc2, nonce, 16);
    hmac_update(&rc2, ct, ctlen);
    uint8_t expect[32], got[32];
    hmac_final(&rc2, expect);
    if (hex_decode(rtag, got, 32) != 0 || !ct_equal(expect, got, 32))
        die("response MAC mismatch — discarding");
    // The key proved itself on this device: keep it under the device's name.
    if (g_adopt_to) {
        save_token(g_adopt_to, key, tok, "");
        g_adopt_to = NULL;
    }

    uint8_t k_enc_resp[32];
    l = strlen(LABEL_ENC_RESP);
    memcpy(lbl, LABEL_ENC_RESP, l);
    memcpy(lbl + l, nonce, 16);
    hmac_sha256(key, 32, lbl, l + 16, k_enc_resp);
    keystream_xor(k_enc_resp, nonce, ct, ctlen);

    fwrite(ct, 1, ctlen, stdout);
    fputc('\n', stdout);
    free(ct);
    buf_free(&resp);
    return 0;
}

/// LAN pairing (mode A): X25519 to a shared secret, device wraps the key.
/// Blocks until someone taps Allow on the device.
static int do_pair(const char *hostport, const char *client_name) {
    char host[256], port[16];
    split_host(hostport, host, sizeof host, port, sizeof port);

    uint8_t priv[32], pub[32];
    random_bytes(priv, 32);
    x25519_base(pub, priv);

    char pub_b64[64];
    base64_encode(pub, 32, pub_b64);

    uint8_t fp[32];
    sha256(pub, 32, fp);
    char fphex[65];
    hex_encode(fp, 32, fphex);
    fphex[8] = 0;
    fprintf(stderr, "key fingerprint: %s  (verify it matches the on-device prompt)\n", fphex);
    fprintf(stderr, "waiting for Allow on the device…\n");

    buf req;
    buf_init(&req);
    buf_appendf(&req, "{\"client_name\":\"%s\",\"pub\":\"%s\"}", client_name, pub_b64);

    buf resp;
    int status = 0;
    http_post(host, port, "/pair", (const char *)req.data, req.len, &resp, &status);
    buf_free(&req);
    if (status != 200) {
        fprintf(stderr, "ictrl: pair failed (HTTP %d): %s\n", status,
                resp.data ? (const char *)resp.data : "");
        buf_free(&resp);
        return 1;
    }

    char devpub_b64[128], tokct_hex[128];
    if (json_str((const char *)resp.data, "pub", devpub_b64, sizeof devpub_b64) != 0 ||
        json_str((const char *)resp.data, "token_ct", tokct_hex, sizeof tokct_hex) != 0)
        die("malformed pair response");

    uint8_t devpub[32];
    if (base64_decode(devpub_b64, strlen(devpub_b64), devpub) != 32)
        die("bad device public key");

    uint8_t shared[32];
    x25519(shared, priv, devpub);

    // k_wrap = HMAC(shared, "ictrl-pair" || clientPub || devicePub)
    hmac_ctx wc;
    hmac_init(&wc, shared, 32);
    hmac_update(&wc, (const uint8_t *)LABEL_PAIR, strlen(LABEL_PAIR));
    hmac_update(&wc, pub, 32);
    hmac_update(&wc, devpub, 32);
    uint8_t k_wrap[32];
    hmac_final(&wc, k_wrap);

    uint8_t pad[32];
    hmac_sha256(k_wrap, 32, (const uint8_t *)LABEL_WRAP, strlen(LABEL_WRAP), pad);

    uint8_t token_ct[32], key[32];
    if (hex_decode(tokct_hex, token_ct, 32) != 0) die("bad token_ct");
    for (int i = 0; i < 32; i++) key[i] = token_ct[i] ^ pad[i];

    uint8_t kh[32];
    sha256(key, 32, kh);
    char tok[9];
    hex_encode(kh, 4, tok);

    save_token(STORE_KEY(hostport), key, tok, client_name);
    fprintf(g_pair_implicit ? stderr : stdout,
            "paired — tok=%s (key cached in ~/.ictrl/token.json)\n", tok);
    buf_free(&resp);
    return 0;
}

static void usage(void) {
    fprintf(stderr,
        "ictrl — iCTRL encrypted JSON-RPC client (protocol v1)\n\n"
        "Usage:\n"
        "  ictrl [--host HOST:PORT] pair [--name NAME]   pair (tap Allow on the device)\n"
        "  ictrl [--host HOST:PORT] call METHOD [JSON]   one RPC call\n"
        "  ictrl [--host HOST:PORT] shot [FILE]          save a screenshot (JPEG)\n"
        "  ictrl [--host HOST:PORT] skill               fetch the operating manual\n"
#ifdef __APPLE__
        "  ictrl scan                                    list nearby devices (peer-to-peer Wi-Fi)\n"
        "  ictrl --nearby NAME|ID call|shot|pair ...     use a nearby device; pairs on first use\n"
#endif
        "\nDefault host is 127.0.0.1:8200 (inside Minis this is the device itself).\n"
        "Env: ICTRL_HOST overrides the default host.\n");
}

/// Pulls a top-level numeric field out of a JSON response. Enough for the few
/// scalars `shot` reports; not a general parser (nested objects are ignored).
/// Returns -1 when the key is absent.
static double json_num(const char *json, const char *key) {
    char needle[64];
    snprintf(needle, sizeof needle, "\"%s\"", key);
    const char *p = strstr(json, needle);
    if (!p) return -1;
    p = strchr(p + strlen(needle), ':');
    if (!p) return -1;
    p++;
    while (*p == ' ' || *p == '\t' || *p == '\n') p++;
    if (*p != '-' && *p != '+' && *p != '.' && (*p < '0' || *p > '9')) return -1;
    return atof(p);
}

/// `shot` — screenshot straight to a file, decoding the base64 for the caller.
static int do_shot(const char *hostport, const char *path, int argc, char **argv) {
    const char *fmt = "jpeg";
    double quality = 0.6, scale = 2.0;
    for (int i = 0; i < argc; i++) {
        if (!strcmp(argv[i], "--png")) fmt = "png";
        else if (!strcmp(argv[i], "--quality") && i + 1 < argc) quality = atof(argv[++i]);
        else if (!strcmp(argv[i], "--scale") && i + 1 < argc) scale = atof(argv[++i]);
    }
    char params[160];
    if (!strcmp(fmt, "png"))
        snprintf(params, sizeof params, "{\"format\":\"png\",\"scale\":%g}", scale);
    else
        snprintf(params, sizeof params,
                 "{\"format\":\"jpeg\",\"quality\":%g,\"scale\":%g}", quality, scale);

    // Capture the RPC output instead of printing it, then pull out `data`.
    int pipefd[2];
    if (pipe(pipefd) != 0) die("pipe: %s", strerror(errno));
    fflush(stdout);
    int saved = dup(STDOUT_FILENO);
    dup2(pipefd[1], STDOUT_FILENO);
    close(pipefd[1]);

    // A screenshot can exceed the pipe buffer, so drain it from a child while
    // the parent writes — otherwise the RPC would block on a full pipe.
    pid_t pid = fork();
    if (pid == 0) {
        close(pipefd[0]);
        int rc = rpc_call(hostport, "screenshot", params);
        fflush(stdout);
        _exit(rc);
    }
    dup2(saved, STDOUT_FILENO);
    close(saved);
    close(pipefd[1] == -1 ? pipefd[1] : -1);

    buf json;
    buf_init(&json);
    uint8_t chunk[65536];
    for (;;) {
        ssize_t r = read(pipefd[0], chunk, sizeof chunk);
        if (r <= 0) break;
        buf_append(&json, chunk, (size_t)r);
    }
    close(pipefd[0]);
    int wstatus = 0;
    waitpid(pid, &wstatus, 0);

    const char *dp = strstr((const char *)json.data, "\"data\"");
    if (!dp) {
        fprintf(stderr, "ictrl: screenshot failed: %s\n", (const char *)json.data);
        buf_free(&json);
        return 1;
    }
    dp = strchr(dp, ':');
    while (*dp && *dp != '"') dp++;
    dp++;
    const char *dend = strchr(dp, '"');
    if (!dend) die("malformed screenshot response");

    uint8_t *img = malloc((size_t)(dend - dp));
    if (!img) die("out of memory");
    size_t imglen = base64_decode(dp, (size_t)(dend - dp), img);

    FILE *f = fopen(path, "wb");
    if (!f) die("cannot write %s: %s", path, strerror(errno));
    fwrite(img, 1, imglen, f);
    fclose(f);
    // Report the coordinate spaces alongside the file. Seeing only the pixel
    // size invites deriving the divisor from device_scale, which is wrong once
    // the shot is downscaled: a 1206x2622 screen saved at scale 2 is an 804x1748
    // file, and dividing by 3 lands a tap ~200pt away from the target.
    double px_w = json_num((const char *)json.data, "pixel_width");
    double px_h = json_num((const char *)json.data, "pixel_height");
    double pt_w = json_num((const char *)json.data, "point_width");
    double pt_h = json_num((const char *)json.data, "point_height");
    double sc   = json_num((const char *)json.data, "scale");
    if (sc > 0) {
        fprintf(stderr, "%s  %zu bytes  %.0fx%.0fpx  ->  %.0fx%.0fpt"
                        "  (scale %g: tap_x = px/%g, tap_y = py/%g)\n",
                path, imglen, px_w, px_h, pt_w, pt_h, sc, sc, sc);
    } else {
        fprintf(stderr, "%s  %zu bytes\n", path, imglen);
    }
    free(img);
    buf_free(&json);
    return 0;
}

/// Point key lookup at this device's record, "device:<id>": one key per
/// device whatever the channel (USB, LAN, nearby), so a phone paired once is
/// reachable over all of them, and two phones taking turns at one address
/// (USB forwarding to 127.0.0.1) keep their own keys. The id comes from
/// nearby discovery or GET /whoami. A key still stored under an older name
/// ("nearby:<id>", or the address) is used, and saved under the device name
/// once a call with it succeeds. A server too old for /whoami keeps the
/// address as the name.
static void use_device_key(const char *hostport, const char *known_id, int pairing) {
    static char device_key[96], older[192];
    char id[80] = {0};
    if (known_id) {
        snprintf(id, sizeof id, "%s", known_id);
    } else {
        char host[256], port[16];
        split_host(hostport, host, sizeof host, port, sizeof port);
        buf out;
        int status = 0;
        http_get(host, port, "/whoami", &out, &status);
        if (status == 200 && out.data) json_str((const char *)out.data, "device_id", id, sizeof id);
        buf_free(&out);
    }
    if (!id[0]) return;
    snprintf(device_key, sizeof device_key, "device:%s", id);
    g_store_key = device_key;
    if (pairing) return;   // a new key goes under the device name, never an older one
    uint8_t key[32];
    char tok[9];
    if (load_token(device_key, key, tok) == 0) return;
    snprintf(older, sizeof older, "nearby:%s", id);
    if (load_token(older, key, tok) != 0) snprintf(older, sizeof older, "%s", hostport);
    if (load_token(older, key, tok) == 0) {
        g_store_key = older;
        g_adopt_to = device_key;
    }
    // Otherwise no key yet: pairing saves it under the device name.
}

int main(int argc, char **argv) {
    const char *hostport = getenv("ICTRL_HOST");
    if (!hostport) hostport = "127.0.0.1:8200";

    int i = 1;
    const char *nearby = NULL;
    while (i < argc && (!strncmp(argv[i], "--host", 6) || !strcmp(argv[i], "--nearby"))) {
        if (i + 1 >= argc) { usage(); return 2; }
        if (!strcmp(argv[i], "--nearby")) nearby = argv[i + 1];
        else hostport = argv[i + 1];
        i += 2;
    }
    if (i >= argc) { usage(); return 2; }

    const char *cmd = argv[i++];

#ifdef __APPLE__
    static nearby_device devs[NEARBY_MAX];
    if (!strcmp(cmd, "scan")) {
        int n = nearby_scan(devs, NEARBY_MAX, 3.0, NULL);
        if (n == -1) die("no awdl0 interface — is Wi-Fi turned on?");
        if (n < 0) die("nearby browse failed");
        if (n == 0) printf("no nearby devices — on the phone, turn on Nearby Discovery (iCTRL notification) "
                           "and keep Wi-Fi switched on; it need not be joined to a network\n");
        for (int k = 0; k < n; k++) {
            char store[96], older[96];
            snprintf(store, sizeof store, "device:%s", devs[k].id);
            snprintf(older, sizeof older, "nearby:%s", devs[k].id);
            uint8_t key[32];
            char tok[9];
            int paired = load_token(store, key, tok) == 0 || load_token(older, key, tok) == 0;
            printf("%-32s id=%.8s  %s\n", devs[k].name, devs[k].id, paired ? "paired" : "");
        }
        return 0;
    }
    static char nearby_host[128];
    if (nearby) {
        int n = nearby_scan(devs, NEARBY_MAX, 6.0, nearby);
        if (n == -1) die("no awdl0 interface — is Wi-Fi turned on?");
        const nearby_device *hit = NULL;
        for (int k = 0; k < (n > 0 ? n : 0); k++) {
            if (!nearby_matches(&devs[k], nearby)) continue;
            if (hit && strcmp(hit->id, devs[k].id))
                die("\"%s\" matches several devices; use the id", nearby);
            hit = &devs[k];
        }
        if (!hit) die("no nearby device matches \"%s\" — run: ictrl scan. On the phone, turn on Nearby Discovery and keep Wi-Fi switched on", nearby);
        snprintf(nearby_host, sizeof nearby_host, "%s", hit->host);
        hostport = nearby_host;
        use_device_key(hostport, hit->id, !strcmp(cmd, "pair"));
        // First use pairs (approve once on the phone); later runs reuse the key.
        uint8_t key[32];
        char tok[9];
        if (strcmp(cmd, "pair") && load_token(g_store_key, key, tok) != 0) {
            fprintf(stderr, "pairing with %s — approve the prompt on the phone\n", hit->name);
            char name[256];
            if (gethostname(name, sizeof name) != 0) snprintf(name, sizeof name, "ictrl");
            g_pair_implicit = 1;
            if (do_pair(hostport, name) != 0) return 1;
            g_pair_implicit = 0;
        }
    }
#else
    if (nearby || !strcmp(cmd, "scan"))
        die("nearby discovery needs macOS (Apple peer-to-peer Wi-Fi)");
#endif

    if (!nearby && (!strcmp(cmd, "pair") || !strcmp(cmd, "call") || !strcmp(cmd, "shot")))
        use_device_key(hostport, NULL, !strcmp(cmd, "pair"));

    if (!strcmp(cmd, "pair")) {
        const char *name = "minis";
        for (int j = i; j + 1 < argc; j++)
            if (!strcmp(argv[j], "--name")) name = argv[j + 1];
        return do_pair(hostport, name);
    }
    if (!strcmp(cmd, "call")) {
        if (i >= argc) { usage(); return 2; }
        const char *method = argv[i++];
        const char *params = (i < argc) ? argv[i] : "{}";
        return rpc_call(hostport, method, params);
    }
    if (!strcmp(cmd, "shot")) {
        const char *path = (i < argc && argv[i][0] != '-') ? argv[i++] : "screenshot.jpg";
        return do_shot(hostport, path, argc - i, argv + i);
    }
    if (!strcmp(cmd, "skill")) {
        char host[256], port[16];
        split_host(hostport, host, sizeof host, port, sizeof port);
        buf out;
        int status = 0;
        http_get(host, port, "/skill", &out, &status);
        fwrite(out.data, 1, out.len, stdout);
        buf_free(&out);
        return status == 200 ? 0 : 1;
    }

    usage();
    return 2;
}
