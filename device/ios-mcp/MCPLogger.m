#import "MCPLogger.h"
#import "IOSMCPPreferences.h"
#import <CoreFoundation/CoreFoundation.h>
#import <errno.h>
#import <fcntl.h>
#import <string.h>
#import <sys/time.h>
#import <sys/file.h>
#import <sys/stat.h>
#import <unistd.h>

static const unsigned long long MCPLoggerMaxBytes = 2ULL * 1024ULL * 1024ULL;
static const NSUInteger MCPLoggerMaxArchives = 1;

static dispatch_queue_t MCPLoggerQueue(void) {
    static dispatch_queue_t queue;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        queue = dispatch_queue_create("com.witchan.ios-mcp.debug-log", DISPATCH_QUEUE_SERIAL);
    });
    return queue;
}

static NSString *MCPLoggerTimestamp(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);

    struct tm localTime;
    localtime_r(&tv.tv_sec, &localTime);

    char buffer[40];
    strftime(buffer, sizeof(buffer), "%Y-%m-%d %H:%M:%S", &localTime);
    char zone[8];
    strftime(zone, sizeof(zone), "%z", &localTime);
    return [NSString stringWithFormat:@"%s.%03d%s", buffer, (int)(tv.tv_usec / 1000), zone];
}

static NSString *MCPLoggerSanitizedMessage(NSString *message) {
    if (![message isKindOfClass:[NSString class]] || message.length == 0) {
        return @"";
    }

    NSString *clean = [message stringByReplacingOccurrencesOfString:@"\r" withString:@" "];
    clean = [clean stringByReplacingOccurrencesOfString:@"\n" withString:@" "];
    if (clean.length > 4096) {
        clean = [[clean substringToIndex:4096] stringByAppendingString:@"...<truncated>"];
    }
    return clean;
}

// 直接读取偏好（每次都会访问 CFPreferences，成本较高）。
static BOOL MCPReadDebugLoggingPreference(void) {
    CFPropertyListRef value = CFPreferencesCopyAppValue((__bridge CFStringRef)IOS_MCP_DEBUG_LOGGING_PREFERENCE_KEY,
                                                        (__bridge CFStringRef)IOS_MCP_PREFERENCES_DOMAIN);
    if (!value) {
        return NO;
    }

    BOOL enabled = NO;
    CFTypeID typeID = CFGetTypeID(value);
    if (typeID == CFBooleanGetTypeID()) {
        enabled = CFBooleanGetValue((CFBooleanRef)value);
    } else if (typeID == CFNumberGetTypeID()) {
        int numericValue = 0;
        CFNumberGetValue((CFNumberRef)value, kCFNumberIntType, &numericValue);
        enabled = numericValue != 0;
    }

    CFRelease(value);
    return enabled;
}

// 带短 TTL 缓存的开关查询：日志在热路径（HID/AX 等）会被高频调用，关闭时若每次都读
// CFPreferences 反而影响性能。缓存最多 2 秒，切换开关后最迟约 2 秒生效。
static const CFTimeInterval kMCPDebugLoggingCacheTTL = 2.0;
static BOOL sMCPDebugLoggingCached = NO;
static CFAbsoluteTime sMCPDebugLoggingCacheTime = 0;
static NSString *sMCPLoggerLastError = nil;

static NSObject *MCPLoggerStateLock(void) {
    static NSObject *lock;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        lock = [NSObject new];
    });
    return lock;
}

static void MCPLoggerSetLastError(NSString *message) {
    @synchronized (MCPLoggerStateLock()) {
        sMCPLoggerLastError = [message copy];
    }
}

static void MCPLoggerSetLastErrno(NSString *operation, int err) {
    NSString *message = [NSString stringWithFormat:@"%@ failed errno=%d error=%s",
                         operation ?: @"log_write",
                         err,
                         strerror(err)];
    MCPLoggerSetLastError(message);
}

static void MCPLoggerClearLastError(void) {
    @synchronized (MCPLoggerStateLock()) {
        sMCPLoggerLastError = nil;
    }
}

static BOOL MCPLoggerWriteAll(int fd, NSData *data) {
    const uint8_t *bytes = data.bytes;
    NSUInteger remaining = data.length;
    NSUInteger offset = 0;

    while (remaining > 0) {
        ssize_t written = write(fd, bytes + offset, remaining);
        if (written < 0 && errno == EINTR) {
            continue;
        }
        if (written <= 0) {
            MCPLoggerSetLastErrno(@"write", errno);
            return NO;
        }
        offset += (NSUInteger)written;
        remaining -= (NSUInteger)written;
    }
    return YES;
}

@implementation MCPLogger

+ (BOOL)isDebugLoggingEnabled {
    CFAbsoluteTime now = CFAbsoluteTimeGetCurrent();
    @synchronized (MCPLoggerStateLock()) {
        CFAbsoluteTime last = sMCPDebugLoggingCacheTime;
        if (last != 0 && (now - last) >= 0 && (now - last) < kMCPDebugLoggingCacheTTL) {
            return sMCPDebugLoggingCached;
        }
    }

    BOOL enabled = MCPReadDebugLoggingPreference();
    @synchronized (MCPLoggerStateLock()) {
        sMCPDebugLoggingCached = enabled;
        sMCPDebugLoggingCacheTime = now;
    }
    return enabled;
}

+ (NSString *)logDirectoryPath {
    return @"/var/mobile/Library/Logs/iOSMCP";
}

+ (NSString *)logFilePath {
    return [[self logDirectoryPath] stringByAppendingPathComponent:@"ios-mcp.log"];
}

+ (NSString *)previousLogFilePath {
    return [[self logDirectoryPath] stringByAppendingPathComponent:@"ios-mcp.1.log"];
}

+ (NSString *)archivedLogFilePathAtIndex:(NSUInteger)index {
    if (index == 0) {
        return [self logFilePath];
    }
    return [[self logDirectoryPath] stringByAppendingPathComponent:
            [NSString stringWithFormat:@"ios-mcp.%lu.log", (unsigned long)index]];
}

+ (NSArray<NSString *> *)allLogFilePaths {
    NSMutableArray<NSString *> *paths = [NSMutableArray arrayWithObject:[self logFilePath]];
    for (NSUInteger index = 1; index <= MCPLoggerMaxArchives; index++) {
        [paths addObject:[self archivedLogFilePathAtIndex:index]];
    }
    return paths;
}

+ (NSString *)lockFilePath {
    return [[self logDirectoryPath] stringByAppendingPathComponent:@"ios-mcp.lock"];
}

+ (NSString *)lastLogError {
    @synchronized (MCPLoggerStateLock()) {
        return [sMCPLoggerLastError copy];
    }
}

+ (void)log:(NSString *)format, ... {
    if (!format.length || ![self isDebugLoggingEnabled]) {
        return;
    }

    va_list args;
    va_start(args, format);
    NSString *message = [[NSString alloc] initWithFormat:format arguments:args];
    va_end(args);

    NSLog(@"[witchan][ios-mcp] %@", message);
    [self logMessage:message];
}

+ (void)logMessage:(NSString *)message {
    if (!message.length || ![self isDebugLoggingEnabled]) {
        return;
    }

    NSString *cleanMessage = MCPLoggerSanitizedMessage(message);
    NSString *line = [NSString stringWithFormat:@"%@ pid=%d %@\n",
                      MCPLoggerTimestamp(),
                      getpid(),
                      cleanMessage];
    NSData *lineData = [line dataUsingEncoding:NSUTF8StringEncoding];
    if (!lineData.length) {
        return;
    }

    dispatch_async(MCPLoggerQueue(), ^{
        if (![self isDebugLoggingEnabled]) {
            return;
        }

        NSFileManager *fm = [NSFileManager defaultManager];
        NSString *dirPath = [self logDirectoryPath];
        NSError *dirError = nil;
        if (![fm createDirectoryAtPath:dirPath
           withIntermediateDirectories:YES
                            attributes:@{NSFilePosixPermissions: @0755}
                                 error:&dirError]) {
            MCPLoggerSetLastError([NSString stringWithFormat:@"createDirectory failed: %@",
                                   dirError.localizedDescription ?: @"unknown"]);
            return;
        }

        NSString *logPath = [self logFilePath];
        NSString *previousPath = [self previousLogFilePath];
        NSString *lockPath = [self lockFilePath];
        int lockFd = open(lockPath.fileSystemRepresentation, O_CREAT | O_RDWR, 0644);
        if (lockFd < 0) {
            MCPLoggerSetLastErrno(@"open_lock", errno);
            return;
        }

        BOOL locked = NO;
        while (flock(lockFd, LOCK_EX) < 0) {
            if (errno == EINTR) {
                continue;
            }
            MCPLoggerSetLastErrno(@"flock", errno);
            close(lockFd);
            return;
        }
        locked = YES;

        BOOL operationHadError = NO;
        struct stat st = {0};
        unsigned long long currentSize = 0;
        if (stat(logPath.fileSystemRepresentation, &st) == 0) {
            currentSize = (unsigned long long)st.st_size;
        } else if (errno != ENOENT) {
            MCPLoggerSetLastErrno(@"stat", errno);
            operationHadError = YES;
        }

        if (currentSize > 0 && currentSize + lineData.length > MCPLoggerMaxBytes) {
            NSString *oldestPath = [self archivedLogFilePathAtIndex:MCPLoggerMaxArchives];
            if (unlink(oldestPath.fileSystemRepresentation) < 0 && errno != ENOENT) {
                MCPLoggerSetLastErrno(@"unlink_previous", errno);
                operationHadError = YES;
            }
            for (NSUInteger index = MCPLoggerMaxArchives; index > 1; index--) {
                NSString *fromPath = [self archivedLogFilePathAtIndex:index - 1];
                NSString *toPath = [self archivedLogFilePathAtIndex:index];
                if (rename(fromPath.fileSystemRepresentation, toPath.fileSystemRepresentation) < 0 && errno != ENOENT) {
                    MCPLoggerSetLastErrno(@"rotate_archive", errno);
                    operationHadError = YES;
                }
            }
            if (rename(logPath.fileSystemRepresentation, previousPath.fileSystemRepresentation) < 0 && errno != ENOENT) {
                MCPLoggerSetLastErrno(@"rotate", errno);
                operationHadError = YES;
            }
        }

        int logFd = open(logPath.fileSystemRepresentation, O_CREAT | O_APPEND | O_WRONLY, 0644);
        if (logFd < 0) {
            MCPLoggerSetLastErrno(@"open_log", errno);
        } else {
            if (MCPLoggerWriteAll(logFd, lineData) && !operationHadError) {
                MCPLoggerClearLastError();
            }
            close(logFd);
        }

        if (locked) {
            flock(lockFd, LOCK_UN);
        }
        close(lockFd);
    });
}

+ (BOOL)clearLogsWithError:(NSError **)error {
    __block BOOL ok = YES;
    __block NSError *localError = nil;

    dispatch_sync(MCPLoggerQueue(), ^{
        NSFileManager *fm = [NSFileManager defaultManager];
        NSString *dirPath = [self logDirectoryPath];
        [fm createDirectoryAtPath:dirPath
      withIntermediateDirectories:YES
                       attributes:@{NSFilePosixPermissions: @0755}
                            error:nil];
        int lockFd = open([self lockFilePath].fileSystemRepresentation, O_CREAT | O_RDWR, 0644);
        if (lockFd < 0) {
            ok = NO;
            localError = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
            return;
        }
        while (flock(lockFd, LOCK_EX) < 0) {
            if (errno == EINTR) {
                continue;
            }
            ok = NO;
            localError = [NSError errorWithDomain:NSPOSIXErrorDomain code:errno userInfo:nil];
            close(lockFd);
            return;
        }

        NSArray<NSString *> *paths = [self allLogFilePaths];
        for (NSString *path in paths) {
            if (![fm fileExistsAtPath:path]) {
                continue;
            }
            NSError *removeError = nil;
            if (![fm removeItemAtPath:path error:&removeError]) {
                ok = NO;
                localError = removeError;
                break;
            }
        }
        flock(lockFd, LOCK_UN);
        close(lockFd);
    });

    if (!ok && error) {
        *error = localError;
    }
    return ok;
}

@end
