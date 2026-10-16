// Nearby discovery (macOS only): find iCTRL devices advertised over Apple
// peer-to-peer Wi-Fi (AWDL) with the system dns_sd API.
//
// The phone registers "_ictrl._tcp" on its awdl0 interface only, with TXT
// keys "v" (protocol version) and "id" (stable device id). Each instance found
// on awdl0 is resolved to a link-local IPv6 address scoped to awdl0; callers
// connect with the socket bound to that interface (see tcp_connect).
//
// Not part of the Linux build: AWDL exists only between Apple devices.

#ifdef __APPLE__

#include "nearby.h"

#include <arpa/inet.h>
#include <dns_sd.h>
#include <net/if.h>
#include <netinet/in.h>
#include <stdio.h>
#include <string.h>
#include <sys/select.h>
#include <sys/time.h>

#define NEARBY_FLAGS (kDNSServiceFlagsIncludeAWDL | kDNSServiceFlagsIncludeP2P)
#define MAX_REFS 64

typedef struct {
    nearby_device dev;
    uint16_t port;
    int resolved;
} pending;

static struct {
    uint32_t awdl;
    pending found[NEARBY_MAX];
    int nfound;
    DNSServiceRef refs[MAX_REFS];
    int nrefs;
} S;

static double now_s(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return tv.tv_sec + tv.tv_usec / 1e6;
}

static void add_ref(DNSServiceRef r) {
    if (S.nrefs < MAX_REFS) S.refs[S.nrefs++] = r;
    else DNSServiceRefDeallocate(r);
}

static void txt_value(const unsigned char *txt, uint16_t len, const char *key, char *out, size_t outsz) {
    uint8_t vlen = 0;
    const void *v = TXTRecordGetValuePtr(len, txt, key, &vlen);
    if (!v) { out[0] = 0; return; }
    size_t n = vlen < outsz - 1 ? vlen : outsz - 1;
    memcpy(out, v, n);
    out[n] = 0;
}

static void addr_cb(DNSServiceRef r, DNSServiceFlags f, uint32_t ifi, DNSServiceErrorType e,
                    const char *host, const struct sockaddr *a, uint32_t ttl, void *ctx) {
    (void)r; (void)f; (void)ifi; (void)host; (void)ttl;
    pending *p = ctx;
    if (e || !a || a->sa_family != AF_INET6 || p->dev.host[0]) return;
    char s[INET6_ADDRSTRLEN];
    inet_ntop(AF_INET6, &((const struct sockaddr_in6 *)a)->sin6_addr, s, sizeof s);
    snprintf(p->dev.host, sizeof p->dev.host, "[%s%%awdl0]:%u", s, p->port);
}

static void resolve_cb(DNSServiceRef r, DNSServiceFlags f, uint32_t ifi, DNSServiceErrorType e,
                       const char *full, const char *target, uint16_t port, uint16_t txtlen,
                       const unsigned char *txt, void *ctx) {
    (void)r; (void)f; (void)ifi; (void)full;
    pending *p = ctx;
    if (e || p->resolved) return;
    p->resolved = 1;
    p->port = ntohs(port);
    txt_value(txt, txtlen, "id", p->dev.id, sizeof p->dev.id);
    DNSServiceRef ga;
    if (DNSServiceGetAddrInfo(&ga, NEARBY_FLAGS, S.awdl, kDNSServiceProtocol_IPv6, target,
                              addr_cb, p) == kDNSServiceErr_NoError)
        add_ref(ga);
}

static void browse_cb(DNSServiceRef r, DNSServiceFlags f, uint32_t ifi, DNSServiceErrorType e,
                      const char *name, const char *type, const char *domain, void *ctx) {
    (void)r; (void)ctx;
    // AWDL instances only: the service is never advertised elsewhere, and a
    // same-named entry on another interface is not this transport.
    if (e || !(f & kDNSServiceFlagsAdd) || ifi != S.awdl || S.nfound >= NEARBY_MAX) return;
    pending *p = &S.found[S.nfound++];
    memset(p, 0, sizeof *p);
    snprintf(p->dev.name, sizeof p->dev.name, "%s", name);
    DNSServiceRef rs;
    if (DNSServiceResolve(&rs, NEARBY_FLAGS, S.awdl, name, type, domain, resolve_cb, p)
        == kDNSServiceErr_NoError)
        add_ref(rs);
}

int nearby_matches(const nearby_device *d, const char *query) {
    if (!strcasecmp(d->name, query)) return 1;
    size_t q = strlen(query);
    return q >= 4 && !strncasecmp(d->id, query, q);
}

int nearby_scan(nearby_device *out, int max, double wait_s, const char *want) {
    memset(&S, 0, sizeof S);
    S.awdl = if_nametoindex("awdl0");
    if (!S.awdl) return -1;
    DNSServiceRef b;
    if (DNSServiceBrowse(&b, NEARBY_FLAGS, 0, "_ictrl._tcp", NULL, browse_cb, NULL)
        != kDNSServiceErr_NoError)
        return -2;
    add_ref(b);

    double deadline = now_s() + wait_s;
    for (;;) {
        if (want) {
            int hit = 0;
            for (int k = 0; k < S.nfound; k++)
                if (S.found[k].dev.host[0] && nearby_matches(&S.found[k].dev, want)) hit = 1;
            if (hit) break;
        }
        double left = deadline - now_s();
        if (left <= 0) break;
        fd_set rs;
        FD_ZERO(&rs);
        int maxfd = -1;
        for (int k = 0; k < S.nrefs; k++) {
            int fd = DNSServiceRefSockFD(S.refs[k]);
            FD_SET(fd, &rs);
            if (fd > maxfd) maxfd = fd;
        }
        double slice = left < 0.25 ? left : 0.25;
        struct timeval tv = { (long)slice, (int)((slice - (long)slice) * 1e6) };
        if (select(maxfd + 1, &rs, NULL, NULL, &tv) <= 0) continue;
        int n = S.nrefs;   // callbacks may append refs; service the current set
        for (int k = 0; k < n; k++)
            if (FD_ISSET(DNSServiceRefSockFD(S.refs[k]), &rs)) DNSServiceProcessResult(S.refs[k]);
    }
    for (int k = 0; k < S.nrefs; k++) DNSServiceRefDeallocate(S.refs[k]);

    int count = 0;
    for (int k = 0; k < S.nfound && count < max; k++)
        if (S.found[k].dev.host[0]) out[count++] = S.found[k].dev;
    return count;
}

#endif
