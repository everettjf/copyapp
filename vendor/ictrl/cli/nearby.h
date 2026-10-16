#ifndef ICTRL_NEARBY_H
#define ICTRL_NEARBY_H

// Nearby discovery over Apple peer-to-peer Wi-Fi (macOS only; see nearby.c).

#define NEARBY_MAX 32

typedef struct {
    char name[256];   // advertised device name
    char id[64];      // stable device id (TXT "id")
    char host[128];   // "[fe80::…%awdl0]:port"
} nearby_device;

/// Browse for up to `wait_s` seconds and fill `out` with resolved devices.
/// With `want` set, returns as soon as a device matching it is resolved.
/// Returns the number found, -1 without an awdl0 interface, -2 if the browse
/// could not start.
int nearby_scan(nearby_device *out, int max, double wait_s, const char *want);

/// Whether a device matches a query: its exact name (case-insensitive) or a
/// prefix of its id of at least four characters.
int nearby_matches(const nearby_device *d, const char *query);

#endif
