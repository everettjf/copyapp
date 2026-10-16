#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface LockStateMonitor : NSObject

+ (instancetype)sharedMonitor;

@property (nonatomic, readonly) BOOL isLocked;

- (BOOL)lockScreenWithTimeout:(NSTimeInterval)timeout error:(NSError *__autoreleasing _Nullable * _Nullable)error;
- (BOOL)unlockScreenWithTimeout:(NSTimeInterval)timeout error:(NSError *__autoreleasing _Nullable * _Nullable)error;

@end

NS_ASSUME_NONNULL_END
