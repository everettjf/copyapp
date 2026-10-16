#import "ClipboardManager.h"
#import "MCPLogger.h"
#import <CommonCrypto/CommonDigest.h>
#import <UIKit/UIKit.h>

#define CLIPBOARD_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[Clipboard] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)

static NSString *MCP_SHA1Hex(NSString *value) {
    NSData *data = [value dataUsingEncoding:NSUTF8StringEncoding];
    if (!data) return nil;

    unsigned char digest[CC_SHA1_DIGEST_LENGTH];
    CC_SHA1(data.bytes, (CC_LONG)data.length, digest);

    NSMutableString *hex = [NSMutableString stringWithCapacity:CC_SHA1_DIGEST_LENGTH * 2];
    for (NSUInteger i = 0; i < CC_SHA1_DIGEST_LENGTH; i++) {
        [hex appendFormat:@"%02x", digest[i]];
    }
    return hex;
}

static BOOL MCP_IsBinaryPlist(NSData *data) {
    if (data.length < 8) return NO;
    const char magic[] = "bplist00";
    return memcmp(data.bytes, magic, 8) == 0;
}

static BOOL MCP_StringLooksReadable(NSString *text) {
    if (text.length == 0) return NO;

    NSUInteger controlCount = 0;
    NSCharacterSet *controls = [NSCharacterSet controlCharacterSet];
    for (NSUInteger i = 0; i < text.length; i++) {
        unichar ch = [text characterAtIndex:i];
        if ((ch == '\n') || (ch == '\r') || (ch == '\t')) continue;
        if ([controls characterIsMember:ch]) controlCount++;
    }
    return controlCount == 0 || ((double)controlCount / (double)text.length) < 0.03;
}

static BOOL MCP_StringLooksLikeURL(NSString *text) {
    NSString *lower = [text lowercaseString];
    return [lower hasPrefix:@"http://"] ||
           [lower hasPrefix:@"https://"] ||
           [lower hasPrefix:@"file://"];
}

static void MCP_CollectStrings(id object, NSMutableArray<NSString *> *strings) {
    if (!object || object == [NSNull null]) return;

    if ([object isKindOfClass:[NSString class]]) {
        NSString *value = (NSString *)object;
        if (value.length > 0) [strings addObject:value];
        return;
    }

    if ([object isKindOfClass:[NSURL class]]) {
        NSString *value = [(NSURL *)object absoluteString];
        if (value.length > 0) [strings addObject:value];
        return;
    }

    if ([object isKindOfClass:[NSArray class]]) {
        for (id item in (NSArray *)object) {
            MCP_CollectStrings(item, strings);
        }
        return;
    }

    if ([object isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = (NSDictionary *)object;
        for (id key in dict) {
            MCP_CollectStrings(dict[key], strings);
        }
    }
}

static NSArray<NSString *> *MCP_StringsFromPlistData(NSData *data) {
    if (data.length == 0) return @[];

    NSError *error = nil;
    id plist = [NSPropertyListSerialization propertyListWithData:data
                                                         options:NSPropertyListImmutable
                                                          format:nil
                                                           error:&error];
    if (!plist) return @[];

    NSMutableArray<NSString *> *strings = [NSMutableArray array];
    MCP_CollectStrings(plist, strings);
    return strings;
}

static NSString *MCP_ExistingPasteboardCacheRoot(void) {
    NSArray<NSString *> *roots = @[
        @"/private/var/mobile/Library/Caches/com.apple.Pasteboard",
        @"/var/mobile/Library/Caches/com.apple.Pasteboard",
        @"/var/jb/private/var/mobile/Library/Caches/com.apple.Pasteboard",
        @"/var/jb/var/mobile/Library/Caches/com.apple.Pasteboard"
    ];

    NSFileManager *fm = [NSFileManager defaultManager];
    for (NSString *root in roots) {
        BOOL isDirectory = NO;
        if ([fm fileExistsAtPath:root isDirectory:&isDirectory] && isDirectory) {
            return root;
        }
    }
    return nil;
}

static NSString *MCP_GeneralPasteboardCacheDirectory(void) {
    NSString *root = MCP_ExistingPasteboardCacheRoot();
    NSString *nameHash = MCP_SHA1Hex(@"com.apple.UIKit.pboard.general");
    if (!root || !nameHash) return nil;
    return [root stringByAppendingPathComponent:nameHash];
}

static NSArray<NSString *> *MCP_CacheDataFilesSortedForReading(NSString *directory) {
    NSFileManager *fm = [NSFileManager defaultManager];
    NSArray<NSString *> *names = [fm contentsOfDirectoryAtPath:directory error:nil];
    NSMutableArray<NSDictionary *> *entries = [NSMutableArray array];

    for (NSString *name in names) {
        if ([name isEqualToString:@"Manifest.plist"]) continue;
        NSString *path = [directory stringByAppendingPathComponent:name];

        BOOL isDirectory = NO;
        if (![fm fileExistsAtPath:path isDirectory:&isDirectory] || isDirectory) continue;

        NSDictionary *attrs = [fm attributesOfItemAtPath:path error:nil];
        NSNumber *size = attrs[NSFileSize] ?: @0;
        NSDate *modifiedAt = attrs[NSFileModificationDate] ?: [NSDate distantPast];
        [entries addObject:@{ @"path": path,
                              @"size": size,
                              @"modifiedAt": modifiedAt }];
    }

    [entries sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        NSDate *am = a[@"modifiedAt"];
        NSDate *bm = b[@"modifiedAt"];
        NSComparisonResult dateOrder = [bm compare:am];
        if (dateOrder != NSOrderedSame) return dateOrder;

        unsigned long long as = [a[@"size"] unsignedLongLongValue];
        unsigned long long bs = [b[@"size"] unsignedLongLongValue];
        if (as < bs) return NSOrderedAscending;
        if (as > bs) return NSOrderedDescending;
        return [a[@"path"] compare:b[@"path"]];
    }];

    NSMutableArray<NSString *> *paths = [NSMutableArray arrayWithCapacity:entries.count];
    for (NSDictionary *entry in entries) {
        [paths addObject:entry[@"path"]];
    }
    return paths;
}

static NSDictionary *MCP_ReadGeneralPasteboardFromCache(void) {
    NSString *directory = MCP_GeneralPasteboardCacheDirectory();
    NSFileManager *fm = [NSFileManager defaultManager];
    BOOL isDirectory = NO;
    if (!directory || ![fm fileExistsAtPath:directory isDirectory:&isDirectory] || !isDirectory) {
        CLIPBOARD_LOG(@"Pasteboard cache directory missing");
        return nil;
    }

    NSString *manifestPath = [directory stringByAppendingPathComponent:@"Manifest.plist"];
    NSData *manifestData = [NSData dataWithContentsOfFile:manifestPath];
    NSArray<NSString *> *manifestStrings = manifestData ? MCP_StringsFromPlistData(manifestData) : @[];

    BOOL hasURL = NO;
    BOOL hasImage = NO;
    for (NSString *type in manifestStrings) {
        if ([type isEqualToString:@"public.url"] ||
            [type isEqualToString:@"public.file-url"] ||
            [type isEqualToString:@"NSURLPboardType"]) {
            hasURL = YES;
        }

        if ([type isEqualToString:@"public.image"] ||
            [type isEqualToString:@"public.png"] ||
            [type isEqualToString:@"public.jpeg"] ||
            [type isEqualToString:@"public.heic"] ||
            [type isEqualToString:@"com.apple.uikit.image"]) {
            hasImage = YES;
        }
    }

    NSString *text = nil;
    NSString *url = nil;
    NSArray<NSString *> *dataFiles = MCP_CacheDataFilesSortedForReading(directory);

    // Prefer raw UTF-8 files. pasted stores plain text representations this way,
    // and reading these files does not enter the paste authorization path.
    for (NSString *path in dataFiles) {
        NSDictionary *attrs = [fm attributesOfItemAtPath:path error:nil];
        unsigned long long size = [attrs[NSFileSize] unsignedLongLongValue];
        if (size == 0 || size > 1024 * 1024) continue;

        NSData *data = [NSData dataWithContentsOfFile:path];
        if (!data || MCP_IsBinaryPlist(data)) continue;

        NSString *candidate = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
        if (candidate.length > 0 && MCP_StringLooksReadable(candidate)) {
            text = candidate;
            if (MCP_StringLooksLikeURL(candidate)) {
                url = candidate;
                hasURL = YES;
            }
            break;
        }
    }

    // Some URL representations are small binary plists. Use them only as a
    // fallback so LinkPresentation metadata does not become clipboard text.
    if (!text || (!url && hasURL)) {
        for (NSString *path in dataFiles) {
            NSDictionary *attrs = [fm attributesOfItemAtPath:path error:nil];
            unsigned long long size = [attrs[NSFileSize] unsignedLongLongValue];
            if (size == 0 || size > 256 * 1024) continue;

            NSData *data = [NSData dataWithContentsOfFile:path];
            if (!data || !MCP_IsBinaryPlist(data)) continue;

            NSArray<NSString *> *strings = MCP_StringsFromPlistData(data);
            for (NSString *candidate in strings) {
                if (!url && MCP_StringLooksLikeURL(candidate)) {
                    url = candidate;
                    hasURL = YES;
                }
                if (!text && MCP_StringLooksReadable(candidate) &&
                    ![candidate hasPrefix:@"NS"] &&
                    ![candidate hasPrefix:@"$"]) {
                    text = candidate;
                }
                if (text && (!hasURL || url)) break;
            }
            if (text && (!hasURL || url)) break;
        }
    }

    NSMutableDictionary *info = [@{
        @"text": text ?: [NSNull null],
        @"hasImage": @(hasImage),
        @"hasURL": @(hasURL)
    } mutableCopy];
    if (url.length > 0) {
        info[@"url"] = url;
    }

    CLIPBOARD_LOG(@"Read pasteboard cache textChars=%lu hasImage=%@ hasURL=%@ files=%lu",
                  (unsigned long)text.length,
                  hasImage ? @"yes" : @"no",
                  hasURL ? @"yes" : @"no",
                  (unsigned long)dataFiles.count);
    return info;
}

static BOOL MCP_CachePasteboardInfoHasReadableContent(NSDictionary *info) {
    if (!info) return NO;

    id text = info[@"text"];
    if ([text isKindOfClass:[NSString class]] && [(NSString *)text length] > 0) {
        return YES;
    }

    id url = info[@"url"];
    if ([url isKindOfClass:[NSString class]] && [(NSString *)url length] > 0) {
        return YES;
    }

    if ([info[@"hasImage"] boolValue]) {
        return YES;
    }

    return NO;
}

static BOOL MCP_ShouldAvoidDirectPasteboardRead(void) {
    NSOperatingSystemVersion version = [[NSProcessInfo processInfo] operatingSystemVersion];
    return version.majorVersion >= 16;
}

static NSDictionary *MCP_ReadGeneralPasteboardDirectlyOnCurrentThread(void) {
    UIPasteboard *pb = [UIPasteboard generalPasteboard];
    NSString *text = pb.string;
    BOOL hasImage = pb.hasImages;
    BOOL hasURL = pb.hasURLs;
    NSURL *url = hasURL ? pb.URL : nil;

    NSMutableDictionary *info = [@{
        @"text": text ?: [NSNull null],
        @"hasImage": @(hasImage),
        @"hasURL": @(hasURL)
    } mutableCopy];
    if (url.absoluteString.length > 0) {
        info[@"url"] = url.absoluteString;
    }

    CLIPBOARD_LOG(@"Read clipboard directly textChars=%lu hasImage=%@ hasURL=%@",
                  (unsigned long)text.length,
                  hasImage ? @"yes" : @"no",
                  hasURL ? @"yes" : @"no");
    return [info copy];
}

static NSDictionary *MCP_ReadGeneralPasteboardDirectly(void) {
    __block NSDictionary *result;

    if (MCP_ShouldAvoidDirectPasteboardRead()) {
        dispatch_semaphore_t done = dispatch_semaphore_create(0);

        static dispatch_queue_t pbReadQueue;
        static dispatch_once_t onceToken;
        dispatch_once(&onceToken, ^{
            pbReadQueue = dispatch_queue_create("com.witchan.ios-mcp.clipboard.read", DISPATCH_QUEUE_SERIAL);
        });

        dispatch_async(pbReadQueue, ^{
            result = MCP_ReadGeneralPasteboardDirectlyOnCurrentThread();
            dispatch_semaphore_signal(done);
        });

        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(5 * NSEC_PER_SEC))) != 0) {
            CLIPBOARD_LOG(@"Direct clipboard read timed out after 5s; pasteboardd may be busy");
            return nil;
        }
        return result;
    }

    dispatch_block_t block = ^{
        result = MCP_ReadGeneralPasteboardDirectlyOnCurrentThread();
    };

    if ([NSThread isMainThread]) block();
    else dispatch_sync(dispatch_get_main_queue(), block);
    return result;
}

@implementation ClipboardManager

+ (instancetype)sharedInstance {
    static ClipboardManager *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[ClipboardManager alloc] init];
    });
    return instance;
}

- (NSDictionary *)readClipboard {
    NSDictionary *cacheInfo = MCP_ReadGeneralPasteboardFromCache();
    if (MCP_CachePasteboardInfoHasReadableContent(cacheInfo)) {
        return cacheInfo;
    }

    if (cacheInfo) {
        CLIPBOARD_LOG(@"Pasteboard cache has no readable content; falling back to direct clipboard read");
    }

    NSDictionary *directInfo = MCP_ReadGeneralPasteboardDirectly();
    if (directInfo) return directInfo;
    if (cacheInfo) return cacheInfo;

    return @{ @"text": [NSNull null],
              @"hasImage": @NO,
              @"hasURL": @NO,
              @"cacheMiss": @YES };
}

- (BOOL)writeText:(NSString *)text {
    if (!text) return NO;

    if (!MCP_ShouldAvoidDirectPasteboardRead()) {
        __block BOOL ok = NO;
        dispatch_block_t block = ^{
            [UIPasteboard generalPasteboard].string = text;
            ok = YES;
            CLIPBOARD_LOG(@"Wrote clipboard directly textChars=%lu", (unsigned long)text.length);
        };

        if ([NSThread isMainThread]) {
            block();
        } else {
            dispatch_sync(dispatch_get_main_queue(), block);
        }
        return ok;
    }

    // 与 readClipboard 同理：写入也跨进程到 pasteboardd，
    // 不要在 SpringBoard 主线程上同步等待。复用后台串行队列并加超时保护。
    __block BOOL ok = NO;
    dispatch_semaphore_t done = dispatch_semaphore_create(0);

    static dispatch_queue_t pbQueue;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        pbQueue = dispatch_queue_create("com.witchan.ios-mcp.clipboard.write", DISPATCH_QUEUE_SERIAL);
    });

    dispatch_async(pbQueue, ^{
        [UIPasteboard generalPasteboard].string = text;
        ok = YES;
        CLIPBOARD_LOG(@"Wrote clipboard textChars=%lu", (unsigned long)text.length);
        dispatch_semaphore_signal(done);
    });

    if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(5 * NSEC_PER_SEC))) != 0) {
        CLIPBOARD_LOG(@"Write clipboard timed out after 5s; pasteboardd may be busy");
        return NO;
    }

    return ok;
}

@end
