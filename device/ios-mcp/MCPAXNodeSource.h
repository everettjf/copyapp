#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>

@class MCPAXAttributeBridge;

NS_ASSUME_NONNULL_BEGIN

@interface MCPAXNodeSource : NSObject

- (instancetype)initWithAttributeBridge:(MCPAXAttributeBridge *)attributeBridge;

- (NSDictionary * _Nullable)elementAtPoint:(CGPoint)point
                                       pid:(pid_t)pid
                                  contextId:(uint32_t)contextId
                                  displayId:(uint32_t)displayId
                    allowParameterizedHitTest:(BOOL)allowParameterizedHitTest
                                     error:(NSString * _Nullable * _Nullable)error;

- (NSDictionary * _Nullable)compactElementsForPid:(pid_t)pid
                                         bundleId:(NSString * _Nullable)bundleId
                                        contextId:(uint32_t)contextId
                                        displayId:(uint32_t)displayId
                                      maxElements:(NSInteger)maxElements
                                      visibleOnly:(BOOL)visibleOnly
                                    clickableOnly:(BOOL)clickableOnly
                                            error:(NSString * _Nullable * _Nullable)error;

@end

NS_ASSUME_NONNULL_END
