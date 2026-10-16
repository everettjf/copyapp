#ifndef XCTestPrivate_Bridging_Header_h
#define XCTestPrivate_Bridging_Header_h

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>
#import <XCTest/XCTest.h>
#import "LockStateMonitor.h"
#import "ForegroundApp.h"
#import "QuiescenceDisabler.h"
#import "ObjCException.h"

@interface EarlyURLHook : NSObject
+ (NSArray<NSURL *> *)drainURLs;
+ (NSArray<NSString *> *)drainLogs;
+ (void)markTestStarted;
+ (void)markSetUpEntered;
@end

NS_ASSUME_NONNULL_BEGIN

@class XCPointerEventPath;

@interface XCSynthesizedEventRecord : NSObject
- (instancetype)initWithName:(NSString *)name;
- (void)addPointerEventPath:(XCPointerEventPath *)eventPath;
- (BOOL)synthesizeWithError:(NSError * _Nullable * _Nullable)error;
@end

@interface XCPointerEventPath : NSObject
- (instancetype)initForTouchAtPoint:(CGPoint)point offset:(NSTimeInterval)offset;
- (void)pressDownAtOffset:(NSTimeInterval)offset;
- (void)liftUpAtOffset:(NSTimeInterval)offset;
- (void)moveToPoint:(CGPoint)point atOffset:(NSTimeInterval)offset;
- (instancetype)initForTextInput;
- (void)typeText:(NSString *)text
        atOffset:(NSTimeInterval)offset
     typingSpeed:(NSUInteger)typingSpeed
    shouldRedact:(BOOL)shouldRedact;
@end

@interface XCUIDevice (FBPrivate)
- (void)pressLockButton;
@end

/// The public `-[XCUIScreenshot image]` decodes from `PNGRepresentation`, so
/// every captured frame is PNG-compressed and then immediately decompressed
/// just to hand back a bitmap — pure waste for a video pipeline that only
/// wants pixels. `internalImage` is the already-decoded frame the screenshot
/// is holding, wrapped in XCTest's own XCTImage; `platformImage` unwraps it
/// to a UIImage.
///
/// NOTE: `internalImage` returns XCTImage, NOT UIImage — declaring it as the
/// latter compiles fine and then crashes with "-[XCTImage CGImage]:
/// unrecognized selector" the first time a frame is encoded.
///
/// Private, so treat both as optional: call sites must fall back to `.image`
/// when either is unavailable (see VideoBroadcaster's frame grabber).
/// How a captured frame is encoded — a UTI ("public.jpeg") plus a 0…1 quality.
/// Declared as a protocol rather than an @interface: the class lives in a
/// private framework we do not link, so declaring the class would leave the
/// linker looking for a symbol that isn't there. We only ever obtain instances
/// at runtime via NSClassFromString.
@protocol XCTImageEncoding <NSObject>
@end

@interface XCTImage : NSObject
- (UIImage * _Nullable)platformImage;
/// The ENCODED bytes, when the image is holding a compressed representation
/// rather than a bitmap — i.e. what we asked the capture side to produce.
- (NSData * _Nullable)data;
- (id<XCTImageEncoding> _Nullable)encoding;
@end

@interface XCUIScreenshot (ICTRLPrivate)
- (XCTImage * _Nullable)internalImage;
@end

/// Capture asking the system for a specific encoding, so compression happens on
/// the capture side instead of us hauling a ~6 MB bitmap per frame through the
/// process. `rect` of CGRectNull means the whole screen.
///
/// NOTE: older WebDriverAgent used `screenshotDataForQuality:rect:error:`, which
/// no longer exists in current Xcode SDKs — this is the surviving equivalent.
@interface XCUIScreen (ICTRLPrivate)
- (XCUIScreenshot * _Nullable)screenshotWithPreferredEncoding:(id<XCTImageEncoding>)encoding
                                                         rect:(CGRect)rect
                                                      options:(NSDictionary * _Nullable)options
                                                        error:(NSError * _Nullable * _Nullable)error;
/// Xcode 27's shape: the options argument is gone (the 4-argument form above
/// no longer exists there, which silently forced the slow bitmap path).
- (XCUIScreenshot * _Nullable)screenshotWithPreferredEncoding:(id<XCTImageEncoding>)encoding
                                                         rect:(CGRect)rect
                                                        error:(NSError * _Nullable * _Nullable)error;
@end

NS_ASSUME_NONNULL_END

#endif
