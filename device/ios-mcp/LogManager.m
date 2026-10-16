#import "LogManager.h"
#import "MCPProcessUtil.h"
#import "MCPLogger.h"

#define LOG_LOG(fmt, ...) [MCPLogger log:@"[LogManager] " fmt, ##__VA_ARGS__]

static const NSInteger kLogDefaultMaxLines = 500;
static const NSInteger kLogHardMaxLines = 5000;
static const NSInteger kLogDefaultSeconds = 5;
static const NSInteger kLogMaxSeconds = 60;
static const NSInteger kCrashDefaultLimit = 30;

// Crash report directories (resolved through the jailbreak prefix at call time).
static NSArray<NSString *> *LogCrashDirectories(void) {
    return @[
        @"/var/mobile/Library/Logs/CrashReporter",
        @"/var/mobile/Library/Logs/CrashReporter/Retired",
        @"/Library/Logs/CrashReporter"
    ];
}

@implementation LogManager

+ (instancetype)sharedInstance {
    static LogManager *instance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[LogManager alloc] init];
    });
    return instance;
}

#pragma mark - Syslog (OSLogStore, in-process)

#pragma mark - Syslog (live stream via mcp-logreader helper)

// Reads the unified system log by spawning the bundled mcp-logreader helper, which
// connects to diagnosticd's live event stream (the same mechanism Console.app uses)
// via OSLogEventLiveStream. The helper carries the com.apple.private.logging.stream
// entitlement, so it can read ALL processes' logs — not just the MCP host's.
//
// This is a LIVE capture: it collects events arriving during a `lastSeconds` window,
// not historical logs. `process` filters by process name, `level` by error/fault.
- (NSDictionary *)syslogWithProcess:(NSString *)process
                              level:(NSString *)level
                        lastSeconds:(NSInteger)lastSeconds
                           maxLines:(NSInteger)maxLines
                              error:(NSString **)error {
    if (error) *error = nil;
    if (maxLines <= 0) maxLines = kLogDefaultMaxLines;
    if (maxLines > kLogHardMaxLines) maxLines = kLogHardMaxLines;
    if (lastSeconds <= 0) lastSeconds = kLogDefaultSeconds;
    if (lastSeconds > kLogMaxSeconds) lastSeconds = kLogMaxSeconds;

    NSString *helper = MCPResolvedJailbreakPath(@"/usr/bin/mcp-logreader");
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:helper]) {
        if (error) *error = @"mcp-logreader helper not installed";
        return nil;
    }

    NSMutableArray<NSString *> *args = [NSMutableArray array];
    [args addObject:@"--seconds"]; [args addObject:[NSString stringWithFormat:@"%ld", (long)lastSeconds]];
    [args addObject:@"--max-lines"]; [args addObject:[NSString stringWithFormat:@"%ld", (long)maxLines]];
    if (process.length) { [args addObject:@"--process"]; [args addObject:process]; }
    if (level.length && ![level isEqualToString:@"all"]) { [args addObject:@"--level"]; [args addObject:level]; }

    // Allow the helper its full capture window plus margin.
    NSTimeInterval timeout = (NSTimeInterval)lastSeconds + 10.0;
    NSString *output = nil;
    NSString *runError = nil;
    int exitCode = -1;
    BOOL finished = MCPRunProcess(helper,
                                  args,
                                  MCPJailbreakEnvironment(),
                                  timeout,
                                  4 * 1024 * 1024,
                                  &output,
                                  &exitCode,
                                  &runError);
    if (!finished) {
        if (error) *error = runError.length ? runError : @"mcp-logreader timed out";
        LOG_LOG(@"syslog helper failed: %@", runError ?: @"-");
        return nil;
    }

    // Parse NDJSON: one log object per line, final {"_summary":...} line.
    NSMutableArray<NSDictionary *> *entries = [NSMutableArray array];
    BOOL truncated = NO;
    NSString *helperError = nil;
    for (NSString *line in [output componentsSeparatedByString:@"\n"]) {
        NSString *trimmed = [line stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceCharacterSet]];
        if (trimmed.length == 0) continue;
        NSData *d = [trimmed dataUsingEncoding:NSUTF8StringEncoding];
        NSDictionary *obj = [NSJSONSerialization JSONObjectWithData:d options:0 error:nil];
        if (![obj isKindOfClass:[NSDictionary class]]) continue;
        if (obj[@"_summary"]) {
            truncated = [obj[@"truncated"] boolValue];
            continue;
        }
        if (obj[@"_error"]) { helperError = obj[@"_error"]; continue; }
        [entries addObject:obj];
    }

    if (entries.count == 0 && helperError.length) {
        if (error) *error = helperError;
        return nil;
    }

    LOG_LOG(@"syslog ok entries=%lu lastSeconds=%ld process=%@ exit=%d",
            (unsigned long)entries.count, (long)lastSeconds, process ?: @"-", exitCode);
    return @{
        @"entries": entries,
        @"count": @(entries.count),
        @"capture_seconds": @(lastSeconds),
        @"process": process ?: @"",
        @"mode": @"live_stream",
        @"truncated": @(truncated)
    };
}

#pragma mark - Crash logs (direct file access, in-process)

- (NSDictionary *)crashLogsForBundleId:(NSString *)bundleId
                                 limit:(NSInteger)limit
                                 error:(NSString **)error {
    if (error) *error = nil;
    if (limit <= 0) limit = kCrashDefaultLimit;

    NSFileManager *fm = [NSFileManager defaultManager];
    NSMutableArray<NSDictionary *> *reports = [NSMutableArray array];
    NSMutableArray<NSString *> *scanned = [NSMutableArray array];

    for (NSString *dir in LogCrashDirectories()) {
        NSString *resolved = MCPResolvedJailbreakPath(dir);
        BOOL isDir = NO;
        if (![fm fileExistsAtPath:resolved isDirectory:&isDir] || !isDir) continue;
        [scanned addObject:dir];

        NSError *listError = nil;
        NSArray<NSString *> *names = [fm contentsOfDirectoryAtPath:resolved error:&listError];
        if (!names) continue;

        for (NSString *name in names) {
            NSString *lower = name.lowercaseString;
            if (![lower hasSuffix:@".ips"] && ![lower hasSuffix:@".crash"]) continue;
            if (bundleId.length && ![name hasPrefix:bundleId]) continue;

            NSString *full = [resolved stringByAppendingPathComponent:name];
            NSDictionary<NSFileAttributeKey, id> *attrs = [fm attributesOfItemAtPath:full error:nil];
            long long size = [attrs[NSFileSize] longLongValue];
            NSDate *mtime = attrs[NSFileModificationDate];

            [reports addObject:@{
                @"name": name,
                @"path": full,
                @"date": @(mtime ? (long long)mtime.timeIntervalSince1970 : 0),
                @"size": @(size)
            }];
        }
    }

    // Newest first.
    [reports sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        return [b[@"date"] compare:a[@"date"]];
    }];
    if ((NSInteger)reports.count > limit) {
        [reports removeObjectsInRange:NSMakeRange(limit, reports.count - limit)];
    }

    LOG_LOG(@"crashlist ok count=%lu bundle=%@ scannedDirs=%lu",
            (unsigned long)reports.count, bundleId ?: @"-", (unsigned long)scanned.count);
    return @{@"reports": reports, @"count": @(reports.count), @"scanned_dirs": scanned};
}

- (NSDictionary *)crashLogContentAtPath:(NSString *)path error:(NSString **)error {
    if (error) *error = nil;
    if (path.length == 0) {
        if (error) *error = @"path is required";
        return nil;
    }
    NSString *resolved = MCPResolvedJailbreakPath(path);
    NSError *readError = nil;
    NSString *content = [NSString stringWithContentsOfFile:resolved encoding:NSUTF8StringEncoding error:&readError];
    if (!content) {
        if (error) *error = [NSString stringWithFormat:@"Cannot read crash log: %@",
                             readError.localizedDescription ?: @"unreadable"];
        return nil;
    }
    return @{@"path": path, @"content": content};
}

@end
