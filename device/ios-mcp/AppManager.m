#import "AppManager.h"
#import "AccessibilityManager.h"
#import "MCPProcessUtil.h"
#import "SpringBoardPrivate.h"
#include <roothide.h>
#import <Security/Security.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import "IOSMCPPreferences.h"
#import "MCPLogger.h"
#import <fcntl.h>
#import <spawn.h>
#import <string.h>
#import <sys/stat.h>
#import <sys/wait.h>
#import <unistd.h>

extern char **environ;

typedef struct __SecCode const *SecStaticCodeRef;
typedef CF_OPTIONS(uint32_t, MCPSecCSFlags) {
    kMCPSecCSDefaultFlags = 0
};
#define kMCPSecCSRequirementInformation (1 << 2)

OSStatus SecStaticCodeCreateWithPathAndAttributes(CFURLRef path,
                                                  MCPSecCSFlags flags,
                                                  CFDictionaryRef attributes,
                                                  SecStaticCodeRef *staticCode);
OSStatus SecCodeCopySigningInformation(SecStaticCodeRef code,
                                       MCPSecCSFlags flags,
                                       CFDictionaryRef *information);
extern CFStringRef kSecCodeInfoEntitlementsDict;

@interface UIApplication (MCPPrivate)
- (id)_accessibilityFrontMostApplication;
@end

#define APP_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[App] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)

static id MCPAppMsgSendObject(id target, SEL selector) {
    if (!target || !selector) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(target, selector);
}

static id MCPAppMsgSendObjectArg(id target, SEL selector, id arg) {
    if (!target || !selector) return nil;
    return ((id (*)(id, SEL, id))objc_msgSend)(target, selector, arg);
}

static BOOL MCPURLUsesSettingsScheme(NSURL *url) {
    NSString *scheme = url.scheme.lowercaseString ?: @"";
    return [scheme isEqualToString:@"prefs"] || [scheme isEqualToString:@"app-prefs"];
}

static NSString *MCPAppLogSafePath(NSString *path) {
    if (![path isKindOfClass:[NSString class]] || path.length == 0) {
        return @"-";
    }
    NSString *extension = path.pathExtension.lowercaseString;
    if (extension.length > 0 && extension.length <= 12) {
        return [NSString stringWithFormat:@"<path:.%@>", extension];
    }
    return @"<path>";
}

static NSString *MCPAppLogSafeURLString(NSString *urlString) {
    if (![urlString isKindOfClass:[NSString class]] || urlString.length == 0) {
        return @"-";
    }
    NSURLComponents *components = [NSURLComponents componentsWithString:urlString];
    NSString *scheme = components.scheme.lowercaseString;
    NSString *host = components.host;
    if (scheme.length > 0 && host.length > 0) {
        return [NSString stringWithFormat:@"<url:%@://%@>", scheme, host];
    }
    if (scheme.length > 0) {
        return [NSString stringWithFormat:@"<url:%@>", scheme];
    }
    return @"<url>";
}

static NSString *MCPAppLogRedactedText(NSString *text) {
    if (![text isKindOfClass:[NSString class]] || text.length == 0) {
        return @"-";
    }
    NSString *result = [[text stringByReplacingOccurrencesOfString:@"\r" withString:@" "]
                        stringByReplacingOccurrencesOfString:@"\n" withString:@" "];
    NSArray<NSDictionary<NSString *, NSString *> *> *rules = @[
        @{@"pattern": @"(?i)\\b[a-z][a-z0-9+.-]*://[^\\s\\\"'<>]+", @"replacement": @"<url>"},
        @{@"pattern": @"(?i)\\b(prefs|app-prefs):[^\\s\\\"'<>]+", @"replacement": @"<url>"},
        @{@"pattern": @"(/private)?/(var|tmp|Applications|User|Users|Library)[^\\s\\\"'<>]*", @"replacement": @"<path>"}
    ];
    for (NSDictionary<NSString *, NSString *> *rule in rules) {
        NSError *regexError = nil;
        NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:rule[@"pattern"]
                                                                               options:0
                                                                                 error:&regexError];
        if (!regex || regexError) {
            continue;
        }
        result = [regex stringByReplacingMatchesInString:result
                                                 options:0
                                                   range:NSMakeRange(0, result.length)
                                            withTemplate:rule[@"replacement"]];
    }
    if (result.length > 256) {
        result = [[result substringToIndex:256] stringByAppendingString:@"...<truncated>"];
    }
    return result;
}

static NSString *MCPSpringBoardKillallPath(void) {
    NSFileManager *fm = [NSFileManager defaultManager];
    for (NSString *candidate in @[
        MCPResolvedJailbreakPath(@"/usr/bin/killall"),
        MCPResolvedJailbreakPath(@"/bin/killall"),
        @"/usr/bin/killall",
        @"/bin/killall"
    ]) {
        if (candidate.length && [fm isExecutableFileAtPath:candidate]) {
            return candidate;
        }
    }
    return nil;
}

static BOOL MCPScheduleSpringBoardRestart(NSString **error) {
    NSString *killallPath = MCPSpringBoardKillallPath();
    if (!killallPath.length) {
        if (error) *error = @"killall executable not found";
        return NO;
    }

    NSString *spawnPath = [killallPath copy];
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(800 * NSEC_PER_MSEC)), dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
        pid_t pid = 0;
        char *const argv[] = {"killall", "-9", "SpringBoard", NULL};
        int status = posix_spawn(&pid, spawnPath.fileSystemRepresentation, NULL, NULL, argv, NULL);
        if (status != 0) {
            APP_LOG(@"Failed to spawn SpringBoard restart via %@: %s", MCPAppLogSafePath(spawnPath), strerror(status));
            return;
        }
        APP_LOG(@"Scheduled SpringBoard restart pid=%d", pid);
    });
    return YES;
}

static BOOL MCPDebPackageIdIsSafe(NSString *packageId) {
    if (![packageId isKindOfClass:[NSString class]]) {
        return NO;
    }

    const char *utf8 = packageId.UTF8String;
    if (!utf8) {
        return NO;
    }

    size_t length = strlen(utf8);
    if (length == 0 || length > 128 || length != [packageId lengthOfBytesUsingEncoding:NSUTF8StringEncoding]) {
        return NO;
    }

    unsigned char first = (unsigned char)utf8[0];
    if (!((first >= 'A' && first <= 'Z') || (first >= 'a' && first <= 'z') || (first >= '0' && first <= '9'))) {
        return NO;
    }

    for (size_t i = 1; i < length; i++) {
        unsigned char ch = (unsigned char)utf8[i];
        BOOL allowed = ((ch >= 'A' && ch <= 'Z') ||
                        (ch >= 'a' && ch <= 'z') ||
                        (ch >= '0' && ch <= '9') ||
                        ch == '+' ||
                        ch == '-' ||
                        ch == '.');
        if (!allowed) {
            return NO;
        }
    }

    return YES;
}

static NSUInteger MCPAppLogUTF8Length(NSString *text) {
    return [text isKindOfClass:[NSString class]] ? [text lengthOfBytesUsingEncoding:NSUTF8StringEncoding] : 0;
}

static BOOL MCPReadFileHeader(NSString *path, uint32_t *outMagic) {
    if (outMagic) *outMagic = 0;

    FILE *fp = fopen(path.fileSystemRepresentation, "rb");
    if (!fp) return NO;

    uint32_t magic = 0;
    size_t bytesRead = fread(&magic, 1, sizeof(magic), fp);
    fclose(fp);
    if (bytesRead != sizeof(magic)) return NO;

    if (outMagic) *outMagic = magic;
    return YES;
}

static BOOL MCPIsMachOFile(NSString *path) {
    uint32_t magic = 0;
    if (!MCPReadFileHeader(path, &magic)) return NO;

    switch (magic) {
        case 0xfeedface:
        case 0xcefaedfe:
        case 0xfeedfacf:
        case 0xcffaedfe:
        case 0xcafebabe:
        case 0xbebafeca:
            return YES;
        default:
            return NO;
    }
}

static BOOL MCPIsSameFile(NSString *path1, NSString *path2) {
    if (path1.length == 0 || path2.length == 0) return NO;

    struct stat sb1 = {0};
    struct stat sb2 = {0};
    if (stat(path1.fileSystemRepresentation, &sb1) != 0) return NO;
    if (stat(path2.fileSystemRepresentation, &sb2) != 0) return NO;
    return (sb1.st_dev == sb2.st_dev && sb1.st_ino == sb2.st_ino);
}

static NSDictionary<NSString *, id> *MCPDumpEntitlementsFromBinaryAtPath(NSString *binaryPath) {
    if (binaryPath.length == 0) return nil;

    SecStaticCodeRef codeRef = NULL;
    OSStatus createStatus = SecStaticCodeCreateWithPathAndAttributes((__bridge CFURLRef)[NSURL fileURLWithPath:binaryPath],
                                                                     kMCPSecCSDefaultFlags,
                                                                     NULL,
                                                                     &codeRef);
    if (createStatus != errSecSuccess || codeRef == NULL) {
        return nil;
    }

    CFDictionaryRef signingInfo = NULL;
    OSStatus copyStatus = SecCodeCopySigningInformation(codeRef,
                                                        kMCPSecCSRequirementInformation,
                                                        &signingInfo);
    CFRelease(codeRef);
    if (copyStatus != errSecSuccess || signingInfo == NULL) {
        if (signingInfo) CFRelease(signingInfo);
        return nil;
    }

    NSDictionary *entitlementsDict = nil;
    CFTypeRef entitlements = CFDictionaryGetValue(signingInfo, kSecCodeInfoEntitlementsDict);
    if (entitlements && CFGetTypeID(entitlements) == CFDictionaryGetTypeID()) {
        entitlementsDict = [(__bridge NSDictionary *)entitlements copy];
    }

    CFRelease(signingInfo);
    return entitlementsDict;
}

static NSDictionary<NSString *, id> *MCPFallbackMainExecutableEntitlements(void) {
    return @{
        @"application-identifier": @"TROLLTROLL.*",
        @"com.apple.developer.team-identifier": @"TROLLTROLL",
        @"get-task-allow": @YES,
        @"keychain-access-groups": @[
            @"TROLLTROLL.*",
            @"com.apple.token"
        ]
    };
}

static NSDate *MCPBestFileDate(NSDictionary<NSFileAttributeKey, id> *attributes) {
    NSDate *creationDate = attributes[NSFileCreationDate];
    NSDate *modificationDate = attributes[NSFileModificationDate];
    if (!creationDate) return modificationDate;
    if (!modificationDate) return creationDate;
    return ([creationDate compare:modificationDate] == NSOrderedDescending) ? creationDate : modificationDate;
}

static NSString *MCPShellQuote(NSString *string) {
    NSString *value = string ?: @"";
    return [NSString stringWithFormat:@"'%@'", [value stringByReplacingOccurrencesOfString:@"'" withString:@"'\\''"]];
}

static NSString *MCPConfiguredSudoPassword(void) {
    CFPropertyListRef value = CFPreferencesCopyAppValue(CFSTR("sudo_password"),
                                                        (__bridge CFStringRef)IOS_MCP_PREFERENCES_DOMAIN);
    if (value && CFGetTypeID(value) == CFStringGetTypeID()) {
        NSString *password = [(__bridge NSString *)value copy];
        CFRelease(value);
        if (password.length > 0) return password;
    } else if (value) {
        CFRelease(value);
    }
    return @"alpine";
}

static NSString *MCPBootstrapArgumentPath(NSString *path);

static NSString *MCPDpkgBootstrapPathForDeb(NSString *path) {
    if (!path.isAbsolutePath || ![path.pathExtension.lowercaseString isEqualToString:@"deb"]) {
        return path ?: @"";
    }

#ifdef MCP_ROOTHIDE
    NSFileManager *fm = [NSFileManager defaultManager];

    NSString *systemPathFromBootstrap = jbroot(path);
    if (systemPathFromBootstrap.length > 0 &&
        [fm fileExistsAtPath:systemPathFromBootstrap]) {
        return path;
    }

    if ([fm fileExistsAtPath:path]) {
        NSString *bootstrapPath = rootfs(path);
        return bootstrapPath.length > 0 ? bootstrapPath : path;
    }

    NSString *bootstrapPath = rootfs(path);
    return bootstrapPath.length > 0 ? bootstrapPath : path;
#else
    return path;
#endif
}

static NSArray<NSString *> *MCPDpkgBootstrapArguments(NSArray<NSString *> *dpkgArguments) {
    NSMutableArray<NSString *> *convertedArguments = [NSMutableArray arrayWithCapacity:dpkgArguments.count];
    for (NSString *argument in dpkgArguments) {
        NSString *converted = argument;
        if (argument.isAbsolutePath &&
            [argument.pathExtension.lowercaseString isEqualToString:@"deb"]) {
            converted = MCPDpkgBootstrapPathForDeb(argument);
        }
        [convertedArguments addObject:converted ?: @""];
    }
    return convertedArguments;
}

static BOOL MCPDpkgOutputLooksLikeHelperPrivilegeFailure(NSString *output, int exitCode) {
    if (exitCode == 111) return YES;
    if (![output isKindOfClass:[NSString class]] || output.length == 0) return NO;
    return [output rangeOfString:@"setgid(0) failed"].location != NSNotFound ||
           [output rangeOfString:@"setuid(0) failed"].location != NSNotFound ||
           [output rangeOfString:@"dpkg package does not exist:"].location != NSNotFound;
}

static BOOL MCPRunDpkgWithPrivileges(NSArray<NSString *> *dpkgArguments,
                                     NSTimeInterval timeout,
                                     NSUInteger maxOutputBytes,
                                     NSString **output,
                                     int *exitCode,
                                     NSString **errorMessage) {
    if (output) *output = @"";
    if (exitCode) *exitCode = -1;
    if (errorMessage) *errorMessage = nil;

    NSArray<NSString *> *bootstrapDpkgArguments = MCPDpkgBootstrapArguments(dpkgArguments);
    NSMutableArray<NSString *> *helperArguments = [NSMutableArray arrayWithObject:@"/usr/bin/dpkg"];
    if (bootstrapDpkgArguments.count > 0) {
        [helperArguments addObjectsFromArray:bootstrapDpkgArguments];
    }

    NSFileManager *fm = [NSFileManager defaultManager];
    NSString *mcpRootPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-root");
    NSString *helperOutput = nil;
    NSString *helperError = nil;
    int helperExitCode = -1;
    BOOL helperFinished = NO;

    if ([fm isExecutableFileAtPath:mcpRootPath]) {
        helperFinished = MCPRunProcess(mcpRootPath,
                                       helperArguments,
                                       MCPJailbreakEnvironment(),
                                       timeout,
                                       maxOutputBytes,
                                       &helperOutput,
                                       &helperExitCode,
                                       &helperError);
        if (helperFinished && helperExitCode == 0) {
            if (output) *output = helperOutput;
            if (exitCode) *exitCode = helperExitCode;
            if (errorMessage) *errorMessage = helperError;
            return YES;
        }

        if (!MCPDpkgOutputLooksLikeHelperPrivilegeFailure(helperOutput, helperExitCode)) {
            if (output) *output = helperOutput;
            if (exitCode) *exitCode = helperExitCode;
            if (errorMessage) *errorMessage = helperError;
            return helperFinished;
        }

        APP_LOG(@"mcp-root dpkg privilege failed, trying sudo fallback (exit=%d outputBytes=%lu)",
                helperExitCode,
                (unsigned long)MCPAppLogUTF8Length(helperOutput));
    }

    NSString *sudoPath = MCPResolvedJailbreakPath(@"/usr/bin/sudo");
    NSString *shellPath = MCPResolvedJailbreakPath(@"/bin/sh");
    NSString *dpkgPath = MCPResolvedJailbreakPath(@"/usr/bin/dpkg");
    if (![fm isExecutableFileAtPath:sudoPath]) {
        if (output) *output = helperOutput ?: @"";
        if (exitCode) *exitCode = helperExitCode;
        if (errorMessage) {
            *errorMessage = helperError ?: @"mcp-root privilege escalation failed and sudo is not available";
        }
        return helperFinished;
    }
    if (![fm isExecutableFileAtPath:shellPath]) {
        shellPath = @"/bin/sh";
    }
    if (![fm isExecutableFileAtPath:dpkgPath]) {
        if (output) *output = helperOutput ?: @"";
        if (exitCode) *exitCode = helperExitCode;
        if (errorMessage) *errorMessage = @"dpkg executable not found";
        return NO;
    }

    NSMutableArray<NSString *> *parts = [NSMutableArray arrayWithObjects:
                                         @"printf '%s\\n'",
                                         MCPShellQuote(MCPConfiguredSudoPassword()),
                                         @"|",
                                         MCPShellQuote(sudoPath),
                                         @"-k",
                                         @"-S",
                                         @"-p",
                                         @"''",
                                         MCPShellQuote(dpkgPath),
                                         nil];
    for (NSString *argument in bootstrapDpkgArguments) {
        [parts addObject:MCPShellQuote(argument)];
    }
    NSString *command = [parts componentsJoinedByString:@" "];

    NSString *sudoOutput = nil;
    NSString *sudoError = nil;
    int sudoExitCode = -1;
    BOOL sudoFinished = MCPRunProcess(shellPath,
                                      @[@"-lc", command],
                                      MCPJailbreakEnvironment(),
                                      timeout,
                                      maxOutputBytes,
                                      &sudoOutput,
                                      &sudoExitCode,
                                      &sudoError);
    if (output) *output = sudoOutput;
    if (exitCode) *exitCode = sudoExitCode;
    if (errorMessage) {
        if (sudoError.length > 0) {
            *errorMessage = sudoError;
        } else if (!sudoFinished && helperOutput.length > 0) {
            *errorMessage = [NSString stringWithFormat:@"mcp-root failed: %@", helperOutput];
        }
    }
    return sudoFinished;
}

static BOOL MCPWriteFileToShellPath(NSString *sourcePath, NSString *destPath, NSString **output, NSString **errorMessage) {
    if (output) *output = @"";
    if (errorMessage) *errorMessage = nil;
    if (!sourcePath.length || !destPath.length) {
        if (errorMessage) *errorMessage = @"Missing source or destination path";
        return NO;
    }

    int sourceFD = open(sourcePath.fileSystemRepresentation, O_RDONLY);
    if (sourceFD < 0) {
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"Failed to open source DEB: %s", strerror(errno)];
        return NO;
    }

    NSString *shellPath = MCPResolvedJailbreakPath(@"/bin/sh");
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:shellPath]) {
        shellPath = @"/bin/sh";
    }

    NSString *parent = destPath.stringByDeletingLastPathComponent;
    NSString *command = [NSString stringWithFormat:@"mkdir -p %@ && cat > %@ && chmod 0644 %@",
                         MCPShellQuote(parent),
                         MCPShellQuote(destPath),
                         MCPShellQuote(destPath)];

    int stdinPipe[2] = {-1, -1};
    int outputPipe[2] = {-1, -1};
    if (pipe(stdinPipe) != 0) {
        close(sourceFD);
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"stdin pipe failed: %s", strerror(errno)];
        return NO;
    }
    if (pipe(outputPipe) != 0) {
        close(sourceFD);
        close(stdinPipe[0]);
        close(stdinPipe[1]);
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"output pipe failed: %s", strerror(errno)];
        return NO;
    }

    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, stdinPipe[0], STDIN_FILENO);
    posix_spawn_file_actions_adddup2(&actions, outputPipe[1], STDOUT_FILENO);
    posix_spawn_file_actions_adddup2(&actions, outputPipe[1], STDERR_FILENO);
    posix_spawn_file_actions_addclose(&actions, stdinPipe[1]);
    posix_spawn_file_actions_addclose(&actions, outputPipe[0]);

    const char *shell = shellPath.fileSystemRepresentation;
    char *const argv[] = {
        (char *)(shellPath.lastPathComponent.UTF8String ?: "sh"),
        "-lc",
        (char *)(command.UTF8String ?: ""),
        NULL
    };

    pid_t pid = 0;
    int spawnStatus = posix_spawn(&pid, shell, &actions, NULL, argv, environ);
    posix_spawn_file_actions_destroy(&actions);
    close(stdinPipe[0]);
    close(outputPipe[1]);

    if (spawnStatus != 0) {
        close(sourceFD);
        close(stdinPipe[1]);
        close(outputPipe[0]);
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"posix_spawn shell failed: %s", strerror(spawnStatus)];
        return NO;
    }

    BOOL writeFailed = NO;
    int savedErrno = 0;
    uint8_t fileBuffer[65536];
    while (1) {
        ssize_t bytesRead = read(sourceFD, fileBuffer, sizeof(fileBuffer));
        if (bytesRead < 0 && errno == EINTR) continue;
        if (bytesRead < 0) {
            writeFailed = YES;
            savedErrno = errno;
            break;
        }
        if (bytesRead == 0) break;

        uint8_t *cursor = fileBuffer;
        ssize_t remaining = bytesRead;
        while (remaining > 0) {
            ssize_t written = write(stdinPipe[1], cursor, (size_t)remaining);
            if (written < 0 && errno == EINTR) continue;
            if (written <= 0) {
                writeFailed = YES;
                savedErrno = errno;
                remaining = 0;
                break;
            }
            cursor += written;
            remaining -= written;
        }
        if (writeFailed) break;
    }
    close(sourceFD);
    close(stdinPipe[1]);

    NSMutableData *captured = [NSMutableData data];
    char buffer[4096];
    ssize_t n = 0;
    while ((n = read(outputPipe[0], buffer, sizeof(buffer))) > 0) {
        if (captured.length < 64 * 1024) {
            NSUInteger allowed = MIN((NSUInteger)n, (64 * 1024) - captured.length);
            [captured appendBytes:buffer length:allowed];
        }
    }
    close(outputPipe[0]);

    int status = 0;
    int waitStatus = waitpid(pid, &status, 0);
    NSString *capturedOutput = [[NSString alloc] initWithData:captured encoding:NSUTF8StringEncoding] ?: @"";
    if (output) *output = capturedOutput;

    if (writeFailed) {
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"Failed to stream staged DEB: %s %@", strerror(savedErrno), MCPAppLogRedactedText(capturedOutput)];
        return NO;
    }
    if (waitStatus < 0) {
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"waitpid failed: %s", strerror(errno)];
        return NO;
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        if (errorMessage) *errorMessage = [NSString stringWithFormat:@"staging shell failed: %@", MCPAppLogRedactedText(capturedOutput)];
        return NO;
    }
    return YES;
}

static void MCPRemoveShellPath(NSString *path) {
    if (!path.length) return;
    NSString *shellPath = MCPResolvedJailbreakPath(@"/bin/sh");
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:shellPath]) {
        shellPath = @"/bin/sh";
    }
    NSString *command = [NSString stringWithFormat:@"rm -f %@", MCPShellQuote(path)];
    NSString *output = nil;
    NSString *runError = nil;
    int exitCode = -1;
    MCPRunProcess(shellPath,
                  @[@"-lc", command],
                  MCPJailbreakEnvironment(),
                  10,
                  64 * 1024,
                  &output,
                  &exitCode,
                  &runError);
}

static NSString *MCPStageDebForDpkg(NSString *debPath, NSString **stagedPath, NSString **stageError) {
    if (stagedPath) *stagedPath = nil;
    if (stageError) *stageError = nil;

    if (!debPath.length) {
        if (stageError) *stageError = @"Empty DEB path";
        return nil;
    }

    NSFileManager *fm = [NSFileManager defaultManager];
    if (![fm fileExistsAtPath:debPath]) {
        if (stageError) *stageError = [NSString stringWithFormat:@"DEB file not found: %@", debPath];
        return nil;
    }

    NSString *fileName = [NSString stringWithFormat:@"ios-mcp-dpkg-%@.deb", [[NSUUID UUID] UUIDString]];
    NSString *visiblePath = [@"/var/tmp" stringByAppendingPathComponent:fileName];
    NSString *stageOutput = nil;
    NSString *writeError = nil;
    if (!MCPWriteFileToShellPath(debPath, visiblePath, &stageOutput, &writeError)) {
        if (stageError) *stageError = writeError ?: stageOutput ?: @"Failed to stage DEB for dpkg";
        return nil;
    }

    if (stagedPath) *stagedPath = visiblePath;
    return visiblePath;
}

static NSString *MCPBootstrapArgumentPath(NSString *path) {
    if (path.length == 0) return path ?: @"";
    NSString *converted = rootfs(path);
    return converted.length > 0 ? converted : path;
}

static NSString *MCPFrontmostBundleIdentifier(void) {
    NSDictionary *info = [[AccessibilityManager sharedInstance] frontmostApplicationInfo];
    NSString *bundleId = [info[@"bundleId"] isKindOfClass:[NSString class]] ? info[@"bundleId"] : nil;
    return bundleId ?: @"";
}

static NSDictionary *MCPFrontmostApplicationInfo(void) {
    NSDictionary *info = [[AccessibilityManager sharedInstance] frontmostApplicationInfo];
    return [info isKindOfClass:[NSDictionary class]] ? info : @{};
}

static NSString *MCPNormalizedInstalledAppType(id proxy, NSString *bundleId, NSString *rawType) {
    if ([rawType isEqualToString:@"User"]) return @"User";

    NSString *bundlePath = nil;
    if ([proxy respondsToSelector:@selector(bundleURL)]) {
        id bundleURL = MCPAppMsgSendObject(proxy, @selector(bundleURL));
        if ([bundleURL isKindOfClass:[NSURL class]]) {
            bundlePath = [((NSURL *)bundleURL).path stringByStandardizingPath];
        }
    }

    if ([bundlePath containsString:@"/Containers/Bundle/Application/"]) {
        return @"User";
    }

    if (bundleId.length > 0 && ![bundleId hasPrefix:@"com.apple."]) {
        return @"User";
    }

    if ([rawType isEqualToString:@"Internal"]) return @"System";
    return rawType.length > 0 ? rawType : @"System";
}

static BOOL MCPWaitForFrontmostApp(NSString *expectedBundleId,
                                   NSTimeInterval timeout,
                                   NSDictionary **outFrontmostInfo) {
    if (outFrontmostInfo) *outFrontmostInfo = @{};
    if (expectedBundleId.length == 0) return NO;

    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:MAX(timeout, 0.1)];
    NSDictionary *lastInfo = @{};

    while ([deadline timeIntervalSinceNow] > 0) {
        lastInfo = MCPFrontmostApplicationInfo();
        NSString *frontmostBundleId = [lastInfo[@"bundleId"] isKindOfClass:[NSString class]] ? lastInfo[@"bundleId"] : nil;
        if ([frontmostBundleId isEqualToString:expectedBundleId]) {
            if (outFrontmostInfo) *outFrontmostInfo = lastInfo;
            return YES;
        }

        [NSThread sleepForTimeInterval:0.1];
    }

    lastInfo = MCPFrontmostApplicationInfo();
    if (outFrontmostInfo) *outFrontmostInfo = lastInfo;
    return NO;
}

static BOOL MCPWaitForURLOpenVerification(NSURL *url, NSString *previousBundleId, NSTimeInterval timeout) {
    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:MAX(timeout, 0.1)];
    BOOL settingsURL = MCPURLUsesSettingsScheme(url);

    while ([deadline timeIntervalSinceNow] > 0) {
        [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];

        NSString *bundleId = MCPFrontmostBundleIdentifier();
        if (bundleId.length == 0) continue;

        if (settingsURL) {
            if ([bundleId isEqualToString:@"com.apple.Preferences"]) {
                return YES;
            }
            continue;
        }

        if (previousBundleId.length > 0) {
            if (![bundleId isEqualToString:previousBundleId]) {
                return YES;
            }
        } else if (![bundleId isEqualToString:@"com.apple.springboard"]) {
            return YES;
        }
    }

    return NO;
}

@implementation AppManager

+ (instancetype)sharedInstance {
    static AppManager *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[AppManager alloc] init];
    });
    return instance;
}

#pragma mark - Launch

- (BOOL)launchApp:(NSString *)bundleId error:(NSString **)error {
    if (!bundleId.length) {
        if (error) *error = @"Empty bundle ID";
        return NO;
    }

    __block BOOL ok = NO;
    __block NSString *errMsg = nil;

    // Prefer LaunchServices from the current client worker. Calling the legacy
    // SBUIController activation path synchronously on SpringBoard's main queue
    // can block that queue for several seconds on some iOS versions.
    Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
    if (LSWorkspaceClass) {
        @try {
            SEL defaultWorkspaceSel = @selector(defaultWorkspace);
            if (![LSWorkspaceClass respondsToSelector:defaultWorkspaceSel]) {
                errMsg = @"LSApplicationWorkspace defaultWorkspace is unavailable";
            } else {
                id workspace = ((id (*)(id, SEL))objc_msgSend)((id)LSWorkspaceClass, defaultWorkspaceSel);
                SEL openSel = @selector(openApplicationWithBundleID:);
                if (!workspace) {
                    errMsg = @"LSApplicationWorkspace defaultWorkspace returned nil";
                } else if (![workspace respondsToSelector:openSel]) {
                    errMsg = @"LSApplicationWorkspace openApplicationWithBundleID: is unavailable";
                } else {
                    CFAbsoluteTime startedAt = CFAbsoluteTimeGetCurrent();
                    BOOL opened = ((BOOL (*)(id, SEL, NSString *))objc_msgSend)(workspace, openSel, bundleId);
                    APP_LOG(@"LaunchServices launch request for %@ returned %@ in %.0fms",
                            bundleId,
                            opened ? @"YES" : @"NO",
                            (CFAbsoluteTimeGetCurrent() - startedAt) * 1000.0);
                    if (opened) {
                        ok = YES;
                    } else {
                        errMsg = @"LSApplicationWorkspace openApplicationWithBundleID: returned NO";
                    }
                }
            }
        } @catch (NSException *exception) {
            errMsg = [NSString stringWithFormat:@"LSApplicationWorkspace launch failed: %@",
                      exception.reason ?: exception.name ?: @"unknown exception"];
            APP_LOG(@"LaunchServices launch exception for %@: %@ - %@",
                    bundleId,
                    exception.name ?: @"unknown",
                    exception.reason ?: @"-");
        }
    } else {
        errMsg = @"LSApplicationWorkspace is unavailable";
    }

    // Keep the SpringBoard-private path only as a compatibility fallback.
    dispatch_block_t fallbackBlock = ^{
        Class SBAppCtrl = objc_getClass("SBApplicationController");
        if (SBAppCtrl) {
            id appCtrl = [SBAppCtrl performSelector:@selector(sharedInstance)];
            id sbApp = [appCtrl performSelector:@selector(applicationWithBundleIdentifier:) withObject:bundleId];
            if (sbApp) {
                Class SBUICtrlClass = objc_getClass("SBUIController");
                if (SBUICtrlClass) {
                    id ctrl = [SBUICtrlClass performSelector:@selector(sharedInstance)];
                    SEL activateSel = @selector(activateApplication:);
                    if ([ctrl respondsToSelector:activateSel]) {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
                        [ctrl performSelector:activateSel withObject:sbApp];
#pragma clang diagnostic pop
                        APP_LOG(@"Launched app via activateApplication: %@", bundleId);
                        ok = YES;
                        return;
                    }
                }
            }
        }
        NSString *primaryError = errMsg.length > 0 ? errMsg : @"LaunchServices request failed";
        errMsg = [NSString stringWithFormat:@"%@; SBUIController fallback unavailable for %@",
                  primaryError,
                  bundleId];
    };

    if (!ok) {
        if ([NSThread isMainThread]) {
            fallbackBlock();
        } else {
            dispatch_sync(dispatch_get_main_queue(), fallbackBlock);
        }
    }

    if (!ok) {
        if (error) *error = errMsg;
        return NO;
    }

    NSDictionary *frontmostInfo = nil;
    if (MCPWaitForFrontmostApp(bundleId, 5.0, &frontmostInfo)) {
        APP_LOG(@"Launch confirmed in foreground: %@", bundleId);
        return YES;
    }

    NSString *frontmostBundleId = [frontmostInfo[@"bundleId"] isKindOfClass:[NSString class]] ? frontmostInfo[@"bundleId"] : nil;
    NSString *frontmostName = [frontmostInfo[@"name"] isKindOfClass:[NSString class]] ? frontmostInfo[@"name"] : nil;
    if (error) {
        if (frontmostBundleId.length > 0) {
            *error = [NSString stringWithFormat:@"Launch request sent for %@, but frontmost app is still %@%@",
                      bundleId,
                      frontmostBundleId,
                      frontmostName.length > 0 ? [NSString stringWithFormat:@" (%@)", frontmostName] : @""];
        } else {
            *error = [NSString stringWithFormat:@"Launch request sent for %@, but it did not become frontmost within 5 seconds", bundleId];
        }
    }
    APP_LOG(@"Launch not confirmed for %@, currentFrontmostBundleId=%@", bundleId, frontmostBundleId ?: @"-");
    return NO;
}

#pragma mark - Kill

- (BOOL)killApp:(NSString *)bundleId error:(NSString **)error {
    if (!bundleId.length) {
        if (error) *error = @"Empty bundle ID";
        return NO;
    }

    __block BOOL ok = NO;
    __block NSString *errMsg = nil;

    dispatch_block_t block = ^{
        Class FBSClass = objc_getClass("FBSSystemService");
        if (!FBSClass) {
            errMsg = @"FBSSystemService not available";
            return;
        }

        id service = [FBSClass performSelector:@selector(sharedService)];

        SEL termSel = @selector(terminateApplication:forReason:andReport:withDescription:);
        if ([service respondsToSelector:termSel]) {
            NSMethodSignature *sig = [service methodSignatureForSelector:termSel];
            NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
            inv.target = service;
            inv.selector = termSel;
            NSString *bid = bundleId;
            [inv setArgument:&bid atIndex:2];
            int reason = 1;
            [inv setArgument:&reason atIndex:3];
            BOOL report = NO;
            [inv setArgument:&report atIndex:4];
            NSString *desc = @"Terminated via ios-mcp";
            [inv setArgument:&desc atIndex:5];
            [inv invoke];

            APP_LOG(@"Killed app: %@", bundleId);
            ok = YES;
        } else {
            errMsg = @"terminateApplication: selector not available";
        }
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }

    if (error) *error = errMsg;
    return ok;
}

#pragma mark - List Installed

- (NSArray<NSDictionary *> *)listInstalledApps:(NSString *)type {
    __block NSArray *result = @[];

    dispatch_block_t block = ^{
        Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
        if (!LSWorkspaceClass) return;

        id workspace = [LSWorkspaceClass performSelector:@selector(defaultWorkspace)];
        NSArray *allApps = [workspace performSelector:@selector(allInstalledApplications)];

        NSMutableArray *list = [NSMutableArray array];
        for (id proxy in allApps) {
            NSString *appId   = [proxy performSelector:@selector(applicationIdentifier)];
            NSString *name    = [proxy performSelector:@selector(localizedName)];
            NSString *rawType = [proxy performSelector:@selector(applicationType)];

            if (!appId) continue;

            NSString *appType = MCPNormalizedInstalledAppType(proxy, appId, rawType);

            // Filter by type
            if ([type isEqualToString:@"user"] && ![appType isEqualToString:@"User"]) continue;
            if ([type isEqualToString:@"system"] && [appType isEqualToString:@"User"]) continue;

            [list addObject:@{
                @"bundleId": appId ?: @"",
                @"name":     name ?: @"",
                @"type":     appType ?: @""
            }];
        }

        result = [list copy];
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }
    return result;
}

#pragma mark - List Running

- (NSArray<NSDictionary *> *)listRunningApps {
    __block NSArray *result = @[];

    dispatch_block_t block = ^{
        Class SBAppCtrl = objc_getClass("SBApplicationController");
        if (!SBAppCtrl) return;

        id controller = [SBAppCtrl performSelector:@selector(sharedInstance)];

        NSArray *running = nil;
        if ([controller respondsToSelector:@selector(runningApplications)]) {
            running = [controller performSelector:@selector(runningApplications)];
        } else {
            // Fallback: iterate all and check isRunning
            NSArray *all = [controller performSelector:@selector(allApplications)];
            NSMutableArray *filtered = [NSMutableArray array];
            for (id app in all) {
                BOOL isRunning = NO;
                NSMethodSignature *sig = [app methodSignatureForSelector:@selector(isRunning)];
                if (sig) {
                    NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
                    inv.target = app;
                    inv.selector = @selector(isRunning);
                    [inv invoke];
                    [inv getReturnValue:&isRunning];
                }
                if (isRunning) [filtered addObject:app];
            }
            running = filtered;
        }

        NSMutableArray *list = [NSMutableArray array];
        for (id app in running) {
            NSString *bid  = [app performSelector:@selector(bundleIdentifier)];
            NSString *name = [app performSelector:@selector(displayName)];
            if (!bid) continue;
            [list addObject:@{
                @"bundleId": bid ?: @"",
                @"name":     name ?: @""
            }];
        }

        result = [list copy];
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }
    return result;
}

#pragma mark - Frontmost App

- (NSDictionary *)getFrontmostApp {
    NSDictionary *resolved = [[AccessibilityManager sharedInstance] frontmostApplicationInfo];
    if ([resolved isKindOfClass:[NSDictionary class]] && resolved.count > 0) {
        return resolved;
    }

    __block NSDictionary *result = @{};

    dispatch_block_t block = ^{
        id frontApp = nil;
        Class springBoardClass = objc_getClass("SpringBoard");
        SEL sharedApplicationSel = @selector(sharedApplication);
        SEL frontmostSel = @selector(_accessibilityFrontMostApplication);
        if (springBoardClass && [springBoardClass respondsToSelector:sharedApplicationSel]) {
            id springBoard = MCPAppMsgSendObject((id)springBoardClass, sharedApplicationSel);
            if (springBoard && [springBoard respondsToSelector:frontmostSel]) {
                frontApp = MCPAppMsgSendObject(springBoard, frontmostSel);
            }
        }

        if (frontApp && [frontApp respondsToSelector:@selector(bundleIdentifier)]) {
            NSString *bid  = [frontApp performSelector:@selector(bundleIdentifier)];
            NSString *name = [frontApp performSelector:@selector(displayName)];
            NSMutableDictionary *info = [NSMutableDictionary dictionary];
            if (bid.length > 0) info[@"bundleId"] = bid;
            if (name.length > 0) info[@"name"] = name;
            result = info;
        } else {
            result = @{@"bundleId": @"com.apple.springboard", @"name": @"SpringBoard"};
        }
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }
    return result;
}

#pragma mark - Open URL

- (BOOL)openURL:(NSString *)urlString error:(NSString **)error {
    if (!urlString.length) {
        if (error) *error = @"Empty URL";
        return NO;
    }

    NSURL *url = [NSURL URLWithString:urlString];
    if (!url) {
        if (error) *error = [NSString stringWithFormat:@"Invalid URL: %@", urlString];
        return NO;
    }

    __block BOOL ok = NO;
    __block BOOL attemptedOpen = NO;
    __block NSString *errMsg = nil;
    __block NSString *previousBundleId = @"";

    dispatch_block_t block = ^{
        previousBundleId = MCPFrontmostBundleIdentifier();
        UIApplication *app = [UIApplication sharedApplication];

        // Method 1: UIApplication openURL:options:completionHandler:
        if ([app respondsToSelector:@selector(openURL:options:completionHandler:)]) {
            attemptedOpen = YES;

            __block BOOL completionCalled = NO;
            [app openURL:url options:@{} completionHandler:^(BOOL success) {
                completionCalled = YES;
                ok = success;
                if (!success) errMsg = @"openURL returned NO";
            }];

            NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:1.5];
            while (!completionCalled && [deadline timeIntervalSinceNow] > 0) {
                [[NSRunLoop currentRunLoop] runMode:NSDefaultRunLoopMode beforeDate:[NSDate dateWithTimeIntervalSinceNow:0.05]];
            }

            if (!completionCalled && !ok && !errMsg) {
                errMsg = @"openURL completion timed out";
            }
            if (ok) return;
        }

        // Method 2: legacy UIApplication openURL:
        SEL legacyOpenSel = @selector(openURL:);
        if ([app respondsToSelector:legacyOpenSel]) {
            attemptedOpen = YES;
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
            BOOL opened = ((BOOL (*)(id, SEL, NSURL *))objc_msgSend)(app, legacyOpenSel, url);
#pragma clang diagnostic pop
            if (opened) {
                APP_LOG(@"Opened URL via UIApplication: %@", MCPAppLogSafeURLString(urlString));
                ok = YES;
                errMsg = nil;
                return;
            }
            if (!errMsg) {
                errMsg = @"openURL returned NO";
            }
        }

        // Method 3: LSApplicationWorkspace openSensitiveURL:withOptions:
        Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
        if (LSWorkspaceClass) {
            id workspace = [LSWorkspaceClass performSelector:@selector(defaultWorkspace)];
            SEL openSel = @selector(openSensitiveURL:withOptions:);
            if ([workspace respondsToSelector:openSel]) {
                attemptedOpen = YES;
                NSMethodSignature *sig = [workspace methodSignatureForSelector:openSel];
                NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
                inv.target = workspace;
                inv.selector = openSel;
                NSURL *u = url;
                [inv setArgument:&u atIndex:2];
                NSDictionary *opts = @{};
                [inv setArgument:&opts atIndex:3];
                [inv invoke];

                BOOL result = NO;
                if (strcmp(sig.methodReturnType, @encode(BOOL)) == 0) {
                    [inv getReturnValue:&result];
                } else {
                    result = YES;
                }

                if (result) {
                    APP_LOG(@"Opened URL via LSApplicationWorkspace: %@", MCPAppLogSafeURLString(urlString));
                    ok = YES;
                    errMsg = nil;
                    return;
                }
                if (!errMsg) {
                    errMsg = @"openSensitiveURL returned NO";
                }
            }
        }

        if (!ok && attemptedOpen && MCPWaitForURLOpenVerification(url, previousBundleId, 1.0)) {
            APP_LOG(@"Verified URL open after dispatch: %@", MCPAppLogSafeURLString(urlString));
            ok = YES;
            errMsg = nil;
            return;
        }

        if (!ok && !errMsg) {
            errMsg = @"No URL open method available";
        }
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }

    // Some private schemes (notably prefs:/app-prefs:) can report NO from
    // UIKit/LS even though SpringBoard performs the handoff shortly after the
    // call returns. Verify the visible foreground transition once more outside
    // the main-thread open dispatch before reporting failure.
    if (!ok && attemptedOpen && MCPWaitForURLOpenVerification(url, previousBundleId, 2.0)) {
        APP_LOG(@"Verified URL open after main dispatch returned: %@", MCPAppLogSafeURLString(urlString));
        ok = YES;
        errMsg = nil;
    }

    if (error) *error = errMsg;
    return ok;
}

#pragma mark - Fakesign

- (NSString *)appBundlePathForBundleId:(NSString *)bundleId mainExecutablePath:(NSString **)mainExecutablePath {
    if (mainExecutablePath) *mainExecutablePath = nil;
    if (!bundleId.length) return nil;

    NSFileManager *fm = [NSFileManager defaultManager];
    NSString *containerBase = @"/var/containers/Bundle/Application";
    NSArray *uuids = [fm contentsOfDirectoryAtPath:containerBase error:nil];

    NSString *bestAppPath = nil;
    NSString *bestBinaryPath = nil;
    NSDate *newestDate = nil;

    for (NSString *uuid in uuids) {
        NSString *uuidDir = [containerBase stringByAppendingPathComponent:uuid];
        NSArray *contents = [fm contentsOfDirectoryAtPath:uuidDir error:nil];
        for (NSString *item in contents) {
            if (![item.pathExtension.lowercaseString isEqualToString:@"app"]) continue;

            NSString *appDir = [uuidDir stringByAppendingPathComponent:item];
            NSString *plistPath = [appDir stringByAppendingPathComponent:@"Info.plist"];
            NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:plistPath];
            if (![bundleId isEqualToString:info[@"CFBundleIdentifier"]]) continue;

            NSString *executable = info[@"CFBundleExecutable"];
            if (!executable.length) continue;

            NSString *binaryPath = [appDir stringByAppendingPathComponent:executable];
            NSDictionary *attrs = [fm attributesOfItemAtPath:binaryPath error:nil];
            NSDate *modDate = attrs[NSFileModificationDate];
            if (!modDate) modDate = [NSDate distantPast];

            if (!newestDate || [modDate compare:newestDate] == NSOrderedDescending) {
                newestDate = modDate;
                bestAppPath = appDir;
                bestBinaryPath = binaryPath;
            }
        }
    }

    if (mainExecutablePath) *mainExecutablePath = bestBinaryPath;
    return bestAppPath;
}

- (NSString *)waitForAppBundlePathForBundleId:(NSString *)bundleId mainExecutablePath:(NSString **)mainExecutablePath timeout:(NSTimeInterval)timeout {
    if (mainExecutablePath) *mainExecutablePath = nil;
    if (!bundleId.length) return nil;

    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:MAX(timeout, 0.1)];
    while ([deadline timeIntervalSinceNow] > 0) {
        NSString *resolvedExecutable = nil;
        NSString *resolvedBundlePath = [self appBundlePathForBundleId:bundleId mainExecutablePath:&resolvedExecutable];
        if (resolvedBundlePath.length > 0 && resolvedExecutable.length > 0) {
            if (mainExecutablePath) *mainExecutablePath = resolvedExecutable;
            return resolvedBundlePath;
        }
        [NSThread sleepForTimeInterval:0.25];
    }

    return nil;
}

- (NSString *)newestInstalledAppBundlePathAfterDate:(NSDate *)afterDate
                                   resolvedBundleId:(NSString **)resolvedBundleId
                                 mainExecutablePath:(NSString **)mainExecutablePath {
    if (resolvedBundleId) *resolvedBundleId = nil;
    if (mainExecutablePath) *mainExecutablePath = nil;

    NSString *basePath = @"/var/containers/Bundle/Application";
    NSFileManager *fm = [NSFileManager defaultManager];
    NSArray<NSString *> *uuidDirs = [fm contentsOfDirectoryAtPath:basePath error:nil];
    if (uuidDirs.count == 0) return nil;

    NSString *bestAppPath = nil;
    NSString *bestExecutablePath = nil;
    NSString *bestBundleId = nil;
    NSDate *bestDate = nil;

    for (NSString *uuid in uuidDirs) {
        NSString *uuidDir = [basePath stringByAppendingPathComponent:uuid];
        NSDictionary *uuidAttributes = [fm attributesOfItemAtPath:uuidDir error:nil];
        NSDate *uuidDate = MCPBestFileDate(uuidAttributes);

        NSArray<NSString *> *items = [fm contentsOfDirectoryAtPath:uuidDir error:nil];
        for (NSString *item in items) {
            if (![item.pathExtension.lowercaseString isEqualToString:@"app"]) continue;

            NSString *appDir = [uuidDir stringByAppendingPathComponent:item];
            NSDictionary *appAttributes = [fm attributesOfItemAtPath:appDir error:nil];
            NSDate *appDate = MCPBestFileDate(appAttributes);
            NSDate *candidateDate = appDate ?: uuidDate;
            if (uuidDate && candidateDate && [uuidDate compare:candidateDate] == NSOrderedDescending) {
                candidateDate = uuidDate;
            }
            if (afterDate && candidateDate && [candidateDate compare:afterDate] == NSOrderedAscending) {
                continue;
            }

            NSString *plistPath = [appDir stringByAppendingPathComponent:@"Info.plist"];
            NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:plistPath];
            NSString *bundleId = [info[@"CFBundleIdentifier"] isKindOfClass:[NSString class]] ? info[@"CFBundleIdentifier"] : nil;
            NSString *executable = [info[@"CFBundleExecutable"] isKindOfClass:[NSString class]] ? info[@"CFBundleExecutable"] : nil;
            if (!bundleId.length || !executable.length) continue;

            NSString *binaryPath = [appDir stringByAppendingPathComponent:executable];
            if (![fm fileExistsAtPath:binaryPath]) continue;

            if (!bestDate || (candidateDate && [candidateDate compare:bestDate] == NSOrderedDescending)) {
                bestDate = candidateDate;
                bestAppPath = appDir;
                bestExecutablePath = binaryPath;
                bestBundleId = bundleId;
            }
        }
    }

    if (resolvedBundleId) *resolvedBundleId = bestBundleId;
    if (mainExecutablePath) *mainExecutablePath = bestExecutablePath;
    return bestAppPath;
}

- (NSString *)waitForInstalledAppBundlePathForBundleId:(NSString *)bundleId
                                         installedAfter:(NSDate *)installedAfter
                                      resolvedBundleId:(NSString **)resolvedBundleId
                                    mainExecutablePath:(NSString **)mainExecutablePath
                                               timeout:(NSTimeInterval)timeout {
    if (resolvedBundleId) *resolvedBundleId = bundleId;
    if (mainExecutablePath) *mainExecutablePath = nil;

    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:MAX(timeout, 0.1)];
    NSString *stablePath = nil;
    NSString *stableExecutable = nil;
    NSString *stableBundleId = bundleId;
    NSDate *stableSince = nil;

    while ([deadline timeIntervalSinceNow] > 0) {
        NSString *candidateBundleId = bundleId;
        NSString *candidateExecutable = nil;
        NSString *candidatePath = nil;

        if (bundleId.length > 0) {
            candidatePath = [self appBundlePathForBundleId:bundleId mainExecutablePath:&candidateExecutable];
        }
        if (!candidatePath.length || !candidateExecutable.length) {
            candidatePath = [self newestInstalledAppBundlePathAfterDate:installedAfter
                                                       resolvedBundleId:&candidateBundleId
                                                     mainExecutablePath:&candidateExecutable];
        }

        if (candidatePath.length > 0 && candidateExecutable.length > 0) {
            NSDate *now = [NSDate date];
            if ([candidatePath isEqualToString:stablePath] && [candidateExecutable isEqualToString:stableExecutable]) {
                if (stableSince && [now timeIntervalSinceDate:stableSince] >= 1.0) {
                    if (resolvedBundleId) *resolvedBundleId = candidateBundleId.length ? candidateBundleId : stableBundleId;
                    if (mainExecutablePath) *mainExecutablePath = candidateExecutable;
                    return candidatePath;
                }
            } else {
                stablePath = candidatePath;
                stableExecutable = candidateExecutable;
                stableBundleId = candidateBundleId;
                stableSince = now;
            }
        }

        [NSThread sleepForTimeInterval:0.25];
    }

    return nil;
}

- (NSString *)bundleExecutablePathForBundlePath:(NSString *)bundlePath {
    if (!bundlePath.length) return nil;

    NSFileManager *fm = [NSFileManager defaultManager];
    BOOL isDirectory = NO;
    if (![fm fileExistsAtPath:bundlePath isDirectory:&isDirectory] || !isDirectory) return nil;

    NSString *plistPath = [bundlePath stringByAppendingPathComponent:@"Info.plist"];
    NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:plistPath];
    NSString *executable = [info[@"CFBundleExecutable"] isKindOfClass:[NSString class]] ? info[@"CFBundleExecutable"] : nil;
    if (executable.length > 0) {
        NSString *binaryPath = [bundlePath stringByAppendingPathComponent:executable];
        if ([fm fileExistsAtPath:binaryPath]) return binaryPath;
    }

    if ([bundlePath.pathExtension.lowercaseString isEqualToString:@"framework"]) {
        NSString *fallback = bundlePath.lastPathComponent.stringByDeletingPathExtension;
        NSString *binaryPath = [bundlePath stringByAppendingPathComponent:fallback];
        if ([fm fileExistsAtPath:binaryPath]) return binaryPath;
    }

    return nil;
}

- (BOOL)isSignableBundlePath:(NSString *)path {
    if (!path.length) return NO;

    NSString *extension = path.pathExtension.lowercaseString;
    return ([extension isEqualToString:@"app"] ||
            [extension isEqualToString:@"appex"] ||
            [extension isEqualToString:@"framework"]);
}

- (BOOL)hasSignableBundleAncestorForPath:(NSString *)path withinRoot:(NSString *)rootPath {
    if (!path.length || !rootPath.length) return NO;

    NSString *parentPath = [path stringByDeletingLastPathComponent];
    while (parentPath.length > 0 && ![parentPath isEqualToString:@"/"]) {
        if ([parentPath isEqualToString:rootPath]) return NO;
        if ([self isSignableBundlePath:parentPath]) {
            return YES;
        }
        NSString *nextParent = [parentPath stringByDeletingLastPathComponent];
        if ([nextParent isEqualToString:parentPath]) break;
        parentPath = nextParent;
    }

    return NO;
}

- (NSArray<NSString *> *)signTargetsForAppBundlePath:(NSString *)appBundlePath {
    if (!appBundlePath.length) return @[];

    NSFileManager *fm = [NSFileManager defaultManager];
    NSMutableArray<NSString *> *targets = [NSMutableArray array];
    NSMutableSet<NSString *> *seenTargets = [NSMutableSet set];

    NSDirectoryEnumerator<NSString *> *enumerator = [fm enumeratorAtPath:appBundlePath];
    for (NSString *relativePath in enumerator) {
        NSString *fullPath = [appBundlePath stringByAppendingPathComponent:relativePath];
        BOOL isDirectory = NO;
        if (![fm fileExistsAtPath:fullPath isDirectory:&isDirectory]) continue;

        if (isDirectory) {
            if ([self isSignableBundlePath:fullPath] && ![seenTargets containsObject:fullPath]) {
                [seenTargets addObject:fullPath];
                [targets addObject:fullPath];
            }
            continue;
        }

        if (!MCPIsMachOFile(fullPath)) continue;
        if ([self hasSignableBundleAncestorForPath:fullPath withinRoot:appBundlePath]) {
            continue;
        }
        if (![seenTargets containsObject:fullPath]) {
            [seenTargets addObject:fullPath];
            [targets addObject:fullPath];
        }
    }

    if (![seenTargets containsObject:appBundlePath]) {
        [seenTargets addObject:appBundlePath];
        [targets addObject:appBundlePath];
    }

    [targets sortUsingComparator:^NSComparisonResult(NSString *lhs, NSString *rhs) {
        NSUInteger lhsDepth = lhs.pathComponents.count;
        NSUInteger rhsDepth = rhs.pathComponents.count;
        if (lhsDepth > rhsDepth) return NSOrderedAscending;
        if (lhsDepth < rhsDepth) return NSOrderedDescending;
        return [lhs compare:rhs];
    }];
    return targets;
}

- (NSString *)bundleIdFromAppInstOutput:(NSString *)output {
    if (![output isKindOfClass:[NSString class]] || output.length == 0) return nil;

    NSArray<NSString *> *lines = [output componentsSeparatedByCharactersInSet:[NSCharacterSet newlineCharacterSet]];
    for (NSString *line in lines) {
        if ([line hasPrefix:@"APPINST_BUNDLE_ID="]) {
            NSString *bundleId = [line substringFromIndex:@"APPINST_BUNDLE_ID=".length];
            if (bundleId.length > 0) return bundleId;
        }
    }

    NSArray<NSString *> *markers = @[@"Installing \"", @"Successfully installed \""];
    for (NSString *marker in markers) {
        NSRange r1 = [output rangeOfString:marker];
        if (r1.location == NSNotFound) continue;
        NSUInteger start = r1.location + r1.length;
        NSRange r2 = [output rangeOfString:@"\"" options:0 range:NSMakeRange(start, output.length - start)];
        if (r2.location != NSNotFound) {
            NSString *bundleId = [output substringWithRange:NSMakeRange(start, r2.location - start)];
            if (bundleId.length > 0) return bundleId;
        }
    }
    return nil;
}

- (BOOL)fakesignInstalledAppForBundleId:(NSString *)bundleId installedAfter:(NSDate *)installedAfter error:(NSString **)error {
    if (error) *error = nil;

    NSMutableArray<NSString *> *ldidCandidates = [NSMutableArray array];
    NSString *bundledLdidPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-ldid");
    if ([NSFileManager.defaultManager isExecutableFileAtPath:bundledLdidPath]) {
        [ldidCandidates addObject:bundledLdidPath];
    }
    NSString *mcpRootPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-root");
    NSString *sudoPath = MCPResolvedJailbreakPath(@"/usr/bin/sudo");
    NSString *chmodPath = MCPResolvedJailbreakPath(@"/bin/chmod");
    NSString *shellPath = MCPResolvedJailbreakPath(@"/bin/sh");
    if (![NSFileManager.defaultManager isExecutableFileAtPath:chmodPath]) {
        chmodPath = MCPResolvedJailbreakPath(@"/usr/bin/chmod");
    }
    if (![NSFileManager.defaultManager isExecutableFileAtPath:shellPath]) {
        shellPath = @"/bin/sh";
    }
    if (ldidCandidates.count == 0) {
        APP_LOG(@"mcp-ldid not found, skipping fakesign for %@", bundleId);
        if (error) *error = @"mcp-ldid not found";
        return NO;
    }
    if (![NSFileManager.defaultManager isExecutableFileAtPath:mcpRootPath]) {
        APP_LOG(@"mcp-root not found, skipping fakesign for %@", bundleId);
    }

    BOOL sudoAvailable = [NSFileManager.defaultManager isExecutableFileAtPath:sudoPath];
    NSString *sudoPassword = sudoAvailable ? MCPConfiguredSudoPassword() : nil;
    if (![NSFileManager.defaultManager isExecutableFileAtPath:mcpRootPath] && !sudoAvailable) {
        if (error) *error = @"No privileged helper available";
        return NO;
    }

    NSString *mainExecutablePath = nil;
    NSString *resolvedBundleId = bundleId;
    NSString *appBundlePath = [self waitForInstalledAppBundlePathForBundleId:bundleId
                                                               installedAfter:installedAfter
                                                            resolvedBundleId:&resolvedBundleId
                                                          mainExecutablePath:&mainExecutablePath
                                                                     timeout:15.0];
    if (!appBundlePath.length || !mainExecutablePath.length) {
        APP_LOG(@"Could not find installed app bundle for %@ after %@", bundleId ?: @"<unknown>", installedAfter ?: [NSDate date]);
        if (error) *error = @"Could not find installed app bundle";
        return NO;
    }

    BOOL (^runPrivilegedCommand)(NSString *, NSArray<NSString *> *, NSTimeInterval, NSUInteger, NSString **, int *, NSString **) =
    ^BOOL(NSString *toolPath,
          NSArray<NSString *> *arguments,
          NSTimeInterval timeout,
          NSUInteger maxOutputBytes,
          NSString **commandOutput,
          int *commandExitCode,
          NSString **commandError) {
        if (commandOutput) *commandOutput = nil;
        if (commandExitCode) *commandExitCode = -1;
        if (commandError) *commandError = nil;

        if ([NSFileManager.defaultManager isExecutableFileAtPath:mcpRootPath]) {
            NSMutableArray<NSString *> *argv = [NSMutableArray arrayWithObject:toolPath];
            if (arguments.count > 0) {
                [argv addObjectsFromArray:arguments];
            }
            BOOL finished = MCPRunProcess(mcpRootPath,
                                          argv,
                                          MCPJailbreakEnvironment(),
                                          timeout,
                                          maxOutputBytes,
                                          commandOutput,
                                          commandExitCode,
                                          commandError);
            if (finished && (!commandExitCode || *commandExitCode == 0)) {
                return YES;
            }
        }

        if (!sudoAvailable) {
            return NO;
        }

        NSMutableArray<NSString *> *parts = [NSMutableArray arrayWithObjects:
                                             @"printf '%s\\n'",
                                             MCPShellQuote(sudoPassword ?: @""),
                                             @"|",
                                             MCPShellQuote(sudoPath),
                                             @"-k",
                                             @"-S",
                                             @"-p",
                                             @"''",
                                             MCPShellQuote(toolPath),
                                             nil];
        for (NSString *argument in arguments) {
            [parts addObject:MCPShellQuote(argument)];
        }
        NSString *command = [parts componentsJoinedByString:@" "];
        return MCPRunProcess(shellPath,
                             @[@"-lc", command],
                             MCPJailbreakEnvironment(),
                             timeout,
                             maxOutputBytes,
                             commandOutput,
                             commandExitCode,
                             commandError);
    };
    BOOL (^runShellCommand)(NSString *, NSString **) =
    ^BOOL(NSString *command, NSString **commandFailure) {
        if (commandFailure) *commandFailure = nil;
        NSString *output = nil;
        NSString *spawnError = nil;
        int exitCode = -1;
        BOOL finished = runPrivilegedCommand(shellPath,
                                             @[@"-lc", command],
                                             30,
                                             256 * 1024,
                                             &output,
                                             &exitCode,
                                             &spawnError);
        if (finished && exitCode == 0) {
            return YES;
        }

        NSString *failure = output.length > 0 ? output : spawnError;
        if (commandFailure) *commandFailure = failure ?: @"Unknown shell failure";
        APP_LOG(@"Privileged shell command failed (spawnError=%@ exit=%d commandBytes=%lu)",
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(command));
        return NO;
    };

    BOOL (^signAdhocTarget)(NSString *, NSDictionary *, NSString **) =
    ^BOOL(NSString *signTarget, NSDictionary *entitlements, NSString **signFailure) {
        if (signFailure) *signFailure = nil;
        if (signTarget.length == 0) {
            if (signFailure) *signFailure = @"Empty sign target";
            return NO;
        }

        NSString *entitlementsPath = nil;
        NSString *signArg = @"-s";
        if (entitlements != nil) {
            NSData *entitlementsXML = [NSPropertyListSerialization dataWithPropertyList:entitlements
                                                                                 format:NSPropertyListXMLFormat_v1_0
                                                                                options:0
                                                                                  error:nil];
            if (!entitlementsXML) {
                if (signFailure) *signFailure = @"Failed to serialize entitlements";
                return NO;
            }

            entitlementsPath = [[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString]
                                stringByAppendingPathExtension:@"plist"];
            if (![entitlementsXML writeToFile:entitlementsPath atomically:NO]) {
                if (signFailure) *signFailure = @"Failed to write entitlements plist";
                return NO;
            }
            signArg = [@"-S" stringByAppendingString:MCPBootstrapArgumentPath(entitlementsPath)];
        }

        NSString *bootstrapSignTarget = MCPBootstrapArgumentPath(signTarget);
        BOOL signedTarget = NO;
        NSString *lastOutput = nil;
        NSString *lastSpawnError = nil;
        int lastExitCode = -1;

        for (NSString *ldidPath in ldidCandidates) {
            NSString *output = nil;
            NSString *spawnError = nil;
            int exitCode = -1;
            BOOL finished = runPrivilegedCommand(ldidPath,
                                                 @[signArg, bootstrapSignTarget],
                                                 30,
                                                 128 * 1024,
                                                 &output,
                                                 &exitCode,
                                                 &spawnError);
            if (finished && exitCode == 0) {
                APP_LOG(@"Fakesigned %@ with %@ (%@)",
                        resolvedBundleId ?: bundleId ?: @"<unknown>",
                        ldidPath.lastPathComponent,
                        MCPAppLogSafePath(signTarget));
                signedTarget = YES;
                break;
            }

            lastOutput = output;
            lastSpawnError = spawnError;
            lastExitCode = exitCode;
            APP_LOG(@"mcp-ldid failed for %@ via %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                    MCPAppLogSafePath(signTarget),
                    ldidPath.lastPathComponent,
                    MCPAppLogRedactedText(spawnError ?: @"none"),
                    exitCode,
                    (unsigned long)MCPAppLogUTF8Length(output));
        }

        if (entitlementsPath.length > 0) {
            [[NSFileManager defaultManager] removeItemAtPath:entitlementsPath error:nil];
        }

        if (!signedTarget) {
            if (signFailure) {
                *signFailure = lastOutput.length > 0 ? lastOutput : (lastSpawnError ?: @"mcp-ldid failed");
            }
            APP_LOG(@"mcp-ldid failed for %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                    MCPAppLogSafePath(signTarget),
                    MCPAppLogRedactedText(lastSpawnError ?: @"none"),
                    lastExitCode,
                    (unsigned long)MCPAppLogUTF8Length(lastOutput));
            return NO;
        }

        return YES;
    };

    NSFileManager *fm = [NSFileManager defaultManager];
    NSString *signFailure = nil;
    NSString *mainExecutable = mainExecutablePath;

    NSURL *fileURL = nil;
    NSDirectoryEnumerator<NSURL *> *plistEnumerator =
    [fm enumeratorAtURL:[NSURL fileURLWithPath:appBundlePath]
 includingPropertiesForKeys:nil
                    options:0
               errorHandler:nil];

    while ((fileURL = [plistEnumerator nextObject])) {
        NSString *filePath = fileURL.path;
        if (![filePath.lastPathComponent isEqualToString:@"Info.plist"]) continue;

        NSDictionary *infoDict = [NSDictionary dictionaryWithContentsOfFile:filePath];
        if (![infoDict isKindOfClass:[NSDictionary class]]) continue;

        NSString *targetBundleId = [infoDict[@"CFBundleIdentifier"] isKindOfClass:[NSString class]] ? infoDict[@"CFBundleIdentifier"] : nil;
        NSString *bundleExecutable = [infoDict[@"CFBundleExecutable"] isKindOfClass:[NSString class]] ? infoDict[@"CFBundleExecutable"] : nil;
        if (targetBundleId.length == 0 || bundleExecutable.length == 0) continue;

        NSString *bundlePath = [filePath stringByDeletingLastPathComponent];
        NSString *bundleExecutablePath = [bundlePath stringByAppendingPathComponent:bundleExecutable];
        if (![fm fileExistsAtPath:bundleExecutablePath]) continue;

        NSString *packageType = [infoDict[@"CFBundlePackageType"] isKindOfClass:[NSString class]] ? infoDict[@"CFBundlePackageType"] : nil;
        if ([packageType isEqualToString:@"FMWK"]) continue;

        NSMutableDictionary *entitlementsToUse = [MCPDumpEntitlementsFromBinaryAtPath(bundleExecutablePath) mutableCopy];
        if (MCPIsSameFile(bundleExecutablePath, mainExecutable) && !entitlementsToUse) {
            entitlementsToUse = [MCPFallbackMainExecutableEntitlements() mutableCopy];
        }
        if (!entitlementsToUse) {
            entitlementsToUse = [NSMutableDictionary dictionary];
        }

#ifdef MCP_ROOTHIDE
        entitlementsToUse[@"jb.pmap_cs.custom_trust"] = @"PMAP_CS_APP_STORE";
#endif

        if (!signAdhocTarget(bundleExecutablePath, entitlementsToUse, &signFailure)) {
            if (error) *error = signFailure ?: @"Failed to sign bundle executable";
            return NO;
        }
    }

    if (!signAdhocTarget(appBundlePath, nil, &signFailure)) {
        if (error) *error = signFailure ?: @"Failed to recursively sign app bundle";
        return NO;
    }

    NSString *bootstrapAppBundlePath = MCPBootstrapArgumentPath(appBundlePath);
    NSString *permissionFailure = nil;

    if (![fm isExecutableFileAtPath:chmodPath]) {
        if (error) *error = @"chmod not found";
        return NO;
    }

    NSString *resetPermsCommand = [NSString stringWithFormat:@"find %@ -exec chmod 0644 {} +",
                                   MCPShellQuote(bootstrapAppBundlePath)];
    if (!runShellCommand(resetPermsCommand, &permissionFailure)) {
        if (error) *error = permissionFailure ?: @"Failed to reset app permissions";
        return NO;
    }

    NSString *dirPermsCommand = [NSString stringWithFormat:@"find %@ -type d -exec chmod 0755 {} +",
                                 MCPShellQuote(bootstrapAppBundlePath)];
    if (!runShellCommand(dirPermsCommand, &permissionFailure)) {
        if (error) *error = permissionFailure ?: @"Failed to set directory permissions";
        return NO;
    }

    NSMutableArray<NSString *> *machOPaths = [NSMutableArray array];
    NSDirectoryEnumerator<NSString *> *machOEnumerator = [fm enumeratorAtPath:appBundlePath];
    for (NSString *relativePath in machOEnumerator) {
        NSString *fullPath = [appBundlePath stringByAppendingPathComponent:relativePath];
        BOOL isDirectory = NO;
        if (![fm fileExistsAtPath:fullPath isDirectory:&isDirectory] || isDirectory) continue;
        if (!MCPIsMachOFile(fullPath)) continue;
        [machOPaths addObject:fullPath];
    }

    const NSUInteger chmodBatchSize = 32;
    for (NSUInteger idx = 0; idx < machOPaths.count; idx += chmodBatchSize) {
        NSRange batchRange = NSMakeRange(idx, MIN(chmodBatchSize, machOPaths.count - idx));
        NSArray<NSString *> *batch = [machOPaths subarrayWithRange:batchRange];
        NSMutableArray<NSString *> *chmodArguments = [NSMutableArray arrayWithObject:@"0755"];
        for (NSString *binaryPath in batch) {
            [chmodArguments addObject:MCPBootstrapArgumentPath(binaryPath)];
        }

        NSString *chmodOutput = nil;
        NSString *chmodError = nil;
        int chmodExitCode = -1;
        BOOL chmodFinished = runPrivilegedCommand(chmodPath,
                                                  chmodArguments,
                                                  15,
                                                  128 * 1024,
                                                  &chmodOutput,
                                                  &chmodExitCode,
                                                  &chmodError);
        if (!(chmodFinished && chmodExitCode == 0)) {
            APP_LOG(@"chmod failed for Mach-O batch (spawnError=%@ exit=%d outputBytes=%lu)",
                    MCPAppLogRedactedText(chmodError ?: @"none"),
                    chmodExitCode,
                    (unsigned long)MCPAppLogUTF8Length(chmodOutput));
            if (error) *error = chmodOutput.length > 0 ? chmodOutput : (chmodError ?: @"Failed to set Mach-O permissions");
            return NO;
        }
    }

    return YES;
}

- (void)fakesignApp:(NSString *)bundleId {
    [self fakesignInstalledAppForBundleId:bundleId installedAfter:nil error:nil];
}

- (BOOL)retryFakesignInstalledAppForBundleId:(NSString *)bundleId installedAfter:(NSDate *)installedAfter {
    NSString *lastError = nil;
    for (NSUInteger attempt = 0; attempt < 3; attempt++) {
        if ([self fakesignInstalledAppForBundleId:bundleId installedAfter:installedAfter error:&lastError]) {
            return YES;
        }
        APP_LOG(@"Fakesign attempt %lu failed for %@: %@", (unsigned long)(attempt + 1), bundleId ?: @"<unknown>", MCPAppLogRedactedText(lastError ?: @"unknown error"));
        if (attempt < 2) {
            [NSThread sleepForTimeInterval:2.0];
        }
    }
    return NO;
}

#pragma mark - Install App

- (BOOL)installDebPackage:(NSString *)debPath error:(NSString **)error {
    if (![debPath.pathExtension.lowercaseString isEqualToString:@"deb"]) {
        if (error) *error = @"DEB install requires a .deb file";
        return NO;
    }
    if (!debPath.isAbsolutePath) {
        if (error) *error = @"DEB install requires an absolute device path";
        return NO;
    }

    NSString *stageError = nil;
    NSString *stagedDebPath = nil;
    NSString *dpkgDebPath = MCPStageDebForDpkg(debPath, &stagedDebPath, &stageError);
    if (!dpkgDebPath.length) {
        if (error) *error = stageError ?: @"Failed to stage DEB for dpkg";
        return NO;
    }

    APP_LOG(@"Installing DEB via privileged dpkg: %@", MCPAppLogSafePath(debPath));
    NSString *output = nil;
    NSString *spawnError = nil;
    int exitCode = -1;
    BOOL finished = MCPRunDpkgWithPrivileges(@[@"-i", dpkgDebPath],
                                             180,
                                             512 * 1024,
                                             &output,
                                             &exitCode,
                                             &spawnError);
    if (stagedDebPath.length > 0) {
        MCPRemoveShellPath(stagedDebPath);
    }
    if (!finished || exitCode != 0) {
        APP_LOG(@"dpkg install failed (spawnError=%@ exit=%d outputBytes=%lu)",
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(output));
        NSString *details = output.length > 0 ? output : (spawnError ?: @"unknown error");
        if (error) *error = [NSString stringWithFormat:@"dpkg install failed: %@", details];
        return NO;
    }

    APP_LOG(@"dpkg install succeeded outputBytes=%lu", (unsigned long)MCPAppLogUTF8Length(output));
    NSString *restartError = nil;
    if (!MCPScheduleSpringBoardRestart(&restartError)) {
        if (error) *error = [NSString stringWithFormat:@"DEB installed but failed to schedule SpringBoard restart: %@", restartError ?: @"unknown error"];
        return NO;
    }

    return YES;
}

- (BOOL)installApp:(NSString *)packagePath error:(NSString **)error {
    if (!packagePath.length) {
        if (error) *error = @"Empty package path";
        return NO;
    }

    NSFileManager *fm = [NSFileManager defaultManager];
    if (![fm fileExistsAtPath:packagePath]) {
        if (error) *error = [NSString stringWithFormat:@"File not found: %@", packagePath];
        return NO;
    }

    NSString *extension = packagePath.pathExtension.lowercaseString ?: @"";
    if ([extension isEqualToString:@"deb"]) {
        return [self installDebPackage:packagePath error:error];
    }
    // TIPA is an IPA archive with a different extension. Use the same helpers
    // and Customer package type, including the LSApplicationWorkspace fallback.
    BOOL isIPA = [extension isEqualToString:@"ipa"] || [extension isEqualToString:@"tipa"];
    if (!isIPA) {
        if (error) *error = [NSString stringWithFormat:@"Unsupported package extension: .%@ (expected .ipa, .tipa or .deb)", extension.length ? extension : @"<none>"];
        return NO;
    }

    NSDate *installStartedAt = [NSDate date];
    NSString *ipaPath = packagePath;
    NSString *ipaBundleId = [self bundleIdFromIPA:ipaPath];

#ifdef MCP_ROOTHIDE
    NSString *mcpRootPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-root");
    BOOL canUseMcpRoot = [fm isExecutableFileAtPath:mcpRootPath];
    NSString *rootHelperPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-roothelper");
    if ([fm fileExistsAtPath:rootHelperPath]) {
        NSString *launchPath = canUseMcpRoot ? mcpRootPath : rootHelperPath;
        NSArray<NSString *> *arguments = canUseMcpRoot ? @[@"/usr/bin/mcp-roothelper", ipaPath] : @[ipaPath];
        APP_LOG(@"Installing via %s%s: %@",
                canUseMcpRoot ? "mcp-root -> " : "",
                "mcp-roothelper",
                MCPAppLogSafePath(ipaPath));
        NSString *output = nil;
        NSString *spawnError = nil;
        int exitCode = -1;
        BOOL finished = MCPRunProcess(launchPath,
                                      arguments,
                                      MCPJailbreakEnvironment(),
                                      180,
                                      512 * 1024,
                                      &output,
                                      &exitCode,
                                      &spawnError);
        if (finished && exitCode == 0) {
            APP_LOG(@"mcp-roothelper succeeded outputBytes=%lu", (unsigned long)MCPAppLogUTF8Length(output));
            return YES;
        }

        APP_LOG(@"mcp-roothelper failed (spawnError=%@ exit=%d outputBytes=%lu)",
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(output));
    }
#endif

    // Method 1: Use mcp-appinst CLI (bundled with ios-mcp, works with mcp-appsync)
    NSString *appinstPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-appinst");
    if ([fm fileExistsAtPath:appinstPath]) {
        NSString *launchPath = appinstPath;
        NSArray<NSString *> *arguments = @[ipaPath];
#ifdef MCP_ROOTHIDE
        if (canUseMcpRoot) {
            launchPath = mcpRootPath;
            arguments = @[@"/usr/bin/mcp-appinst", ipaPath];
        }
#endif
        APP_LOG(@"Installing via %s%s: %@",
#ifdef MCP_ROOTHIDE
                (launchPath == mcpRootPath) ? "mcp-root -> " :
#endif
                "",
                "mcp-appinst",
                MCPAppLogSafePath(ipaPath));
        NSString *output = nil;
        NSString *spawnError = nil;
        int exitCode = -1;
        BOOL finished = MCPRunProcess(launchPath,
                                      arguments,
                                      MCPJailbreakEnvironment(),
                                      120,
                                      512 * 1024,
                                      &output,
                                      &exitCode,
                                      &spawnError);
        if (finished && exitCode == 0) {
            APP_LOG(@"mcp-appinst succeeded outputBytes=%lu", (unsigned long)MCPAppLogUTF8Length(output));
#ifndef MCP_ROOTHIDE
            NSString *bundleId = ipaBundleId.length > 0 ? ipaBundleId : [self bundleIdFromAppInstOutput:output];
            [self retryFakesignInstalledAppForBundleId:bundleId installedAfter:installStartedAt];
#endif
            return YES;
        }

        APP_LOG(@"mcp-appinst failed (spawnError=%@ exit=%d outputBytes=%lu)",
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(output));
        // Fall through to LSApplicationWorkspace
    }

    // Method 2: LSApplicationWorkspace (works when AppSync hooks installd)
    NSString *packageType = isIPA ? @"Customer" : @"Developer";

    __block BOOL ok = NO;
    __block NSString *errMsg = nil;

    dispatch_block_t block = ^{
        Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
        if (!LSWorkspaceClass) {
            errMsg = @"LSApplicationWorkspace not available";
            return;
        }

        id workspace = [LSWorkspaceClass performSelector:@selector(defaultWorkspace)];
        NSURL *appURL = [NSURL fileURLWithPath:ipaPath];

        NSArray *optionsList = @[
            @{@"PackageType": packageType},
            @{},
        ];

        for (NSDictionary *options in optionsList) {
            SEL installSel = @selector(installApplication:withOptions:error:);
            if ([workspace respondsToSelector:installSel]) {
                NSMethodSignature *sig = [workspace methodSignatureForSelector:installSel];
                NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
                inv.target = workspace;
                inv.selector = installSel;
                NSURL *url = appURL;
                [inv setArgument:&url atIndex:2];
                NSDictionary *opts = options;
                [inv setArgument:&opts atIndex:3];
                __autoreleasing NSError *installError = nil;
                [inv setArgument:&installError atIndex:4];
                [inv invoke];

                BOOL result = NO;
                if (strcmp(sig.methodReturnType, @encode(BOOL)) == 0) {
                    [inv getReturnValue:&result];
                }

                if (result) {
                    APP_LOG(@"Installed app from: %@ (options: %@)", MCPAppLogSafePath(ipaPath), options);
                    ok = YES;
                    return;
                }
                if (installError) {
                    errMsg = [NSString stringWithFormat:@"Install failed: %@", installError.localizedDescription];
                } else {
                    errMsg = [NSString stringWithFormat:@"installApplication returned NO (options: %@)", options];
                }
                continue;
            }
        }

        if (!ok && !errMsg) {
            errMsg = @"No install method available";
        }
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }

    // Auto fakesign after LSApplicationWorkspace install
    if (ok) {
        NSString *bundleId = ipaBundleId.length > 0 ? ipaBundleId : [self bundleIdFromIPA:ipaPath];
        [self retryFakesignInstalledAppForBundleId:bundleId installedAfter:installStartedAt];
    }

    if (error) *error = errMsg;
    return ok;
}

- (NSString *)bundleIdFromIPA:(NSString *)ipaPath {
#ifdef MCP_ROOTHIDE
    NSString *rootHelperPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-roothelper");
    if ([[NSFileManager defaultManager] isExecutableFileAtPath:rootHelperPath]) {
        NSString *output = nil;
        NSString *spawnError = nil;
        int exitCode = -1;
        BOOL finished = MCPRunProcess(rootHelperPath,
                                      @[@"--bundle-id", ipaPath],
                                      MCPJailbreakEnvironment(),
                                      30,
                                      64 * 1024,
                                      &output,
                                      &exitCode,
                                      &spawnError);
        if (finished && exitCode == 0) {
            NSArray<NSString *> *lines = [[output stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]]
                                          componentsSeparatedByCharactersInSet:[NSCharacterSet newlineCharacterSet]];
            NSString *bundleId = lines.lastObject;
            if (bundleId.length > 0) return bundleId;
        } else {
            APP_LOG(@"mcp-roothelper --bundle-id failed for %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                    MCPAppLogSafePath(ipaPath),
                    MCPAppLogRedactedText(spawnError ?: @"none"),
                    exitCode,
                    (unsigned long)MCPAppLogUTF8Length(output));
        }
    }
#endif

    NSString *appinstPath = MCPResolvedJailbreakPath(@"/usr/bin/mcp-appinst");
    if ([[NSFileManager defaultManager] isExecutableFileAtPath:appinstPath]) {
        NSString *output = nil;
        NSString *spawnError = nil;
        int exitCode = -1;
        BOOL finished = MCPRunProcess(appinstPath,
                                      @[@"--bundle-id", ipaPath],
                                      MCPJailbreakEnvironment(),
                                      30,
                                      64 * 1024,
                                      &output,
                                      &exitCode,
                                      &spawnError);
        if (finished && exitCode == 0) {
            NSArray<NSString *> *lines = [[output stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]]
                                          componentsSeparatedByCharactersInSet:[NSCharacterSet newlineCharacterSet]];
            NSString *bundleId = lines.lastObject;
            if (bundleId.length > 0) return bundleId;
        } else {
            APP_LOG(@"mcp-appinst --bundle-id failed for %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                    MCPAppLogSafePath(ipaPath),
                    MCPAppLogRedactedText(spawnError ?: @"none"),
                    exitCode,
                    (unsigned long)MCPAppLogUTF8Length(output));
        }
    }

    NSString *unzipPath = MCPResolvedJailbreakPath(@"/usr/bin/unzip");
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:unzipPath]) {
        APP_LOG(@"unzip not found, skipping bundle ID extraction for %@", MCPAppLogSafePath(ipaPath));
        return nil;
    }

    NSString *tmpDir = [NSTemporaryDirectory() stringByAppendingPathComponent:
                        [NSString stringWithFormat:@"mcp_plist_%u", arc4random()]];
    [[NSFileManager defaultManager] createDirectoryAtPath:tmpDir withIntermediateDirectories:YES attributes:nil error:nil];

    NSString *output = nil;
    NSString *spawnError = nil;
    int exitCode = -1;
    BOOL finished = MCPRunProcess(unzipPath,
                                  @[@"-o", @"-q", ipaPath, @"Payload/*/Info.plist", @"-d", tmpDir],
                                  MCPJailbreakEnvironment(),
                                  30,
                                  128 * 1024,
                                  &output,
                                  &exitCode,
                                  &spawnError);
    if (!finished || exitCode != 0) {
        APP_LOG(@"unzip failed for %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                MCPAppLogSafePath(ipaPath),
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(output));
        [[NSFileManager defaultManager] removeItemAtPath:tmpDir error:nil];
        return nil;
    }

    NSString *bundleId = nil;
    NSString *payloadDir = [tmpDir stringByAppendingPathComponent:@"Payload"];
    NSArray *contents = [[NSFileManager defaultManager] contentsOfDirectoryAtPath:payloadDir error:nil];
    for (NSString *item in contents) {
        if ([item.pathExtension.lowercaseString isEqualToString:@"app"]) {
            NSString *plistPath = [[payloadDir stringByAppendingPathComponent:item] stringByAppendingPathComponent:@"Info.plist"];
            NSDictionary *info = [NSDictionary dictionaryWithContentsOfFile:plistPath];
            bundleId = [info[@"CFBundleIdentifier"] isKindOfClass:[NSString class]] ? info[@"CFBundleIdentifier"] : nil;
            if (bundleId.length > 0) break;
        }
    }

    [[NSFileManager defaultManager] removeItemAtPath:tmpDir error:nil];
    return bundleId;
}

#pragma mark - Uninstall App

- (BOOL)isAppInstalled:(NSString *)bundleId {
    if (!bundleId.length) return NO;

    __block BOOL installed = NO;
    dispatch_block_t block = ^{
        Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
        if (LSWorkspaceClass) {
            id workspace = [LSWorkspaceClass performSelector:@selector(defaultWorkspace)];
            SEL proxySel = @selector(applicationProxyForIdentifier:);
            if ([workspace respondsToSelector:proxySel]) {
                id proxy = MCPAppMsgSendObjectArg(workspace, proxySel, bundleId);
                if (proxy) {
                    installed = YES;
                    return;
                }
            }

            SEL allAppsSel = @selector(allInstalledApplications);
            if ([workspace respondsToSelector:allAppsSel]) {
                NSArray *allApps = MCPAppMsgSendObject(workspace, allAppsSel);
                for (id proxy in allApps) {
                    if (![proxy respondsToSelector:@selector(applicationIdentifier)]) continue;
                    NSString *appId = [proxy performSelector:@selector(applicationIdentifier)];
                    if ([appId isEqualToString:bundleId]) {
                        installed = YES;
                        return;
                    }
                }
            }
        }

        Class SBAppCtrl = objc_getClass("SBApplicationController");
        if (SBAppCtrl) {
            id appCtrl = [SBAppCtrl performSelector:@selector(sharedInstance)];
            if ([appCtrl respondsToSelector:@selector(applicationWithBundleIdentifier:)]) {
                id sbApp = MCPAppMsgSendObjectArg(appCtrl, @selector(applicationWithBundleIdentifier:), bundleId);
                installed = (sbApp != nil);
            }
        }
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }
    return installed;
}

- (NSDictionary *)appInfoForBundleId:(NSString *)bundleId error:(NSString **)error {
    if (error) *error = nil;
    if (bundleId.length == 0) {
        if (error) *error = @"bundle_id is required";
        return nil;
    }

    __block NSDictionary *result = nil;
    __block NSString *failure = nil;

    dispatch_block_t block = ^{
        Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
        if (!LSWorkspaceClass) {
            failure = @"LSApplicationWorkspace unavailable";
            return;
        }
        id workspace = [LSWorkspaceClass performSelector:@selector(defaultWorkspace)];

        id proxy = nil;
        SEL proxySel = @selector(applicationProxyForIdentifier:);
        if ([workspace respondsToSelector:proxySel]) {
            proxy = MCPAppMsgSendObjectArg(workspace, proxySel, bundleId);
        }
        if (!proxy) {
            // Fallback scan in case applicationProxyForIdentifier: returns a placeholder.
            SEL allAppsSel = @selector(allInstalledApplications);
            if ([workspace respondsToSelector:allAppsSel]) {
                NSArray *allApps = MCPAppMsgSendObject(workspace, allAppsSel);
                for (id candidate in allApps) {
                    if (![candidate respondsToSelector:@selector(applicationIdentifier)]) continue;
                    NSString *appId = [candidate performSelector:@selector(applicationIdentifier)];
                    if ([appId isEqualToString:bundleId]) { proxy = candidate; break; }
                }
            }
        }
        if (!proxy) {
            failure = [NSString stringWithFormat:@"App not installed: %@", bundleId];
            return;
        }

        NSMutableDictionary *info = [NSMutableDictionary dictionary];
        info[@"bundle_id"] = bundleId;

        if ([proxy respondsToSelector:@selector(localizedName)]) {
            NSString *name = MCPAppMsgSendObject(proxy, @selector(localizedName));
            if ([name isKindOfClass:[NSString class]]) info[@"name"] = name;
        }

        NSString *rawType = nil;
        if ([proxy respondsToSelector:@selector(applicationType)]) {
            rawType = MCPAppMsgSendObject(proxy, @selector(applicationType));
        }
        info[@"type"] = MCPNormalizedInstalledAppType(proxy, bundleId, rawType ?: @"");

        // Bundle (.app) path.
        NSString *bundlePath = nil;
        if ([proxy respondsToSelector:@selector(bundleURL)]) {
            id bundleURL = MCPAppMsgSendObject(proxy, @selector(bundleURL));
            if ([bundleURL isKindOfClass:[NSURL class]]) {
                bundlePath = [((NSURL *)bundleURL).path stringByStandardizingPath];
            }
        }
        if (bundlePath.length) info[@"bundle_path"] = bundlePath;

        // Data container (sandbox) path.
        NSString *dataContainer = nil;
        if ([proxy respondsToSelector:@selector(dataContainerURL)]) {
            id dataURL = MCPAppMsgSendObject(proxy, @selector(dataContainerURL));
            if ([dataURL isKindOfClass:[NSURL class]]) {
                dataContainer = [((NSURL *)dataURL).path stringByStandardizingPath];
            }
        }
        if (dataContainer.length) info[@"data_container"] = dataContainer;

        // App Group / shared container paths.
        if ([proxy respondsToSelector:@selector(groupContainerURLs)]) {
            id groupURLs = MCPAppMsgSendObject(proxy, @selector(groupContainerURLs));
            if ([groupURLs isKindOfClass:[NSDictionary class]]) {
                NSMutableDictionary *groups = [NSMutableDictionary dictionary];
                [(NSDictionary *)groupURLs enumerateKeysAndObjectsUsingBlock:^(id key, id obj, BOOL *stop) {
                    if ([key isKindOfClass:[NSString class]] && [obj isKindOfClass:[NSURL class]]) {
                        groups[key] = [((NSURL *)obj).path stringByStandardizingPath];
                    }
                }];
                if (groups.count) info[@"group_containers"] = groups;
            }
        }

        // Version info from Info.plist.
        NSString *executablePath = nil;
        if (bundlePath.length) {
            NSString *infoPlistPath = [bundlePath stringByAppendingPathComponent:@"Info.plist"];
            NSDictionary *plist = [NSDictionary dictionaryWithContentsOfFile:infoPlistPath];
            if ([plist isKindOfClass:[NSDictionary class]]) {
                if ([plist[@"CFBundleShortVersionString"] isKindOfClass:[NSString class]]) {
                    info[@"short_version"] = plist[@"CFBundleShortVersionString"];
                }
                if ([plist[@"CFBundleVersion"] isKindOfClass:[NSString class]]) {
                    info[@"version"] = plist[@"CFBundleVersion"];
                }
                if ([plist[@"DTPlatformVersion"] isKindOfClass:[NSString class]]) {
                    info[@"sdk_version"] = plist[@"DTPlatformVersion"];
                }
                if ([plist[@"MinimumOSVersion"] isKindOfClass:[NSString class]]) {
                    info[@"minimum_os_version"] = plist[@"MinimumOSVersion"];
                }
                NSString *executable = [plist[@"CFBundleExecutable"] isKindOfClass:[NSString class]] ? plist[@"CFBundleExecutable"] : nil;
                if (executable.length) {
                    executablePath = [bundlePath stringByAppendingPathComponent:executable];
                    info[@"executable_path"] = executablePath;
                }
            }
        }

        // Entitlements from the main executable (reuses the fakesign code path's dumper).
        if (executablePath.length) {
            NSDictionary *entitlements = MCPDumpEntitlementsFromBinaryAtPath(executablePath);
            if (entitlements.count) info[@"entitlements"] = entitlements;
        }

        result = [info copy];
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }

    if (!result) {
        if (error) *error = failure ?: @"Failed to read app info";
        return nil;
    }
    return result;
}

- (BOOL)debPackageInstalled:(NSString *)packageId statusOutput:(NSString **)statusOutput error:(NSString **)error {
    NSString *output = nil;
    NSString *spawnError = nil;
    int exitCode = -1;
    BOOL finished = MCPRunDpkgWithPrivileges(@[@"-s", packageId],
                                             30,
                                             128 * 1024,
                                             &output,
                                             &exitCode,
                                             &spawnError);
    if (statusOutput) *statusOutput = output;

    if (!finished) {
        APP_LOG(@"dpkg status failed for %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                packageId,
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(output));
        if (error) *error = spawnError ?: @"dpkg status failed";
        return NO;
    }

    if (exitCode != 0) {
        return NO;
    }

    return [output rangeOfString:@"Status: install ok installed"].location != NSNotFound;
}

- (BOOL)uninstallDebPackage:(NSString *)packageId error:(NSString **)error {
    if (!MCPDebPackageIdIsSafe(packageId)) {
        if (error) *error = [NSString stringWithFormat:@"Invalid DEB package id: %@", packageId ?: @"<nil>"];
        return NO;
    }

    NSString *statusOutput = nil;
    NSString *statusError = nil;
    if (![self debPackageInstalled:packageId statusOutput:&statusOutput error:&statusError]) {
        if (error) {
            NSString *details = statusError.length ? statusError : statusOutput;
            *error = details.length > 0 ?
                [NSString stringWithFormat:@"DEB package not installed: %@ (%@)", packageId, MCPAppLogRedactedText(details)] :
                [NSString stringWithFormat:@"DEB package not installed: %@", packageId];
        }
        return NO;
    }

    APP_LOG(@"Uninstalling DEB via privileged dpkg: %@", packageId);
    NSString *output = nil;
    NSString *spawnError = nil;
    int exitCode = -1;
    BOOL finished = MCPRunDpkgWithPrivileges(@[@"-r", packageId],
                                             180,
                                             512 * 1024,
                                             &output,
                                             &exitCode,
                                             &spawnError);
    if (!finished || exitCode != 0) {
        APP_LOG(@"dpkg remove failed for %@ (spawnError=%@ exit=%d outputBytes=%lu)",
                packageId,
                MCPAppLogRedactedText(spawnError ?: @"none"),
                exitCode,
                (unsigned long)MCPAppLogUTF8Length(output));
        NSString *details = output.length > 0 ? output : (spawnError ?: @"unknown error");
        if (error) *error = [NSString stringWithFormat:@"dpkg remove failed: %@", details];
        return NO;
    }

    if ([self debPackageInstalled:packageId statusOutput:nil error:nil]) {
        if (error) *error = [NSString stringWithFormat:@"dpkg remove completed but package is still installed: %@", packageId];
        return NO;
    }

    APP_LOG(@"dpkg remove succeeded outputBytes=%lu", (unsigned long)MCPAppLogUTF8Length(output));
    NSString *restartError = nil;
    if (!MCPScheduleSpringBoardRestart(&restartError)) {
        if (error) *error = [NSString stringWithFormat:@"DEB removed but failed to schedule SpringBoard restart: %@", restartError ?: @"unknown error"];
        return NO;
    }

    return YES;
}

- (BOOL)uninstallApp:(NSString *)bundleId error:(NSString **)error {
    if (!bundleId.length) {
        if (error) *error = @"Empty app or package identifier";
        return NO;
    }

    if (![self isAppInstalled:bundleId]) {
        return [self uninstallDebPackage:bundleId error:error];
    }

    __block BOOL ok = NO;
    __block NSString *errMsg = nil;

    dispatch_block_t block = ^{
        Class LSWorkspaceClass = objc_getClass("LSApplicationWorkspace");
        if (!LSWorkspaceClass) {
            errMsg = @"LSApplicationWorkspace not available";
            return;
        }

        id workspace = [LSWorkspaceClass performSelector:@selector(defaultWorkspace)];

        SEL uninstallSel = @selector(uninstallApplication:withOptions:);
        if ([workspace respondsToSelector:uninstallSel]) {
            NSMethodSignature *sig = [workspace methodSignatureForSelector:uninstallSel];
            NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
            inv.target = workspace;
            inv.selector = uninstallSel;
            NSString *bid = bundleId;
            [inv setArgument:&bid atIndex:2];
            NSDictionary *opts = @{};
            [inv setArgument:&opts atIndex:3];
            [inv invoke];

            BOOL result = NO;
            if (strcmp(sig.methodReturnType, @encode(BOOL)) == 0) {
                [inv getReturnValue:&result];
            }

            if (result) {
                APP_LOG(@"Uninstalled app: %@", bundleId);
                ok = YES;
                return;
            }
            errMsg = @"uninstallApplication returned NO";
            return;
        }

        errMsg = @"No uninstall method available";
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }

    if (!ok) {
        if (error) *error = errMsg;
        return NO;
    }

    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:10.0];
    while ([deadline timeIntervalSinceNow] > 0) {
        if (![self isAppInstalled:bundleId]) {
            if (error) *error = nil;
            return YES;
        }
        [NSThread sleepForTimeInterval:0.25];
    }

    if (error) {
        *error = [NSString stringWithFormat:@"Uninstall request was accepted, but %@ is still installed", bundleId];
    }
    return NO;
}

@end
