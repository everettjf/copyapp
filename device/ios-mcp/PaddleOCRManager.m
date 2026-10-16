#import "PaddleOCRManager.h"
#import "ScreenManager.h"
#import "MCPProcessUtil.h"
#import "MCPLogger.h"
#import "MCPOCRRequestContext.h"
#import <ImageIO/ImageIO.h>
#include <arpa/inet.h>
#include <fcntl.h>
#include <poll.h>
#include <spawn.h>
#include <signal.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <sys/wait.h>
#include <unistd.h>
#include <math.h>

// SpringBoard may have closed standard descriptors. Keep spawn source FDs away
// from 0/1/2 so subsequent close actions cannot close the remapped child stdio.
static BOOL MCPKeepFDAboveStdio(int *fd) {
    if (*fd >= 3) return YES;
    int moved = fcntl(*fd, F_DUPFD_CLOEXEC, 3);
    if (moved < 0) return NO;
    close(*fd);
    *fd = moved;
    return YES;
}

@implementation PaddleOCRManager {
    NSLock *_gate;
    pid_t _pid;
    int _fd;
    int _stderrFD;
    NSMutableData *_diagnostics;
    int _exitStatus;
}
+ (instancetype)sharedInstance {
    static PaddleOCRManager *instance;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ instance = [self new]; });
    return instance;
}
- (instancetype)init {
    if ((self = [super init])) { _gate = [NSLock new]; _fd = -1; _pid = -1; _stderrFD = -1; }
    return self;
}
- (void)drainDiagnostics {
    if (_stderrFD < 0) return;
    uint8_t bytes[1024]; ssize_t n;
    while ((n = read(_stderrFD, bytes, sizeof(bytes))) > 0) {
        [_diagnostics appendBytes:bytes length:n];
        if (_diagnostics.length > 4096) [_diagnostics replaceBytesInRange:NSMakeRange(0, _diagnostics.length - 4096) withBytes:NULL length:0];
    }
}
- (void)stopWorker {
    [self drainDiagnostics];
    if (_fd >= 0) { close(_fd); _fd = -1; }
    if (_pid > 0) {
        pid_t status;
        do { status = waitpid(_pid, &_exitStatus, WNOHANG); } while (status < 0 && errno == EINTR);
        if (status == 0) {
            kill(_pid, SIGKILL);
            // Work is actually gone before unlock; never signal a reaped/reused PID.
            while (waitpid(_pid, &_exitStatus, 0) < 0 && errno == EINTR) {}
        }
        _pid = -1;
    }
    [self drainDiagnostics];
    if (_stderrFD >= 0) { close(_stderrFD); _stderrFD = -1; }
}
- (BOOL)startWorker:(NSString **)error {
    if (_pid > 0) {
        pid_t result;
        do { result = waitpid(_pid, NULL, WNOHANG); } while (result < 0 && errno == EINTR);
        if (result == 0) return YES;
        _pid = -1;
        if (_fd >= 0) { close(_fd); _fd = -1; }
        if (_stderrFD >= 0) { close(_stderrFD); _stderrFD = -1; }
    }
    NSString *path = MCPResolvedJailbreakPath(@"/usr/libexec/ios-mcp/mcp-ocr-worker");
    NSString *resources = MCPResolvedJailbreakPath(@"/usr/share/ios-mcp/paddleocr");
    if (![[NSFileManager defaultManager] isExecutableFileAtPath:path]) {
        if (error) *error = @"PaddleOCR: worker is missing or not executable";
        return NO;
    }
    int pair[2];
    if (socketpair(AF_UNIX, SOCK_STREAM, 0, pair)) { if (error) *error = @"PaddleOCR: socketpair failed"; return NO; }
    int diagnostics[2];
    if (pipe(diagnostics)) { close(pair[0]); close(pair[1]); if (error) *error = @"PaddleOCR: diagnostic pipe failed"; return NO; }
    if (!MCPKeepFDAboveStdio(&pair[0]) || !MCPKeepFDAboveStdio(&pair[1]) ||
        !MCPKeepFDAboveStdio(&diagnostics[0]) || !MCPKeepFDAboveStdio(&diagnostics[1])) {
        close(pair[0]); close(pair[1]); close(diagnostics[0]); close(diagnostics[1]);
        if (error) *error = @"PaddleOCR: could not reserve worker IPC descriptors";
        return NO;
    }
    fcntl(diagnostics[0], F_SETFL, O_NONBLOCK);
    fcntl(diagnostics[0], F_SETFD, FD_CLOEXEC); fcntl(diagnostics[1], F_SETFD, FD_CLOEXEC);
    _diagnostics = [NSMutableData data]; _exitStatus = 0;
    int yes = 1;
    setsockopt(pair[0], SOL_SOCKET, SO_NOSIGPIPE, &yes, sizeof(yes));
    fcntl(pair[0], F_SETFL, O_NONBLOCK);
    fcntl(pair[0], F_SETFD, FD_CLOEXEC); fcntl(pair[1], F_SETFD, FD_CLOEXEC);
    posix_spawn_file_actions_t actions;
    posix_spawn_file_actions_init(&actions);
    posix_spawn_file_actions_adddup2(&actions, pair[1], STDIN_FILENO);
    posix_spawn_file_actions_adddup2(&actions, pair[1], STDOUT_FILENO);
    posix_spawn_file_actions_adddup2(&actions, diagnostics[1], STDERR_FILENO);
    posix_spawn_file_actions_addclose(&actions, diagnostics[0]);
    posix_spawn_file_actions_addclose(&actions, diagnostics[1]);
    posix_spawn_file_actions_addclose(&actions, pair[0]);
    posix_spawn_file_actions_addclose(&actions, pair[1]);
    posix_spawnattr_t attr;
    posix_spawnattr_init(&attr);
    posix_spawnattr_setflags(&attr, POSIX_SPAWN_CLOEXEC_DEFAULT);
    char *argv[] = {(char *)path.fileSystemRepresentation, "--resources", (char *)resources.fileSystemRepresentation, NULL};
    // Do not carry tweak injection into the inference subprocess.
    char *env[] = {"PATH=/usr/bin:/bin", "LANG=en_US.UTF-8", NULL};
    int status = posix_spawn(&_pid, path.fileSystemRepresentation, &actions, &attr, argv, env);
    posix_spawnattr_destroy(&attr); posix_spawn_file_actions_destroy(&actions);
    close(pair[1]);
    close(diagnostics[1]);
    if (status) {
        close(pair[0]); close(diagnostics[0]); _pid = -1;
        if (error) *error = [NSString stringWithFormat:@"PaddleOCR: worker launch failed: %s", strerror(status)];
        return NO;
    }
    _fd = pair[0];
    _stderrFD = diagnostics[0];
    [MCPLogger log:@"[OCR] engine=paddleocr worker_started pid=%d provider=CPUExecutionProvider", _pid];
    return YES;
}
- (BOOL)transfer:(void *)bytes length:(size_t)length writing:(BOOL)writing context:(MCPOCRRequestContext *)context {
    uint8_t *p = bytes;
    while (length && ![context shouldStop]) {
        [self drainDiagnostics];
        struct pollfd f = {_fd, writing ? POLLOUT : POLLIN, 0};
        int ready = poll(&f, 1, 50);
        // Some jailbreak SpringBoard sandboxes reject poll on AF_UNIX with EPERM.
        // select has the same bounded readiness semantics without a busy loop.
        if (ready < 0 && errno == EPERM && _fd < FD_SETSIZE) {
            f.revents = 0;
            fd_set descriptors; FD_ZERO(&descriptors); FD_SET(_fd, &descriptors);
            struct timeval timeout = {0, 50000};
            ready = select(_fd + 1, writing ? NULL : &descriptors, writing ? &descriptors : NULL, NULL, &timeout);
        }
        if (ready < 0 && errno == EINTR) continue;
        if (ready < 0 || (f.revents & (POLLERR | POLLNVAL))) {
            [_diagnostics appendData:[[NSString stringWithFormat:@"IPC poll failed fd=%d events=%d errno=%d; ", _fd, f.revents, errno] dataUsingEncoding:NSUTF8StringEncoding]];
            return NO;
        }
        if (!ready) continue;
        ssize_t n = writing ? send(_fd, p, length, MSG_DONTWAIT) : recv(_fd, p, length, MSG_DONTWAIT);
        if (n < 0 && (errno == EINTR || errno == EAGAIN)) continue;
        if (n <= 0) {
            [_diagnostics appendData:[[NSString stringWithFormat:@"IPC %@ failed fd=%d result=%ld errno=%d; ", writing ? @"send" : @"recv", _fd, (long)n, errno] dataUsingEncoding:NSUTF8StringEncoding]];
            return NO;
        }
        p += n; length -= n;
    }
    return length == 0 && ![context shouldStop];
}
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages minConfidence:(double)minConfidence
                                      region:(NSDictionary *)region fast:(BOOL)fast error:(NSString **)error {
    if (error) *error = nil;
    if (NSThread.isMainThread) { if (error) *error = @"PaddleOCR: call from a background thread"; return nil; }
    for (NSString *language in languages) {
        NSString *tag = [[language stringByReplacingOccurrencesOfString:@"_" withString:@"-"] lowercaseString];
        if (![@[@"zh", @"zh-hans", @"zh-hant", @"zh-cn", @"zh-tw", @"en", @"en-us", @"en-gb"] containsObject:tag]) {
            if (error) *error = [NSString stringWithFormat:@"PaddleOCR: unsupported recognition language %@ (model supports Chinese and English)", language];
            return nil;
        }
    }
    if (![_gate tryLock]) { if (error) *error = @"PaddleOCR: busy (1 active request, queue limit 0); retry later"; return nil; }
    @try {
        MCPOCRRequestContext *context = [MCPOCRRequestContext current];
        if (!context) { context = [MCPOCRRequestContext new]; context.clientSocket = -1; context.deadline = NSProcessInfo.processInfo.systemUptime + 30; }
        if ([context shouldStop]) { if (error) *error = @"PaddleOCR: request cancelled or timed out"; return nil; }
        MCPScreenGeometry geometry;
        UIImage *image = [[ScreenManager sharedInstance] captureScreenImageWithGeometry:&geometry];
        if (!image.CGImage) { if (error) *error = @"PaddleOCR: screen capture failed"; return nil; }
        size_t pw = CGImageGetWidth(image.CGImage), ph = CGImageGetHeight(image.CGImage);
        if (!pw || !ph || pw > 8192 || ph > 8192 || pw * ph > 16000000) {
            if (error) *error = @"PaddleOCR: screenshot exceeds 16 megapixel / 8192 edge limit"; return nil;
        }
        double W = geometry.interfaceBounds.size.width, H = geometry.interfaceBounds.size.height;
        if (W < 1 || H < 1) { if (error) *error = @"PaddleOCR: invalid screen geometry"; return nil; }
        CGRect fixedRegion = geometry.fixedBounds;
        if (region) fixedRegion = CGRectIntersection(fixedRegion, CGRectMake([region[@"x"] doubleValue], [region[@"y"] doubleValue],
                                                            [region[@"width"] doubleValue], [region[@"height"] doubleValue]));
        NSMutableDictionary *recognition = [@{@"engine": @"paddleocr", @"provider": @"CPUExecutionProvider",
            @"runtime": @"onnxruntime-1.20.1", @"model": @"PP-OCRv5_mobile", @"uses_cpu_only": @YES,
            @"requested_level": fast ? @"fast" : @"accurate", @"level": @"mobile", @"languages": @[@"zh-Hans", @"en-US"],
            @"revision": @5, @"adjustments": @[@"fixed_mobile_model"], @"confidence_metric": @"mean_ctc_probability"} mutableCopy];
        NSDictionary *screen = @{@"width": @((int)round(geometry.fixedBounds.size.width)),
            @"height": @((int)round(geometry.fixedBounds.size.height)), @"coordinate_space": @"fixed"};
        if (CGRectIsNull(fixedRegion) || CGRectIsEmpty(fixedRegion))
            return @{@"texts": @[], @"count": @0, @"recognition": recognition, @"screen": screen};
        CGRect oriented = CGRectApplyAffineTransform(fixedRegion, CGAffineTransformInvert(geometry.interfaceToFixed));
        oriented = CGRectIntersection(oriented, CGRectMake(0, 0, W, H));
        int orientation = 1;
        if (geometry.interfaceOrientation == UIInterfaceOrientationLandscapeLeft) orientation = 8;
        else if (geometry.interfaceOrientation == UIInterfaceOrientationLandscapeRight) orientation = 6;
        else if (geometry.interfaceOrientation == UIInterfaceOrientationPortraitUpsideDown) orientation = 3;
        NSData *png = UIImagePNGRepresentation(image);
        if (!png || png.length > 24 * 1024 * 1024) { if (error) *error = @"PaddleOCR: image encoding failed or exceeds 24 MB"; return nil; }
        NSDictionary *payload = @{@"image": [png base64EncodedStringWithOptions:0], @"orientation": @(orientation),
            @"min_confidence": @(minConfidence), @"roi": @[@(oriented.origin.x / W), @(oriented.origin.y / H),
            @(oriented.size.width / W), @(oriented.size.height / H)]};
        NSData *data = [NSJSONSerialization dataWithJSONObject:payload options:0 error:nil];
        if (!data || data.length > 32 * 1024 * 1024) { if (error) *error = @"PaddleOCR: request payload too large"; return nil; }
        if (![self startWorker:error]) return nil;
        uint32_t length = htonl((uint32_t)data.length), responseLength = 0;
        BOOL ok = [self transfer:&length length:4 writing:YES context:context] &&
                  [self transfer:(void *)data.bytes length:data.length writing:YES context:context] &&
                  [self transfer:&responseLength length:4 writing:NO context:context];
        responseLength = ntohl(responseLength);
        NSMutableData *response = nil;
        if (ok && responseLength > 0 && responseLength <= 1024 * 1024) {
            response = [NSMutableData dataWithLength:responseLength];
            ok = [self transfer:response.mutableBytes length:responseLength writing:NO context:context];
        } else ok = NO;
        if (!ok) {
            NSString *reason = [context shouldStop] ? @"cancelled, disconnected or exceeded 30 second deadline" : @"worker exited or returned invalid IPC (including memory limit)";
            [self stopWorker];
            NSString *diagnostics = [[NSString alloc] initWithData:_diagnostics encoding:NSUTF8StringEncoding] ?: @"";
            if (error) *error = [NSString stringWithFormat:@"PaddleOCR: %@ (worker status=%d). %@", reason, _exitStatus, diagnostics];
            return nil;
        }
        NSDictionary *result = [NSJSONSerialization JSONObjectWithData:response options:0 error:nil];
        if (![result isKindOfClass:NSDictionary.class] || result[@"error"] || ![result[@"texts"] isKindOfClass:NSArray.class]) {
            if (error) *error = [result isKindOfClass:NSDictionary.class] && [result[@"error"] isKindOfClass:NSString.class] ? result[@"error"] : @"PaddleOCR: invalid worker result";
            [self stopWorker]; return nil;
        }
        recognition[@"worker_pid"] = result[@"worker_pid"];
        // Successful initialization warnings must not pollute a later cancellation error.
        [self drainDiagnostics];
        [_diagnostics setLength:0];
        NSMutableArray *texts = [NSMutableArray array];
        for (NSDictionary *item in result[@"texts"]) {
            NSArray *b = item[@"box"];
            if (![b isKindOfClass:NSArray.class] || b.count != 4) { [self stopWorker]; if (error) *error = @"PaddleOCR: malformed box"; return nil; }
            CGRect rect = CGRectApplyAffineTransform(CGRectMake([b[0] doubleValue] * W, [b[1] doubleValue] * H,
                                         [b[2] doubleValue] * W, [b[3] doubleValue] * H), geometry.interfaceToFixed);
            rect = CGRectIntersection(rect, fixedRegion);
            if (CGRectIsEmpty(rect) || CGRectIsNull(rect)) continue;
            int x = round(rect.origin.x), y = round(rect.origin.y), w = round(rect.size.width), h = round(rect.size.height);
            [texts addObject:@{@"text": item[@"text"], @"confidence": @(round([item[@"confidence"] doubleValue] * 100) / 100),
                @"rect": @{@"x": @(x), @"y": @(y), @"width": @(w), @"height": @(h)}, @"tap": @{@"x": @(x + w / 2), @"y": @(y + h / 2)}}];
        }
        [MCPLogger log:@"[OCR] engine=paddleocr provider=CPUExecutionProvider pid=%d count=%lu", _pid, (unsigned long)texts.count];
        return @{@"texts": texts, @"count": @(texts.count), @"recognition": recognition, @"screen": screen};
    } @catch (NSException *exception) {
        [self stopWorker];
        if (error) *error = [NSString stringWithFormat:@"PaddleOCR: %@", exception.reason];
        return nil;
    } @finally { [_gate unlock]; }
}
@end
