#import "FileSystemManager.h"
#import "MCPProcessUtil.h"
#import "MCPLogger.h"
#import <sys/stat.h>

#define FS_LOG(fmt, ...) [MCPLogger log:@"[FileSystem] " fmt, ##__VA_ARGS__]

// Default read cap for the JSON tool path. Larger files should use GET /download_file.
static const NSUInteger kFSDefaultMaxReadBytes = 512 * 1024;
static const NSUInteger kFSHardMaxReadBytes = 4 * 1024 * 1024;

@implementation FileSystemManager

+ (instancetype)sharedInstance {
    static FileSystemManager *instance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[FileSystemManager alloc] init];
    });
    return instance;
}

#pragma mark - Path helpers

// Resolve a caller-supplied absolute path to a concrete on-disk path, honoring the
// jailbreak root prefix (rootless/roothide). Falls back to the literal path.
//
// NOTE: file operations run in-process (the MCP server lives inside SpringBoard, which
// already has broad read access to other apps' containers and system paths). There is no
// shell/mcp-root fallback: the bundled setuid mcp-root helper only whitelists a fixed set
// of commands and rejects /bin/sh, so a privileged shell fallback could never run anyway.
// When direct access is denied we report the underlying errno honestly rather than pretend
// to elevate.
static NSString *FSResolvePath(NSString *path) {
    if (path.length == 0) return @"";
    NSString *resolved = MCPResolvedJailbreakPath(path);
    return resolved.length ? resolved : path;
}

static NSString *FSFileTypeString(mode_t mode) {
    if (S_ISDIR(mode)) return @"directory";
    if (S_ISLNK(mode)) return @"symlink";
    if (S_ISREG(mode)) return @"file";
    if (S_ISFIFO(mode)) return @"fifo";
    if (S_ISSOCK(mode)) return @"socket";
    if (S_ISCHR(mode)) return @"char_device";
    if (S_ISBLK(mode)) return @"block_device";
    return @"unknown";
}

static NSString *FSModeOctal(mode_t mode) {
    return [NSString stringWithFormat:@"%03o", (unsigned)(mode & 07777)];
}

#pragma mark - List directory

- (NSDictionary *)listDirectoryAtPath:(NSString *)path error:(NSString **)error {
    if (error) *error = nil;
    if (path.length == 0) {
        if (error) *error = @"path is required";
        return nil;
    }

    NSString *resolved = FSResolvePath(path);
    NSFileManager *fm = [NSFileManager defaultManager];

    BOOL isDir = NO;
    if (![fm fileExistsAtPath:resolved isDirectory:&isDir]) {
        if (error) *error = [NSString stringWithFormat:@"No such file or directory: %@", path];
        return nil;
    }
    if (!isDir) {
        if (error) *error = @"path is not a directory; use read_file";
        return nil;
    }

    NSError *listError = nil;
    NSArray<NSString *> *names = [fm contentsOfDirectoryAtPath:resolved error:&listError];
    if (!names) {
        if (error) *error = [NSString stringWithFormat:@"Cannot list directory: %@",
                             listError.localizedDescription ?: @"permission denied"];
        FS_LOG(@"list failed path=%@ err=%@", path, listError.localizedDescription ?: @"-");
        return nil;
    }

    NSMutableArray<NSDictionary *> *entries = [NSMutableArray array];
    for (NSString *name in [names sortedArrayUsingSelector:@selector(localizedStandardCompare:)]) {
        NSString *child = [resolved stringByAppendingPathComponent:name];
        struct stat st;
        NSMutableDictionary *entry = [@{@"name": name} mutableCopy];
        if (lstat(child.fileSystemRepresentation, &st) == 0) {
            entry[@"type"] = FSFileTypeString(st.st_mode);
            entry[@"size"] = @(st.st_size);
            entry[@"mode"] = FSModeOctal(st.st_mode);
            entry[@"mtime"] = @((long long)st.st_mtimespec.tv_sec);
            if (S_ISLNK(st.st_mode)) {
                char buf[1024];
                ssize_t n = readlink(child.fileSystemRepresentation, buf, sizeof(buf) - 1);
                if (n > 0) {
                    buf[n] = '\0';
                    entry[@"symlink_target"] = [NSString stringWithUTF8String:buf] ?: @"";
                }
            }
        } else {
            entry[@"type"] = @"unknown";
        }
        [entries addObject:entry];
    }

    FS_LOG(@"list ok path=%@ count=%lu", path, (unsigned long)entries.count);
    return @{@"path": path, @"resolved_path": resolved, @"entries": entries};
}

#pragma mark - Read file

- (NSDictionary *)readFileAtPath:(NSString *)path
                        maxBytes:(NSUInteger)maxBytes
                     forceBinary:(BOOL)forceBinary
                           error:(NSString **)error {
    if (error) *error = nil;
    if (path.length == 0) {
        if (error) *error = @"path is required";
        return nil;
    }
    if (maxBytes == 0) maxBytes = kFSDefaultMaxReadBytes;
    if (maxBytes > kFSHardMaxReadBytes) maxBytes = kFSHardMaxReadBytes;

    NSString *resolved = FSResolvePath(path);
    NSFileManager *fm = [NSFileManager defaultManager];

    BOOL isDir = NO;
    if (![fm fileExistsAtPath:resolved isDirectory:&isDir]) {
        if (error) *error = [NSString stringWithFormat:@"No such file or directory: %@", path];
        return nil;
    }
    if (isDir) {
        if (error) *error = @"path is a directory; use list_dir";
        return nil;
    }

    // Read up to maxBytes+1 so we can detect truncation.
    NSFileHandle *handle = [NSFileHandle fileHandleForReadingAtPath:resolved];
    if (!handle) {
        if (error) *error = [NSString stringWithFormat:@"Cannot open file: %@ (permission denied or unreadable)", path];
        FS_LOG(@"read failed path=%@ (open)", path);
        return nil;
    }

    NSData *data = nil;
    @try {
        data = [handle readDataOfLength:maxBytes + 1];
    } @catch (NSException *e) {
        data = nil;
    }
    [handle closeFile];

    if (!data) {
        if (error) *error = [NSString stringWithFormat:@"Cannot read file: %@", path];
        return nil;
    }

    BOOL truncated = NO;
    if (data.length > maxBytes) {
        truncated = YES;
        data = [data subdataWithRange:NSMakeRange(0, maxBytes)];
    }

    NSString *encoding = @"utf8";
    NSString *content = nil;
    if (!forceBinary) {
        content = [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    }
    if (!content) {
        encoding = @"base64";
        content = [data base64EncodedStringWithOptions:0];
    }

    FS_LOG(@"read ok path=%@ bytes=%lu enc=%@ trunc=%@",
           path, (unsigned long)data.length, encoding, truncated ? @"yes" : @"no");

    return @{
        @"path": path,
        @"resolved_path": resolved,
        @"size": @(data.length),
        @"encoding": encoding,
        @"content": content ?: @"",
        @"truncated": @(truncated),
        @"hint": truncated ? @"Output truncated; use GET /download_file?path=... for the full file." : @""
    };
}

#pragma mark - Write file

- (NSDictionary *)writeFileAtPath:(NSString *)path
                          content:(NSString *)content
                         encoding:(NSString *)encoding
                            error:(NSString **)error {
    if (error) *error = nil;
    if (path.length == 0) {
        if (error) *error = @"path is required";
        return nil;
    }
    if (content == nil) content = @"";

    NSData *data = nil;
    if ([encoding isEqualToString:@"base64"]) {
        data = [[NSData alloc] initWithBase64EncodedString:content options:NSDataBase64DecodingIgnoreUnknownCharacters];
        if (!data) {
            if (error) *error = @"content is not valid base64";
            return nil;
        }
    } else {
        data = [content dataUsingEncoding:NSUTF8StringEncoding] ?: [NSData data];
    }

    NSString *resolved = FSResolvePath(path);
    NSError *writeError = nil;
    if (![data writeToFile:resolved options:NSDataWritingAtomic error:&writeError]) {
        if (error) *error = [NSString stringWithFormat:@"Cannot write file: %@",
                             writeError.localizedDescription ?: @"permission denied"];
        FS_LOG(@"write failed path=%@ err=%@", path, writeError.localizedDescription ?: @"-");
        return nil;
    }

    FS_LOG(@"write ok path=%@ bytes=%lu", path, (unsigned long)data.length);
    return @{
        @"path": path,
        @"resolved_path": resolved,
        @"bytes_written": @(data.length)
    };
}

#pragma mark - Download resolution

- (NSString *)resolveDownloadPath:(NSString *)path
                      isTemporary:(BOOL *)isTemporary
                            error:(NSString **)error {
    if (isTemporary) *isTemporary = NO;
    if (error) *error = nil;
    if (path.length == 0) {
        if (error) *error = @"path is required";
        return nil;
    }

    NSString *resolved = FSResolvePath(path);
    NSFileManager *fm = [NSFileManager defaultManager];
    BOOL isDir = NO;

    if (![fm fileExistsAtPath:resolved isDirectory:&isDir]) {
        if (error) *error = @"File not found";
        return nil;
    }
    if (isDir) {
        if (error) *error = @"path is a directory";
        return nil;
    }
    if (![fm isReadableFileAtPath:resolved]) {
        if (error) *error = @"File is not readable";
        return nil;
    }
    return resolved;
}

@end
