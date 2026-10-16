#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

/// Public tool coordinates are fixed screen points (the framebuffer/screenshot orientation).
/// Capture once per operation; UIKit coordinate spaces must be read together on the main thread.
typedef struct {
    CGRect fixedBounds;
    CGRect interfaceBounds;
    CGAffineTransform interfaceToFixed;
    UIInterfaceOrientation interfaceOrientation;
} MCPScreenGeometry;

FOUNDATION_EXPORT MCPScreenGeometry MCPGetScreenGeometry(void);
FOUNDATION_EXPORT NSString *MCPInterfaceOrientationName(UIInterfaceOrientation orientation);

@interface ScreenManager : NSObject

+ (instancetype)sharedInstance;

/// Get screen info: width, height, scale, orientation
- (NSDictionary *)screenInfo;

/// Best-effort device interaction state from SpringBoard private APIs.
- (NSDictionary *)deviceInteractionState;

/// Take screenshot and return encoded image payload with data/mimeType.
- (NSDictionary *)takeScreenshotPayload;

/// Capture the current screen as a UIImage (for in-process OCR). Runs capture on the
/// main thread. Returns nil if all private capture paths fail.
- (UIImage *)captureScreenImage;

/// Returns geometry from the same main-thread capture, for mapping OCR results and regions.
- (UIImage *)captureScreenImageWithGeometry:(MCPScreenGeometry *)geometry;

@end
