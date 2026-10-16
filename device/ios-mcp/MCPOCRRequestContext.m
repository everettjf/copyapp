#import "MCPOCRRequestContext.h"
#include <sys/socket.h>
#include <errno.h>

@implementation MCPOCRRequestContext {
    NSString *_key;
}
+ (NSMutableDictionary *)requests {
    static NSMutableDictionary *requests;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ requests = [NSMutableDictionary dictionary]; });
    return requests;
}
+ (NSString *)key:(id)requestID session:(NSString *)session {
    if (![requestID isKindOfClass:NSString.class] && ![requestID isKindOfClass:NSNumber.class]) return nil;
    NSData *data = [NSJSONSerialization dataWithJSONObject:@[session ?: @"", requestID] options:0 error:nil];
    return [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
}
+ (instancetype)current { return NSThread.currentThread.threadDictionary[@"MCPOCRRequestContext"]; }
+ (instancetype)beginRequest:(id)requestID session:(NSString *)session socket:(int)socket {
    MCPOCRRequestContext *ctx = [self new];
    ctx.clientSocket = socket;
    ctx.deadline = NSProcessInfo.processInfo.systemUptime + 30;
    ctx->_key = [self key:requestID session:session];
    @synchronized([self requests]) {
        if (ctx->_key && [self requests][ctx->_key]) return nil;
        if (ctx->_key) [self requests][ctx->_key] = ctx;
    }
    NSThread.currentThread.threadDictionary[@"MCPOCRRequestContext"] = ctx;
    return ctx;
}
+ (void)cancelRequest:(id)requestID session:(NSString *)session {
    NSString *key = [self key:requestID session:session];
    if (!key) return;
    @synchronized([self requests]) { ((MCPOCRRequestContext *)[self requests][key]).cancelled = YES; }
}
- (BOOL)shouldStop {
    if (self.cancelled || NSProcessInfo.processInfo.systemUptime >= self.deadline) return YES;
    if (self.clientSocket >= 0) {
        char byte;
        ssize_t n = recv(self.clientSocket, &byte, 1, MSG_PEEK | MSG_DONTWAIT);
        if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK && errno != EINTR)) return YES;
    }
    return NO;
}
- (void)finish {
    @synchronized([MCPOCRRequestContext requests]) {
        if (_key && [MCPOCRRequestContext requests][_key] == self) [[MCPOCRRequestContext requests] removeObjectForKey:_key];
    }
    [NSThread.currentThread.threadDictionary removeObjectForKey:@"MCPOCRRequestContext"];
}
@end
