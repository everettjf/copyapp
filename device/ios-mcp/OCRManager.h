#import <Foundation/Foundation.h>

@protocol MCPOCREngine <NSObject>
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages
                               minConfidence:(double)minConfidence
                                      region:(NSDictionary *)region
                                        fast:(BOOL)fast
                                       error:(NSString **)error;
@end

/// Per-request router for Vision and PaddleOCR. Captures the current screen, recognizes text,
/// and returns each text block with screen-point coordinates (ready for tap_screen).
@interface OCRManager : NSObject

+ (instancetype)sharedInstance;
/// Immutable request default, shared by execution, MCP schema and cancellation routing.
+ (NSString *)defaultEngine;

/// Validate an optional region before capture/recognition. nil means full screen.
+ (BOOL)validateRegion:(NSDictionary *)region error:(NSString **)error;
+ (BOOL)validateEngine:(id)engine error:(NSString **)error;

/// Recognize text on the current screen using the default PaddleOCR engine.
/// Call from a background thread. To use Apple Vision, call the overload with engine="vision".
///   languages:     recognition languages (e.g. @[@"zh-Hans", @"en"]); nil = default.
///   minConfidence: drop results below this confidence (0..1).
///   region:        optional screen-point rect {x,y,width,height} to limit OCR; nil = full screen.
///                  All fields must be finite numbers, width/height > 0. Partly off-screen regions
///                  are clipped; wholly off-screen regions return no texts. Invalid regions fail.
///   fast:          Vision speed preference; PaddleOCR always uses its fixed mobile model.
/// Vision accurate recognition runs on CPU directly. No engine fallback on failure.
/// Returns "texts" (text/confidence/rect/tap), "count", "screen", and "recognition" (actual
/// level/languages/revision/CPU configuration), or nil with *error.
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages
                               minConfidence:(double)minConfidence
                                      region:(NSDictionary *)region
                                        fast:(BOOL)fast
                                       error:(NSString **)error;

/// nil engine always means PaddleOCR. Invalid values fail; no saved preference or fallback.
/// PaddleOCR: Chinese/English mobile model, CPU EP only; fast does not change the fixed model.
/// minConfidence filters mean CTC probability (not calibrated to Vision).
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages
                               minConfidence:(double)minConfidence
                                      region:(NSDictionary *)region
                                        fast:(BOOL)fast
                                      engine:(NSString *)engine
                                       error:(NSString **)error;
@end
