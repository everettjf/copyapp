#pragma once

#ifdef MCP_ROOTHIDE
// Resolve the randomized jailbreak root through roothide's real SDK.
// roothide/theos provides this header and links its implementation.
#include <roothide.h>
#else
// The validated iOS 16 rootless package uses the fixed /var/jb layout.
#import <Foundation/Foundation.h>

static inline NSString *jbroot(NSString *path) {
    if (![path hasPrefix:@"/"]) return path;
    return [@"/var/jb" stringByAppendingString:path];
}

static inline NSString *rootfs(NSString *path) {
    return path;
}
#endif
