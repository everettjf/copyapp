#import "OCRManager.h"

/// Owns one lazy, reusable, crash-isolated CPU worker. No dependency on ONNX in SpringBoard.
@interface PaddleOCRManager : NSObject <MCPOCREngine>
+ (instancetype)sharedInstance;
@end
