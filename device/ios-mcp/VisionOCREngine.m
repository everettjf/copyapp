#import "VisionOCREngine.h"
#import "ScreenManager.h"
#import "MCPLogger.h"
#import <UIKit/UIKit.h>
#import <Vision/Vision.h>
#import <ImageIO/ImageIO.h>
#import <math.h>

#define OCR_LOG(fmt, ...) [MCPLogger log:@"[OCR] engine=vision " fmt, ##__VA_ARGS__]

@implementation VisionOCREngine

+ (instancetype)sharedInstance {
    static VisionOCREngine *instance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[VisionOCREngine alloc] init];
    });
    return instance;
}

static BOOL OCRParseRegion(NSDictionary *region, CGRect *outRect, NSString **error) {
    if (error) *error = nil;
    if (!region) return YES;
    if (![region isKindOfClass:[NSDictionary class]]) {
        if (error) *error = @"Invalid region: expected an object with x, y, width and height";
        return NO;
    }
    NSArray<NSString *> *keys = @[@"x", @"y", @"width", @"height"];
    double values[4];
    for (NSUInteger i = 0; i < keys.count; i++) {
        id value = region[keys[i]];
        if (![value isKindOfClass:[NSNumber class]] ||
            CFGetTypeID((__bridge CFTypeRef)value) == CFBooleanGetTypeID() ||
            !isfinite([value doubleValue])) {
            if (error) *error = [NSString stringWithFormat:@"Invalid region.%@: expected a finite number", keys[i]];
            return NO;
        }
        values[i] = [value doubleValue];
    }
    if (values[2] <= 0 || values[3] <= 0) {
        if (error) *error = @"Invalid region: width and height must be greater than 0";
        return NO;
    }
    if (!isfinite(values[0] + values[2]) || !isfinite(values[1] + values[3])) {
        if (error) *error = @"Invalid region: x + width and y + height must be finite";
        return NO;
    }
    if (outRect) *outRect = CGRectMake(values[0], values[1], values[2], values[3]);
    return YES;
}

+ (BOOL)validateRegion:(NSDictionary *)region error:(NSString **)error {
    return OCRParseRegion(region, NULL, error);
}

static NSArray<NSString *> *OCRSupportedLanguages(VNRecognizeTextRequest *request, NSError **error) API_AVAILABLE(ios(13.0)) {
    if (@available(iOS 15.0, *)) {
        return [request supportedRecognitionLanguagesAndReturnError:error];
    }
    return [VNRecognizeTextRequest supportedRecognitionLanguagesForTextRecognitionLevel:request.recognitionLevel
                                                                               revision:request.revision error:error];
}

// Preserve priority order. Accept case/underscore variations and bare language codes such as
// "en", but never silently drop an unsupported language (notably Chinese in the fast path).
static NSArray<NSString *> *OCRResolveLanguages(NSArray<NSString *> *languages, NSArray<NSString *> *supported) {
    NSMutableArray *resolved = [NSMutableArray array];
    for (NSString *language in languages) {
        NSString *tag = [language stringByReplacingOccurrencesOfString:@"_" withString:@"-"];
        NSString *match = nil;
        for (NSString *candidate in supported) {
            if ([tag caseInsensitiveCompare:candidate] == NSOrderedSame) { match = candidate; break; }
        }
        if (!match && tag.length && ![tag containsString:@"-"]) {
            NSString *prefix = [[tag lowercaseString] stringByAppendingString:@"-"];
            for (NSString *candidate in supported) {
                if ([[candidate lowercaseString] hasPrefix:prefix]) { match = candidate; break; }
            }
        }
        if (!match) return nil;
        if (![resolved containsObject:match]) [resolved addObject:match];
    }
    return resolved;
}

static NSString *OCRErrorDescription(NSError *error) {
    NSMutableArray *parts = [NSMutableArray array];
    // Keep the Core ML cause, not just Vision's generic "internal error" message.
    for (NSUInteger depth = 0; error && depth < 4; depth++) {
        [parts addObject:[NSString stringWithFormat:@"%@ (%@:%ld)", error.localizedDescription,
                          error.domain, (long)error.code]];
        error = error.userInfo[NSUnderlyingErrorKey];
    }
    return parts.count ? [parts componentsJoinedByString:@"; "] : @"Vision OCR failed";
}

// Vision should see upright text even though the framebuffer remains in fixed orientation.
static CGImagePropertyOrientation OCROrientation(UIInterfaceOrientation orientation) {
    switch (orientation) {
        case UIInterfaceOrientationLandscapeLeft: return kCGImagePropertyOrientationLeft;
        case UIInterfaceOrientationLandscapeRight: return kCGImagePropertyOrientationRight;
        case UIInterfaceOrientationPortraitUpsideDown: return kCGImagePropertyOrientationDown;
        default: return kCGImagePropertyOrientationUp;
    }
}

// Downsample a CGImage so its longest edge is at most maxEdge pixels, via CoreGraphics.
// Vision text recognition does not need full-resolution input; shrinking a large iPad
// capture (e.g. 1620x2160) cuts recognition time several fold. Returns NULL if no
// downsample is needed or on failure (caller then keeps the original). Coordinate mapping is
// unaffected: Vision reports normalized boxes, which are mapped back onto the screen point size.
static CGImageRef OCRCreateDownsampled(CGImageRef src, CGFloat maxEdge) CF_RETURNS_RETAINED {
    if (!src) return NULL;
    size_t w = CGImageGetWidth(src);
    size_t h = CGImageGetHeight(src);
    size_t longEdge = MAX(w, h);
    if (longEdge == 0 || longEdge <= (size_t)maxEdge) return NULL;

    double scale = maxEdge / (double)longEdge;
    size_t nw = (size_t)(w * scale);
    size_t nh = (size_t)(h * scale);
    if (nw == 0 || nh == 0) return NULL;

    CGColorSpaceRef cs = CGColorSpaceCreateDeviceRGB();
    CGContextRef ctx = CGBitmapContextCreate(NULL, nw, nh, 8, 0, cs,
                                             kCGImageAlphaPremultipliedLast | kCGBitmapByteOrder32Big);
    CGColorSpaceRelease(cs);
    if (!ctx) return NULL;
    CGContextSetInterpolationQuality(ctx, kCGInterpolationMedium);
    CGContextDrawImage(ctx, CGRectMake(0, 0, nw, nh), src);
    CGImageRef out = CGBitmapContextCreateImage(ctx);
    CGContextRelease(ctx);
    return out;
}

- (NSDictionary *)recognizeTextWithLanguages:(NSArray<NSString *> *)languages
                               minConfidence:(double)minConfidence
                                      region:(NSDictionary *)region
                                        fast:(BOOL)fast
                                       error:(NSString **)error {
    if (error) *error = nil;
    // The tweak executes in SpringBoard. On the XR with iOS 16.1.1, Vision's
    // text detector twice terminated that process while disposing an ANE
    // semaphore, including after usesCPUOnly was set. Keep OCR out of this
    // host process; Copy APP runs Vision on the Mac against a USB screenshot.
    if ([[NSProcessInfo processInfo].processName isEqualToString:@"SpringBoard"]) {
        if (error) *error = @"Vision OCR is disabled inside SpringBoard; use Copy APP host OCR on a screenshot";
        return nil;
    }
    CGRect requestedRegion = CGRectZero;
    if (!OCRParseRegion(region, &requestedRegion, error)) return nil;

    if (@available(iOS 13.0, *)) {
        MCPScreenGeometry geometry;
        UIImage *image = [[ScreenManager sharedInstance] captureScreenImageWithGeometry:&geometry];
        if (!image || !image.CGImage) {
            if (error) *error = @"Failed to capture screen for OCR";
            return nil;
        }

        // Vision's oriented image uses interface coordinates. Public regions/results use fixed
        // screenshot points. Do not derive either from UIImage.scale (Display Zoom differs).
        CGSize pointSize = geometry.interfaceBounds.size;
        CGFloat W = pointSize.width;
        CGFloat H = pointSize.height;
        if (W < 1.0 || H < 1.0) {
            if (error) *error = @"Failed to determine screen point size for OCR";
            return nil;
        }

        __block NSArray<VNRecognizedTextObservation *> *observations = nil;
        __block NSError *visionError = nil;

        VNRecognizeTextRequest *request = [[VNRecognizeTextRequest alloc] initWithCompletionHandler:^(VNRequest *req, NSError *err) {
            visionError = err;
            observations = (NSArray<VNRecognizedTextObservation *> *)req.results;
        }];
        request.recognitionLevel = fast ? VNRequestTextRecognitionLevelFast : VNRequestTextRecognitionLevelAccurate;
        NSArray *requestedLanguages = languages.count ? languages : @[@"en-US"];
        // iOS 13 / revision 1 cannot recognize Chinese. Never force a newer revision.
        // Prefer Chinese+English only if THIS revision's accurate path supports both.
        if (!languages.count) {
            if (@available(iOS 14.0, *)) {
                VNRequestTextRecognitionLevel selectedLevel = request.recognitionLevel;
                request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
                NSArray *accurateLanguages = OCRSupportedLanguages(request, nil);
                if (OCRResolveLanguages(@[@"zh-Hans", @"en-US"], accurateLanguages))
                    requestedLanguages = @[@"zh-Hans", @"en-US"];
                request.recognitionLevel = selectedLevel;
            }
        }
        NSMutableArray *adjustments = [NSMutableArray array];
        NSError *languageError = nil;
        NSArray *supported = OCRSupportedLanguages(request, &languageError);
        NSArray *resolved = supported ? OCRResolveLanguages(requestedLanguages, supported) : nil;
        if (supported && !resolved && fast) {
            // fast is a speed preference, not permission to switch to a Latin-only recognizer.
            request.recognitionLevel = VNRequestTextRecognitionLevelAccurate;
            languageError = nil;
            supported = OCRSupportedLanguages(request, &languageError);
            resolved = supported ? OCRResolveLanguages(requestedLanguages, supported) : nil;
            [adjustments addObject:@"fast_unsupported_languages"];
        }
        if (!resolved) {
            if (error) *error = languageError ? OCRErrorDescription(languageError) :
                [NSString stringWithFormat:@"OCR languages %@ are not supported by Vision revision %lu on this device. Supported languages: %@",
                 requestedLanguages, (unsigned long)request.revision, supported ?: @[]];
            return nil;
        }
        request.recognitionLanguages = resolved;
        request.usesLanguageCorrection = request.recognitionLevel == VNRequestTextRecognitionLevelAccurate;
        // Outside SpringBoard, prefer CPU on either recognition level.
        request.usesCPUOnly = YES;

        NSDictionary *recognition = @{
            @"engine": @"vision",
            @"requested_level": fast ? @"fast" : @"accurate",
            @"level": request.recognitionLevel == VNRequestTextRecognitionLevelFast ? @"fast" : @"accurate",
            @"languages": request.recognitionLanguages,
            @"revision": @(request.revision),
            @"uses_cpu_only": @(request.usesCPUOnly),
            @"adjustments": adjustments
        };
        NSDictionary *screen = @{@"width": @((int)round(geometry.fixedBounds.size.width)),
                                 @"height": @((int)round(geometry.fixedBounds.size.height)),
                                 @"coordinate_space": @"fixed"};

        // Limit OCR to a region of interest if provided (Vision uses normalized, origin bottom-left).
        // The ROI is kept so observation boxes, which Vision normalizes against the ROI rather than
        // the full image, can be mapped back to full-image space below.
        CGRect roi = CGRectMake(0, 0, 1, 1);
        if (region) {
            // Clip before rotating so even very large finite inputs cannot overflow the transform.
            CGRect clippedRegion = CGRectIntersection(requestedRegion, geometry.fixedBounds);
            if (CGRectIsNull(clippedRegion) || CGRectIsEmpty(clippedRegion)) {
                // Do not leave Vision's default full-screen ROI in place for an empty intersection.
                OCR_LOG(@"empty region: no intersection with screen");
                return @{@"texts": @[], @"count": @0, @"recognition": recognition, @"screen": screen};
            }
            CGRect orientedRegion = CGRectApplyAffineTransform(clippedRegion,
                                             CGAffineTransformInvert(geometry.interfaceToFixed));
            double left = MAX(0.0, MIN(CGRectGetMinX(orientedRegion), W));
            double top = MAX(0.0, MIN(CGRectGetMinY(orientedRegion), H));
            double right = MAX(left, MIN(CGRectGetMaxX(orientedRegion), W));
            double bottom = MAX(top, MIN(CGRectGetMaxY(orientedRegion), H));
            if (right <= left || bottom <= top) {
                return @{@"texts": @[], @"count": @0, @"recognition": recognition, @"screen": screen};
            }
            roi = CGRectMake(left / W,
                             (H - bottom) / H,  // flip Y to bottom-left origin
                             (right - left) / W,
                             (bottom - top) / H);
            request.regionOfInterest = roi;
        }

        // Downsample large captures before OCR (longest edge cap). Speeds up Vision on
        // high-res iPad screens; coordinates still map back via the captured screen geometry.
        CGImageRef ocrImage = image.CGImage;
        CGImageRef downsampled = OCRCreateDownsampled(image.CGImage, 1600.0);
        if (downsampled) ocrImage = downsampled;

        CGImagePropertyOrientation orientation = OCROrientation(geometry.interfaceOrientation);
        VNImageRequestHandler *handler = [[VNImageRequestHandler alloc] initWithCGImage:ocrImage
                                                                         orientation:orientation options:@{}];
        NSError *performError = nil;
        BOOL ok = [handler performRequests:@[request] error:&performError];

        if (downsampled) CGImageRelease(downsampled);
        if (!ok || visionError) {
            NSString *msg = OCRErrorDescription(performError ?: visionError);
            if (error) *error = msg;
            OCR_LOG(@"failed: %@", msg);
            return nil;
        }

        NSMutableArray<NSDictionary *> *texts = [NSMutableArray array];
        for (VNRecognizedTextObservation *obs in observations) {
            VNRecognizedText *top = [[obs topCandidates:1] firstObject];
            if (!top) continue;
            double conf = top.confidence;
            if (conf < minConfidence) continue;

            NSString *str = top.string ?: @"";
            if (str.length == 0) continue;

            // boundingBox is normalized (0..1), origin bottom-left, and relative to the ROI rather
            // than the whole image. Compose it back into full-image space before scaling to points;
            // roi is the full unit rect when no region was requested, making this a no-op then.
            CGRect bb = obs.boundingBox;
            double fx = roi.origin.x + bb.origin.x * roi.size.width;
            double fy = roi.origin.y + bb.origin.y * roi.size.height;
            double fw = bb.size.width * roi.size.width;
            double fh = bb.size.height * roi.size.height;

            double x = fx * W;
            double w = fw * W;
            double h = fh * H;
            double y = (1.0 - fy - fh) * H; // flip Y to top-left origin

            CGRect fixedRect = CGRectApplyAffineTransform(CGRectMake(x, y, w, h), geometry.interfaceToFixed);
            int ix = (int)round(fixedRect.origin.x), iy = (int)round(fixedRect.origin.y);
            int iw = (int)round(fixedRect.size.width), ih = (int)round(fixedRect.size.height);

            [texts addObject:@{
                @"text": str,
                @"confidence": @(round(conf * 100) / 100.0),
                @"rect": @{@"x": @(ix), @"y": @(iy), @"width": @(iw), @"height": @(ih)},
                @"tap": @{@"x": @(ix + iw / 2), @"y": @(iy + ih / 2)}
            }];
        }

        OCR_LOG(@"ok count=%lu recognition=%@", (unsigned long)texts.count, recognition);
        return @{
            @"texts": texts,
            @"count": @(texts.count),
            @"recognition": recognition,
            @"screen": screen
        };
    }

    if (error) *error = @"OCR requires iOS 13 or later";
    return nil;
}

@end
