#import "OCRManager.h"
#import "VisionOCREngine.h"
#import "PaddleOCRManager.h"
#import "MCPLogger.h"
#include <math.h>

@implementation OCRManager
+ (NSString *)defaultEngine { return @"paddleocr"; }
+ (instancetype)sharedInstance {
    static OCRManager *instance;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ instance = [self new]; });
    return instance;
}
+ (BOOL)validateRegion:(NSDictionary *)region error:(NSString **)error {
    return [VisionOCREngine validateRegion:region error:error];
}
+ (BOOL)validateEngine:(id)engine error:(NSString **)error {
    if (!engine || ([engine isKindOfClass:NSString.class] &&
                    ([engine isEqualToString:@"vision"] || [engine isEqualToString:@"paddleocr"]))) return YES;
    if (error) *error = @"Invalid engine: expected 'vision' or 'paddleocr'";
    return NO;
}
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages minConfidence:(double)confidence
                                      region:(NSDictionary *)region fast:(BOOL)fast error:(NSString **)error {
    // Legacy native callers default independently of any preceding call.
    return [self recognizeTextWithLanguages:languages minConfidence:confidence region:region fast:fast engine:nil error:error];
}
- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages minConfidence:(double)confidence
                                      region:(NSDictionary *)region fast:(BOOL)fast engine:(NSString *)engine error:(NSString **)error {
    if (error) *error = nil;
    if (![OCRManager validateEngine:engine error:error] || ![OCRManager validateRegion:region error:error]) return nil;
    if (!isfinite(confidence) || confidence < 0 || confidence > 1) {
        if (error) *error = @"Invalid min_confidence: expected a finite number in 0..1";
        return nil;
    }
    if (languages && ![languages isKindOfClass:NSArray.class]) {
        if (error) *error = @"Invalid languages: expected an array of strings";
        return nil;
    }
    for (id language in languages) if (![language isKindOfClass:NSString.class] || ![language length]) {
        if (error) *error = @"Invalid languages: expected nonempty strings";
        return nil;
    }
    NSString *selected = engine ?: [OCRManager defaultEngine];
    [MCPLogger log:@"[OCR] request engine=%@", selected];
    id<MCPOCREngine> implementation = [selected isEqualToString:@"paddleocr"] ?
        (id<MCPOCREngine>)[PaddleOCRManager sharedInstance] : (id<MCPOCREngine>)[VisionOCREngine sharedInstance];
    NSString *reason = nil;
    NSDictionary *result = [implementation recognizeTextWithLanguages:languages minConfidence:confidence region:region fast:fast error:&reason];
    if (!result) {
        if (error) *error = [NSString stringWithFormat:@"%@ OCR failed: %@", selected, reason ?: @"unknown error"];
        [MCPLogger log:@"[OCR] engine=%@ failed=%@", selected, reason ?: @"unknown error"];
    }
    return result; // Never retry against a different engine.
}
@end
