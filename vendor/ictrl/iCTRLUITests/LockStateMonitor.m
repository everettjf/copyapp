#import "LockStateMonitor.h"
#import <notify.h>
#import <XCTest/XCTest.h>

@interface XCUIDevice (FBPrivate)
- (void)pressLockButton;
@end

@implementation LockStateMonitor {
    BOOL _isLocked;
    int _notifyToken;
}

+ (instancetype)sharedMonitor {
    static LockStateMonitor *sharedInstance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        sharedInstance = [[self alloc] init];
    });
    return sharedInstance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _isLocked = NO;
        int status = notify_register_dispatch("com.apple.springboard.lockstate",
                                             &_notifyToken,
                                             dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_HIGH, 0),
                                             ^(int token) {
            uint64_t state = UINT64_MAX;
            notify_get_state(token, &state);
            self->_isLocked = (state != 0);
        });
        if (status != NOTIFY_STATUS_OK) {
            NSLog(@"iCTRL: Failed to register lock state notifications");
        }
    }
    return self;
}

- (BOOL)isLocked {
    return _isLocked;
}

- (BOOL)lockScreenWithTimeout:(NSTimeInterval)timeout error:(NSError **)error {
    if (_isLocked) return YES;

    [[XCUIDevice sharedDevice] pressLockButton];

    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
    while ([NSDate date].timeIntervalSinceReferenceDate < deadline.timeIntervalSinceReferenceDate) {
        if (_isLocked) return YES;
        [NSThread sleepForTimeInterval:0.1];
    }

    if (error) {
        *error = [NSError errorWithDomain:@"LockStateMonitor" code:1
                    userInfo:@{NSLocalizedDescriptionKey: @"Lock timeout"}];
    }
    return NO;
}

- (BOOL)unlockScreenWithTimeout:(NSTimeInterval)timeout error:(NSError **)error {
    if (!_isLocked) return YES;

    [[XCUIDevice sharedDevice] pressButton:XCUIDeviceButtonHome];
    [NSThread sleepForTimeInterval:1.0];
    [[XCUIDevice sharedDevice] pressButton:XCUIDeviceButtonHome];
    [NSThread sleepForTimeInterval:1.0];

    NSDate *deadline = [NSDate dateWithTimeIntervalSinceNow:timeout];
    while ([NSDate date].timeIntervalSinceReferenceDate < deadline.timeIntervalSinceReferenceDate) {
        if (!_isLocked) return YES;
        [NSThread sleepForTimeInterval:0.1];
    }

    if (error) {
        *error = [NSError errorWithDomain:@"LockStateMonitor" code:2
                    userInfo:@{NSLocalizedDescriptionKey: @"Unlock timeout (passcode may be required)"}];
    }
    return NO;
}

- (void)dealloc {
    notify_cancel(_notifyToken);
}

@end
