#import "OCRManager.h"

@interface VisionOCREngine : NSObject <MCPOCREngine>
+ (instancetype)sharedInstance;
+ (BOOL)validateRegion:(NSDictionary *)region error:(NSString **)error;
@end
