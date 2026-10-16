#import "MCPAXNodeSource.h"
#import "ScreenManager.h"
#import "MCPAXAttributeBridge.h"
#import "AXPrivate.h"
#import <UIKit/UIKit.h>
#import <objc/message.h>
#import <dlfcn.h>
#import "MCPLogger.h"

#define MCP_AX_NODE_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[AXNodeSource] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)

static const BOOL MCPAXNodeSourceEnableNumericSampledHitMerge = YES;

static const uint32_t kMCPAXNodeAttributeLabel = 2001;
static const uint32_t kMCPAXNodeAttributeFrame = 2003;
static const uint32_t kMCPAXNodeAttributeTraits = 2004;
static const uint32_t kMCPAXNodeAttributeValue = 2006;
static const uint32_t kMCPAXNodeAttributeVisibleElements = 3015;
static const uint32_t kMCPAXNodeAttributeExplorerElements = 3022;
static const uint32_t kMCPAXNodeAttributeElementsWithSemanticContext = 3025;
static const uint32_t kMCPAXNodeAttributeNativeFocusableElements = 3029;
static const uint32_t kMCPAXNodeAttributeSiriContentNativeFocusableElements = 3031;
static const uint32_t kMCPAXNodeAttributeSiriContentElementsWithSemanticContext = 3032;
static const uint32_t kMCPAXNodeAttributeChildren = 5001;
static const uint32_t kMCPAXNodeAttributeIsElement = 2016;
static const uint32_t kMCPAXNodeAttributeWindowContextId = 2021;
static const uint32_t kMCPAXNodeAttributeWindowDisplayId = 2123;
static const uint32_t kMCPAXNodeSnapshotAttributeElementType = 5003;
static const uint32_t kMCPAXNodeSnapshotAttributeElementBaseType = 5004;
static const uint32_t kMCPAXNodeSnapshotAttributeIdentifier = 5019;

static NSString * const kMCPAXNodeSnapshotKeyElement = @"UIAccessibilitySnapshotKeyElement";
static NSString * const kMCPAXNodeSnapshotKeyChildren = @"UIAccessibilitySnapshotKeyChildren";
static NSString * const kMCPAXNodeSnapshotKeyAttributes = @"UIAccessibilitySnapshotKeyAttributes";
static NSString * const kMCPAXNodeSnapshotRemoteViewBridge = @"RemoteViewBridge";
static NSString * const kMCPAXNodeSnapshotRemoteElementClass = @"AXRemoteElement";

static NSString *MCPAXNodeCompactFrameString(NSDictionary *frame);
static NSString *MCPAXNodeStringFromValue(id value);
static id MCPAXNodeNormalizedValue(id value);
static id MCPAXNodeSanitizeSnapshotValue(id value, NSInteger depth);
static NSDictionary *MCPAXNodePipelineProbeValueSummary(id value);
static BOOL MCPAXNodeStringLooksLikeAXError(NSString *value);
static NSArray<NSValue *> *MCPAXNodeScreenProbePoints(CGRect bounds);

typedef struct {
    BOOL attempted;
    CFTypeID (*getTypeID)(void);
    int (*getType)(CFTypeRef value);
    Boolean (*getValue)(CFTypeRef value, int type, void *outValue);
} MCPAXNodeAXValueRuntime;

static MCPAXNodeAXValueRuntime MCPAXNodeSharedAXValueRuntime(void) {
    static MCPAXNodeAXValueRuntime runtime;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        runtime.attempted = YES;
        runtime.getTypeID = (CFTypeID (*)(void))dlsym(RTLD_DEFAULT, "AXValueGetTypeID");
        runtime.getType = (int (*)(CFTypeRef))dlsym(RTLD_DEFAULT, "AXValueGetType");
        runtime.getValue = (Boolean (*)(CFTypeRef, int, void *))dlsym(RTLD_DEFAULT, "AXValueGetValue");
    });
    return runtime;
}

static BOOL MCPAXNodeCopyAXValue(id object, int expectedType, void *outValue) {
    if (!object || !outValue) return NO;

    MCPAXNodeAXValueRuntime runtime = MCPAXNodeSharedAXValueRuntime();
    if (!runtime.getType || !runtime.getValue) return NO;

    CFTypeRef valueRef = (__bridge CFTypeRef)object;
    if (runtime.getTypeID) {
        @try {
            if (CFGetTypeID(valueRef) != runtime.getTypeID()) {
                return NO;
            }
        } @catch (__unused NSException *exception) {
            return NO;
        }
    }

    int actualType = 0;
    @try {
        actualType = runtime.getType(valueRef);
    } @catch (__unused NSException *exception) {
        return NO;
    }
    if (actualType != expectedType) return NO;

    @try {
        return runtime.getValue(valueRef, expectedType, outValue);
    } @catch (__unused NSException *exception) {
        return NO;
    }
}

static NSDictionary *MCPAXNodeFrameDictionary(CGRect frame) {
    return @{
        @"x": @((int)CGRectGetMinX(frame)),
        @"y": @((int)CGRectGetMinY(frame)),
        @"width": @((int)CGRectGetWidth(frame)),
        @"height": @((int)CGRectGetHeight(frame))
    };
}

static NSDictionary *MCPAXNodePointDictionary(CGPoint point) {
    return @{
        @"x": @((int)lrint(point.x)),
        @"y": @((int)lrint(point.y))
    };
}

static NSString *MCPAXNodePipelineProbeTruncatedDescription(id value) {
    if (!value) return nil;
    NSString *description = nil;
    @try {
        description = [value description];
    } @catch (__unused NSException *exception) {
        description = nil;
    }
    if (description.length > 240) {
        return [[description substringToIndex:240] stringByAppendingString:@"…"];
    }
    return description;
}

static NSDictionary *MCPAXNodePipelineProbeValueSummary(id value) {
    if (!value || value == NSNull.null) {
        return @{@"present": @NO};
    }

    NSMutableDictionary *summary = [NSMutableDictionary dictionary];
    summary[@"present"] = @YES;
    NSString *className = NSStringFromClass([value class]);
    if (className.length > 0) summary[@"class"] = className;
    @try {
        summary[@"cfTypeId"] = @((unsigned long)CFGetTypeID((__bridge CFTypeRef)value));
    } @catch (__unused NSException *exception) {
    }

    if ([value isKindOfClass:[NSString class]]) {
        NSString *stringValue = (NSString *)value;
        summary[@"type"] = @"string";
        summary[@"length"] = @(stringValue.length);
        summary[@"value"] = stringValue.length > 240 ?
            [[stringValue substringToIndex:240] stringByAppendingString:@"…"] :
            stringValue;
        return summary;
    }

    if ([value isKindOfClass:[NSNumber class]]) {
        summary[@"type"] = @"number";
        summary[@"value"] = value;
        return summary;
    }

    if ([value isKindOfClass:[NSArray class]]) {
        NSArray *array = (NSArray *)value;
        summary[@"type"] = @"array";
        summary[@"count"] = @(array.count);
        NSMutableArray *itemClasses = [NSMutableArray array];
        NSUInteger limit = MIN((NSUInteger)array.count, (NSUInteger)6);
        for (NSUInteger idx = 0; idx < limit; idx++) {
            id item = array[idx];
            NSString *itemClass = item ? NSStringFromClass([item class]) : @"nil";
            [itemClasses addObject:itemClass ?: @"NSObject"];
        }
        if (itemClasses.count > 0) summary[@"firstItemClasses"] = itemClasses;
        return summary;
    }

    if ([value isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = (NSDictionary *)value;
        summary[@"type"] = @"dictionary";
        summary[@"count"] = @(dict.count);
        NSArray *keys = dict.allKeys;
        if (keys.count > 0) {
            NSUInteger limit = MIN((NSUInteger)keys.count, (NSUInteger)12);
            NSMutableArray *keyStrings = [NSMutableArray array];
            for (NSUInteger idx = 0; idx < limit; idx++) {
                NSString *keyString = [keys[idx] description] ?: @"";
                [keyStrings addObject:keyString];
            }
            summary[@"sampleKeys"] = keyStrings;
        }
        return summary;
    }

    if ([value isKindOfClass:[NSValue class]]) {
        summary[@"type"] = @"value";
        NSString *description = MCPAXNodePipelineProbeTruncatedDescription(value);
        if (description.length > 0) summary[@"description"] = description;
        return summary;
    }

    summary[@"type"] = @"object";
    NSString *description = MCPAXNodePipelineProbeTruncatedDescription(value);
    if (description.length > 0) summary[@"description"] = description;
    return summary;
}

static BOOL MCPAXNodeCGRectFromObject(id object, CGRect *frame) {
    if (!object || !frame) return NO;

    if ([object isKindOfClass:[NSValue class]]) {
        @try {
            *frame = [object CGRectValue];
            return YES;
        } @catch (__unused NSException *exception) {
        }
    }

    CGRect axFrame = CGRectZero;
    if (MCPAXNodeCopyAXValue(object, 3, &axFrame)) {
        *frame = axFrame;
        return YES;
    }

    if ([object isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = object;
        NSNumber *x = dict[@"x"] ?: dict[@"X"];
        NSNumber *y = dict[@"y"] ?: dict[@"Y"];
        NSNumber *width = dict[@"width"] ?: dict[@"Width"];
        NSNumber *height = dict[@"height"] ?: dict[@"Height"];
        if (x && y && width && height) {
            *frame = CGRectMake(x.doubleValue, y.doubleValue, width.doubleValue, height.doubleValue);
            return YES;
        }
    }

    if ([object isKindOfClass:[NSString class]]) {
        CGRect parsed = CGRectFromString(object);
        if (!CGRectEqualToRect(parsed, CGRectZero) || [object containsString:@"0"]) {
            *frame = parsed;
            return YES;
        }
    }

    if ([object isKindOfClass:[NSArray class]]) {
        NSArray *values = object;
        if (values.count >= 4) {
            *frame = CGRectMake([values[0] doubleValue],
                                [values[1] doubleValue],
                                [values[2] doubleValue],
                                [values[3] doubleValue]);
            return YES;
        }
    }

    return NO;
}

static BOOL MCPAXNodeFrameValueHasVisibleArea(id object) {
    CGRect frame = CGRectZero;
    if (!MCPAXNodeCGRectFromObject(object, &frame)) return NO;
    return CGRectGetWidth(frame) > 0.5 && CGRectGetHeight(frame) > 0.5;
}

static BOOL MCPAXNodeCGPointFromObject(id object, CGPoint *point) {
    if (!object || !point) return NO;

    if ([object isKindOfClass:[NSValue class]]) {
        @try {
            *point = [object CGPointValue];
            return YES;
        } @catch (__unused NSException *exception) {
        }
    }

    CGPoint axPoint = CGPointZero;
    if (MCPAXNodeCopyAXValue(object, 1, &axPoint)) {
        *point = axPoint;
        return YES;
    }

    if ([object isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = object;
        NSNumber *x = dict[@"x"] ?: dict[@"X"];
        NSNumber *y = dict[@"y"] ?: dict[@"Y"];
        if (x && y) {
            *point = CGPointMake(x.doubleValue, y.doubleValue);
            return YES;
        }
    }

    if ([object isKindOfClass:[NSArray class]]) {
        NSArray *values = object;
        if (values.count >= 2) {
            *point = CGPointMake([values[0] doubleValue], [values[1] doubleValue]);
            return YES;
        }
    }

    if ([object isKindOfClass:[NSString class]]) {
        CGPoint parsed = CGPointFromString(object);
        if (!CGPointEqualToPoint(parsed, CGPointZero) || [object containsString:@"0"]) {
            *point = parsed;
            return YES;
        }
    }

    return NO;
}

static id MCPAXNodeMsgSendObject(id target, SEL selector) {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(target, selector);
}

static id MCPAXNodeMsgSendObjectArg(id target, SEL selector, id arg) {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;
    return ((id (*)(id, SEL, id))objc_msgSend)(target, selector, arg);
}

static id MCPAXNodeMsgSendObjectUIntArg(id target, SEL selector, uint32_t arg) {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;
    return ((id (*)(id, SEL, uint32_t))objc_msgSend)(target, selector, arg);
}

static unsigned long long MCPAXNodeUnsignedLongLongSelector(id target, SEL selector, BOOL *didRead) {
    if (didRead) *didRead = NO;
    if (!target || !selector || ![target respondsToSelector:selector]) return 0;
    if (didRead) *didRead = YES;
    return ((unsigned long long (*)(id, SEL))objc_msgSend)(target, selector);
}

static BOOL MCPAXNodeCGRectSelector(id target, SEL selector, CGRect *frame) {
    if (!frame) return NO;
    if (!target || !selector || ![target respondsToSelector:selector]) return NO;
    *frame = ((CGRect (*)(id, SEL))objc_msgSend)(target, selector);
    return YES;
}

static BOOL MCPAXNodeBoolSelector(id target, SEL selector, BOOL fallbackValue) {
    if (!target || !selector || ![target respondsToSelector:selector]) return fallbackValue;
    return ((BOOL (*)(id, SEL))objc_msgSend)(target, selector);
}

static NSString *MCPAXNodeStringFromValue(id value) {
    if (!value || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSString class]]) return value;
    if ([value isKindOfClass:[NSAttributedString class]]) return [(NSAttributedString *)value string];
    if ([value respondsToSelector:@selector(string)]) {
        id stringValue = ((id (*)(id, SEL))objc_msgSend)(value, @selector(string));
        if ([stringValue isKindOfClass:[NSString class]]) return stringValue;
    }
    if ([value respondsToSelector:@selector(stringValue)]) {
        id stringValue = [value stringValue];
        if ([stringValue isKindOfClass:[NSString class]]) return stringValue;
    }
    return nil;
}

static id MCPAXNodeNormalizedValue(id value) {
    if (!value || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSString class]] ||
        [value isKindOfClass:[NSNumber class]] ||
        [value isKindOfClass:[NSDictionary class]] ||
        [value isKindOfClass:[NSArray class]]) {
        return value;
    }

    if ([value isKindOfClass:[NSValue class]]) {
        @try {
            CGRect frame = [value CGRectValue];
            return MCPAXNodeFrameDictionary(frame);
        } @catch (__unused NSException *exception) {
        }
    }

    CGRect frame = CGRectZero;
    if (MCPAXNodeCopyAXValue(value, 3, &frame)) {
        return MCPAXNodeFrameDictionary(frame);
    }

    CGPoint point = CGPointZero;
    if (MCPAXNodeCopyAXValue(value, 1, &point)) {
        return MCPAXNodePointDictionary(point);
    }

    return [value description];
}

static NSNumber *MCPAXNodeNumberFromValue(id value) {
    if (!value || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSNumber class]]) return value;
    if ([value isKindOfClass:[NSString class]]) {
        NSString *stringValue = (NSString *)value;
        if (stringValue.length == 0) return nil;
        return @([stringValue doubleValue]);
    }
    if ([value respondsToSelector:@selector(doubleValue)] &&
        ![value isKindOfClass:[NSDictionary class]] &&
        ![value isKindOfClass:[NSArray class]]) {
        return @([value doubleValue]);
    }
    return nil;
}

static NSInteger MCPAXNodeCollectionCount(id value) {
    if (!value || value == NSNull.null) return 0;
    if ([value isKindOfClass:[NSArray class]]) return [(NSArray *)value count];
    if ([value respondsToSelector:@selector(count)]) {
        return (NSInteger)[value count];
    }
    return 1;
}

static NSArray *MCPAXNodeCollectionToArray(id value) {
    if (!value || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSArray class]]) return value;
    if ([value respondsToSelector:@selector(array)]) {
        id arrayValue = ((id (*)(id, SEL))objc_msgSend)(value, @selector(array));
        if ([arrayValue isKindOfClass:[NSArray class]]) return arrayValue;
    }
    if ([value isKindOfClass:[NSSet class]]) {
        return [(NSSet *)value allObjects];
    }
    if ([value respondsToSelector:@selector(allObjects)]) {
        id objects = ((id (*)(id, SEL))objc_msgSend)(value, @selector(allObjects));
        if ([objects isKindOfClass:[NSArray class]]) return objects;
    }
    return nil;
}

static NSString *MCPAXNodeWrapperFingerprint(id element) {
    if (!element) return nil;
    id uiElement = MCPAXNodeMsgSendObject(element, @selector(uiElement));
    if (uiElement) {
        return [NSString stringWithFormat:@"uie:%p", (__bridge void *)uiElement];
    }
    return [NSString stringWithFormat:@"obj:%p", element];
}

static BOOL MCPAXNodeWrapperMatchesPid(id element, MCPAXAttributeBridge *attributeBridge, pid_t expectedPid) {
    if (!element || expectedPid <= 0 || !attributeBridge) return YES;

    id uiElement = MCPAXNodeMsgSendObject(element, @selector(uiElement));
    if (!uiElement) {
        id application = MCPAXNodeMsgSendObject(element, @selector(application));
        uiElement = MCPAXNodeMsgSendObject(application, @selector(uiElement));
    }
    if (!uiElement) return YES;

    pid_t resolvedPid = 0;
    if (![attributeBridge getPid:&resolvedPid fromElement:(__bridge AXUIElementRef)uiElement]) {
        return YES;
    }
    return resolvedPid <= 0 || resolvedPid == expectedPid;
}

static BOOL MCPAXNodeAppendUniqueRoot(NSMutableArray *roots,
                                      NSMutableSet<NSString *> *rootFingerprints,
                                      id root,
                                      MCPAXAttributeBridge *attributeBridge,
                                      pid_t expectedPid) {
    if (!root) return NO;
    if (!MCPAXNodeWrapperMatchesPid(root, attributeBridge, expectedPid)) return NO;

    NSString *fingerprint = MCPAXNodeWrapperFingerprint(root);
    if (fingerprint.length > 0) {
        if ([rootFingerprints containsObject:fingerprint]) {
            return NO;
        }
        [rootFingerprints addObject:fingerprint];
    }

    [roots addObject:root];
    return YES;
}

static void MCPAXNodeAppendRootsFromValue(NSMutableArray *roots,
                                          NSMutableSet<NSString *> *rootFingerprints,
                                          id value,
                                          NSString *sourceKey,
                                          NSMutableDictionary<NSString *, NSNumber *> *rootSourceCounts,
                                          MCPAXAttributeBridge *attributeBridge,
                                          pid_t expectedPid) {
    NSInteger addedCount = 0;
    if ([value isKindOfClass:[NSArray class]]) {
        for (id item in (NSArray *)value) {
            if (MCPAXNodeAppendUniqueRoot(roots, rootFingerprints, item, attributeBridge, expectedPid)) {
                addedCount++;
            }
        }
    } else if (MCPAXNodeAppendUniqueRoot(roots, rootFingerprints, value, attributeBridge, expectedPid)) {
        addedCount = 1;
    }

    if (sourceKey.length > 0 && rootSourceCounts) {
        rootSourceCounts[sourceKey] = @(addedCount);
    }
}

static NSString *MCPAXNodeCompactSummaryFromCounts(NSDictionary<NSString *, NSNumber *> *counts) {
    if (![counts isKindOfClass:[NSDictionary class]] || counts.count == 0) return nil;

    NSArray<NSString *> *keys = [[counts allKeys] sortedArrayUsingSelector:@selector(compare:)];
    NSMutableArray<NSString *> *parts = [NSMutableArray arrayWithCapacity:keys.count];
    for (NSString *key in keys) {
        NSNumber *value = [counts[key] isKindOfClass:[NSNumber class]] ? counts[key] : nil;
        if (!value) continue;
        [parts addObject:[NSString stringWithFormat:@"%@=%@", key, value]];
    }
    return parts.count > 0 ? [parts componentsJoinedByString:@","] : nil;
}

static NSNumber *MCPAXNodeResolvedPidForDiagnosticValue(id value, MCPAXAttributeBridge *attributeBridge) {
    if (!value || !attributeBridge || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSArray class]] ||
        [value isKindOfClass:[NSDictionary class]] ||
        [value isKindOfClass:[NSString class]] ||
        [value isKindOfClass:[NSNumber class]]) {
        return nil;
    }

    id element = value;
    if ([value respondsToSelector:@selector(uiElement)]) {
        element = MCPAXNodeMsgSendObject(value, @selector(uiElement));
    }
    if (!element) return nil;

    pid_t resolvedPid = 0;
    @try {
        if ([attributeBridge getPid:&resolvedPid fromElement:(__bridge AXUIElementRef)element] && resolvedPid > 0) {
            return @(resolvedPid);
        }
    } @catch (__unused NSException *exception) {
    }
    return nil;
}

static NSDictionary *MCPAXNodeDiagnosticAssociationSummary(NSDictionary<NSString *, id> *directValues,
                                                           MCPAXAttributeBridge *attributeBridge) {
    if (![directValues isKindOfClass:[NSDictionary class]] || directValues.count == 0) return nil;

    NSMutableDictionary *summary = [NSMutableDictionary dictionary];

    for (NSString *key in @[@"windowContextId", @"windowDisplayId", @"containerType"]) {
        id value = MCPAXNodeNormalizedValue(directValues[key]);
        if (value) summary[key] = value;
    }

    for (NSString *key in @[@"visibleFrame", @"focusableFrameForZoom", @"centerPoint", @"visiblePoint"]) {
        id value = MCPAXNodeNormalizedValue(directValues[key]);
        if (value) summary[key] = value;
    }

    for (NSString *key in @[@"userInputLabels", @"containerTypes"]) {
        id value = MCPAXNodeSanitizeSnapshotValue(directValues[key], 0);
        if (value) summary[key] = value;
    }

    for (NSString *key in @[@"url", @"path"]) {
        NSString *value = MCPAXNodeStringFromValue(directValues[key]);
        if (value.length > 0) summary[key] = value;
    }

    for (NSString *key in @[@"application", @"remoteApplication", @"elementParent", @"remoteParent"]) {
        if (!directValues[key]) continue;
        summary[[NSString stringWithFormat:@"%@Present", key]] = @YES;
        NSNumber *resolvedPid = MCPAXNodeResolvedPidForDiagnosticValue(directValues[key], attributeBridge);
        if (resolvedPid) {
            summary[[NSString stringWithFormat:@"%@Pid", key]] = resolvedPid;
        }
    }

    return summary.count > 0 ? summary : nil;
}

static NSString *MCPAXNodeCompactAssociationSummary(NSDictionary *association) {
    if (![association isKindOfClass:[NSDictionary class]] || association.count == 0) return nil;

    NSMutableArray<NSString *> *parts = [NSMutableArray array];
    for (NSString *key in @[
        @"applicationPid",
        @"remoteApplicationPid",
        @"elementParentPid",
        @"remoteParentPid",
        @"windowContextId",
        @"windowDisplayId",
        @"containerType"
    ]) {
        id value = association[key];
        if ([value isKindOfClass:[NSNumber class]]) {
            [parts addObject:[NSString stringWithFormat:@"%@=%@", key, value]];
        }
    }

    NSArray *userInputLabels = [association[@"userInputLabels"] isKindOfClass:[NSArray class]] ? association[@"userInputLabels"] : nil;
    if (userInputLabels.count > 0) {
        NSUInteger limit = MIN((NSUInteger)2, userInputLabels.count);
        NSArray *sample = [userInputLabels subarrayWithRange:NSMakeRange(0, limit)];
        [parts addObject:[NSString stringWithFormat:@"userInputLabels=%@", [sample componentsJoinedByString:@"|"]]];
    }

    NSString *frame = MCPAXNodeCompactFrameString(association[@"visibleFrame"]);
    if (frame.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"visibleFrame=%@", frame]];
    }

    return parts.count > 0 ? [parts componentsJoinedByString:@", "] : nil;
}

static NSString *MCPAXNodeCompactDiagnosticsSummary(NSDictionary *diagnostics) {
    if (![diagnostics isKindOfClass:[NSDictionary class]] || diagnostics.count == 0) return nil;

    NSMutableArray<NSString *> *parts = [NSMutableArray array];
    NSNumber *resolvedPid = [diagnostics[@"resolvedPid"] isKindOfClass:[NSNumber class]] ? diagnostics[@"resolvedPid"] : nil;
    if (resolvedPid) {
        [parts addObject:[NSString stringWithFormat:@"resolvedPid=%@", resolvedPid]];
    }

    NSString *role = [diagnostics[@"role"] isKindOfClass:[NSString class]] ? diagnostics[@"role"] : nil;
    if (role.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"role=%@", role]];
    }

    NSString *publicCounts = MCPAXNodeCompactSummaryFromCounts(diagnostics[@"publicChildAttributeCounts"]);
    if (publicCounts.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"public[%@]", publicCounts]];
    }

    NSString *numericCounts = MCPAXNodeCompactSummaryFromCounts(diagnostics[@"numericAttributeCounts"]);
    if (numericCounts.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"numeric[%@]", numericCounts]];
    }

    NSString *xcCounts = MCPAXNodeCompactSummaryFromCounts(diagnostics[@"xcAttributeCounts"]);
    if (xcCounts.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"xc[%@]", xcCounts]];
    }

    NSString *directCounts = MCPAXNodeCompactSummaryFromCounts(diagnostics[@"directAttributeCounts"]);
    if (directCounts.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"direct[%@]", directCounts]];
    }

    NSString *association = MCPAXNodeCompactAssociationSummary(diagnostics[@"directAssociation"]);
    if (association.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"assoc[%@]", association]];
    }

    NSString *rootCounts = MCPAXNodeCompactSummaryFromCounts(diagnostics[@"axelementRootCounts"]);
    if (rootCounts.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"axelement[%@]", rootCounts]];
    }

    return parts.count > 0 ? [parts componentsJoinedByString:@"; "] : nil;
}

static BOOL MCPAXNodeNumberDictionaryHasPositiveValue(id value) {
    if (![value isKindOfClass:[NSDictionary class]]) return NO;
    for (id item in [(NSDictionary *)value allValues]) {
        if ([item isKindOfClass:[NSNumber class]] && [(NSNumber *)item integerValue] > 0) {
            return YES;
        }
    }
    return NO;
}

static BOOL MCPAXNodeNumberDictionaryHasPositiveValueForKeys(id value, NSSet<NSString *> *keys) {
    if (![value isKindOfClass:[NSDictionary class]] || keys.count == 0) return NO;
    NSDictionary *dict = (NSDictionary *)value;
    for (NSString *key in keys) {
        NSNumber *number = [dict[key] isKindOfClass:[NSNumber class]] ? dict[key] : nil;
        if (number.integerValue > 0) return YES;
    }
    return NO;
}

static BOOL MCPAXNodeDiagnosticsHasRenderablePayload(NSDictionary *diagnostics) {
    if (![diagnostics isKindOfClass:[NSDictionary class]] || diagnostics.count == 0) return NO;

    /*
     iOS 14 can return a valid AX application ref plus bookkeeping-only fields
     (pid/context/display id, or an error dictionary from userTestingSnapshot)
     while exposing no real UI payload.  Treat only children/visible/focusable
     candidates or real geometry/string payload as renderable; role/identifier
     alone is not enough because it commonly describes only the app wrapper.
     */
    if (MCPAXNodeNumberDictionaryHasPositiveValueForKeys(diagnostics[@"publicChildAttributeCounts"],
                                                        [NSSet setWithArray:@[
                                                            (__bridge NSString *)kAXChildrenAttribute,
                                                            @"AXVisibleChildren",
                                                            @"AXWindows",
                                                            @"AXElements"
                                                        ]])) {
        return YES;
    }

    if (MCPAXNodeNumberDictionaryHasPositiveValueForKeys(diagnostics[@"numericAttributeCounts"],
                                                        [NSSet setWithArray:@[
                                                            @"3015_visibleElements",
                                                            @"5001_children"
                                                        ]])) {
        return YES;
    }

    if (MCPAXNodeNumberDictionaryHasPositiveValueForKeys(diagnostics[@"xcAttributeCounts"],
                                                        [NSSet setWithArray:@[
                                                            @"children",
                                                            @"childrenCount",
                                                            @"userTestingElements",
                                                            @"visibleFrame"
                                                        ]])) {
        return YES;
    }

    NSSet<NSString *> *renderableDirectKeys = [NSSet setWithArray:@[
        @"visibleElements",
        @"elementsWithSemanticContext",
        @"nativeFocusableElements",
        @"explorerElements",
        @"siriContentNativeFocusableElements",
        @"siriContentElementsWithSemanticContext",
        @"userInputLabels",
        @"containerTypes",
        @"visibleFrame",
        @"focusableFrameForZoom",
        @"containerType",
        @"url",
        @"path",
        @"centerPoint",
        @"visiblePoint"
    ]];
    if (MCPAXNodeNumberDictionaryHasPositiveValueForKeys(diagnostics[@"directAttributeCounts"], renderableDirectKeys)) {
        return YES;
    }

    NSDictionary *snapshotSummary = [diagnostics[@"userTestingSnapshotSummary"] isKindOfClass:[NSDictionary class]] ? diagnostics[@"userTestingSnapshotSummary"] : nil;
    NSNumber *snapshotChildCount = [snapshotSummary[@"childCount"] isKindOfClass:[NSNumber class]] ? snapshotSummary[@"childCount"] : nil;
    NSString *snapshotLabel = [snapshotSummary[@"label"] isKindOfClass:[NSString class]] ? snapshotSummary[@"label"] : nil;
    NSString *snapshotIdentifier = [snapshotSummary[@"identifier"] isKindOfClass:[NSString class]] ? snapshotSummary[@"identifier"] : nil;
    if (snapshotChildCount.integerValue > 0 || snapshotLabel.length > 0 || snapshotIdentifier.length > 0) return YES;

    return NO;
}

static BOOL MCPAXNodeDiagnosticsSuggestInactiveAXRuntime(NSDictionary *diagnostics) {
    if (![diagnostics isKindOfClass:[NSDictionary class]] || diagnostics.count == 0) return NO;
    NSNumber *resolvedPid = [diagnostics[@"resolvedPid"] isKindOfClass:[NSNumber class]] ? diagnostics[@"resolvedPid"] : nil;
    if (!resolvedPid) return NO;
    return !MCPAXNodeDiagnosticsHasRenderablePayload(diagnostics);
}

static NSString *MCPAXNodeInactiveRuntimeSkipReason(void) {
    return @"skipped: app AX element was creatable, but all readable UI attributes/candidate counts were empty; this matches an inactive AXRuntime state and avoids slow position hit-test fallbacks";
}

static double MCPAXNodeSystemVersionNumber(void) {
    NSString *systemVersion = [[UIDevice currentDevice] systemVersion];
    return systemVersion.length > 0 ? systemVersion.doubleValue : 0.0;
}

static BOOL MCPAXNodeIsPreIOS15Runtime(void) {
    double version = MCPAXNodeSystemVersionNumber();
    return version > 0.0 && version < 15.0;
}

static BOOL MCPAXNodeIsIOS15Runtime(void) {
    double version = MCPAXNodeSystemVersionNumber();
    return version >= 15.0 && version < 16.0;
}

static NSInteger MCPAXNodeIntegerCount(NSDictionary *counts, NSString *key) {
    NSNumber *number = [counts[key] isKindOfClass:[NSNumber class]] ? counts[key] : nil;
    return number.integerValue;
}

static NSDictionary *MCPAXNodeTraversalGuardForDiagnostics(NSDictionary *diagnostics,
                                                           NSInteger requestedMaxDepth,
                                                           NSInteger requestedMaxElements) {
    if (!MCPAXNodeIsPreIOS15Runtime()) return nil;
    if (![diagnostics isKindOfClass:[NSDictionary class]] || diagnostics.count == 0) return nil;
    if (requestedMaxDepth <= 2 && requestedMaxElements <= 50) return nil;

    NSDictionary *directCounts = [diagnostics[@"directAttributeCounts"] isKindOfClass:[NSDictionary class]] ?
        diagnostics[@"directAttributeCounts"] :
        nil;
    NSDictionary *numericCounts = [diagnostics[@"numericAttributeCounts"] isKindOfClass:[NSDictionary class]] ?
        diagnostics[@"numericAttributeCounts"] :
        nil;

    NSInteger visibleCount = MAX(MCPAXNodeIntegerCount(directCounts, @"visibleElements"),
                                 MCPAXNodeIntegerCount(numericCounts, @"3015_visibleElements"));
    NSInteger explorerCount = MCPAXNodeIntegerCount(directCounts, @"explorerElements");
    NSInteger nativeFocusableCount = MAX(MCPAXNodeIntegerCount(directCounts, @"nativeFocusableElements"),
                                         MCPAXNodeIntegerCount(directCounts, @"siriContentNativeFocusableElements"));

    /*
     On iOS 14, SpringBoard-hosted AXRuntime can expose a large first-level
     candidate set for complex third-party apps while deeper AX attribute
     crawling may trap inside AXRuntime/UIAccessibility and take SpringBoard
     down.  A shallow tree still returns actionable elements, so cap the crawl
     before walking risky descendants.  Small/system apps are left unchanged.
     */
    BOOL complexCandidateSet = (visibleCount >= 20 || explorerCount >= 30 || nativeFocusableCount >= 10);
    if (!complexCandidateSet) return nil;

    NSInteger cappedDepth = MIN(requestedMaxDepth, 2);
    NSInteger cappedElements = MIN(requestedMaxElements, 50);
    if (cappedDepth == requestedMaxDepth && cappedElements == requestedMaxElements) return nil;

    NSMutableDictionary *guard = [NSMutableDictionary dictionary];
    guard[@"applied"] = @YES;
    guard[@"reason"] = @"ios14_complex_app_shallow_traversal_guard";
    guard[@"requestedMaxDepth"] = @(requestedMaxDepth);
    guard[@"requestedMaxElements"] = @(requestedMaxElements);
    guard[@"effectiveMaxDepth"] = @(cappedDepth);
    guard[@"effectiveMaxElements"] = @(cappedElements);
    guard[@"visibleElements"] = @(visibleCount);
    guard[@"explorerElements"] = @(explorerCount);
    guard[@"nativeFocusableElements"] = @(nativeFocusableCount);
    guard[@"systemVersion"] = [[UIDevice currentDevice] systemVersion] ?: @"unknown";
    return guard;
}

static NSDictionary *MCPAXNodeIOS15SnapshotGuard(NSInteger requestedMaxDepth,
                                                 NSInteger requestedMaxElements) {
    if (!MCPAXNodeIsIOS15Runtime()) return nil;

    NSInteger cappedDepth = MIN(requestedMaxDepth, 2);
    NSInteger cappedElements = MIN(requestedMaxElements, 50);

    NSMutableDictionary *guard = [NSMutableDictionary dictionary];
    guard[@"applied"] = @YES;
    guard[@"reason"] = @"ios15_user_testing_snapshot_guard";
    guard[@"requestedMaxDepth"] = @(requestedMaxDepth);
    guard[@"requestedMaxElements"] = @(requestedMaxElements);
    guard[@"effectiveMaxDepth"] = @(cappedDepth);
    guard[@"effectiveMaxElements"] = @(cappedElements);
    guard[@"snapshotPreferred"] = @YES;
    guard[@"systemVersion"] = [[UIDevice currentDevice] systemVersion] ?: @"unknown";
    return guard;
}

static NSString *MCPAXNodeCompactFrameString(NSDictionary *frame) {
    if (![frame isKindOfClass:[NSDictionary class]]) return nil;
    NSNumber *x = [frame[@"x"] isKindOfClass:[NSNumber class]] ? frame[@"x"] : nil;
    NSNumber *y = [frame[@"y"] isKindOfClass:[NSNumber class]] ? frame[@"y"] : nil;
    NSNumber *width = [frame[@"width"] isKindOfClass:[NSNumber class]] ? frame[@"width"] : nil;
    NSNumber *height = [frame[@"height"] isKindOfClass:[NSNumber class]] ? frame[@"height"] : nil;
    if (!x || !y || !width || !height) return nil;
    return [NSString stringWithFormat:@"%.0f,%.0f,%.0f,%.0f",
            x.doubleValue,
            y.doubleValue,
            width.doubleValue,
            height.doubleValue];
}

static BOOL MCPAXNodeFrameContainsPoint(NSDictionary *frame, CGPoint point, CGFloat tolerance) {
    if (![frame isKindOfClass:[NSDictionary class]]) return NO;
    NSNumber *x = [frame[@"x"] isKindOfClass:[NSNumber class]] ? frame[@"x"] : nil;
    NSNumber *y = [frame[@"y"] isKindOfClass:[NSNumber class]] ? frame[@"y"] : nil;
    NSNumber *width = [frame[@"width"] isKindOfClass:[NSNumber class]] ? frame[@"width"] : nil;
    NSNumber *height = [frame[@"height"] isKindOfClass:[NSNumber class]] ? frame[@"height"] : nil;
    if (!x || !y || !width || !height || width.doubleValue <= 0 || height.doubleValue <= 0) return NO;
    CGRect rect = CGRectMake(x.doubleValue, y.doubleValue, width.doubleValue, height.doubleValue);
    return CGRectContainsPoint(CGRectInset(rect, -tolerance, -tolerance), point);
}

static CGFloat MCPAXNodeFrameArea(NSDictionary *frame) {
    if (![frame isKindOfClass:[NSDictionary class]]) return CGFLOAT_MAX;
    NSNumber *width = [frame[@"width"] isKindOfClass:[NSNumber class]] ? frame[@"width"] : nil;
    NSNumber *height = [frame[@"height"] isKindOfClass:[NSNumber class]] ? frame[@"height"] : nil;
    if (!width || !height || width.doubleValue <= 0 || height.doubleValue <= 0) return CGFLOAT_MAX;
    return (CGFloat)(width.doubleValue * height.doubleValue);
}

static NSInteger MCPAXNodeNumericFallbackMaxElements(NSInteger requestedMaxElements) {
    if (requestedMaxElements <= 0) return 50;
    return MIN(requestedMaxElements, 2000);
}

// AX attribute frames/clipping use interface coordinates, while native AX hit-test APIs take
// fixed display points. Convert attribute results exactly once at the public boundary.
static id MCPAXNodeResultInFixedCoordinates(id value, CGAffineTransform transform) {
    if ([value isKindOfClass:NSArray.class]) {
        NSMutableArray *result = [NSMutableArray arrayWithCapacity:[value count]];
        for (id child in value) [result addObject:MCPAXNodeResultInFixedCoordinates(child, transform)];
        return result;
    }
    if (![value isKindOfClass:NSDictionary.class]) return value;
    NSMutableDictionary *result = [value mutableCopy];
    for (NSString *key in value) {
        id child = value[key];
        BOOL rectKey = [@[@"rect", @"visible_rect", @"frame", @"visibleFrame", @"focusable_frame_for_zoom"] containsObject:key];
        BOOL pointKey = [@[@"tap", @"center_point", @"visible_point", @"hit_test_point", @"samplePoint"] containsObject:key];
        if ((rectKey || pointKey) && [child isKindOfClass:NSDictionary.class] &&
            [child[@"x"] isKindOfClass:NSNumber.class] && [child[@"y"] isKindOfClass:NSNumber.class]) {
            NSMutableDictionary *converted = [child mutableCopy];
            if (rectKey && [child[@"width"] isKindOfClass:NSNumber.class] && [child[@"height"] isKindOfClass:NSNumber.class]) {
                CGRect rect = CGRectMake([child[@"x"] doubleValue], [child[@"y"] doubleValue],
                                         [child[@"width"] doubleValue], [child[@"height"] doubleValue]);
                rect = CGRectApplyAffineTransform(rect, transform);
                converted[@"x"] = @(rect.origin.x); converted[@"y"] = @(rect.origin.y);
                converted[@"width"] = @(rect.size.width); converted[@"height"] = @(rect.size.height);
            } else if (pointKey) {
                CGPoint point = CGPointApplyAffineTransform(CGPointMake([child[@"x"] doubleValue], [child[@"y"] doubleValue]), transform);
                converted[@"x"] = @(point.x); converted[@"y"] = @(point.y);
            }
            result[key] = converted;
        } else {
            result[key] = MCPAXNodeResultInFixedCoordinates(child, transform);
        }
    }
    return result;
}

static CGRect MCPAXNodeScreenBounds(void) {
    CGRect bounds = UIScreen.mainScreen.bounds;
    return CGRectIsEmpty(bounds) ? CGRectMake(0, 0, 375, 667) : bounds;
}

static CGRect MCPAXNodeIntersectionWithScreen(CGRect frame, CGRect screenBounds) {
    if (CGRectIsNull(frame) || CGRectIsEmpty(frame)) return CGRectNull;
    CGRect clipped = CGRectIntersection(frame, screenBounds);
    return (CGRectIsNull(clipped) || CGRectIsEmpty(clipped)) ? CGRectNull : clipped;
}

static NSDictionary *MCPAXNodeIntegerFrameDictionary(CGRect frame) {
    return @{
        @"x": @((NSInteger)lrint(CGRectGetMinX(frame))),
        @"y": @((NSInteger)lrint(CGRectGetMinY(frame))),
        @"width": @((NSInteger)lrint(CGRectGetWidth(frame))),
        @"height": @((NSInteger)lrint(CGRectGetHeight(frame)))
    };
}

static NSDictionary *MCPAXNodeIntegerPointDictionary(CGPoint point) {
    return @{
        @"x": @((NSInteger)lrint(point.x)),
        @"y": @((NSInteger)lrint(point.y))
    };
}

static NSDictionary *MCPAXNodeCompactScreenDictionary(CGRect screenBounds) {
    CGFloat scale = UIScreen.mainScreen.scale;
    if (scale <= 0.0) scale = 1.0;

    CGFloat width = CGRectGetWidth(screenBounds);
    CGFloat height = CGRectGetHeight(screenBounds);
    return @{
        @"width": @((NSInteger)lrint(width)),
        @"height": @((NSInteger)lrint(height)),
        @"scale": @(scale),
        @"pixel_width": @((NSInteger)lrint(width * scale)),
        @"pixel_height": @((NSInteger)lrint(height * scale)),
        @"orientation": width >= height ? @"landscape" : @"portrait"
    };
}

static NSString *MCPAXNodeCompactFrameFingerprint(NSDictionary *frame) {
    if (![frame isKindOfClass:[NSDictionary class]]) return @"";
    NSNumber *x = [frame[@"x"] isKindOfClass:[NSNumber class]] ? frame[@"x"] : nil;
    NSNumber *y = [frame[@"y"] isKindOfClass:[NSNumber class]] ? frame[@"y"] : nil;
    NSNumber *width = [frame[@"width"] isKindOfClass:[NSNumber class]] ? frame[@"width"] : nil;
    NSNumber *height = [frame[@"height"] isKindOfClass:[NSNumber class]] ? frame[@"height"] : nil;
    if (!x || !y || !width || !height) return @"";
    return [NSString stringWithFormat:@"%.0f,%.0f,%.0f,%.0f",
            x.doubleValue,
            y.doubleValue,
            width.doubleValue,
            height.doubleValue];
}

static NSString *MCPAXNodeCompactPointFingerprint(NSDictionary *point) {
    if (![point isKindOfClass:[NSDictionary class]]) return @"";
    NSNumber *x = [point[@"x"] isKindOfClass:[NSNumber class]] ? point[@"x"] : nil;
    NSNumber *y = [point[@"y"] isKindOfClass:[NSNumber class]] ? point[@"y"] : nil;
    if (!x || !y) return @"";
    return [NSString stringWithFormat:@"%.0f,%.0f", x.doubleValue, y.doubleValue];
}

static NSString *MCPAXNodeCompactElementFingerprint(NSDictionary *element) {
    if (![element isKindOfClass:[NSDictionary class]]) return nil;
    NSString *text = [element[@"text"] isKindOfClass:[NSString class]] ? element[@"text"] : @"";
    NSString *type = [element[@"type"] isKindOfClass:[NSString class]] ? element[@"type"] : @"";
    NSString *rect = MCPAXNodeCompactFrameFingerprint(element[@"rect"]);
    NSString *tap = MCPAXNodeCompactPointFingerprint(element[@"tap"]);
    NSNumber *contextId = [element[@"contextId"] isKindOfClass:[NSNumber class]] ? element[@"contextId"] : @0;
    return [NSString stringWithFormat:@"%@|%@|%@|%@|%@", contextId, type, text, rect, tap];
}

static NSArray<NSValue *> *MCPAXNodeCompactScreenProbePoints(CGRect bounds) {
    if (CGRectIsEmpty(bounds)) return @[];

    NSMutableArray<NSValue *> *points = [NSMutableArray array];
    NSMutableSet<NSString *> *seen = [NSMutableSet set];
    void (^appendPoint)(CGPoint) = ^(CGPoint point) {
        if (!CGRectContainsPoint(bounds, point)) return;
        NSString *key = [NSString stringWithFormat:@"%.0f,%.0f", point.x, point.y];
        if ([seen containsObject:key]) return;
        [seen addObject:key];
        [points addObject:[NSValue valueWithCGPoint:point]];
    };

    for (NSValue *pointValue in MCPAXNodeScreenProbePoints(bounds)) {
        appendPoint(pointValue.CGPointValue);
    }

    CGFloat minX = CGRectGetMinX(bounds);
    CGFloat minY = CGRectGetMinY(bounds);
    CGFloat width = CGRectGetWidth(bounds);
    CGFloat height = CGRectGetHeight(bounds);

    NSArray<NSNumber *> *xFractions = @[@0.08, @0.25, @0.50, @0.75, @0.92];
    NSArray<NSNumber *> *yFractions = @[@0.06, @0.24, @0.47, @0.64, @0.75, @0.89, @0.97];
    for (NSNumber *yFraction in yFractions) {
        CGFloat y = minY + height * yFraction.doubleValue;
        for (NSNumber *xFraction in xFractions) {
            CGFloat x = minX + width * xFraction.doubleValue;
            appendPoint(CGPointMake(x, y));
        }
    }

    return points;
}

static void MCPAXNodeAddCompactText(NSMutableOrderedSet<NSString *> *texts, id value) {
    if (!texts || !value || value == NSNull.null) return;

    if ([value isKindOfClass:[NSArray class]]) {
        for (id item in (NSArray *)value) {
            MCPAXNodeAddCompactText(texts, item);
        }
        return;
    }

    NSString *string = MCPAXNodeStringFromValue(value);
    NSString *trimmed = [string isKindOfClass:[NSString class]] ?
        [string stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] :
        nil;
    if (trimmed.length > 0 && !MCPAXNodeStringLooksLikeAXError(trimmed)) {
        [texts addObject:trimmed];
    }
}

static BOOL MCPAXNodeStringLooksLikeAXError(NSString *value) {
    if (![value isKindOfClass:[NSString class]] || value.length == 0) return NO;
    return ([value containsString:@"error:-252"] ||
            [value containsString:@"kAXValueAXErrorType"]);
}

static BOOL MCPAXNodeSerializedNodeHasRenderablePayload(NSDictionary *node) {
    if (![node isKindOfClass:[NSDictionary class]] || node.count == 0) return NO;

    NSArray *children = [node[@"children"] isKindOfClass:[NSArray class]] ? node[@"children"] : nil;
    if (children.count > 0) return YES;

    for (NSString *key in @[
        @"label",
        @"value",
        @"title",
        @"placeholder",
        @"url",
        @"path"
    ]) {
        NSString *value = [node[key] isKindOfClass:[NSString class]] ? node[key] : nil;
        if (value.length > 0 && !MCPAXNodeStringLooksLikeAXError(value)) return YES;
    }

    for (NSString *key in @[@"frame", @"visibleFrame", @"focusable_frame_for_zoom"]) {
        if (MCPAXNodeFrameValueHasVisibleArea(node[key])) return YES;
    }

    for (NSString *key in @[
        @"center_point",
        @"visible_point",
        @"user_input_labels",
        @"userTestingSnapshot",
        @"userTestingSnapshotSummary"
    ]) {
        id value = node[key];
        if ([value isKindOfClass:[NSDictionary class]] && [(NSDictionary *)value count] > 0) return YES;
        if ([value isKindOfClass:[NSArray class]] && [(NSArray *)value count] > 0) return YES;
    }

    for (NSString *key in @[@"child_count"]) {
        NSNumber *value = [node[key] isKindOfClass:[NSNumber class]] ? node[key] : nil;
        if (value.integerValue > 0) return YES;
    }

    return NO;
}

static NSArray<NSString *> *MCPAXNodeSemanticLabels(NSDictionary *node) {
    NSMutableArray<NSString *> *labels = [NSMutableArray array];

    NSString *(^normalizedString)(id) = ^NSString *(id value) {
        NSString *stringValue = MCPAXNodeStringFromValue(value);
        if (![stringValue isKindOfClass:[NSString class]]) return nil;
        NSString *trimmed = [stringValue stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        return trimmed.length > 0 ? trimmed : nil;
    };

    for (NSString *key in @[@"identifier", @"label", @"title", @"description", @"placeholder", @"url", @"path"]) {
        NSString *value = normalizedString(node[key]);
        if (value.length > 0 && ![labels containsObject:value]) {
            [labels addObject:value];
        }
    }

    NSArray *userInputLabels = [node[@"user_input_labels"] isKindOfClass:[NSArray class]] ? node[@"user_input_labels"] : nil;
    for (id item in userInputLabels) {
        NSString *value = normalizedString(item);
        if (value.length > 0 && ![labels containsObject:value]) {
            [labels addObject:value];
        }
    }

    NSString *valueString = normalizedString(node[@"value"]);
    if (valueString.length > 0 && !MCPAXNodeStringLooksLikeAXError(valueString) && ![labels containsObject:valueString]) {
        [labels addObject:valueString];
    }

    return labels;
}

static NSString *MCPAXNodeFingerprintForNode(NSDictionary *node) {
    if (![node isKindOfClass:[NSDictionary class]]) return nil;
    NSString *role = [node[@"role"] isKindOfClass:[NSString class]] ? node[@"role"] : @"";
    NSArray<NSString *> *semanticLabels = MCPAXNodeSemanticLabels(node);
    NSString *semanticKey = semanticLabels.count > 0 ? [semanticLabels componentsJoinedByString:@"|"] : @"";
    NSString *frame = MCPAXNodeCompactFrameString(node[@"frame"]) ?: @"";
    NSDictionary *centerPoint = [node[@"center_point"] isKindOfClass:[NSDictionary class]] ? node[@"center_point"] : nil;
    NSString *center = centerPoint ? [NSString stringWithFormat:@"%.0f,%.0f",
                                      [centerPoint[@"x"] doubleValue],
                                      [centerPoint[@"y"] doubleValue]] : @"";
    id containerType = node[@"container_type"] ?: @"";
    return [NSString stringWithFormat:@"%@|%@|%@|%@|%@", role, semanticKey, frame, center, containerType];
}

static NSString *MCPAXNodePrimarySemanticLabel(NSDictionary *node) {
    NSArray<NSString *> *semanticLabels = MCPAXNodeSemanticLabels(node);
    return semanticLabels.firstObject;
}

static BOOL MCPAXNodePointsEqual(NSDictionary *lhs, NSDictionary *rhs) {
    NSDictionary *leftPoint = [lhs isKindOfClass:[NSDictionary class]] ? lhs : nil;
    NSDictionary *rightPoint = [rhs isKindOfClass:[NSDictionary class]] ? rhs : nil;
    if (!leftPoint || !rightPoint) return NO;

    NSNumber *leftX = [leftPoint[@"x"] isKindOfClass:[NSNumber class]] ? leftPoint[@"x"] : nil;
    NSNumber *leftY = [leftPoint[@"y"] isKindOfClass:[NSNumber class]] ? leftPoint[@"y"] : nil;
    NSNumber *rightX = [rightPoint[@"x"] isKindOfClass:[NSNumber class]] ? rightPoint[@"x"] : nil;
    NSNumber *rightY = [rightPoint[@"y"] isKindOfClass:[NSNumber class]] ? rightPoint[@"y"] : nil;
    if (!leftX || !leftY || !rightX || !rightY) return NO;

    return (lrint(leftX.doubleValue) == lrint(rightX.doubleValue) &&
            lrint(leftY.doubleValue) == lrint(rightY.doubleValue));
}

static BOOL MCPAXNodeContainerTypesCompatible(NSDictionary *parent, NSDictionary *child) {
    id parentType = [parent isKindOfClass:[NSDictionary class]] ? parent[@"container_type"] : nil;
    id childType = [child isKindOfClass:[NSDictionary class]] ? child[@"container_type"] : nil;
    if (!parentType || !childType) return YES;
    return [parentType isEqual:childType];
}

static BOOL MCPAXNodeLooksLikeDuplicateWrapper(NSDictionary *parent, NSDictionary *child) {
    if (![parent isKindOfClass:[NSDictionary class]] || ![child isKindOfClass:[NSDictionary class]]) return NO;

    NSString *parentFingerprint = MCPAXNodeFingerprintForNode(parent);
    NSString *childFingerprint = MCPAXNodeFingerprintForNode(child);
    if (parentFingerprint.length > 0 && [parentFingerprint isEqualToString:childFingerprint]) {
        return YES;
    }

    NSString *parentPrimaryLabel = MCPAXNodePrimarySemanticLabel(parent);
    NSString *childPrimaryLabel = MCPAXNodePrimarySemanticLabel(child);
    if (parentPrimaryLabel.length == 0 || childPrimaryLabel.length == 0) return NO;
    if (![parentPrimaryLabel isEqualToString:childPrimaryLabel]) return NO;

    NSString *parentRole = [parent[@"role"] isKindOfClass:[NSString class]] ? parent[@"role"] : nil;
    NSString *childRole = [child[@"role"] isKindOfClass:[NSString class]] ? child[@"role"] : nil;
    if (parentRole.length > 0 && childRole.length > 0 && ![parentRole isEqualToString:childRole]) {
        return NO;
    }

    if (!MCPAXNodeContainerTypesCompatible(parent, child)) {
        return NO;
    }

    NSString *parentFrame = MCPAXNodeCompactFrameString(parent[@"frame"]);
    NSString *childFrame = MCPAXNodeCompactFrameString(child[@"frame"]);
    BOOL sameFrame = (parentFrame.length > 0 && childFrame.length > 0 && [parentFrame isEqualToString:childFrame]);
    BOOL sameCenter = MCPAXNodePointsEqual(parent[@"center_point"], child[@"center_point"]);
    if (!(sameFrame || sameCenter)) {
        return NO;
    }

    return YES;
}

static BOOL MCPAXNodeIsLowSignalLeafWrapper(NSDictionary *node) {
    if (![node isKindOfClass:[NSDictionary class]]) return NO;

    NSArray<NSString *> *semanticLabels = MCPAXNodeSemanticLabels(node);
    if (semanticLabels.count > 0) return NO;

    NSArray *children = [node[@"children"] isKindOfClass:[NSArray class]] ? node[@"children"] : nil;
    if (children.count > 0) return NO;

    for (NSString *key in @[@"frame", @"visibleFrame", @"center_point", @"visible_point",
                            @"focusable_frame_for_zoom", @"identifier", @"title",
                            @"description", @"placeholder", @"url", @"path"]) {
        if (node[key]) return NO;
    }

    if ([node[@"value"] isKindOfClass:[NSString class]] && [((NSString *)node[@"value"]) length] > 0) {
        return NO;
    }

    id semanticContext = [node[@"semanticContext"] isKindOfClass:[NSDictionary class]] ? node[@"semanticContext"] : nil;
    NSDictionary *candidateCounts = [semanticContext[@"candidateCounts"] isKindOfClass:[NSDictionary class]] ? semanticContext[@"candidateCounts"] : nil;
    for (id value in candidateCounts.allValues) {
        if ([value respondsToSelector:@selector(integerValue)] && [value integerValue] > 0) {
            return NO;
        }
    }

    return YES;
}

static NSComparisonResult MCPAXNodeCompareNodesByFrame(NSDictionary *lhs, NSDictionary *rhs) {
    NSDictionary *leftFrame = [lhs isKindOfClass:[NSDictionary class]] ? lhs[@"frame"] : nil;
    NSDictionary *rightFrame = [rhs isKindOfClass:[NSDictionary class]] ? rhs[@"frame"] : nil;

    CGFloat ly = [leftFrame[@"y"] doubleValue];
    CGFloat ry = [rightFrame[@"y"] doubleValue];
    if (ly < ry) return NSOrderedAscending;
    if (ly > ry) return NSOrderedDescending;

    CGFloat lx = [leftFrame[@"x"] doubleValue];
    CGFloat rx = [rightFrame[@"x"] doubleValue];
    if (lx < rx) return NSOrderedAscending;
    if (lx > rx) return NSOrderedDescending;

    NSString *llabel = [lhs[@"label"] isKindOfClass:[NSString class]] ? lhs[@"label"] : @"";
    NSString *rlabel = [rhs[@"label"] isKindOfClass:[NSString class]] ? rhs[@"label"] : @"";
    if (llabel.length == 0) {
        NSArray<NSString *> *semanticLabels = MCPAXNodeSemanticLabels(lhs);
        llabel = semanticLabels.firstObject ?: @"";
    }
    if (rlabel.length == 0) {
        NSArray<NSString *> *semanticLabels = MCPAXNodeSemanticLabels(rhs);
        rlabel = semanticLabels.firstObject ?: @"";
    }
    return [llabel compare:rlabel];
}

static NSString *MCPAXNodePointerStringForObject(id value) {
    if (!value || value == NSNull.null) return nil;
    return [NSString stringWithFormat:@"%p", (__bridge const void *)value];
}

static NSArray *MCPAXNodeUniqueArrayByDescription(id value) {
    NSArray *array = [value isKindOfClass:[NSArray class]] ? value : nil;
    if (!array) return nil;
    NSMutableOrderedSet *ordered = [NSMutableOrderedSet orderedSet];
    for (id item in array) {
        if (!item || item == NSNull.null) continue;
        NSString *key = [item isKindOfClass:[NSString class]] ? item : [item description];
        if (key.length == 0) continue;
        [ordered addObject:item];
    }
    return ordered.count > 0 ? ordered.array : nil;
}

static void MCPAXNodeStripInternalKeysRecursively(NSMutableDictionary *node) {
    if (![node isKindOfClass:[NSMutableDictionary class]]) return;

    [node removeObjectForKey:@"_ax_ref"];
    [node removeObjectForKey:@"_parent_ax_ref"];
    [node removeObjectForKey:@"_remote_parent_ax_ref"];

    NSArray *children = [node[@"children"] isKindOfClass:[NSArray class]] ? node[@"children"] : nil;
    if (children.count == 0) return;

    NSMutableArray *sanitizedChildren = [NSMutableArray arrayWithCapacity:children.count];
    for (NSDictionary *child in children) {
        if (![child isKindOfClass:[NSDictionary class]]) continue;
        NSMutableDictionary *mutableChild = [child mutableCopy];
        MCPAXNodeStripInternalKeysRecursively(mutableChild);
        [sanitizedChildren addObject:mutableChild];
    }
    node[@"children"] = sanitizedChildren;
}

static void MCPAXNodeMergeChildrenArrays(NSMutableDictionary *into, NSDictionary *from) {
    NSArray *lhs = [into[@"children"] isKindOfClass:[NSArray class]] ? into[@"children"] : nil;
    NSArray *rhs = [from[@"children"] isKindOfClass:[NSArray class]] ? from[@"children"] : nil;
    if (rhs.count == 0) return;
    if (lhs.count == 0) {
        into[@"children"] = rhs;
        return;
    }

    NSMutableOrderedSet *ordered = [NSMutableOrderedSet orderedSet];
    for (NSDictionary *child in lhs) {
        NSString *fingerprint = MCPAXNodeFingerprintForNode(child) ?: [child description];
        if (fingerprint.length > 0) {
            [ordered addObject:child];
        }
    }
    for (NSDictionary *child in rhs) {
        NSString *fingerprint = MCPAXNodeFingerprintForNode(child) ?: [child description];
        BOOL exists = NO;
        for (NSDictionary *existing in ordered.array) {
            NSString *existingFingerprint = MCPAXNodeFingerprintForNode(existing) ?: [existing description];
            if ([existingFingerprint isEqualToString:fingerprint]) {
                exists = YES;
                break;
            }
        }
        if (!exists) {
            [ordered addObject:child];
        }
    }
    into[@"children"] = ordered.array;
}

static void MCPAXNodeMergeSemanticContext(NSMutableDictionary *into, NSDictionary *from) {
    NSDictionary *lhs = [into[@"semanticContext"] isKindOfClass:[NSDictionary class]] ? into[@"semanticContext"] : nil;
    NSDictionary *rhs = [from[@"semanticContext"] isKindOfClass:[NSDictionary class]] ? from[@"semanticContext"] : nil;
    if (!rhs) return;

    NSMutableDictionary *merged = lhs ? [lhs mutableCopy] : [NSMutableDictionary dictionary];
    [rhs enumerateKeysAndObjectsUsingBlock:^(id key, id obj, BOOL *stop) {
        id existing = merged[key];
        if ([existing isKindOfClass:[NSDictionary class]] && [obj isKindOfClass:[NSDictionary class]]) {
            NSMutableDictionary *nested = [existing mutableCopy];
            [(NSDictionary *)obj enumerateKeysAndObjectsUsingBlock:^(id nestedKey, id nestedObj, BOOL *nestedStop) {
                NSNumber *existingNumber = [nested[nestedKey] isKindOfClass:[NSNumber class]] ? nested[nestedKey] : nil;
                NSNumber *incomingNumber = [nestedObj isKindOfClass:[NSNumber class]] ? nestedObj : nil;
                if (existingNumber && incomingNumber) {
                    nested[nestedKey] = @((MAX(existingNumber.integerValue, incomingNumber.integerValue)));
                } else if (!nested[nestedKey]) {
                    nested[nestedKey] = nestedObj;
                }
            }];
            merged[key] = nested;
        } else if (!existing) {
            merged[key] = obj;
        }
    }];
    if (merged.count > 0) {
        into[@"semanticContext"] = merged;
    }
}

static NSMutableDictionary *MCPAXNodeMergedNode(NSDictionary *node) {
    return [node isKindOfClass:[NSDictionary class]] ? [node mutableCopy] : [NSMutableDictionary dictionary];
}

static void MCPAXNodeMergeCandidateNode(NSMutableDictionary *into, NSDictionary *from) {
    for (NSString *key in @[
        @"label", @"title", @"description", @"identifier", @"placeholder",
        @"frame", @"visibleFrame", @"window_context_id", @"window_display_id",
        @"container_type", @"focusable_frame_for_zoom", @"center_point",
        @"visible_point", @"url", @"path", @"automation_type", @"child_count"
    ]) {
        if (!into[key] && from[key]) {
            into[key] = from[key];
        }
    }

    if (!into[@"value"] && from[@"value"] && !MCPAXNodeStringLooksLikeAXError(from[@"value"])) {
        into[@"value"] = from[@"value"];
    }

    NSArray *mergedUserInputLabels = MCPAXNodeUniqueArrayByDescription(into[@"user_input_labels"] ?: from[@"user_input_labels"]);
    if (!mergedUserInputLabels && into[@"user_input_labels"] && from[@"user_input_labels"]) {
        NSMutableOrderedSet *ordered = [NSMutableOrderedSet orderedSet];
        for (id item in (NSArray *)into[@"user_input_labels"]) if (item) [ordered addObject:item];
        for (id item in (NSArray *)from[@"user_input_labels"]) if (item) [ordered addObject:item];
        mergedUserInputLabels = ordered.array;
    }
    if (mergedUserInputLabels.count > 0) into[@"user_input_labels"] = mergedUserInputLabels;

    NSArray *lhsContainerTypes = [into[@"container_types"] isKindOfClass:[NSArray class]] ? into[@"container_types"] : nil;
    NSArray *rhsContainerTypes = [from[@"container_types"] isKindOfClass:[NSArray class]] ? from[@"container_types"] : nil;
    if (rhsContainerTypes.count > 0) {
        NSMutableOrderedSet *ordered = [NSMutableOrderedSet orderedSet];
        for (id item in lhsContainerTypes) if (item) [ordered addObject:item];
        for (id item in rhsContainerTypes) if (item) [ordered addObject:item];
        if (ordered.count > 0) into[@"container_types"] = ordered.array;
    }

    if ([from[@"visible"] respondsToSelector:@selector(boolValue)]) {
        BOOL visible = [from[@"visible"] boolValue] || [into[@"visible"] boolValue];
        into[@"visible"] = @(visible);
    }
    if ([from[@"hittable"] respondsToSelector:@selector(boolValue)]) {
        BOOL hittable = [from[@"hittable"] boolValue] || [into[@"hittable"] boolValue];
        into[@"hittable"] = @(hittable);
    }

    MCPAXNodeMergeSemanticContext(into, from);
    MCPAXNodeMergeChildrenArrays(into, from);
}

static NSArray<NSDictionary *> *MCPAXNodeNormalizedCandidateChildren(NSArray<NSDictionary *> *children,
                                                                     BOOL allowReparenting) {
    if (![children isKindOfClass:[NSArray class]] || children.count == 0) return children;

    NSMutableArray<NSMutableDictionary *> *mergedChildren = [NSMutableArray array];
    NSMutableDictionary<NSString *, NSMutableDictionary *> *byFingerprint = [NSMutableDictionary dictionary];
    for (NSDictionary *child in children) {
        if (![child isKindOfClass:[NSDictionary class]]) continue;
        NSString *fingerprint = MCPAXNodeFingerprintForNode(child);
        if (fingerprint.length == 0) {
            [mergedChildren addObject:[child mutableCopy]];
            continue;
        }

        NSMutableDictionary *existing = byFingerprint[fingerprint];
        if (!existing) {
            existing = MCPAXNodeMergedNode(child);
            byFingerprint[fingerprint] = existing;
            [mergedChildren addObject:existing];
        } else {
            MCPAXNodeMergeCandidateNode(existing, child);
        }
    }

    if (!allowReparenting || mergedChildren.count < 2) {
        return mergedChildren;
    }

    NSMutableDictionary<NSString *, NSMutableDictionary *> *byElementRef = [NSMutableDictionary dictionary];
    for (NSMutableDictionary *child in mergedChildren) {
        NSString *elementRef = [child[@"_ax_ref"] isKindOfClass:[NSString class]] ? child[@"_ax_ref"] : nil;
        if (elementRef.length > 0) {
            byElementRef[elementRef] = child;
        }
    }

    NSMutableArray<NSMutableDictionary *> *topLevel = [NSMutableArray array];
    for (NSMutableDictionary *child in mergedChildren) {
        NSString *parentRef = [child[@"_parent_ax_ref"] isKindOfClass:[NSString class]] ? child[@"_parent_ax_ref"] : nil;
        if (parentRef.length == 0) {
            parentRef = [child[@"_remote_parent_ax_ref"] isKindOfClass:[NSString class]] ? child[@"_remote_parent_ax_ref"] : nil;
        }
        NSMutableDictionary *parentNode = parentRef.length > 0 ? byElementRef[parentRef] : nil;
        if (!parentNode || parentNode == child) {
            [topLevel addObject:child];
            continue;
        }

        NSMutableArray *parentChildren = [parentNode[@"children"] isKindOfClass:[NSArray class]] ?
            [parentNode[@"children"] mutableCopy] :
            [NSMutableArray array];
        BOOL duplicate = NO;
        NSString *childFingerprint = MCPAXNodeFingerprintForNode(child);
        for (NSDictionary *existingChild in parentChildren) {
            NSString *existingFingerprint = MCPAXNodeFingerprintForNode(existingChild) ?: @"";
            NSString *incomingFingerprint = childFingerprint ?: @"";
            if ([existingFingerprint isEqualToString:incomingFingerprint]) {
                duplicate = YES;
                break;
            }
        }
        if (!duplicate) {
            [parentChildren addObject:child];
            parentNode[@"children"] = parentChildren;
        }
    }

    NSArray<NSDictionary *> *result = topLevel.count > 0 ? topLevel : mergedChildren;
    for (NSMutableDictionary *child in mergedChildren) {
        MCPAXNodeStripInternalKeysRecursively(child);
    }
    return result;
}

static NSArray<NSValue *> *MCPAXNodeScreenProbePoints(CGRect bounds) {
    if (CGRectIsEmpty(bounds)) return @[];

    CGFloat midX = CGRectGetMidX(bounds);
    CGFloat midY = CGRectGetMidY(bounds);
    CGFloat quarterY = CGRectGetMinY(bounds) + (CGRectGetHeight(bounds) * 0.25);
    CGFloat lowerY = CGRectGetMinY(bounds) + (CGRectGetHeight(bounds) * 0.75);

    return @[
        [NSValue valueWithCGPoint:CGPointMake(midX, midY)],
        [NSValue valueWithCGPoint:CGPointMake(midX, quarterY)],
        [NSValue valueWithCGPoint:CGPointMake(midX, lowerY)]
    ];
}

static NSArray<NSValue *> *MCPAXNodeDebugGridProbePoints(CGRect bounds) {
    if (CGRectIsEmpty(bounds)) return @[];

    CGFloat minX = CGRectGetMinX(bounds);
    CGFloat minY = CGRectGetMinY(bounds);
    CGFloat width = CGRectGetWidth(bounds);
    CGFloat height = CGRectGetHeight(bounds);

    return @[
        [NSValue valueWithCGPoint:CGPointMake(minX + width * 0.5, minY + height * 0.5)],
        [NSValue valueWithCGPoint:CGPointMake(minX + width * 0.3, minY + height * 0.3)],
        [NSValue valueWithCGPoint:CGPointMake(minX + width * 0.7, minY + height * 0.3)],
        [NSValue valueWithCGPoint:CGPointMake(minX + width * 0.3, minY + height * 0.7)],
        [NSValue valueWithCGPoint:CGPointMake(minX + width * 0.7, minY + height * 0.7)]
    ];
}

static NSString *MCPAXNodeAccessibilityFingerprint(id element) {
    if (!element) return nil;

    NSString *uuid = MCPAXNodeStringFromValue(MCPAXNodeMsgSendObject(element, @selector(uuid)));
    BOOL didReadRemotePid = NO;
    unsigned long long remotePid = MCPAXNodeUnsignedLongLongSelector(element, @selector(remotePid), &didReadRemotePid);
    BOOL didReadContextId = NO;
    unsigned long long contextId = MCPAXNodeUnsignedLongLongSelector(element, @selector(contextId), &didReadContextId);

    if (uuid.length > 0 || didReadRemotePid || didReadContextId) {
        NSMutableArray<NSString *> *parts = [NSMutableArray array];
        if (uuid.length > 0) [parts addObject:[NSString stringWithFormat:@"uuid:%@", uuid]];
        if (didReadRemotePid) [parts addObject:[NSString stringWithFormat:@"pid:%llu", remotePid]];
        if (didReadContextId) [parts addObject:[NSString stringWithFormat:@"ctx:%llu", contextId]];
        return [parts componentsJoinedByString:@"|"];
    }

    return [NSString stringWithFormat:@"%@:%p", NSStringFromClass([element class]) ?: @"NSObject", element];
}

static id MCPAXNodeFirstObjectValueForSelectors(id target, NSArray<NSString *> *selectorNames) {
    for (NSString *selectorName in selectorNames) {
        SEL selector = NSSelectorFromString(selectorName);
        id value = MCPAXNodeMsgSendObject(target, selector);
        if (value && value != NSNull.null) return value;
    }
    return nil;
}

static NSString *MCPAXNodeFirstStringValueForSelectors(id target, NSArray<NSString *> *selectorNames) {
    id value = MCPAXNodeFirstObjectValueForSelectors(target, selectorNames);
    return MCPAXNodeStringFromValue(value);
}

static NSNumber *MCPAXNodeFirstUnsignedNumberForSelectors(id target, NSArray<NSString *> *selectorNames) {
    for (NSString *selectorName in selectorNames) {
        BOOL didRead = NO;
        unsigned long long value = MCPAXNodeUnsignedLongLongSelector(target, NSSelectorFromString(selectorName), &didRead);
        if (didRead) return @(value);
    }
    return nil;
}

static NSArray *MCPAXNodeAccessibilityChildren(id element) {
    id childrenValue = MCPAXNodeFirstObjectValueForSelectors(element, @[@"accessibilityElements", @"children"]);
    return MCPAXNodeCollectionToArray(childrenValue);
}

static BOOL MCPAXNodeSubstantiveNode(NSDictionary *node) {
    if (![node isKindOfClass:[NSDictionary class]]) return NO;
    NSArray *children = [node[@"children"] isKindOfClass:[NSArray class]] ? node[@"children"] : nil;
    if (children.count > 0) return YES;
    for (NSString *key in @[@"label", @"identifier", @"title", @"value", @"pid", @"contextId", @"window_context_id"]) {
        if (node[key]) return YES;
    }
    if (MCPAXNodeFrameValueHasVisibleArea(node[@"frame"]) ||
        MCPAXNodeFrameValueHasVisibleArea(node[@"visibleFrame"]) ||
        MCPAXNodeFrameValueHasVisibleArea(node[@"focusable_frame_for_zoom"])) {
        return YES;
    }
    NSNumber *traits = [node[@"traits"] isKindOfClass:[NSNumber class]] ? node[@"traits"] : nil;
    if (traits.unsignedLongLongValue > 0) return YES;
    return NO;
}

static id MCPAXNodeSanitizeSnapshotValue(id value, NSInteger depth) {
    if (!value || value == NSNull.null) return nil;
    if (depth > 8) return @"<max-depth>";

    if ([value isKindOfClass:[NSString class]] ||
        [value isKindOfClass:[NSNumber class]]) {
        return value;
    }

    if ([value isKindOfClass:[NSDictionary class]]) {
        NSMutableDictionary *result = [NSMutableDictionary dictionary];
        [(NSDictionary *)value enumerateKeysAndObjectsUsingBlock:^(id rawKey, id rawObject, BOOL *stop) {
            NSString *key = MCPAXNodeStringFromValue(rawKey);
            if (key.length == 0) key = [rawKey description];
            id sanitized = MCPAXNodeSanitizeSnapshotValue(rawObject, depth + 1);
            if (key.length > 0 && sanitized) {
                result[key] = sanitized;
            }
        }];
        return result;
    }

    if ([value isKindOfClass:[NSArray class]]) {
        NSMutableArray *result = [NSMutableArray array];
        for (id item in (NSArray *)value) {
            id sanitized = MCPAXNodeSanitizeSnapshotValue(item, depth + 1);
            if (sanitized) [result addObject:sanitized];
        }
        return result;
    }

    if ([value isKindOfClass:[NSValue class]]) {
        CGRect frame = CGRectZero;
        if (MCPAXNodeCGRectFromObject(value, &frame)) {
            return MCPAXNodeFrameDictionary(frame);
        }
    }

    return [value description];
}

static BOOL MCPAXNodeSnapshotContainsRemoteMarkers(id value, NSInteger depth) {
    if (!value || value == NSNull.null || depth > 8) return NO;

    if ([value isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = value;
        for (NSString *key in @[@"isRemoteElement", @"remotePid", @"remoteUUID", @"uuid", @"contextId", @"windowContextId", @"windowDisplayId"]) {
            id marker = dict[key];
            if ([marker isKindOfClass:[NSNumber class]] && [marker boolValue]) return YES;
            if ([marker isKindOfClass:[NSString class]] && [marker length] > 0) return YES;
        }
        for (id child in dict.allValues) {
            if (MCPAXNodeSnapshotContainsRemoteMarkers(child, depth + 1)) return YES;
        }
        return NO;
    }

    if ([value isKindOfClass:[NSArray class]]) {
        for (id child in (NSArray *)value) {
            if (MCPAXNodeSnapshotContainsRemoteMarkers(child, depth + 1)) return YES;
        }
    }
    return NO;
}

static NSDictionary *MCPAXNodeDefaultUserTestingSnapshotOptions(void) {
    static NSDictionary *options = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        options = @{
            @"attributes": @[
                @"automationType",
                @"elementType",
                @"elementBaseType",
                @"identifier",
                @"label",
                @"traits",
                @"userTestingElements",
                @"value",
                @"isUserInteractionEnabled",
                @"viewControllerTitle",
                @"viewControllerClassName",
                @"frame",
                @"visibleFrame",
                @"parent",
                @"horizontalSizeClass",
                @"verticalSizeClass",
                @"placeholderValue",
                @"windowContextId",
                @"windowDisplayId",
                @"isVisible",
                @"isRemoteElement",
                @"localizedStringKey",
                @"localizationBundleID",
                @"localizationBundlePath",
                @"localizedStringTableName"
            ],
            @"UseLegacyElementType": @NO,
            @"preserveRemoteElementPlaceholders": @NO
        };
    });
    return options;
}

static NSDictionary *MCPAXNodeSnapshotAttributes(id snapshot) {
    if (![snapshot isKindOfClass:[NSDictionary class]]) return nil;

    NSDictionary *dict = (NSDictionary *)snapshot;
    id attributes = dict[kMCPAXNodeSnapshotKeyAttributes];
    if ([attributes isKindOfClass:[NSDictionary class]]) return attributes;

    attributes = dict[@"attributes"];
    if ([attributes isKindOfClass:[NSDictionary class]]) return attributes;
    return nil;
}

static NSArray *MCPAXNodeSnapshotChildren(id snapshot) {
    if (![snapshot isKindOfClass:[NSDictionary class]]) return nil;

    NSDictionary *dict = (NSDictionary *)snapshot;
    id children = dict[kMCPAXNodeSnapshotKeyChildren];
    if ([children isKindOfClass:[NSArray class]]) return children;

    children = dict[@"children"] ?: dict[@"userTestingElements"];
    if ([children isKindOfClass:[NSArray class]]) return children;
    return nil;
}

static id MCPAXNodeSnapshotAttributeValue(id snapshot, uint32_t attributeId) {
    NSDictionary *attributes = MCPAXNodeSnapshotAttributes(snapshot);
    if (!attributes) return nil;

    id value = attributes[@(attributeId)];
    if (!value) value = attributes[[NSString stringWithFormat:@"%u", attributeId]];
    return value == NSNull.null ? nil : value;
}

static NSString *MCPAXNodeSnapshotStringAttribute(id snapshot, uint32_t attributeId) {
    return MCPAXNodeStringFromValue(MCPAXNodeSnapshotAttributeValue(snapshot, attributeId));
}

static NSNumber *MCPAXNodeSnapshotNumberAttribute(id snapshot, uint32_t attributeId) {
    return MCPAXNodeNumberFromValue(MCPAXNodeSnapshotAttributeValue(snapshot, attributeId));
}

static BOOL MCPAXNodeSnapshotIsRemoteBridge(id snapshot) {
    return [MCPAXNodeSnapshotStringAttribute(snapshot, kMCPAXNodeSnapshotAttributeIdentifier) isEqualToString:kMCPAXNodeSnapshotRemoteViewBridge];
}

static BOOL MCPAXNodeSnapshotIsRemoteElement(id snapshot) {
    if (MCPAXNodeSnapshotIsRemoteBridge(snapshot)) return YES;

    NSString *elementType = MCPAXNodeSnapshotStringAttribute(snapshot, kMCPAXNodeSnapshotAttributeElementType);
    if ([elementType isEqualToString:kMCPAXNodeSnapshotRemoteElementClass]) return YES;

    NSString *baseType = MCPAXNodeSnapshotStringAttribute(snapshot, kMCPAXNodeSnapshotAttributeElementBaseType);
    if ([baseType isEqualToString:kMCPAXNodeSnapshotRemoteElementClass]) return YES;

    NSDictionary *attributes = MCPAXNodeSnapshotAttributes(snapshot);
    return MCPAXNodeSnapshotContainsRemoteMarkers(attributes ?: snapshot, 0);
}

static NSDictionary *MCPAXNodeUserTestingSnapshotSummary(NSDictionary *snapshot) {
    if (![snapshot isKindOfClass:[NSDictionary class]]) return nil;

    NSMutableDictionary *summary = [NSMutableDictionary dictionary];
    NSArray<NSString *> *rootKeys = [[snapshot allKeys] sortedArrayUsingSelector:@selector(compare:)];
    summary[@"rootKeyCount"] = @(rootKeys.count);
    if (rootKeys.count > 0) summary[@"rootKeys"] = rootKeys;

    NSNumber *contextId = MCPAXNodeSnapshotNumberAttribute(snapshot, kMCPAXNodeAttributeWindowContextId) ?:
        MCPAXNodeNumberFromValue(snapshot[@"windowContextId"] ?: snapshot[@"contextId"]);
    if (contextId.unsignedIntValue > 0) summary[@"windowContextId"] = contextId;

    NSNumber *displayId = MCPAXNodeSnapshotNumberAttribute(snapshot, kMCPAXNodeAttributeWindowDisplayId) ?:
        MCPAXNodeNumberFromValue(snapshot[@"windowDisplayId"] ?: snapshot[@"displayId"]);
    if (displayId.unsignedIntValue > 0) summary[@"windowDisplayId"] = displayId;

    NSString *label = MCPAXNodeSnapshotStringAttribute(snapshot, kMCPAXNodeAttributeLabel) ?:
        MCPAXNodeStringFromValue(snapshot[@"label"]);
    if (label.length > 0) summary[@"label"] = label;

    NSString *identifier = MCPAXNodeSnapshotStringAttribute(snapshot, kMCPAXNodeSnapshotAttributeIdentifier) ?:
        MCPAXNodeStringFromValue(snapshot[@"identifier"]);
    if (identifier.length > 0) summary[@"identifier"] = identifier;

    id children = MCPAXNodeSnapshotChildren(snapshot) ?: snapshot[@"children"] ?: snapshot[@"userTestingElements"];
    summary[@"childCount"] = @(MCPAXNodeCollectionCount(children));
    summary[@"containsRemoteMarkers"] = @(MCPAXNodeSnapshotIsRemoteElement(snapshot) || MCPAXNodeSnapshotContainsRemoteMarkers(snapshot, 0));
    return summary;
}

@interface MCPAXNodeSource ()

@property (nonatomic, strong) MCPAXAttributeBridge *attributeBridge;

- (NSDictionary * _Nullable)buildNumericElementAtPoint:(CGPoint)point
                                                   pid:(pid_t)pid
                                             contextId:(uint32_t)contextId
                                             displayId:(uint32_t)displayId
                                                 error:(NSString * _Nullable * _Nullable)error;

- (NSDictionary * _Nullable)serializeNumericLeafElement:(AXUIElementRef)leafElement;

- (NSDictionary * _Nullable)serializeCompactLeafElement:(AXUIElementRef)leafElement
                                                    pid:(pid_t)pid
                                               bundleId:(NSString * _Nullable)bundleId
                                           screenBounds:(CGRect)screenBounds
                                            visibleOnly:(BOOL)visibleOnly
                                          clickableOnly:(BOOL)clickableOnly;

- (NSDictionary * _Nullable)serializeRemoteElement:(AXUIElementRef)element
                                             depth:(NSInteger)depth
                                          maxDepth:(NSInteger)maxDepth
                                             count:(NSInteger *)count
                                       maxElements:(NSInteger)maxElements
                                           visited:(NSMutableSet<NSString *> *)visited;

- (NSDictionary * _Nullable)serializeRemoteElementLeaf:(AXUIElementRef)element;

- (NSDictionary * _Nullable)snapshotProbeCandidatesForElement:(AXUIElementRef)element
                                                    baseLabel:(NSString *)baseLabel
                                           includeFirstElement:(BOOL)includeFirstElement
                                       includeVisibleCandidates:(NSUInteger)visibleCandidateLimit;

@end

@implementation MCPAXNodeSource

- (instancetype)initWithAttributeBridge:(MCPAXAttributeBridge *)attributeBridge {
    self = [super init];
    if (self) {
        _attributeBridge = attributeBridge;
    }
    return self;
}

- (NSDictionary * _Nullable)elementAtPoint:(CGPoint)fixedPoint
                                       pid:(pid_t)pid
                                  contextId:(uint32_t)contextId
                                  displayId:(uint32_t)displayId
                    allowParameterizedHitTest:(BOOL)allowParameterizedHitTest
                                     error:(NSString * _Nullable * _Nullable)error {
    __block NSDictionary *resultElement = nil;
    __block NSString *resultError = nil;

    [self.attributeBridge performOnMainThreadSync:^{
        MCPScreenGeometry geometry = MCPGetScreenGeometry();
        CGPoint point = CGPointApplyAffineTransform(fixedPoint, CGAffineTransformInvert(geometry.interfaceToFixed));
        @try {
            if (![self.attributeBridge ensureRuntimeAvailable:&resultError]) {
                return;
            }

            [self.attributeBridge ensureAssociationWithRemotePid:pid];

            NSString *hitError = nil;
            NSString *knownContextError = nil;
            NSString *contextChainError = nil;
            NSDictionary *hitDiagnostics = nil;
            NSString *hitStrategy = allowParameterizedHitTest ?
                @"parameterized_then_copyElementAtPosition" :
                @"copyElementAtPosition";
            BOOL skipSlowContextChain = NO;
            AXUIElementRef hitElement = [self.attributeBridge copyHitTestElementAtPoint:fixedPoint
                                                                            expectedPid:pid
                                                                     allowParameterized:allowParameterizedHitTest
                                                                                  error:&hitError];
            if (!hitElement) {
                if (contextId > 0) {
                    hitElement = [self.attributeBridge copyElementAtPoint:fixedPoint
                                                       usingKnownContextId:contextId
                                                               expectedPid:pid
                                                               diagnostics:&hitDiagnostics
                                                                     error:&knownContextError];
                    if (hitElement) {
                        hitStrategy = @"known_context_copyElementUsingContextIdAtPosition";
                    }
                }

                if (!hitElement) {
                    if (MCPAXNodeIsIOS15Runtime()) {
                        NSString *numericPointError = nil;
                        NSDictionary *numericPointElement = [self buildNumericElementAtPoint:point
                                                                                         pid:pid
                                                                                   contextId:contextId
                                                                                   displayId:displayId
                                                                                       error:&numericPointError];
                        if ([numericPointElement isKindOfClass:[NSDictionary class]]) {
                            resultElement = numericPointElement;
                            return;
                        }
                        if (numericPointError.length > 0) {
                            contextChainError = contextChainError.length > 0 ?
                                [contextChainError stringByAppendingFormat:@"; numeric_frame=%@", numericPointError] :
                                [NSString stringWithFormat:@"numeric_frame=%@", numericPointError];
                        }
                        skipSlowContextChain = YES;
                    }

                    if (!hitElement && !skipSlowContextChain) {
                        hitElement = [self.attributeBridge copyContextChainHitElementAtPoint:fixedPoint
                                                                                 expectedPid:pid
                                                                                 diagnostics:&hitDiagnostics
                                                                                       error:&contextChainError];
                        if (hitElement) {
                            hitStrategy = @"context_chain_copyElementUsingContextIdAtPosition";
                        }
                    }
                }

                if (!hitElement) {
                    NSMutableArray<NSString *> *parts = [NSMutableArray array];
                    if (hitError.length > 0) {
                        [parts addObject:hitError];
                    }
                    if (knownContextError.length > 0) {
                        [parts addObject:[NSString stringWithFormat:@"known_context=%@", knownContextError]];
                    }
                    if (contextChainError.length > 0) {
                        [parts addObject:[NSString stringWithFormat:@"context_chain=%@", contextChainError]];
                    }
                    resultError = parts.count > 0 ?
                        [parts componentsJoinedByString:@"; "] :
                        @"Direct AX hit-test returned no element";
                    return;
                }
            }

            NSInteger count = 0;
            NSMutableSet<NSString *> *visited = [NSMutableSet set];
            pid_t resolvedPid = 0;
            BOOL hasResolvedPid = [self.attributeBridge getPid:&resolvedPid fromElement:hitElement];
            if (MCPAXNodeIsIOS15Runtime()) {
                /*
                 For point queries on iOS 15, prefer a shallow leaf result.
                 userTestingSnapshot can be noticeably slower for complex apps and
                 may exceed MCPServer's synchronous wait window.  The full tree path
                 still uses snapshot/numeric fallbacks; hit-test only needs the leaf.
                 */
                NSDictionary *leafElement = [self serializeRemoteElementLeaf:hitElement];
                CFRelease(hitElement);
                if ([leafElement isKindOfClass:[NSDictionary class]]) {
                    NSMutableDictionary *node = [leafElement mutableCopy];
                    node[@"source"] = @"direct_ax_hit_test";
                    node[@"direct_ax_strategy"] = [hitStrategy stringByAppendingString:@"_leaf"];
                    node[@"hit_test_point"] = @{
                        @"x": @((NSInteger)lrint(point.x)),
                        @"y": @((NSInteger)lrint(point.y))
                    };
                    node[@"direct_ax_safety_cap"] = MCPAXNodeIOS15SnapshotGuard(3, 50);
                    NSMutableDictionary *diagnostics = [NSMutableDictionary dictionary];
                    if ([hitDiagnostics isKindOfClass:[NSDictionary class]] && hitDiagnostics.count > 0) {
                        diagnostics[@"hitTestDiagnostics"] = hitDiagnostics;
                    }
                    diagnostics[@"hitTestLeafFirst"] = @YES;
                    diagnostics[@"skippedUserTestingSnapshot"] = @"point_query_timeout_guard";
                    node[@"direct_ax_diagnostics"] = diagnostics;
                    if (contextId > 0) {
                        node[@"contextId"] = @(contextId);
                    }
                    if (displayId > 0) {
                        node[@"displayId"] = @(displayId);
                    }
                    if (hasResolvedPid && resolvedPid > 0) {
                        node[@"pid"] = @(resolvedPid);
                    } else {
                        node[@"pid"] = @(pid);
                    }
                    resultElement = node;
                    return;
                }

                NSString *numericPointError = nil;
                NSDictionary *numericPointElement = [self buildNumericElementAtPoint:point
                                                                                 pid:pid
                                                                           contextId:contextId
                                                                           displayId:displayId
                                                                               error:&numericPointError];
                if ([numericPointElement isKindOfClass:[NSDictionary class]]) {
                    resultElement = numericPointElement;
                    return;
                }
                resultError = [NSString stringWithFormat:@"iOS 15 hit-test leaf serialization unavailable; skipped userTestingSnapshot for point query to avoid timeout; numeric_frame=%@",
                               numericPointError ?: @"unavailable"];
                return;
            }
            NSDictionary *serialized = [self serializeRemoteElement:hitElement
                                                              depth:0
                                                           maxDepth:3
                                                              count:&count
                                                        maxElements:50
                                                            visited:visited];
            NSDictionary *snapshotProbe = [self snapshotProbeCandidatesForElement:hitElement
                                                                        baseLabel:@"hit_element"
                                                               includeFirstElement:NO
                                                           includeVisibleCandidates:0];
            CFRelease(hitElement);

            if (!serialized) {
                resultError = @"Direct AX hit-test returned an empty element";
                return;
            }

            NSMutableDictionary *node = [serialized mutableCopy];
            node[@"source"] = @"direct_ax_hit_test";
            node[@"direct_ax_strategy"] = hitStrategy;
            node[@"hit_test_point"] = @{
                @"x": @((NSInteger)lrint(point.x)),
                @"y": @((NSInteger)lrint(point.y))
            };
            if ([hitDiagnostics isKindOfClass:[NSDictionary class]] && hitDiagnostics.count > 0) {
                node[@"direct_ax_diagnostics"] = hitDiagnostics;
            }
            if (snapshotProbe.count > 0) {
                NSMutableDictionary *diagnostics = [node[@"direct_ax_diagnostics"] isKindOfClass:[NSDictionary class]] ?
                    [node[@"direct_ax_diagnostics"] mutableCopy] :
                    [NSMutableDictionary dictionary];
                diagnostics[@"hitTestSnapshotProbe"] = snapshotProbe;
                node[@"direct_ax_diagnostics"] = diagnostics;
            }
            if (contextId > 0) {
                node[@"contextId"] = @(contextId);
            }
            if (displayId > 0) {
                node[@"displayId"] = @(displayId);
            }

            if (hasResolvedPid && resolvedPid > 0) {
                node[@"pid"] = @(resolvedPid);
            } else {
                node[@"pid"] = @(pid);
            }

            resultElement = node;
        } @catch (NSException *exception) {
            resultError = [NSString stringWithFormat:@"AX hit-test exception: %@: %@", exception.name, exception.reason ?: @"<no reason>"];
            MCP_AX_NODE_LOG(@"Hit-test exception for PID %d: %@: %@", pid, exception.name, exception.reason ?: @"<no reason>");
        } @finally {
            resultElement = MCPAXNodeResultInFixedCoordinates(resultElement, geometry.interfaceToFixed);
        }
    }];

    if (!resultElement && error) *error = resultError;
    return resultElement;
}

- (NSDictionary * _Nullable)serializeRemoteElementLeaf:(AXUIElementRef)element {
    if (!element) return nil;

    NSMutableDictionary *node = [NSMutableDictionary dictionary];
    node[@"_ax_ref"] = [NSString stringWithFormat:@"%p", element];

    NSArray<NSString *> *scalarAttributes = @[
        (__bridge NSString *)kAXRoleAttribute,
        (__bridge NSString *)kAXSubroleAttribute,
        (__bridge NSString *)kAXLabelAttribute,
        (__bridge NSString *)kAXValueAttribute,
        (__bridge NSString *)kAXTitleAttribute,
        (__bridge NSString *)kAXDescriptionAttribute,
        (__bridge NSString *)kAXIdentifierAttribute,
        (__bridge NSString *)kAXPlaceholderAttribute,
        (__bridge NSString *)kAXEnabledAttribute,
        (__bridge NSString *)kAXFocusedAttribute,
        (__bridge NSString *)kAXSelectedAttribute,
        (__bridge NSString *)kAXTraitsAttribute,
        (__bridge NSString *)kAXFrameAttribute
    ];
    NSDictionary<NSString *, id> *scalarValues = [self.attributeBridge copyAttributeMap:element attributes:scalarAttributes] ?: @{};
    NSDictionary<NSString *, id> *xcValues = [self.attributeBridge copyXCAttributeMap:element attributeKeys:@[
        @"automationType",
        @"frame",
        @"identifier",
        @"isRemoteElement",
        @"isVisible",
        @"label",
        @"traits",
        @"value",
        @"visibleFrame",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};
    NSDictionary<NSString *, id> *directValues = [self.attributeBridge copyDirectAttributeMap:element attributeKeys:@[
        @"centerPoint",
        @"containerType",
        @"containerTypes",
        @"focusableFrameForZoom",
        @"path",
        @"url",
        @"userInputLabels",
        @"visibleFrame",
        @"visiblePoint",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};

    NSString *role = [scalarValues[(__bridge NSString *)kAXRoleAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXRoleAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXRoleAttribute];
    NSString *subrole = [scalarValues[(__bridge NSString *)kAXSubroleAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXSubroleAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXSubroleAttribute];
    NSString *label = MCPAXNodeStringFromValue(xcValues[@"label"]) ?:
        ([scalarValues[(__bridge NSString *)kAXLabelAttribute] isKindOfClass:[NSString class]] ?
         scalarValues[(__bridge NSString *)kAXLabelAttribute] :
         [self.attributeBridge copyStringAttribute:element attribute:kAXLabelAttribute]);
    id rawValue = xcValues[@"value"] ?: scalarValues[(__bridge NSString *)kAXValueAttribute] ?: [self.attributeBridge copyAttributeObject:element attribute:kAXValueAttribute];
    NSString *value = MCPAXNodeStringFromValue(rawValue);
    NSString *title = [scalarValues[(__bridge NSString *)kAXTitleAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXTitleAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXTitleAttribute];
    NSString *desc = [scalarValues[(__bridge NSString *)kAXDescriptionAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXDescriptionAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXDescriptionAttribute];
    NSString *identifier = MCPAXNodeStringFromValue(xcValues[@"identifier"]) ?:
        ([scalarValues[(__bridge NSString *)kAXIdentifierAttribute] isKindOfClass:[NSString class]] ?
         scalarValues[(__bridge NSString *)kAXIdentifierAttribute] :
         [self.attributeBridge copyStringAttribute:element attribute:kAXIdentifierAttribute]);
    NSString *placeholder = [scalarValues[(__bridge NSString *)kAXPlaceholderAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXPlaceholderAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXPlaceholderAttribute];
    NSNumber *enabled = [scalarValues[(__bridge NSString *)kAXEnabledAttribute] isKindOfClass:[NSNumber class]] ?
        scalarValues[(__bridge NSString *)kAXEnabledAttribute] :
        [self.attributeBridge copyNumberAttribute:element attribute:kAXEnabledAttribute];
    NSNumber *focused = [scalarValues[(__bridge NSString *)kAXFocusedAttribute] isKindOfClass:[NSNumber class]] ?
        scalarValues[(__bridge NSString *)kAXFocusedAttribute] :
        [self.attributeBridge copyNumberAttribute:element attribute:kAXFocusedAttribute];
    NSNumber *selected = [scalarValues[(__bridge NSString *)kAXSelectedAttribute] isKindOfClass:[NSNumber class]] ?
        scalarValues[(__bridge NSString *)kAXSelectedAttribute] :
        [self.attributeBridge copyNumberAttribute:element attribute:kAXSelectedAttribute];
    id traits = xcValues[@"traits"] ?: scalarValues[(__bridge NSString *)kAXTraitsAttribute];
    if (!traits) {
        traits = [self.attributeBridge copyAttributeObject:element attribute:kAXTraitsAttribute];
    }

    node[@"role"] = role ?: @"AXElement";
    if (subrole.length > 0) node[@"subrole"] = subrole;
    if (label.length > 0) node[@"label"] = label;
    if (value.length > 0 && !MCPAXNodeStringLooksLikeAXError(value)) {
        node[@"value"] = value;
    } else {
        id normalizedValue = MCPAXNodeNormalizedValue(rawValue);
        if ([normalizedValue isKindOfClass:[NSString class]] && MCPAXNodeStringLooksLikeAXError(normalizedValue)) {
            normalizedValue = nil;
        }
        if (normalizedValue) node[@"value"] = normalizedValue;
    }
    if (title.length > 0) node[@"title"] = title;
    if (desc.length > 0) node[@"description"] = desc;
    if (identifier.length > 0) node[@"identifier"] = identifier;
    if (placeholder.length > 0) node[@"placeholder"] = placeholder;
    if (enabled) node[@"enabled"] = enabled;
    if (focused) node[@"focused"] = focused;
    if (selected) node[@"selected"] = selected;
    if ([traits isKindOfClass:[NSArray class]] ||
        [traits isKindOfClass:[NSString class]] ||
        [traits isKindOfClass:[NSNumber class]]) {
        node[@"traits"] = traits;
    }

    id frameValue = xcValues[@"frame"] ?: scalarValues[(__bridge NSString *)kAXFrameAttribute];
    if (!frameValue) {
        frameValue = [self.attributeBridge copyAttributeObject:element attribute:kAXFrameAttribute];
    }
    CGRect frame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(frameValue, &frame)) {
        node[@"frame"] = MCPAXNodeFrameDictionary(frame);
    }

    id visibleFrameValue = xcValues[@"visibleFrame"] ?: directValues[@"visibleFrame"];
    CGRect visibleFrame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(visibleFrameValue, &visibleFrame)) {
        node[@"visibleFrame"] = MCPAXNodeFrameDictionary(visibleFrame);
    }

    NSNumber *isVisible = MCPAXNodeNumberFromValue(xcValues[@"isVisible"]);
    if (isVisible) node[@"visible"] = @([isVisible boolValue]);

    NSNumber *windowContextId = MCPAXNodeNumberFromValue(xcValues[@"windowContextId"] ?: directValues[@"windowContextId"]);
    if (windowContextId.unsignedIntValue > 0) {
        node[@"window_context_id"] = windowContextId;
        node[@"contextId"] = windowContextId;
    }

    NSNumber *windowDisplayId = MCPAXNodeNumberFromValue(xcValues[@"windowDisplayId"] ?: directValues[@"windowDisplayId"]);
    if (windowDisplayId.unsignedIntValue > 0) {
        node[@"window_display_id"] = windowDisplayId;
        node[@"displayId"] = windowDisplayId;
    }

    NSNumber *isRemoteElement = MCPAXNodeNumberFromValue(xcValues[@"isRemoteElement"]);
    if (isRemoteElement) node[@"is_remote_element"] = @([isRemoteElement boolValue]);

    NSNumber *automationType = MCPAXNodeNumberFromValue(xcValues[@"automationType"]);
    if (automationType) node[@"automation_type"] = automationType;

    id containerType = MCPAXNodeNormalizedValue(directValues[@"containerType"]);
    if (containerType) node[@"container_type"] = containerType;

    id containerTypes = MCPAXNodeNormalizedValue(directValues[@"containerTypes"]);
    if (containerTypes) node[@"container_types"] = containerTypes;

    id userInputLabels = MCPAXNodeNormalizedValue(directValues[@"userInputLabels"]);
    if (userInputLabels) node[@"user_input_labels"] = userInputLabels;

    NSString *url = MCPAXNodeStringFromValue(directValues[@"url"]);
    if (url.length > 0) node[@"url"] = url;

    NSString *path = MCPAXNodeStringFromValue(directValues[@"path"]);
    if (path.length > 0) node[@"path"] = path;

    CGRect focusableFrame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(directValues[@"focusableFrameForZoom"], &focusableFrame)) {
        node[@"focusable_frame_for_zoom"] = MCPAXNodeFrameDictionary(focusableFrame);
    }

    CGPoint centerPoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"centerPoint"], &centerPoint)) {
        node[@"center_point"] = MCPAXNodePointDictionary(centerPoint);
    }

    CGPoint visiblePoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"visiblePoint"], &visiblePoint)) {
        node[@"visible_point"] = MCPAXNodePointDictionary(visiblePoint);
    }

    if (!MCPAXNodeSubstantiveNode(node)) {
        return nil;
    }

    [node removeObjectForKey:@"_ax_ref"];
    return node;
}

- (NSDictionary * _Nullable)snapshotProbeCandidatesForElement:(AXUIElementRef)element
                                                    baseLabel:(NSString *)baseLabel
                                           includeFirstElement:(BOOL)includeFirstElement
                                       includeVisibleCandidates:(NSUInteger)visibleCandidateLimit {
    if (!element || baseLabel.length == 0) return nil;

    NSDictionary *snapshotOptions = MCPAXNodeDefaultUserTestingSnapshotOptions();
    NSMutableDictionary<NSString *, id> *results = [NSMutableDictionary dictionary];
    NSMutableSet<NSString *> *candidateKeys = [NSMutableSet set];

    void (^probeCandidate)(AXUIElementRef, NSString *) = ^(AXUIElementRef candidateElement, NSString *strategy) {
        if (!candidateElement || strategy.length == 0) return;
        NSString *candidateKey = [NSString stringWithFormat:@"%p", candidateElement];
        if ([candidateKeys containsObject:candidateKey]) return;
        [candidateKeys addObject:candidateKey];

        NSDictionary *probe = [self.attributeBridge probeUserTestingSnapshotForElement:candidateElement options:snapshotOptions];
        if ([probe isKindOfClass:[NSDictionary class]] && probe.count > 0) {
            results[strategy] = probe;
        }
    };

    probeCandidate(element, baseLabel);

    Class axElementClass = NSClassFromString(@"AXElement");
    if (axElementClass && [axElementClass respondsToSelector:@selector(elementWithAXUIElement:)]) {
        id wrapper = MCPAXNodeMsgSendObjectArg(axElementClass, @selector(elementWithAXUIElement:), (__bridge id)element);
        if (wrapper) {
            AXUIElementRef wrapperElement = (__bridge AXUIElementRef)MCPAXNodeMsgSendObject(wrapper, @selector(uiElement));
            probeCandidate(wrapperElement, [NSString stringWithFormat:@"%@_axelement_wrapper", baseLabel]);

            if (includeFirstElement) {
                id firstElement = MCPAXNodeMsgSendObject(wrapper, @selector(firstElementInApplication));
                AXUIElementRef firstElementRef = (__bridge AXUIElementRef)MCPAXNodeMsgSendObject(firstElement, @selector(uiElement));
                probeCandidate(firstElementRef, [NSString stringWithFormat:@"%@_axelement_firstElementInApplication", baseLabel]);
            }

            if (visibleCandidateLimit > 0) {
                NSArray *visibleElements = MCPAXNodeCollectionToArray(MCPAXNodeMsgSendObject(wrapper, @selector(visibleElements)));
                NSUInteger limit = MIN(visibleCandidateLimit, visibleElements.count);
                for (NSUInteger idx = 0; idx < limit; idx++) {
                    id visibleElement = visibleElements[idx];
                    AXUIElementRef visibleRef = (__bridge AXUIElementRef)MCPAXNodeMsgSendObject(visibleElement, @selector(uiElement));
                    probeCandidate(visibleRef, [NSString stringWithFormat:@"%@_axelement_visible_%lu", baseLabel, (unsigned long)idx]);
                }
            }
        }
    }

    if (results.count == 0) return nil;
    return @{
        @"options": snapshotOptions,
        @"candidates": results
    };
}

- (NSDictionary * _Nullable)serializeNumericLeafElement:(AXUIElementRef)leafElement {
    if (!leafElement) return nil;

    NSArray<NSNumber *> *attributes = @[
        @(kMCPAXNodeAttributeLabel),
        @(kMCPAXNodeAttributeFrame),
        @(kMCPAXNodeAttributeTraits),
        @(kMCPAXNodeAttributeValue),
        @(kMCPAXNodeAttributeIsElement),
        @(kMCPAXNodeAttributeWindowContextId),
        @(kMCPAXNodeAttributeWindowDisplayId)
    ];
    NSDictionary<NSNumber *, id> *values = [self.attributeBridge copyNumericAttributeMap:leafElement attributes:attributes] ?: @{};
    NSDictionary<NSString *, id> *xcValues = [self.attributeBridge copyXCAttributeMap:leafElement attributeKeys:@[
        @"frame",
        @"isVisible",
        @"label",
        @"traits",
        @"value",
        @"visibleFrame",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};
    NSDictionary<NSString *, id> *directValues = [self.attributeBridge copyDirectAttributeMap:leafElement attributeKeys:@[
        @"centerPoint",
        @"containerType",
        @"focusableFrameForZoom",
        @"userInputLabels",
        @"visibleFrame",
        @"visiblePoint",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};

    NSMutableDictionary *node = [NSMutableDictionary dictionary];
    node[@"role"] = @"AXElement";

    NSString *label = MCPAXNodeStringFromValue(xcValues[@"label"]) ?:
        MCPAXNodeStringFromValue(values[@(kMCPAXNodeAttributeLabel)]);
    if (label.length > 0) node[@"label"] = label;

    id rawValue = xcValues[@"value"] ?: values[@(kMCPAXNodeAttributeValue)];
    NSString *stringValue = MCPAXNodeStringFromValue(rawValue);
    if (stringValue.length > 0 && !MCPAXNodeStringLooksLikeAXError(stringValue)) {
        node[@"value"] = stringValue;
    } else {
        id normalizedValue = MCPAXNodeNormalizedValue(rawValue);
        if ([normalizedValue isKindOfClass:[NSString class]] && MCPAXNodeStringLooksLikeAXError(normalizedValue)) {
            normalizedValue = nil;
        }
        if (normalizedValue) node[@"value"] = normalizedValue;
    }

    CGRect frame = CGRectZero;
    id frameValue = xcValues[@"frame"] ?: values[@(kMCPAXNodeAttributeFrame)];
    if (MCPAXNodeCGRectFromObject(frameValue, &frame)) {
        node[@"frame"] = MCPAXNodeFrameDictionary(frame);
    }

    CGRect visibleFrame = CGRectZero;
    id visibleFrameValue = xcValues[@"visibleFrame"] ?: directValues[@"visibleFrame"];
    if (MCPAXNodeCGRectFromObject(visibleFrameValue, &visibleFrame)) {
        node[@"visibleFrame"] = MCPAXNodeFrameDictionary(visibleFrame);
    }

    CGRect focusableFrame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(directValues[@"focusableFrameForZoom"], &focusableFrame)) {
        node[@"focusable_frame_for_zoom"] = MCPAXNodeFrameDictionary(focusableFrame);
    }

    CGPoint centerPoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"centerPoint"], &centerPoint)) {
        node[@"center_point"] = MCPAXNodePointDictionary(centerPoint);
    }

    CGPoint visiblePoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"visiblePoint"], &visiblePoint)) {
        node[@"visible_point"] = MCPAXNodePointDictionary(visiblePoint);
    }

    id traits = xcValues[@"traits"] ?: values[@(kMCPAXNodeAttributeTraits)];
    if ([traits isKindOfClass:[NSArray class]] ||
        [traits isKindOfClass:[NSString class]] ||
        [traits isKindOfClass:[NSNumber class]]) {
        node[@"traits"] = traits;
    }

    NSNumber *isElement = [values[@(kMCPAXNodeAttributeIsElement)] isKindOfClass:[NSNumber class]] ? values[@(kMCPAXNodeAttributeIsElement)] : nil;
    if (isElement) node[@"is_accessible_element"] = isElement;

    NSNumber *isVisible = MCPAXNodeNumberFromValue(xcValues[@"isVisible"]);
    if (isVisible) node[@"visible"] = @([isVisible boolValue]);

    NSNumber *windowContextId = [values[@(kMCPAXNodeAttributeWindowContextId)] isKindOfClass:[NSNumber class]] ?
        values[@(kMCPAXNodeAttributeWindowContextId)] :
        MCPAXNodeNumberFromValue(xcValues[@"windowContextId"] ?: directValues[@"windowContextId"]);
    if (windowContextId.unsignedIntValue > 0) {
        node[@"window_context_id"] = windowContextId;
        node[@"contextId"] = windowContextId;
    }

    NSNumber *windowDisplayId = [values[@(kMCPAXNodeAttributeWindowDisplayId)] isKindOfClass:[NSNumber class]] ?
        values[@(kMCPAXNodeAttributeWindowDisplayId)] :
        MCPAXNodeNumberFromValue(xcValues[@"windowDisplayId"] ?: directValues[@"windowDisplayId"]);
    if (windowDisplayId.unsignedIntValue > 0) {
        node[@"window_display_id"] = windowDisplayId;
        node[@"displayId"] = windowDisplayId;
    }

    id userInputLabels = MCPAXNodeNormalizedValue(directValues[@"userInputLabels"]);
    if (userInputLabels) node[@"user_input_labels"] = userInputLabels;

    id containerType = MCPAXNodeNormalizedValue(directValues[@"containerType"]);
    if (containerType) node[@"container_type"] = containerType;

    return MCPAXNodeSerializedNodeHasRenderablePayload(node) ? node : nil;
}

- (NSDictionary * _Nullable)serializeCompactLeafElement:(AXUIElementRef)leafElement
                                                    pid:(pid_t)pid
                                               bundleId:(NSString * _Nullable)bundleId
                                           screenBounds:(CGRect)screenBounds
                                            visibleOnly:(BOOL)visibleOnly
                                          clickableOnly:(BOOL)clickableOnly {
    if (!leafElement) return nil;

    NSArray<NSNumber *> *numericAttributes = @[
        @(kMCPAXNodeAttributeLabel),
        @(kMCPAXNodeAttributeFrame),
        @(kMCPAXNodeAttributeValue),
        @(kMCPAXNodeAttributeWindowContextId),
        @(kMCPAXNodeAttributeWindowDisplayId)
    ];
    NSDictionary<NSNumber *, id> *numericValues = [self.attributeBridge copyNumericAttributeMap:leafElement attributes:numericAttributes] ?: @{};
    NSDictionary<NSString *, id> *xcValues = [self.attributeBridge copyXCAttributeMap:leafElement attributeKeys:@[
        @"frame",
        @"isVisible",
        @"label",
        @"value",
        @"visibleFrame",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};
    NSDictionary<NSString *, id> *directValues = [self.attributeBridge copyDirectAttributeMap:leafElement attributeKeys:@[
        @"centerPoint",
        @"focusableFrameForZoom",
        @"userInputLabels",
        @"visibleFrame",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};

    CGRect rect = CGRectNull;
    for (id frameValue in @[
        xcValues[@"visibleFrame"] ?: directValues[@"visibleFrame"] ?: NSNull.null,
        xcValues[@"frame"] ?: numericValues[@(kMCPAXNodeAttributeFrame)] ?: NSNull.null,
        directValues[@"focusableFrameForZoom"] ?: NSNull.null
    ]) {
        if (frameValue == NSNull.null) continue;
        CGRect candidate = CGRectZero;
        if (MCPAXNodeCGRectFromObject(frameValue, &candidate) && candidate.size.width > 0.0 && candidate.size.height > 0.0) {
            rect = candidate;
            break;
        }
    }
    if (CGRectIsNull(rect) || CGRectIsEmpty(rect)) return nil;

    CGRect visibleRect = MCPAXNodeIntersectionWithScreen(rect, screenBounds);
    BOOL onScreen = !CGRectIsNull(visibleRect) && !CGRectIsEmpty(visibleRect);
    if (visibleOnly && !onScreen) return nil;

    NSNumber *isVisible = MCPAXNodeNumberFromValue(xcValues[@"isVisible"]);
    BOOL clickable = !isVisible || isVisible.boolValue;
    if (clickableOnly && !clickable) return nil;

    NSMutableOrderedSet<NSString *> *texts = [NSMutableOrderedSet orderedSet];
    MCPAXNodeAddCompactText(texts, xcValues[@"label"]);
    MCPAXNodeAddCompactText(texts, numericValues[@(kMCPAXNodeAttributeLabel)]);
    MCPAXNodeAddCompactText(texts, directValues[@"userInputLabels"]);
    MCPAXNodeAddCompactText(texts, xcValues[@"value"]);
    MCPAXNodeAddCompactText(texts, numericValues[@(kMCPAXNodeAttributeValue)]);

    if (!clickable && texts.count == 0) return nil;

    CGPoint tapPoint = CGPointMake(CGRectGetMidX(onScreen ? visibleRect : rect),
                                   CGRectGetMidY(onScreen ? visibleRect : rect));
    CGPoint centerPoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"centerPoint"], &centerPoint) &&
        CGRectContainsPoint(onScreen ? visibleRect : rect, centerPoint)) {
        tapPoint = centerPoint;
    }

    NSNumber *windowContextId = MCPAXNodeNumberFromValue(numericValues[@(kMCPAXNodeAttributeWindowContextId)] ?:
                                                        xcValues[@"windowContextId"] ?:
                                                        directValues[@"windowContextId"]);
    NSNumber *windowDisplayId = MCPAXNodeNumberFromValue(numericValues[@(kMCPAXNodeAttributeWindowDisplayId)] ?:
                                                        xcValues[@"windowDisplayId"] ?:
                                                        directValues[@"windowDisplayId"]);

    NSMutableDictionary *element = [NSMutableDictionary dictionary];
    element[@"type"] = texts.count > 0 ? @"control" : @"element";
    element[@"clickable"] = @(clickable);
    element[@"rect"] = MCPAXNodeIntegerFrameDictionary(rect);
    if (onScreen) element[@"visible_rect"] = MCPAXNodeIntegerFrameDictionary(visibleRect);
    element[@"tap"] = MCPAXNodeIntegerPointDictionary(tapPoint);
    if (texts.count > 0) {
        element[@"text"] = texts.firstObject;
        if (texts.count > 1) {
            NSMutableArray<NSString *> *aliases = [NSMutableArray array];
            for (NSString *text in texts) {
                if (![text isEqualToString:texts.firstObject]) [aliases addObject:text];
            }
            if (aliases.count > 0) element[@"aliases"] = aliases;
        }
    }
    (void)pid;
    (void)bundleId;
    (void)windowContextId;
    (void)windowDisplayId;
    return element;
}

- (NSDictionary * _Nullable)compactElementsForPid:(pid_t)pid
                                         bundleId:(NSString * _Nullable)bundleId
                                        contextId:(uint32_t)contextId
                                        displayId:(uint32_t)displayId
                                      maxElements:(NSInteger)maxElements
                                      visibleOnly:(BOOL)visibleOnly
                                    clickableOnly:(BOOL)clickableOnly
                                            error:(NSString * _Nullable * _Nullable)error {
    __block NSDictionary *resultPayload = nil;
    __block NSString *resultError = nil;

    [self.attributeBridge performOnMainThreadSync:^{
        @try {
            if (![self.attributeBridge ensureRuntimeAvailable:&resultError]) {
                return;
            }

            [self.attributeBridge ensureAssociationWithRemotePid:pid];

            NSString *appError = nil;
            AXUIElementRef appElement = [self.attributeBridge copyApplicationElementForPid:pid error:&appError];
            if (!appElement) {
                resultError = appError ?: [NSString stringWithFormat:@"AX create_application failed for PID %d", pid];
                return;
            }

            NSInteger limit = MCPAXNodeNumericFallbackMaxElements(maxElements);
            CGRect screenBounds = MCPAXNodeScreenBounds();
            NSMutableArray<NSMutableDictionary *> *elements = [NSMutableArray array];
            NSMutableOrderedSet<NSString *> *seenFingerprints = [NSMutableOrderedSet orderedSet];
            __block NSUInteger appCandidateCount = 0;
            __block NSUInteger windowCandidateCount = 0;
            __block NSUInteger sampledHitCandidateCount = 0;
            __block NSUInteger serializedCandidateCount = 0;

            void (^appendCompactElement)(AXUIElementRef, NSString *, NSDictionary *) =
                ^(AXUIElementRef leafElement, NSString *source, NSDictionary *extra) {
                if (!leafElement || elements.count >= (NSUInteger)limit) return;

                NSDictionary *compact = [self serializeCompactLeafElement:leafElement
                                                                       pid:pid
                                                                  bundleId:bundleId
                                                              screenBounds:screenBounds
                                                               visibleOnly:visibleOnly
                                                             clickableOnly:clickableOnly];
                if (![compact isKindOfClass:[NSDictionary class]]) return;

                NSString *fingerprint = MCPAXNodeCompactElementFingerprint(compact) ?: [compact description];
                if (fingerprint.length > 0 && [seenFingerprints containsObject:fingerprint]) return;
                if (fingerprint.length > 0) [seenFingerprints addObject:fingerprint];

                NSMutableDictionary *mutable = [compact mutableCopy];
                NSString *path = [NSString stringWithFormat:@"c.%lu", (unsigned long)elements.count];
                mutable[@"index"] = @((NSInteger)elements.count);
                mutable[@"path"] = path;
                (void)source;
                (void)extra;

                mutable[@"id"] = path;

                [elements addObject:mutable];
                serializedCandidateCount++;
            };

            NSArray<NSDictionary<NSString *, id> *> *candidateSources = @[
                @{@"source": @"app.numeric.visibleElements", @"attribute": @(kMCPAXNodeAttributeVisibleElements)},
                @{@"source": @"app.numeric.semanticElements", @"attribute": @(kMCPAXNodeAttributeElementsWithSemanticContext)},
                @{@"source": @"app.numeric.explorerElements", @"attribute": @(kMCPAXNodeAttributeExplorerElements)},
                @{@"source": @"app.numeric.focusableElements", @"attribute": @(kMCPAXNodeAttributeNativeFocusableElements)},
                @{@"source": @"app.numeric.siriFocusableElements", @"attribute": @(kMCPAXNodeAttributeSiriContentNativeFocusableElements)},
                @{@"source": @"app.numeric.siriSemanticElements", @"attribute": @(kMCPAXNodeAttributeSiriContentElementsWithSemanticContext)}
            ];

            void (^appendCandidateGroups)(AXUIElementRef, NSString *, BOOL) =
                ^(AXUIElementRef sourceElement, NSString *sourcePrefix, BOOL appLevel) {
                if (!sourceElement || elements.count >= (NSUInteger)limit) return;

                for (NSDictionary<NSString *, id> *sourceInfo in candidateSources) {
                    if (elements.count >= (NSUInteger)limit) break;

                    NSNumber *attributeNumber = [sourceInfo[@"attribute"] isKindOfClass:[NSNumber class]] ? sourceInfo[@"attribute"] : nil;
                    NSString *sourceName = [sourceInfo[@"source"] isKindOfClass:[NSString class]] ? sourceInfo[@"source"] : @"numeric.candidates";
                    if (!attributeNumber) continue;

                    NSArray *leaves = [self.attributeBridge copyNumericAttributeArray:sourceElement
                                                                          attributeId:(uint32_t)attributeNumber.unsignedIntValue];
                    if (appLevel) {
                        appCandidateCount += leaves.count;
                    } else {
                        windowCandidateCount += leaves.count;
                    }
                    if (leaves.count == 0) continue;

                    NSString *qualifiedSource = sourcePrefix.length > 0 ?
                        [NSString stringWithFormat:@"%@.%@", sourcePrefix, sourceName] :
                        sourceName;
                    for (id leaf in leaves) {
                        if (elements.count >= (NSUInteger)limit) break;
                        if (!leaf || leaf == NSNull.null) continue;
                        appendCompactElement((__bridge AXUIElementRef)leaf, qualifiedSource, nil);
                    }
                }
            };

            appendCandidateGroups(appElement, @"application", YES);

            NSArray *windows = [self.attributeBridge copyNumericAttributeArray:appElement
                                                                   attributeId:kMCPAXNodeAttributeChildren];
            for (id window in windows) {
                if (elements.count >= (NSUInteger)limit) break;
                if (!window || window == NSNull.null) continue;
                appendCandidateGroups((__bridge AXUIElementRef)window, @"window", NO);
            }

            NSMutableArray<NSString *> *sampledHitErrors = [NSMutableArray array];
            if (MCPAXNodeSourceEnableNumericSampledHitMerge && elements.count < (NSUInteger)limit) {
                NSArray<NSValue *> *samplePoints = MCPAXNodeCompactScreenProbePoints(screenBounds);
                for (NSValue *pointValue in samplePoints) {
                    if (elements.count >= (NSUInteger)limit) break;

                    CGPoint point = pointValue.CGPointValue;
                    NSString *hitError = nil;
                    CGPoint fixedSample = CGPointApplyAffineTransform(point, MCPGetScreenGeometry().interfaceToFixed);
                    AXUIElementRef hitElement = [self.attributeBridge copyHitTestElementAtPoint:fixedSample
                                                                                    expectedPid:pid
                                                                             allowParameterized:YES
                                                                                          error:&hitError];
                    if (!hitElement) {
                        if (hitError.length > 0) {
                            [sampledHitErrors addObject:[NSString stringWithFormat:@"(%.0f,%.0f)=%@",
                                                         point.x,
                                                         point.y,
                                                         hitError]];
                        }
                        continue;
                    }

                    sampledHitCandidateCount++;
                    NSDictionary *extra = @{
                        @"samplePoint": @{
                            @"x": @((NSInteger)lrint(point.x)),
                            @"y": @((NSInteger)lrint(point.y))
                        }
                    };
                    appendCompactElement(hitElement, @"sampled.hitTest", extra);
                    CFRelease(hitElement);
                }
            }

            CFRelease(appElement);

            if (elements.count == 0) {
                resultError = [NSString stringWithFormat:@"Compact AX crawl serialized no visible nodes (appCandidates=%lu, windows=%lu, windowCandidates=%lu, sampledHits=%lu)",
                               (unsigned long)appCandidateCount,
                               (unsigned long)windows.count,
                               (unsigned long)windowCandidateCount,
                               (unsigned long)sampledHitCandidateCount];
                return;
            }

            NSMutableDictionary *payload = [NSMutableDictionary dictionary];
            payload[@"format"] = @"compact";
            payload[@"source"] = @"direct_ax_compact_attribute_crawl";
            payload[@"direct_ax_strategy"] = @"compact_numeric_candidate_arrays_sampled_hits";
            MCPScreenGeometry geometry = MCPGetScreenGeometry();
            NSMutableDictionary *screen = [MCPAXNodeCompactScreenDictionary(geometry.fixedBounds) mutableCopy];
            screen[@"coordinate_space"] = @"fixed";
            screen[@"orientation"] = MCPInterfaceOrientationName(geometry.interfaceOrientation);
            payload[@"screen"] = screen;
            payload[@"visible_only"] = @(visibleOnly);
            payload[@"clickable_only"] = @(clickableOnly);
            payload[@"count"] = @(elements.count);
            payload[@"element_count"] = @(elements.count);
            payload[@"root_count"] = @(appCandidateCount + windowCandidateCount + sampledHitCandidateCount);
            payload[@"app_candidate_count"] = @(appCandidateCount);
            payload[@"window_candidate_count"] = @(windowCandidateCount);
            payload[@"sampled_hit_count"] = @(sampledHitCandidateCount);
            payload[@"serialized_candidate_count"] = @(serializedCandidateCount);
            payload[@"numeric_max_elements"] = @(limit);
            payload[@"pid"] = @(pid);
            if (bundleId.length > 0) payload[@"bundleId"] = bundleId;
            if (contextId > 0) payload[@"contextId"] = @(contextId);
            if (displayId > 0) payload[@"displayId"] = @(displayId);
            if (sampledHitErrors.count > 0) payload[@"sample_errors"] = sampledHitErrors;
            payload[@"elements"] = elements;
            resultPayload = MCPAXNodeResultInFixedCoordinates(payload, geometry.interfaceToFixed);
        } @catch (NSException *exception) {
            resultError = [NSString stringWithFormat:@"compact AX crawl exception: %@: %@",
                           exception.name,
                           exception.reason ?: @"<no reason>"];
        }
    }];

    if (!resultPayload && error) *error = resultError;
    return resultPayload;
}

- (NSDictionary * _Nullable)buildNumericElementAtPoint:(CGPoint)point
                                                   pid:(pid_t)pid
                                             contextId:(uint32_t)contextId
                                             displayId:(uint32_t)displayId
                                                 error:(NSString * _Nullable * _Nullable)error {
    NSString *appError = nil;
    AXUIElementRef appElement = [self.attributeBridge copyApplicationElementForPid:pid error:&appError];
    if (!appElement) {
        if (error) *error = appError ?: [NSString stringWithFormat:@"AX create_application failed for PID %d", pid];
        return nil;
    }

    NSInteger limit = MCPAXNodeNumericFallbackMaxElements(2000);
    NSMutableOrderedSet<NSString *> *seenFingerprints = [NSMutableOrderedSet orderedSet];
    __block NSInteger serializedCandidateCount = 0;
    __block NSUInteger appCandidateCount = 0;
    __block NSUInteger windowCandidateCount = 0;
    __block NSUInteger sampledHitCandidateCount = 0;
    __block NSUInteger windowCount = 0;
    __block CGFloat bestArea = CGFLOAT_MAX;
    __block NSDictionary *best = nil;

    void (^considerSerializedNode)(NSDictionary *) = ^(NSDictionary *node) {
        if (serializedCandidateCount >= limit) return;
        if (![node isKindOfClass:[NSDictionary class]]) return;

        NSString *fingerprint = MCPAXNodeFingerprintForNode(node) ?: [node description];
        if (fingerprint.length > 0 && [seenFingerprints containsObject:fingerprint]) return;
        if (fingerprint.length > 0) [seenFingerprints addObject:fingerprint];

        serializedCandidateCount++;
        for (NSString *key in @[@"frame", @"visibleFrame", @"focusable_frame_for_zoom"]) {
            NSDictionary *frame = [node[key] isKindOfClass:[NSDictionary class]] ? node[key] : nil;
            if (!MCPAXNodeFrameContainsPoint(frame, point, 2.0)) continue;

            CGFloat area = MCPAXNodeFrameArea(frame);
            if (!best || area < bestArea) {
                best = node;
                bestArea = area;
            }
        }
    };

    void (^considerNumericElement)(AXUIElementRef) = ^(AXUIElementRef leafElement) {
        if (!leafElement || serializedCandidateCount >= limit) return;
        considerSerializedNode([self serializeNumericLeafElement:leafElement]);
    };

    NSArray<NSNumber *> *candidateAttributes = @[
        @(kMCPAXNodeAttributeVisibleElements),
        @(kMCPAXNodeAttributeElementsWithSemanticContext),
        @(kMCPAXNodeAttributeExplorerElements),
        @(kMCPAXNodeAttributeNativeFocusableElements),
        @(kMCPAXNodeAttributeSiriContentNativeFocusableElements),
        @(kMCPAXNodeAttributeSiriContentElementsWithSemanticContext)
    ];

    void (^scanCandidateGroups)(AXUIElementRef, BOOL) = ^(AXUIElementRef sourceElement, BOOL appLevel) {
        if (!sourceElement || serializedCandidateCount >= limit) return;

        for (NSNumber *attributeNumber in candidateAttributes) {
            if (serializedCandidateCount >= limit) break;

            NSArray *leaves = [self.attributeBridge copyNumericAttributeArray:sourceElement
                                                                  attributeId:(uint32_t)attributeNumber.unsignedIntValue];
            if (appLevel) {
                appCandidateCount += leaves.count;
            } else {
                windowCandidateCount += leaves.count;
            }

            for (id leaf in leaves) {
                if (serializedCandidateCount >= limit) break;
                if (!leaf || leaf == NSNull.null) continue;
                considerNumericElement((__bridge AXUIElementRef)leaf);
            }
        }
    };

    scanCandidateGroups(appElement, YES);

    NSArray *windows = [self.attributeBridge copyNumericAttributeArray:appElement attributeId:kMCPAXNodeAttributeChildren];
    windowCount = windows.count;
    for (id window in windows) {
        if (serializedCandidateCount >= limit) break;
        if (!window || window == NSNull.null) continue;
        scanCandidateGroups((__bridge AXUIElementRef)window, NO);
    }

    NSMutableArray<NSString *> *sampledHitErrors = [NSMutableArray array];
    if (MCPAXNodeSourceEnableNumericSampledHitMerge && serializedCandidateCount < limit) {
        CGRect bounds = MCPAXNodeScreenBounds();
        NSArray<NSValue *> *samplePoints = MCPAXNodeScreenProbePoints(bounds);

        for (NSValue *pointValue in samplePoints) {
            if (serializedCandidateCount >= limit) break;

            CGPoint samplePoint = pointValue.CGPointValue;
            NSString *hitError = nil;
            CGPoint fixedSample = CGPointApplyAffineTransform(samplePoint, MCPGetScreenGeometry().interfaceToFixed);
            AXUIElementRef hitElement = [self.attributeBridge copyHitTestElementAtPoint:fixedSample
                                                                            expectedPid:pid
                                                                     allowParameterized:YES
                                                                                  error:&hitError];
            if (!hitElement) {
                if (hitError.length > 0) {
                    [sampledHitErrors addObject:[NSString stringWithFormat:@"(%.0f,%.0f)=%@",
                                                 samplePoint.x,
                                                 samplePoint.y,
                                                 hitError]];
                }
                continue;
            }

            sampledHitCandidateCount++;
            NSDictionary *serialized = [self serializeRemoteElementLeaf:hitElement];
            CFRelease(hitElement);
            if (![serialized isKindOfClass:[NSDictionary class]]) continue;

            NSMutableDictionary *sampleNode = [serialized mutableCopy];
            sampleNode[@"samplePoint"] = @{
                @"x": @((NSInteger)lrint(samplePoint.x)),
                @"y": @((NSInteger)lrint(samplePoint.y))
            };
            considerSerializedNode(sampleNode);
        }
    }

    CFRelease(appElement);

    if (![best isKindOfClass:[NSDictionary class]]) {
        if (error) {
            *error = [NSString stringWithFormat:@"numeric candidate scan has no frame containing point %.0f,%.0f (serialized=%ld, appCandidates=%lu, windows=%lu, windowCandidates=%lu, sampledHits=%lu)",
                      point.x,
                      point.y,
                      (long)serializedCandidateCount,
                      (unsigned long)appCandidateCount,
                      (unsigned long)windowCount,
                      (unsigned long)windowCandidateCount,
                      (unsigned long)sampledHitCandidateCount];
        }
        return nil;
    }

    NSMutableDictionary *node = [best mutableCopy];
    node[@"source"] = @"direct_ax_hit_test";
    node[@"direct_ax_strategy"] = @"numeric_visible_frame_hit_test";
    node[@"hit_test_point"] = @{
        @"x": @((NSInteger)lrint(point.x)),
        @"y": @((NSInteger)lrint(point.y))
    };
    node[@"pid"] = @(pid);
    if (contextId > 0 && !node[@"contextId"]) node[@"contextId"] = @(contextId);
    if (displayId > 0 && !node[@"displayId"]) node[@"displayId"] = @(displayId);

    NSMutableDictionary *diagnostics = [NSMutableDictionary dictionary];
    diagnostics[@"numericFrameFallbackElementCount"] = @(serializedCandidateCount);
    diagnostics[@"numericFrameFallbackWindowCount"] = @(windowCount);
    diagnostics[@"numericFrameFallbackBestArea"] = @(bestArea);
    diagnostics[@"numericFrameFallbackAppCandidateCount"] = @(appCandidateCount);
    diagnostics[@"numericFrameFallbackWindowCandidateCount"] = @(windowCandidateCount);
    diagnostics[@"numericFrameFallbackSampledHitCount"] = @(sampledHitCandidateCount);
    if (sampledHitErrors.count > 0) diagnostics[@"numericFrameFallbackSampleErrors"] = sampledHitErrors;
    node[@"direct_ax_diagnostics"] = diagnostics;
    return node;
}

- (NSDictionary * _Nullable)serializeRemoteElement:(AXUIElementRef)element
                                             depth:(NSInteger)depth
                                          maxDepth:(NSInteger)maxDepth
                                             count:(NSInteger *)count
                                       maxElements:(NSInteger)maxElements
                                           visited:(NSMutableSet<NSString *> *)visited {
    if (!element || depth > maxDepth || !count || !visited || *count >= maxElements) return nil;

    NSString *visitKey = [NSString stringWithFormat:@"%p", element];
    if ([visited containsObject:visitKey]) return nil;
    [visited addObject:visitKey];
    (*count)++;

    NSMutableDictionary *node = [NSMutableDictionary dictionary];
    node[@"_ax_ref"] = [NSString stringWithFormat:@"%p", element];
    NSArray<NSString *> *scalarAttributes = @[
        (__bridge NSString *)kAXRoleAttribute,
        (__bridge NSString *)kAXSubroleAttribute,
        (__bridge NSString *)kAXLabelAttribute,
        (__bridge NSString *)kAXValueAttribute,
        (__bridge NSString *)kAXTitleAttribute,
        (__bridge NSString *)kAXDescriptionAttribute,
        (__bridge NSString *)kAXIdentifierAttribute,
        (__bridge NSString *)kAXPlaceholderAttribute,
        (__bridge NSString *)kAXEnabledAttribute,
        (__bridge NSString *)kAXFocusedAttribute,
        (__bridge NSString *)kAXSelectedAttribute,
        (__bridge NSString *)kAXTraitsAttribute,
        (__bridge NSString *)kAXFrameAttribute
    ];
    NSDictionary<NSString *, id> *scalarValues = [self.attributeBridge copyAttributeMap:element attributes:scalarAttributes] ?: @{};
    NSDictionary<NSString *, id> *xcValues = [self.attributeBridge copyXCAttributeMap:element attributeKeys:@[
        @"automationType",
        @"childrenCount",
        @"frame",
        @"identifier",
        @"isRemoteElement",
        @"isVisible",
        @"label",
        @"traits",
        @"value",
        @"visibleFrame",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};
    NSDictionary<NSString *, id> *directValues = [self.attributeBridge copyDirectAttributeMap:element attributeKeys:@[
        @"application",
        @"centerPoint",
        @"containerType",
        @"containerTypes",
        @"elementParent",
        @"elementsWithSemanticContext",
        @"explorerElements",
        @"focusableFrameForZoom",
        @"nativeFocusableElements",
        @"path",
        @"remoteApplication",
        @"remoteParent",
        @"siriContentElementsWithSemanticContext",
        @"siriContentNativeFocusableElements",
        @"url",
        @"userInputLabels",
        @"visibleElements",
        @"visibleFrame",
        @"visiblePoint",
        @"windowContextId",
        @"windowDisplayId"
    ]] ?: @{};

    NSString *role = [scalarValues[(__bridge NSString *)kAXRoleAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXRoleAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXRoleAttribute];
    NSString *subrole = [scalarValues[(__bridge NSString *)kAXSubroleAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXSubroleAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXSubroleAttribute];
    NSString *label = MCPAXNodeStringFromValue(xcValues[@"label"]) ?:
        ([scalarValues[(__bridge NSString *)kAXLabelAttribute] isKindOfClass:[NSString class]] ?
         scalarValues[(__bridge NSString *)kAXLabelAttribute] :
         [self.attributeBridge copyStringAttribute:element attribute:kAXLabelAttribute]);
    id rawValue = xcValues[@"value"] ?: scalarValues[(__bridge NSString *)kAXValueAttribute] ?: [self.attributeBridge copyAttributeObject:element attribute:kAXValueAttribute];
    NSString *value = MCPAXNodeStringFromValue(rawValue);
    NSString *title = [scalarValues[(__bridge NSString *)kAXTitleAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXTitleAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXTitleAttribute];
    NSString *desc = [scalarValues[(__bridge NSString *)kAXDescriptionAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXDescriptionAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXDescriptionAttribute];
    NSString *identifier = MCPAXNodeStringFromValue(xcValues[@"identifier"]) ?:
        ([scalarValues[(__bridge NSString *)kAXIdentifierAttribute] isKindOfClass:[NSString class]] ?
         scalarValues[(__bridge NSString *)kAXIdentifierAttribute] :
         [self.attributeBridge copyStringAttribute:element attribute:kAXIdentifierAttribute]);
    NSString *placeholder = [scalarValues[(__bridge NSString *)kAXPlaceholderAttribute] isKindOfClass:[NSString class]] ?
        scalarValues[(__bridge NSString *)kAXPlaceholderAttribute] :
        [self.attributeBridge copyStringAttribute:element attribute:kAXPlaceholderAttribute];
    NSNumber *enabled = [scalarValues[(__bridge NSString *)kAXEnabledAttribute] isKindOfClass:[NSNumber class]] ?
        scalarValues[(__bridge NSString *)kAXEnabledAttribute] :
        [self.attributeBridge copyNumberAttribute:element attribute:kAXEnabledAttribute];
    NSNumber *focused = [scalarValues[(__bridge NSString *)kAXFocusedAttribute] isKindOfClass:[NSNumber class]] ?
        scalarValues[(__bridge NSString *)kAXFocusedAttribute] :
        [self.attributeBridge copyNumberAttribute:element attribute:kAXFocusedAttribute];
    NSNumber *selected = [scalarValues[(__bridge NSString *)kAXSelectedAttribute] isKindOfClass:[NSNumber class]] ?
        scalarValues[(__bridge NSString *)kAXSelectedAttribute] :
        [self.attributeBridge copyNumberAttribute:element attribute:kAXSelectedAttribute];
    id traits = xcValues[@"traits"] ?: scalarValues[(__bridge NSString *)kAXTraitsAttribute];
    if (!traits) {
        traits = [self.attributeBridge copyAttributeObject:element attribute:kAXTraitsAttribute];
    }

    node[@"role"] = role ?: @"AXElement";
    if (subrole.length > 0) node[@"subrole"] = subrole;
    if (label.length > 0) node[@"label"] = label;
    if (value.length > 0 && !MCPAXNodeStringLooksLikeAXError(value)) {
        node[@"value"] = value;
    } else {
        id normalizedValue = MCPAXNodeNormalizedValue(rawValue);
        if ([normalizedValue isKindOfClass:[NSString class]] && MCPAXNodeStringLooksLikeAXError(normalizedValue)) {
            normalizedValue = nil;
        }
        if (normalizedValue) node[@"value"] = normalizedValue;
    }
    if (title.length > 0) node[@"title"] = title;
    if (desc.length > 0) node[@"description"] = desc;
    if (identifier.length > 0) node[@"identifier"] = identifier;
    if (placeholder.length > 0) node[@"placeholder"] = placeholder;
    if (enabled) node[@"enabled"] = enabled;
    if (focused) node[@"focused"] = focused;
    if (selected) node[@"selected"] = selected;
    if ([traits isKindOfClass:[NSArray class]] ||
        [traits isKindOfClass:[NSString class]] ||
        [traits isKindOfClass:[NSNumber class]]) {
        node[@"traits"] = traits;
    }

    id frameValue = xcValues[@"frame"] ?: scalarValues[(__bridge NSString *)kAXFrameAttribute];
    if (!frameValue) {
        frameValue = [self.attributeBridge copyAttributeObject:element attribute:kAXFrameAttribute];
    }
    CGRect frame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(frameValue, &frame)) {
        node[@"frame"] = MCPAXNodeFrameDictionary(frame);
    }

    id visibleFrameValue = xcValues[@"visibleFrame"] ?: directValues[@"visibleFrame"];
    CGRect visibleFrame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(visibleFrameValue, &visibleFrame)) {
        node[@"visibleFrame"] = MCPAXNodeFrameDictionary(visibleFrame);
    }

    NSNumber *isVisible = MCPAXNodeNumberFromValue(xcValues[@"isVisible"]);
    if (isVisible) node[@"visible"] = @([isVisible boolValue]);

    NSNumber *childrenCount = MCPAXNodeNumberFromValue(xcValues[@"childrenCount"]);
    if (childrenCount) node[@"child_count"] = childrenCount;

    NSNumber *windowContextId = MCPAXNodeNumberFromValue(xcValues[@"windowContextId"] ?: directValues[@"windowContextId"]);
    if (windowContextId.unsignedIntValue > 0) {
        node[@"window_context_id"] = windowContextId;
        node[@"contextId"] = windowContextId;
    }

    NSNumber *windowDisplayId = MCPAXNodeNumberFromValue(xcValues[@"windowDisplayId"] ?: directValues[@"windowDisplayId"]);
    if (windowDisplayId.unsignedIntValue > 0) {
        node[@"window_display_id"] = windowDisplayId;
        node[@"displayId"] = windowDisplayId;
    }

    NSNumber *isRemoteElement = MCPAXNodeNumberFromValue(xcValues[@"isRemoteElement"]);
    if (isRemoteElement) node[@"is_remote_element"] = @([isRemoteElement boolValue]);

    NSNumber *automationType = MCPAXNodeNumberFromValue(xcValues[@"automationType"]);
    if (automationType) node[@"automation_type"] = automationType;

    id containerType = MCPAXNodeNormalizedValue(directValues[@"containerType"]);
    if (containerType) node[@"container_type"] = containerType;

    id containerTypes = MCPAXNodeNormalizedValue(directValues[@"containerTypes"]);
    if (containerTypes) node[@"container_types"] = containerTypes;

    id userInputLabels = MCPAXNodeNormalizedValue(directValues[@"userInputLabels"]);
    if (userInputLabels) node[@"user_input_labels"] = userInputLabels;

    NSString *url = MCPAXNodeStringFromValue(directValues[@"url"]);
    if (url.length > 0) node[@"url"] = url;

    NSString *path = MCPAXNodeStringFromValue(directValues[@"path"]);
    if (path.length > 0) node[@"path"] = path;

    CGRect focusableFrame = CGRectZero;
    if (MCPAXNodeCGRectFromObject(directValues[@"focusableFrameForZoom"], &focusableFrame)) {
        node[@"focusable_frame_for_zoom"] = MCPAXNodeFrameDictionary(focusableFrame);
    }

    CGPoint centerPoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"centerPoint"], &centerPoint)) {
        node[@"center_point"] = MCPAXNodePointDictionary(centerPoint);
    }

    CGPoint visiblePoint = CGPointZero;
    if (MCPAXNodeCGPointFromObject(directValues[@"visiblePoint"], &visiblePoint)) {
        node[@"visible_point"] = MCPAXNodePointDictionary(visiblePoint);
    }

    NSMutableDictionary *semanticContext = [NSMutableDictionary dictionary];
    NSMutableDictionary<NSString *, NSNumber *> *candidateCounts = [NSMutableDictionary dictionary];
    for (NSString *key in @[
        @"visibleElements",
        @"elementsWithSemanticContext",
        @"nativeFocusableElements",
        @"explorerElements",
        @"siriContentNativeFocusableElements",
        @"siriContentElementsWithSemanticContext"
    ]) {
        if (directValues[key]) {
            candidateCounts[key] = @(MCPAXNodeCollectionCount(directValues[key]));
        }
    }
    if (candidateCounts.count > 0) {
        semanticContext[@"candidateCounts"] = candidateCounts;
    }
    if (directValues[@"remoteParent"]) {
        semanticContext[@"hasRemoteParent"] = @YES;
        NSString *remoteParentRef = MCPAXNodePointerStringForObject(directValues[@"remoteParent"]);
        if (remoteParentRef.length > 0) {
            node[@"_remote_parent_ax_ref"] = remoteParentRef;
        }
    }
    if (directValues[@"remoteApplication"]) {
        semanticContext[@"hasRemoteApplication"] = @YES;
    }
    if (directValues[@"elementParent"]) {
        semanticContext[@"hasElementParent"] = @YES;
        NSString *parentRef = MCPAXNodePointerStringForObject(directValues[@"elementParent"]);
        if (parentRef.length > 0) {
            node[@"_parent_ax_ref"] = parentRef;
        }
    }
    if (containerType) semanticContext[@"containerType"] = containerType;
    if (containerTypes) semanticContext[@"containerTypes"] = containerTypes;
    if (userInputLabels) semanticContext[@"userInputLabels"] = userInputLabels;
    if (node[@"window_context_id"]) semanticContext[@"windowContextId"] = node[@"window_context_id"];
    if (node[@"window_display_id"]) semanticContext[@"windowDisplayId"] = node[@"window_display_id"];
    if (semanticContext.count > 0) {
        node[@"semanticContext"] = semanticContext;
    }

    if (depth == 0) {
        id sanitizedSnapshot = MCPAXNodeSanitizeSnapshotValue([self.attributeBridge copyUserTestingSnapshotForElement:element options:nil], 0);
        if ([sanitizedSnapshot isKindOfClass:[NSDictionary class]] && [sanitizedSnapshot count] > 0) {
            node[@"userTestingSnapshot"] = sanitizedSnapshot;
            NSDictionary *snapshotSummary = MCPAXNodeUserTestingSnapshotSummary(sanitizedSnapshot);
            if (snapshotSummary.count > 0) {
                node[@"userTestingSnapshotSummary"] = snapshotSummary;
            }
        }
    }

    if (depth < maxDepth && *count < maxElements) {
        NSArray *children = [self.attributeBridge copyChildElementsForElement:element];
        NSMutableArray *serializedChildren = [NSMutableArray array];
        for (id child in children) {
            if (*count >= maxElements) break;
            NSDictionary *childNode = [self serializeRemoteElement:(__bridge AXUIElementRef)child
                                                             depth:depth + 1
                                                          maxDepth:maxDepth
                                                             count:count
                                                       maxElements:maxElements
                                                           visited:visited];
            if (!childNode) continue;

            if (MCPAXNodeLooksLikeDuplicateWrapper(node, childNode)) {
                NSArray *promotedChildren = [childNode[@"children"] isKindOfClass:[NSArray class]] ? childNode[@"children"] : nil;
                if (promotedChildren.count > 0) {
                    [serializedChildren addObjectsFromArray:promotedChildren];
                }
                continue;
            }

            if (MCPAXNodeIsLowSignalLeafWrapper(childNode)) {
                continue;
            }

            [serializedChildren addObject:childNode];
        }
        if (serializedChildren.count > 0) {
            BOOL allowReparenting = (depth + 2) <= maxDepth;
            node[@"children"] = MCPAXNodeNormalizedCandidateChildren(serializedChildren, allowReparenting);
        }
    }

    if (depth == 0) {
        MCPAXNodeStripInternalKeysRecursively(node);
    }

    [visited removeObject:visitKey];
    return node;
}

@end
