#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Runs `block` inside an Obj-C @try/@catch so an NSException thrown by XCTest
/// (e.g. XCUIElement.tap on a stale/non-hittable element) can be caught — Swift's
/// do/catch cannot catch NSExceptions, and an uncaught one aborts the runner.
/// Returns the caught exception's reason, or nil if the block completed cleanly.
@interface ObjCException : NSObject
+ (nullable NSString *)catching:(void (^)(void))block;

/// Instantiate XCTest's private XCTImageEncoding by class + selector.
///
/// Lives here because the class ships in a private framework we do not link:
/// naming its type in Swift would leave the linker hunting for a symbol that
/// isn't there, so it has to be built through the runtime. Returns nil if the
/// class or initializer is missing on this OS.
/// Screenshot with an encoding object, through objc_msgSend: Xcode 27's
/// encoding class no longer bridges to the Swift protocol type, and its
/// screenshot selector lost the options argument. Tries
/// screenshotWithPreferredEncoding:rect:error: then the 4-argument form.
+ (nullable id)screenshotOf:(id)screen encoding:(id)encoding;

/// A screenshot straight from the testmanagerd session, in the given
/// encoding: XCTRunnerDaemonSession's requestScreenshotWithRequest:withReply:.
/// The XCUIScreen methods reach the same capture but take about 100ms per
/// frame whatever the format; asked directly, a quarter-quality JPEG of the
/// whole screen comes back in a few tens of milliseconds. Returns the
/// encoded bytes, or nil with the reason in `why` (missing API, error, or
/// no reply within `timeout` seconds).
+ (nullable NSData *)daemonScreenshotWithEncoding:(id)encoding
                                          timeout:(double)timeout
                                              why:(NSString * _Nullable * _Nullable)why;

+ (nullable id)makeImageEncoding:(Class)encodingClass
                             uti:(NSString *)uti
                         quality:(double)quality
                        diagnosis:(NSString * _Nullable * _Nullable)diagnosis;
@end

NS_ASSUME_NONNULL_END
