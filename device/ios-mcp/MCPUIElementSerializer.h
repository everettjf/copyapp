#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

@class MCPAXQueryContext;

@interface MCPUIElementSerializer : NSObject

- (NSDictionary *)normalizedElementFromRawElement:(NSDictionary *)rawElement
                                          context:(MCPAXQueryContext *)context
                                            point:(CGPoint)point;

@end
