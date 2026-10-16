// Build compatibility for rootless-only local experiments. Not a roothide ABI.
#pragma once
#import <Foundation/Foundation.h>

static inline NSString *jbroot(NSString *path) {
    if (![path hasPrefix:@"/"]) return path;
    return [@"/var/jb" stringByAppendingString:path];
}

static inline NSString *rootfs(NSString *path) {
    return path;
}
