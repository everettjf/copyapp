#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import "AXPrivate.h"

NS_ASSUME_NONNULL_BEGIN

@interface MCPAXAttributeBridge : NSObject

- (BOOL)ensureRuntimeAvailable:(NSString * _Nullable * _Nullable)error;
- (void)performOnMainThreadSync:(dispatch_block_t)block;
- (void)ensureAssociationWithRemotePid:(pid_t)remotePid;

- (AXUIElementRef _Nullable)copyApplicationElementForPid:(pid_t)pid
                                                   error:(NSString * _Nullable * _Nullable)error;

- (AXUIElementRef _Nullable)copyContextBoundApplicationElementForPid:(pid_t)expectedPid
                                                          diagnostics:(NSDictionary * _Nullable * _Nullable)diagnostics
                                                                error:(NSString * _Nullable * _Nullable)error;

- (AXUIElementRef _Nullable)copyContextChainHitElementAtPoint:(CGPoint)point
                                                  expectedPid:(pid_t)expectedPid
                                                  diagnostics:(NSDictionary * _Nullable * _Nullable)diagnostics
                                                        error:(NSString * _Nullable * _Nullable)error;

- (AXUIElementRef _Nullable)copyElementAtPoint:(CGPoint)point
                              usingKnownContextId:(uint32_t)contextId
                                      expectedPid:(pid_t)expectedPid
                                      diagnostics:(NSDictionary * _Nullable * _Nullable)diagnostics
                                            error:(NSString * _Nullable * _Nullable)error;

- (AXUIElementRef _Nullable)copySystemWideElement;

- (BOOL)getPid:(pid_t *)pidOut fromElement:(AXUIElementRef)element;
- (NSString *)errorStringForAXError:(AXError)error;
- (AXUIElementRef _Nullable)copyHitTestElementAtPoint:(CGPoint)point
                                          expectedPid:(pid_t)expectedPid
                                   allowParameterized:(BOOL)allowParameterized
                                                error:(NSString * _Nullable * _Nullable)error;

- (id _Nullable)copyAttributeObject:(AXUIElementRef)element
                          attribute:(CFStringRef)attribute;

- (NSDictionary<NSString *, id> * _Nullable)copyAttributeMap:(AXUIElementRef)element
                                                   attributes:(NSArray<NSString *> *)attributes;

- (NSDictionary<NSString *, id> * _Nullable)copyXCAttributeMap:(AXUIElementRef)element
                                                  attributeKeys:(NSArray<NSString *> *)attributeKeys;

- (id _Nullable)copyXCAttributeObject:(AXUIElementRef)element
                         attributeKey:(NSString *)attributeKey;

- (NSDictionary<NSString *, id> * _Nullable)copyDirectAttributeMap:(AXUIElementRef)element
                                                       attributeKeys:(NSArray<NSString *> *)attributeKeys;

- (id _Nullable)copyDirectAttributeObject:(AXUIElementRef)element
                             attributeKey:(NSString *)attributeKey;

- (id _Nullable)copyXCParameterizedAttributeObject:(AXUIElementRef)element
                                      attributeKey:(NSString *)attributeKey
                                         parameter:(id _Nullable)parameter;

- (id _Nullable)copyUserTestingSnapshotForElement:(AXUIElementRef)element
                                          options:(NSDictionary * _Nullable)options;

- (NSDictionary * _Nullable)probeUserTestingSnapshotForElement:(AXUIElementRef)element
                                                       options:(NSDictionary * _Nullable)options;

- (NSDictionary<NSNumber *, id> * _Nullable)copyNumericAttributeMap:(AXUIElementRef)element
                                                         attributes:(NSArray<NSNumber *> *)attributes;

- (NSArray * _Nullable)copyNumericAttributeArray:(AXUIElementRef)element
                                     attributeId:(uint32_t)attributeId;

- (NSArray * _Nullable)copyChildElementsForElement:(AXUIElementRef)element;
- (NSString * _Nullable)copyStringAttribute:(AXUIElementRef)element attribute:(CFStringRef)attribute;
- (NSNumber * _Nullable)copyNumberAttribute:(AXUIElementRef)element attribute:(CFStringRef)attribute;

@end

NS_ASSUME_NONNULL_END
