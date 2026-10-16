#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

@class MCPAXQueryContext;
@class MCPAXRemoteContextResolver;
@class MCPUIElementSerializer;

NS_ASSUME_NONNULL_BEGIN

typedef NSDictionary * _Nullable (^MCPUIElementAtPointProvider)(MCPAXQueryContext *context,
                                                                CGPoint point,
                                                                NSString * _Nullable * _Nullable error);

@interface MCPUIElementsFacade : NSObject

- (instancetype)initWithContextResolver:(MCPAXRemoteContextResolver *)contextResolver
                              serializer:(MCPUIElementSerializer *)serializer
                   directElementProvider:(MCPUIElementAtPointProvider _Nullable)directElementProvider;

- (NSDictionary * _Nullable)elementAtPoint:(CGPoint)point
                                     error:(NSString * _Nullable * _Nullable)error;

@end

NS_ASSUME_NONNULL_END
