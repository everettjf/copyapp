#import <Foundation/Foundation.h>

/// Per-request cancellation; no engine selection is stored here or globally.
@interface MCPOCRRequestContext : NSObject
@property (atomic) BOOL cancelled;
@property (nonatomic) int clientSocket;
@property (nonatomic) NSTimeInterval deadline;
+ (instancetype)current;
+ (instancetype)beginRequest:(id)requestID session:(NSString *)session socket:(int)socket;
+ (void)cancelRequest:(id)requestID session:(NSString *)session;
- (BOOL)shouldStop;
- (void)finish;
@end
