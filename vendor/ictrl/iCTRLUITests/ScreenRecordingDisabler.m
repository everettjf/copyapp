//
//  ScreenRecordingDisabler.m
//  Keeps XCTest from screen-recording the server test, whoever launched it.
//
//  Since Xcode 15 a UI test records the screen by default: at test-case start
//  -[XCUIScreen startDiagnosticScreenRecordingWithCompletion:] asks
//  testmanagerd for a 30fps H.264 video in its own container (tmp/Attachments).
//  The harness deletes it when the test passes. testStartServer runs for hours
//  and normally ends killed, so nobody ever deletes it: over repeated runs it
//  piles up as tens of GB of "System Data" and can fill the disk. A reboot does not
//  clear it, and the runner's sandbox cannot reach that container.
//
//  The scheme turns recording off (preferredScreenCaptureFormat: screenshots),
//  but that only covers xctestruns built from it. XCTest also skips the
//  recording when the runner's own defaults say DisableDiagnosticScreenRecordings
//  (read from standardUserDefaults right before it starts one), so set that
//  at bundle load — before any test case starts — to cover every launcher.
//  Its sibling DisableDiagnosticScreenshots does the same for screenshots.
//

#import <Foundation/Foundation.h>

@interface ScreenRecordingDisabler : NSObject
@end

@implementation ScreenRecordingDisabler

+ (void)load {
    // Registration domain: not persisted, never throws, and nothing else sets
    // this key — so it holds unless a launcher explicitly passes it as NO.
    // DisableDiagnosticScreenshots covers the per-interaction screenshots XCTest
    // takes under the same policy — ~100KB each, orphaned the same way.
    [[NSUserDefaults standardUserDefaults] registerDefaults:@{
        @"DisableDiagnosticScreenRecordings": @YES,
        @"DisableDiagnosticScreenshots": @YES,
    }];
}

@end
