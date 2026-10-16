#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface QuiescenceDisabler : NSObject

/// Cap XCTest's application-state wait for normal interactions.
///
/// MUST be called only AFTER the test has started. Setting this global earlier
/// (it used to be done from +load) also bounds XCTest's own bootstrap step
/// -[XCUIDevice enableAutomationMode:], whose wait for the accessibility server
/// legitimately takes longer — XCTest then fails with "Timed out while enabling
/// automation mode" and exits the process voluntarily, which looks exactly like
/// the runner dying seconds after launch.
+ (void)applyInteractionStateTimeout;

@end

NS_ASSUME_NONNULL_END
