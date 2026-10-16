#import "HIDManager.h"
#import "IOHIDPrivate.h"
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import "MCPLogger.h"

#define HID_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[HID] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)

static uint64_t _touchSenderID = 0x8000000817319372;
static double _deviceScreenWidth = 0;
static double _deviceScreenHeight = 0;
// Keep a tap down long enough for UIKit controls such as UISwitch to observe it as a real touch.
// Dispatching began/moved/ended back-to-back can be coalesced before the control processes it.
static const useconds_t kIOSMCPTapPhaseDelayUs = 50 * 1000;

#define MAX_FINGER_INDEX 20
#define TOUCH_EVENT_NOT_VALID 0
#define TOUCH_EVENT_VALID 1
#define TOUCH_EVENT_VALID_AT_NEXT_APPEND 2
#define TOUCH_EVENT_VALID_INDEX 0
#define TOUCH_EVENT_TYPE_INDEX 1
#define TOUCH_EVENT_X_INDEX 2
#define TOUCH_EVENT_Y_INDEX 3

static int _eventsToAppend[MAX_FINGER_INDEX][4];

@implementation IOSMCPHIDManager {
    IOHIDEventSystemClientRef _hidClient;
    dispatch_queue_t _hidQueue;
    CGFloat _screenScale;
    CGFloat _screenWidth;
    CGFloat _screenHeight;
}

+ (instancetype)sharedInstance {
    static IOSMCPHIDManager *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[IOSMCPHIDManager alloc] init];
    });
    return instance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _hidQueue = dispatch_queue_create("com.witchan.ios-mcp.hid", DISPATCH_QUEUE_SERIAL);
        _hidClient = IOHIDEventSystemClientCreate(kCFAllocatorDefault);
        if (!_hidClient) {
            HID_LOG(@"ERROR: Failed to create IOHIDEventSystemClient");
        }

        dispatch_block_t initBlock = ^{
            UIScreen *screen = [UIScreen mainScreen];
            self->_screenScale = screen.scale;
            // Digitizer coordinates follow the fixed screen, not the interface orientation at
            // the time this lazy singleton happens to be initialized (which may be landscape).
            self->_screenWidth = screen.fixedCoordinateSpace.bounds.size.width;
            self->_screenHeight = screen.fixedCoordinateSpace.bounds.size.height;
            _deviceScreenWidth = self->_screenWidth;
            _deviceScreenHeight = self->_screenHeight;
            memset(_eventsToAppend, 0, sizeof(_eventsToAppend));
            HID_LOG(@"Screen: %.0fx%.0f @%.0fx", self->_screenWidth, self->_screenHeight, self->_screenScale);

            HID_LOG(@"Using fixed sender ID: %llu", _touchSenderID);
        };

        if ([NSThread isMainThread]) {
            initBlock();
        } else {
            dispatch_sync(dispatch_get_main_queue(), initBlock);
        }
    }
    return self;
}

#pragma mark - Button Simulation

- (void)pressButton:(HIDButtonType)button duration:(NSTimeInterval)durationMs completion:(void (^)(BOOL, NSString *))completion {
    dispatch_async(_hidQueue, ^{
        @try {
            uint32_t usagePage = kHIDPage_Consumer;
            uint32_t usage;

            switch (button) {
                case HIDButtonVolumeUp:   usage = kHIDUsage_Csmr_VolumeIncrement; break;
                case HIDButtonVolumeDown: usage = kHIDUsage_Csmr_VolumeDecrement; break;
                case HIDButtonPower:      usage = kHIDUsage_Csmr_Power;           break;
                case HIDButtonHome:       usage = kHIDUsage_Csmr_Menu;            break;
                case HIDButtonMute:       usage = kHIDUsage_Csmr_Mute;            break;
                default:
                    if (completion) completion(NO, @"Unknown button type");
                    return;
            }

            NSString *error = nil;
            if (![self sendKeyboardEventWithPage:usagePage usage:usage down:YES error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            NSTimeInterval ms = durationMs > 0 ? durationMs : 100;
            usleep((useconds_t)(ms * 1000));

            if (![self sendKeyboardEventWithPage:usagePage usage:usage down:NO error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            if (completion) completion(YES, nil);
        } @catch (NSException *exception) {
            HID_LOG(@"Button dispatch exception: %@ - %@", exception.name, exception.reason);
            if (completion) completion(NO, exception.reason ?: exception.name ?: @"Button dispatch exception");
        }
    });
}

- (BOOL)sendKeyboardEventWithPage:(uint32_t)page usage:(uint32_t)usage down:(BOOL)down error:(NSString **)error {
    IOHIDEventRef event = IOHIDEventCreateKeyboardEvent(
        kCFAllocatorDefault,
        mach_absolute_time(),
        page,
        usage,
        down,
        0
    );
    if (!event) {
        if (error) *error = @"Failed to create keyboard HID event";
        return NO;
    }

    IOHIDEventSetIntegerValue(event, 4, 1); // flags
    BOOL ok = [self postHIDEvent:event error:error];
    CFRelease(event);
    return ok;
}

- (BOOL)postHIDEvent:(IOHIDEventRef)event error:(NSString **)error {
    if (!_hidClient) {
        if (error) *error = @"HID client not initialized";
        return NO;
    }

    if (_touchSenderID == 0) {
        HID_LOG(@"ERROR: Fixed sender ID is zero");
        if (error) *error = @"Fixed sender ID is zero";
        return NO;
    }

    IOHIDEventSetSenderID(event, _touchSenderID);
    IOHIDEventSystemClientDispatchEvent(_hidClient, event);
    return YES;
}

#pragma mark - Touch Event Dispatch

static double normalizedTouchX(CGFloat x) {
    double width = _deviceScreenWidth > 0 ? _deviceScreenWidth : 1;
    return x / width;
}

static double normalizedTouchY(CGFloat y) {
    double height = _deviceScreenHeight > 0 ? _deviceScreenHeight : 1;
    return y / height;
}

static IOHIDEventRef createChildTouchEvent(TouchPhase phase, int index, CGPoint point) {
    uint32_t eventMask = 0;
    BOOL range = YES;
    BOOL touch = YES;

    switch (phase) {
        case TouchPhaseBegan:
            eventMask = kIOHIDDigitizerEventRange | kIOHIDDigitizerEventTouch;
            range = YES;
            touch = YES;
            break;
        case TouchPhaseMoved:
            eventMask = kIOHIDDigitizerEventPosition;
            range = YES;
            touch = YES;
            break;
        case TouchPhaseEnded:
            eventMask = kIOHIDDigitizerEventTouch;
            range = NO;
            touch = NO;
            break;
    }

    IOHIDEventRef child = IOHIDEventCreateDigitizerFingerEvent(
        kCFAllocatorDefault,
        mach_absolute_time(),
        index,
        3,
        eventMask,
        normalizedTouchX(point.x),
        normalizedTouchY(point.y),
        0.0f,
        0.0f,
        0.0f,
        range,
        touch,
        0
    );
    if (!child) return NULL;

    IOHIDEventSetFloatValue(child, 0xb0014, 0.04f);
    IOHIDEventSetFloatValue(child, 0xb0015, 0.04f);
    return child;
}

static void appendChildTouchEvent(IOHIDEventRef parent, TouchPhase phase, int index, CGPoint point) {
    IOHIDEventRef child = createChildTouchEvent(phase, index, point);
    if (child) {
        IOHIDEventAppendEvent(parent, child, 0);
        CFRelease(child);
    }
}

- (BOOL)performTouchAtPoint:(CGPoint)point phase:(TouchPhase)phase error:(NSString **)error {
    IOHIDEventRef parent = IOHIDEventCreateDigitizerEvent(
        kCFAllocatorDefault,
        mach_absolute_time(),
        kIOHIDDigitizerTransducerTypeHand,
        99,
        1,
        0,
        0,
        0.0f,
        0.0f,
        0.0f,
        0.0f,
        0.0f,
        0.0f,
        0,
        0,
        0
    );
    if (!parent) {
        if (error) *error = @"Failed to create parent touch HID event";
        return NO;
    }

    IOHIDEventSetIntegerValue(parent, 0xb0019, 1);
    IOHIDEventSetIntegerValue(parent, 0x4, 1);

    const int fingerIndex = 1;
    appendChildTouchEvent(parent, phase, fingerIndex, point);

    switch (phase) {
        case TouchPhaseMoved:
        case TouchPhaseBegan:
            _eventsToAppend[fingerIndex][TOUCH_EVENT_VALID_INDEX] = TOUCH_EVENT_VALID_AT_NEXT_APPEND;
            _eventsToAppend[fingerIndex][TOUCH_EVENT_TYPE_INDEX] = (int)phase;
            _eventsToAppend[fingerIndex][TOUCH_EVENT_X_INDEX] = (int)point.x;
            _eventsToAppend[fingerIndex][TOUCH_EVENT_Y_INDEX] = (int)point.y;
            break;
        case TouchPhaseEnded:
            _eventsToAppend[fingerIndex][TOUCH_EVENT_VALID_INDEX] = TOUCH_EVENT_NOT_VALID;
            break;
    }

    for (int i = 0; i < MAX_FINGER_INDEX; i++) {
        if (_eventsToAppend[i][TOUCH_EVENT_VALID_INDEX] == TOUCH_EVENT_VALID) {
            CGPoint savedPoint = CGPointMake(_eventsToAppend[i][TOUCH_EVENT_X_INDEX], _eventsToAppend[i][TOUCH_EVENT_Y_INDEX]);
            appendChildTouchEvent(parent, (TouchPhase)_eventsToAppend[i][TOUCH_EVENT_TYPE_INDEX], i, savedPoint);
        } else if (_eventsToAppend[i][TOUCH_EVENT_VALID_INDEX] == TOUCH_EVENT_VALID_AT_NEXT_APPEND) {
            _eventsToAppend[i][TOUCH_EVENT_VALID_INDEX] = TOUCH_EVENT_VALID;
        }
    }

    IOHIDEventSetIntegerValue(parent, 0xb0007, 0x23);
    IOHIDEventSetIntegerValue(parent, 0xb0008, 0x1);
    IOHIDEventSetIntegerValue(parent, 0xb0009, 0x1);

    BOOL ok = [self postHIDEvent:parent error:error];
    CFRelease(parent);
    return ok;
}

- (void)sendTouchAtPoint:(CGPoint)point phase:(TouchPhase)phase {
    NSString *error = nil;
    [self performTouchAtPoint:point phase:phase error:&error];
    if (error.length > 0) {
        HID_LOG(@"Touch dispatch failed: %@", error);
    }
}

#pragma mark - Tap

- (BOOL)performTapSequenceAtPoint:(CGPoint)point error:(NSString **)error {
    if (![self performTouchAtPoint:point phase:TouchPhaseBegan error:error]) {
        return NO;
    }
    usleep(kIOSMCPTapPhaseDelayUs);

    if (![self performTouchAtPoint:point phase:TouchPhaseMoved error:error]) {
        return NO;
    }
    usleep(kIOSMCPTapPhaseDelayUs);

    return [self performTouchAtPoint:point phase:TouchPhaseEnded error:error];
}

- (void)tapAtPoint:(CGPoint)point completion:(void (^)(BOOL, NSString *))completion {
    dispatch_async(_hidQueue, ^{
        @try {
            NSString *error = nil;
            if (![self performTapSequenceAtPoint:point error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            if (completion) completion(YES, nil);
        } @catch (NSException *exception) {
            HID_LOG(@"Tap dispatch exception: %@ - %@", exception.name, exception.reason);
            if (completion) completion(NO, exception.reason ?: exception.name ?: @"Tap dispatch exception");
        }
    });
}

#pragma mark - Swipe

- (void)swipeFromPoint:(CGPoint)from
               toPoint:(CGPoint)to
              duration:(NSTimeInterval)durationMs
                 steps:(NSInteger)steps
            completion:(void (^)(BOOL, NSString *))completion {

    dispatch_async(_hidQueue, ^{
        @try {
            NSString *error = nil;
            NSTimeInterval duration = durationMs > 0 ? durationMs : 300;
            NSInteger totalSteps = steps > 0 ? steps : 20;
            useconds_t stepDelay = (useconds_t)((duration * 1000.0) / totalSteps);

            if (![self performTouchAtPoint:from phase:TouchPhaseBegan error:&error]) {
                if (completion) completion(NO, error);
                return;
            }
            usleep(stepDelay);

            for (NSInteger i = 1; i <= totalSteps; i++) {
                CGFloat t = (CGFloat)i / (CGFloat)totalSteps;
                CGPoint current = CGPointMake(
                    from.x + (to.x - from.x) * t,
                    from.y + (to.y - from.y) * t
                );
                if (![self performTouchAtPoint:current phase:TouchPhaseMoved error:&error]) {
                    if (completion) completion(NO, error);
                    return;
                }
                if (i < totalSteps) {
                    usleep(stepDelay);
                }
            }

            usleep(10000);
            if (![self performTouchAtPoint:to phase:TouchPhaseEnded error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            if (completion) completion(YES, nil);
        } @catch (NSException *exception) {
            HID_LOG(@"Swipe dispatch exception: %@ - %@", exception.name, exception.reason);
            if (completion) completion(NO, exception.reason ?: exception.name ?: @"Swipe dispatch exception");
        }
    });
}

#pragma mark - Long Press

- (void)longPressAtPoint:(CGPoint)point
                duration:(NSTimeInterval)durationMs
              completion:(void (^)(BOOL, NSString *))completion {
    // Implement as a stationary swipe (same start/end point) which is proven stable
    CGPoint to = CGPointMake(point.x + 0.5, point.y + 0.5);
    NSTimeInterval duration = durationMs > 0 ? durationMs : 500;
    NSInteger steps = (NSInteger)(duration / 50);
    if (steps < 2) steps = 2;
    [self swipeFromPoint:point toPoint:to duration:duration steps:steps completion:completion];
}

#pragma mark - Double Tap

- (void)doubleTapAtPoint:(CGPoint)point
                interval:(NSTimeInterval)intervalMs
              completion:(void (^)(BOOL, NSString *))completion {
    dispatch_async(_hidQueue, ^{
        @try {
            NSString *error = nil;
            NSTimeInterval interval = intervalMs > 0 ? intervalMs : 100;

            if (![self performTapSequenceAtPoint:point error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            usleep((useconds_t)(interval * 1000));

            if (![self performTapSequenceAtPoint:point error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            if (completion) completion(YES, nil);
        } @catch (NSException *exception) {
            HID_LOG(@"Double tap dispatch exception: %@ - %@", exception.name, exception.reason);
            if (completion) completion(NO, exception.reason ?: exception.name ?: @"Double tap dispatch exception");
        }
    });
}

#pragma mark - Drag and Drop

- (void)dragAlongPoints:(NSArray<NSValue *> *)points
           holdDuration:(NSTimeInterval)holdMs
           moveDuration:(NSTimeInterval)moveMs
                  steps:(NSInteger)steps
             completion:(void (^)(BOOL, NSString *))completion {
    dispatch_async(_hidQueue, ^{
        @try {
            if (points.count < 2) {
                if (completion) completion(NO, @"Drag path requires at least 2 points");
                return;
            }

            NSString *error = nil;
            NSTimeInterval hold = holdMs > 0 ? holdMs : 500;
            NSTimeInterval move = moveMs > 0 ? moveMs : 300;
            NSInteger totalSteps = steps > 0 ? steps : 20;
            NSUInteger segmentCount = points.count - 1;
            if (totalSteps < (NSInteger)segmentCount) {
                totalSteps = (NSInteger)segmentCount;
            }

            CGPoint firstPoint = [points.firstObject CGPointValue];
            CGPoint lastPoint = [points.lastObject CGPointValue];

            NSInteger holdSteps = (NSInteger)(hold / 50);
            if (holdSteps < 2) holdSteps = 2;
            useconds_t holdStepDelay = (useconds_t)((hold * 1000.0) / holdSteps);

            if (![self performTouchAtPoint:firstPoint phase:TouchPhaseBegan error:&error]) {
                if (completion) completion(NO, error);
                return;
            }
            usleep(holdStepDelay);

            for (NSInteger i = 1; i <= holdSteps; i++) {
                if (![self performTouchAtPoint:firstPoint phase:TouchPhaseMoved error:&error]) {
                    if (completion) completion(NO, error);
                    return;
                }
                if (i < holdSteps) {
                    usleep(holdStepDelay);
                }
            }

            useconds_t moveStepDelay = (useconds_t)((move * 1000.0) / totalSteps);
            NSMutableArray<NSNumber *> *segmentWeights = [NSMutableArray arrayWithCapacity:segmentCount];
            CGFloat remainingWeight = 0;
            for (NSUInteger i = 0; i < segmentCount; i++) {
                CGPoint a = [points[i] CGPointValue];
                CGPoint b = [points[i + 1] CGPointValue];
                CGFloat dx = b.x - a.x;
                CGFloat dy = b.y - a.y;
                CGFloat weight = (dx >= 0 ? dx : -dx) + (dy >= 0 ? dy : -dy);
                [segmentWeights addObject:@(weight)];
                remainingWeight += weight;
            }

            NSInteger remainingSteps = totalSteps;

            for (NSUInteger segmentIndex = 0; segmentIndex < segmentCount; segmentIndex++) {
                CGPoint segmentStart = [points[segmentIndex] CGPointValue];
                CGPoint segmentEnd = [points[segmentIndex + 1] CGPointValue];
                NSInteger segmentsLeft = (NSInteger)(segmentCount - segmentIndex);
                NSInteger segmentSteps = remainingSteps;
                if (segmentsLeft > 1) {
                    NSInteger minRemaining = segmentsLeft - 1;
                    NSInteger maxForSegment = remainingSteps - minRemaining;
                    if (remainingWeight > 0) {
                        CGFloat weight = [segmentWeights[segmentIndex] doubleValue];
                        segmentSteps = (NSInteger)((weight / remainingWeight) * remainingSteps + 0.5);
                    } else {
                        segmentSteps = remainingSteps / segmentsLeft;
                    }
                    if (segmentSteps < 1) segmentSteps = 1;
                    if (segmentSteps > maxForSegment) segmentSteps = maxForSegment;
                }

                for (NSInteger i = 1; i <= segmentSteps; i++) {
                    CGFloat t = (CGFloat)i / (CGFloat)segmentSteps;
                    CGPoint current = CGPointMake(
                        segmentStart.x + (segmentEnd.x - segmentStart.x) * t,
                        segmentStart.y + (segmentEnd.y - segmentStart.y) * t
                    );
                    if (![self performTouchAtPoint:current phase:TouchPhaseMoved error:&error]) {
                        if (completion) completion(NO, error);
                        return;
                    }
                    if (remainingSteps > 1) {
                        usleep(moveStepDelay);
                    }
                    remainingSteps--;
                }

                remainingWeight -= [segmentWeights[segmentIndex] doubleValue];
            }

            usleep(10000);
            if (![self performTouchAtPoint:lastPoint phase:TouchPhaseEnded error:&error]) {
                if (completion) completion(NO, error);
                return;
            }

            if (completion) completion(YES, nil);
        } @catch (NSException *exception) {
            HID_LOG(@"Drag dispatch exception: %@ - %@", exception.name, exception.reason);
            if (completion) completion(NO, exception.reason ?: exception.name ?: @"Drag dispatch exception");
        }
    });
}

- (void)dragFromPoint:(CGPoint)from
              toPoint:(CGPoint)to
         holdDuration:(NSTimeInterval)holdMs
         moveDuration:(NSTimeInterval)moveMs
                steps:(NSInteger)steps
           completion:(void (^)(BOOL, NSString *))completion {
    NSArray<NSValue *> *points = @[
        [NSValue valueWithCGPoint:from],
        [NSValue valueWithCGPoint:to],
    ];
    [self dragAlongPoints:points
             holdDuration:holdMs
             moveDuration:moveMs
                    steps:steps
               completion:completion];
}

@end
