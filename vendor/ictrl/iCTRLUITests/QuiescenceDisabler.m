//
//  QuiescenceDisabler.m
//  Disables XCUITest's "wait for quiescence" so interactions don't block for
//  up to 60s on animation-heavy apps (ads, carousels, live cards). Same approach
//  as WebDriverAgent: swizzle -[XCUIApplicationProcess waitForQuiescenceIncludingAnimationsIdle:]
//  to a no-op. This is loaded automatically via +load at test startup.
//

#import <Foundation/Foundation.h>
#import <objc/runtime.h>

// Private XCTest globals that bound how long internal idle/state waits can run.
// XCUIElement.tap()/isHittable/etc. wait for the app to reach an idle state via
// this timeout; XCTest's default can be very long, which is how an element tap
// that navigates blocked ~4-8s. WebDriverAgent bounds it the same way
// (_XCTSetApplicationStateTimeout, see XCUIApplicationProcess+FBQuiescence).
extern void _XCTSetApplicationStateTimeout(NSTimeInterval timeout) __attribute__((weak_import));
extern NSTimeInterval _XCTApplicationStateTimeout(void) __attribute__((weak_import));

@interface QuiescenceDisabler : NSObject
@end

@implementation QuiescenceDisabler

/// Cap for XCTest's application-state wait during normal interactions. Applied
/// once the test is running — never at +load, which would also bound bootstrap.
static const NSTimeInterval kInteractionStateTimeout = 2.0;

// A no-op replacement — return immediately, never wait for the UI to settle.
// Since quiescence never waits, there is no state wait here to bound; the cap is
// applied once from +[QuiescenceDisabler applyInteractionStateTimeout], called
// after the test has started.
static void noopQuiescence(id self, SEL _cmd, BOOL includingAnimations) {}
static void noopQuiescencePreEvent(id self, SEL _cmd, BOOL includingAnimations, BOOL isPreEvent) {}

+ (void)load {
    // NOTE: we deliberately do NOT call _XCTSetApplicationStateTimeout() here.
    //
    // That global also bounds XCTest's own bootstrap step -[XCUIDevice
    // enableAutomationMode:], which waits for the accessibility (GAX) server to
    // turn on. Lowering it at +load — before the test even starts — made that
    // wait expire, and XCTest then exits the process voluntarily:
    //
    //   iCTRLUITests-Runner  got GAX status change notification. on: 0
    //   iCTRLUITests-Runner  Failed to initialize for UI testing:
    //     XCTFuture Code=1000 "Timed out while enabling automation mode."
    //   iCTRLUITests-Runner  Entering exit handler.  → Process exited: voluntary
    //
    // (device log 2026-08-15 00:41:45.70 → 00:41:47.77 — exactly the 2s cap.)
    // Enabling automation mode legitimately takes longer than 2s on a cold start,
    // and much longer when the passcode screen is up, which is why "unlock, then
    // the runner dies seconds later" looked like a lock-screen bug.
    //
    // WebDriverAgent scopes this per call instead: its +load only installs the
    // swizzle, and the timeout is set inside the swizzled method and restored in
    // a @finally (XCUIApplicationProcess+FBQuiescence.m). We now do the same, so
    // the bound applies to quiescence waits without touching bootstrap.
    Class cls = NSClassFromString(@"XCUIApplicationProcess");
    if (!cls) { return; }

    // Newer XCTest: waitForQuiescenceIncludingAnimationsIdle:
    SEL sel1 = NSSelectorFromString(@"waitForQuiescenceIncludingAnimationsIdle:");
    Method m1 = class_getInstanceMethod(cls, sel1);
    if (m1) {
        method_setImplementation(m1, (IMP)noopQuiescence);
        NSLog(@"iCTRL: quiescence wait disabled (waitForQuiescenceIncludingAnimationsIdle:)");
        return;
    }

    // Some XCTest builds: waitForQuiescenceIncludingAnimationsIdle:isPreEvent:
    SEL sel2 = NSSelectorFromString(@"waitForQuiescenceIncludingAnimationsIdle:isPreEvent:");
    Method m2 = class_getInstanceMethod(cls, sel2);
    if (m2) {
        method_setImplementation(m2, (IMP)noopQuiescencePreEvent);
        NSLog(@"iCTRL: quiescence wait disabled (…:isPreEvent:)");
        return;
    }

    NSLog(@"iCTRL: could not find quiescence method to disable");
}

+ (void)applyInteractionStateTimeout {
    if (_XCTSetApplicationStateTimeout == NULL) { return; }
    _XCTSetApplicationStateTimeout(kInteractionStateTimeout);
    NSLog(@"iCTRL: XCTest application-state timeout capped at %.0fs (post-bootstrap)",
          kInteractionStateTimeout);
}

@end
