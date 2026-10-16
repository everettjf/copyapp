#import "MCPAXAttributeBridge.h"
#import <UIKit/UIKit.h>
#import <dispatch/dispatch.h>
#import <dlfcn.h>
#import <mach-o/dyld.h>
#import <objc/message.h>
#import "MCPLogger.h"

#define MCP_AX_BRIDGE_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[AXBridge] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)

typedef struct {
    BOOL available;
    void *handle;
    CFTypeRef (*createAXValue)(int valueType, const void *valuePtr);
    AXUIElementCreateApplicationFunc createApplication;
    AXUIElementCreateAppElementWithPidFunc createAppElementWithPid;
    AXUIElementCreateSystemWideFunc createSystemWide;
    AXUIElementCopyAttributeValueFunc copyAttributeValue;
    AXUIElementCopyParameterizedAttributeValueFunc copyParameterizedAttributeValue;
    AXUIElementCopyMultipleAttributeValuesFunc copyMultipleAttributeValues;
    AXUIElementCopyAttributeNamesFunc copyAttributeNames;
    AXUIElementCopyElementAtPositionFunc copyElementAtPosition;
    AXUIElementCopyElementAtPositionWithParamsFunc copyElementAtPositionWithParams;
    AXUIElementCopyApplicationAtPositionFunc copyApplicationAtPosition;
    AXUIElementCopyApplicationAndContextAtPositionFunc copyApplicationAndContextAtPosition;
    AXUIElementSetMessagingTimeoutFunc setMessagingTimeout;
    AXUIElementCopyElementWithParametersFunc copyElementWithParameters;
    AXUIElementCopyElementUsingContextIdAtPositionFunc copyElementUsingContextIdAtPosition;
    AXUIElementCopyElementUsingDisplayIdAtPositionFunc copyElementUsingDisplayIdAtPosition;
    AXUIElementGetPidFunc getPid;
    AXAddAssociatedPidFunc addAssociatedPid;
    AXIsPidAssociatedFunc isPidAssociated;
    AXIsPidAssociatedWithDisplayTypeFunc isPidAssociatedWithDisplayType;
    AXSetRequestingClientFunc setRequestingClient;
    AXOverrideRequestingClientTypeFunc overrideRequestingClientType;
    CFStringRef xcAttributeAutomationType;
    CFStringRef xcAttributeChildren;
    CFStringRef xcAttributeChildrenCount;
    CFStringRef xcAttributeElementBaseType;
    CFStringRef xcAttributeElementType;
    CFStringRef xcAttributeFrame;
    CFStringRef xcAttributeHorizontalSizeClass;
    CFStringRef xcAttributeIdentifier;
    CFStringRef xcAttributeIsRemoteElement;
    CFStringRef xcAttributeIsUserInteractionEnabled;
    CFStringRef xcAttributeIsVisible;
    CFStringRef xcAttributeLabel;
    CFStringRef xcAttributeLocalizedStringKey;
    CFStringRef xcAttributeLocalizationBundleID;
    CFStringRef xcAttributeLocalizationBundlePath;
    CFStringRef xcAttributeLocalizedStringTableName;
    CFStringRef xcAttributeMainWindow;
    CFStringRef xcAttributeParent;
    CFStringRef xcAttributePlaceholderValue;
    CFStringRef xcAttributeTraits;
    CFStringRef xcAttributeUserTestingElements;
    CFStringRef xcAttributeUserTestingSnapshot;
    CFStringRef xcAttributeValue;
    CFStringRef xcAttributeVisibleFrame;
    CFStringRef xcAttributeViewControllerClassName;
    CFStringRef xcAttributeViewControllerTitle;
    CFStringRef xcAttributeVerticalSizeClass;
    CFStringRef xcAttributeWindowContextId;
    CFStringRef xcAttributeWindowDisplayId;
    CFStringRef xcParameterizedChildrenWithRange;
    CFStringRef xcParameterizedUserTestingSnapshot;
} MCPAXBridgeRuntime;

static MCPAXBridgeRuntime sMCPAXBridgeRuntime;
enum {
    kMCPAXBridgeValueTypeCGPoint = 1
};

static const CFStringRef kMCPAXBridgePointAndDisplayParameterizedAttribute = (CFStringRef)0x16573;
static const CFStringRef kMCPAXBridgePidForContextParameterizedAttribute = (CFStringRef)0x16574;

static inline CFStringRef MCPAXBridgeNumericAttributeRef(uint32_t attrId) {
    return (CFStringRef)(uintptr_t)attrId;
}

static CFStringRef MCPAXBridgeCopyCFStringSymbol(void *handle, const char *symbolName) {
    void *symbol = dlsym(handle, symbolName);
    if (!symbol) return NULL;
    return *(CFStringRef *)symbol;
}

static CFStringRef MCPAXBridgeXCAttributeRefForKey(NSString *attributeKey) {
    if (![attributeKey isKindOfClass:[NSString class]] || attributeKey.length == 0) return NULL;

    if ([attributeKey isEqualToString:@"automationType"]) return sMCPAXBridgeRuntime.xcAttributeAutomationType;
    if ([attributeKey isEqualToString:@"children"]) return sMCPAXBridgeRuntime.xcAttributeChildren ?: kAXChildrenAttribute;
    if ([attributeKey isEqualToString:@"childrenCount"]) return sMCPAXBridgeRuntime.xcAttributeChildrenCount;
    if ([attributeKey isEqualToString:@"elementBaseType"]) return sMCPAXBridgeRuntime.xcAttributeElementBaseType;
    if ([attributeKey isEqualToString:@"elementType"]) return sMCPAXBridgeRuntime.xcAttributeElementType;
    if ([attributeKey isEqualToString:@"frame"]) return sMCPAXBridgeRuntime.xcAttributeFrame ?: kAXFrameAttribute;
    if ([attributeKey isEqualToString:@"horizontalSizeClass"]) return sMCPAXBridgeRuntime.xcAttributeHorizontalSizeClass;
    if ([attributeKey isEqualToString:@"identifier"]) return sMCPAXBridgeRuntime.xcAttributeIdentifier ?: kAXIdentifierAttribute;
    if ([attributeKey isEqualToString:@"isRemoteElement"]) return sMCPAXBridgeRuntime.xcAttributeIsRemoteElement;
    if ([attributeKey isEqualToString:@"isUserInteractionEnabled"]) return sMCPAXBridgeRuntime.xcAttributeIsUserInteractionEnabled;
    if ([attributeKey isEqualToString:@"isVisible"]) return sMCPAXBridgeRuntime.xcAttributeIsVisible;
    if ([attributeKey isEqualToString:@"label"]) return sMCPAXBridgeRuntime.xcAttributeLabel ?: kAXLabelAttribute;
    if ([attributeKey isEqualToString:@"localizedStringKey"]) return sMCPAXBridgeRuntime.xcAttributeLocalizedStringKey;
    if ([attributeKey isEqualToString:@"localizationBundleID"]) return sMCPAXBridgeRuntime.xcAttributeLocalizationBundleID;
    if ([attributeKey isEqualToString:@"localizationBundlePath"]) return sMCPAXBridgeRuntime.xcAttributeLocalizationBundlePath;
    if ([attributeKey isEqualToString:@"localizedStringTableName"]) return sMCPAXBridgeRuntime.xcAttributeLocalizedStringTableName;
    if ([attributeKey isEqualToString:@"mainWindow"]) return sMCPAXBridgeRuntime.xcAttributeMainWindow;
    if ([attributeKey isEqualToString:@"parent"]) return sMCPAXBridgeRuntime.xcAttributeParent;
    if ([attributeKey isEqualToString:@"placeholderValue"]) return sMCPAXBridgeRuntime.xcAttributePlaceholderValue;
    if ([attributeKey isEqualToString:@"traits"]) return sMCPAXBridgeRuntime.xcAttributeTraits ?: kAXTraitsAttribute;
    if ([attributeKey isEqualToString:@"userTestingElements"]) return sMCPAXBridgeRuntime.xcAttributeUserTestingElements;
    if ([attributeKey isEqualToString:@"userTestingSnapshot"]) return sMCPAXBridgeRuntime.xcAttributeUserTestingSnapshot;
    if ([attributeKey isEqualToString:@"value"]) return sMCPAXBridgeRuntime.xcAttributeValue ?: kAXValueAttribute;
    if ([attributeKey isEqualToString:@"visibleFrame"]) return sMCPAXBridgeRuntime.xcAttributeVisibleFrame;
    if ([attributeKey isEqualToString:@"viewControllerClassName"]) return sMCPAXBridgeRuntime.xcAttributeViewControllerClassName;
    if ([attributeKey isEqualToString:@"viewControllerTitle"]) return sMCPAXBridgeRuntime.xcAttributeViewControllerTitle;
    if ([attributeKey isEqualToString:@"verticalSizeClass"]) return sMCPAXBridgeRuntime.xcAttributeVerticalSizeClass;
    if ([attributeKey isEqualToString:@"windowContextId"]) return sMCPAXBridgeRuntime.xcAttributeWindowContextId;
    if ([attributeKey isEqualToString:@"windowDisplayId"]) return sMCPAXBridgeRuntime.xcAttributeWindowDisplayId;
    return NULL;
}

static CFStringRef MCPAXBridgeXCParameterizedAttributeRefForKey(NSString *attributeKey) {
    if (![attributeKey isKindOfClass:[NSString class]] || attributeKey.length == 0) return NULL;
    if ([attributeKey isEqualToString:@"childrenWithRange"]) return sMCPAXBridgeRuntime.xcParameterizedChildrenWithRange;
    if ([attributeKey isEqualToString:@"userTestingSnapshotParameterized"]) return sMCPAXBridgeRuntime.xcParameterizedUserTestingSnapshot;
    return NULL;
}

static CFStringRef MCPAXBridgeDirectAttributeRefForKey(NSString *attributeKey) {
    if (![attributeKey isKindOfClass:[NSString class]] || attributeKey.length == 0) return NULL;

    if ([attributeKey isEqualToString:@"visibleElements"]) return MCPAXBridgeNumericAttributeRef(3015);
    if ([attributeKey isEqualToString:@"explorerElements"]) return MCPAXBridgeNumericAttributeRef(3022);
    if ([attributeKey isEqualToString:@"elementsWithSemanticContext"]) return MCPAXBridgeNumericAttributeRef(3025);
    if ([attributeKey isEqualToString:@"nativeFocusableElements"]) return MCPAXBridgeNumericAttributeRef(3029);
    if ([attributeKey isEqualToString:@"siriContentNativeFocusableElements"]) return MCPAXBridgeNumericAttributeRef(3031);
    if ([attributeKey isEqualToString:@"siriContentElementsWithSemanticContext"]) return MCPAXBridgeNumericAttributeRef(3032);
    if ([attributeKey isEqualToString:@"remoteParent"]) return MCPAXBridgeNumericAttributeRef(2092);
    if ([attributeKey isEqualToString:@"application"]) return MCPAXBridgeNumericAttributeRef(2017);
    if ([attributeKey isEqualToString:@"remoteApplication"]) return MCPAXBridgeNumericAttributeRef(2142);
    if ([attributeKey isEqualToString:@"windowContextId"]) return MCPAXBridgeNumericAttributeRef(2021);
    if ([attributeKey isEqualToString:@"path"]) return MCPAXBridgeNumericAttributeRef(2042);
    if ([attributeKey isEqualToString:@"visibleFrame"]) return MCPAXBridgeNumericAttributeRef(2057);
    if ([attributeKey isEqualToString:@"visiblePoint"]) return MCPAXBridgeNumericAttributeRef(2070);
    if ([attributeKey isEqualToString:@"elementParent"]) return MCPAXBridgeNumericAttributeRef(5002);
    if ([attributeKey isEqualToString:@"windowDisplayId"]) return MCPAXBridgeNumericAttributeRef(2123);
    if ([attributeKey isEqualToString:@"containerTypes"]) return MCPAXBridgeNumericAttributeRef(2145);
    if ([attributeKey isEqualToString:@"focusableFrameForZoom"]) return MCPAXBridgeNumericAttributeRef(2149);
    if ([attributeKey isEqualToString:@"url"]) return MCPAXBridgeNumericAttributeRef(2020);
    if ([attributeKey isEqualToString:@"userInputLabels"]) return MCPAXBridgeNumericAttributeRef(2186);
    if ([attributeKey isEqualToString:@"containerType"]) return MCPAXBridgeNumericAttributeRef(2187);
    if ([attributeKey isEqualToString:@"centerPoint"]) return MCPAXBridgeNumericAttributeRef(2007);
    if ([attributeKey isEqualToString:@"privateChildren"]) return MCPAXBridgeNumericAttributeRef(5001);
    return NULL;
}

static void MCPAXBridgeAppendUniqueObjects(NSMutableOrderedSet *destination, id value) {
    if (!destination || !value || value == NSNull.null) return;

    if ([value isKindOfClass:[NSArray class]]) {
        for (id item in (NSArray *)value) {
            if (item && item != NSNull.null) {
                [destination addObject:item];
            }
        }
        return;
    }

    if ([value respondsToSelector:@selector(allObjects)] &&
        ![value isKindOfClass:[NSDictionary class]] &&
        ![value isKindOfClass:[NSString class]]) {
        id objects = ((id (*)(id, SEL))objc_msgSend)(value, @selector(allObjects));
        if ([objects isKindOfClass:[NSArray class]]) {
            MCPAXBridgeAppendUniqueObjects(destination, objects);
            return;
        }
    }

    [destination addObject:value];
}

static id MCPAXBridgeMsgSendObject(id target, SEL selector) {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(target, selector);
}

static NSNumber *MCPAXBridgeInvokeNumericSelector(id target, SEL selector) {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;
    unsigned long long value = ((unsigned long long (*)(id, SEL))objc_msgSend)(target, selector);
    return @(value);
}

static BOOL MCPAXBridgeStringContainsToken(NSString *value, NSString *token) {
    if (![value isKindOfClass:[NSString class]] || value.length == 0 || token.length == 0) return NO;
    return [value rangeOfString:token options:NSCaseInsensitiveSearch].location != NSNotFound;
}

static NSArray<NSDictionary *> *MCPAXBridgeWorkspaceContextCandidates(void) {
    Class workspaceClass = objc_getClass("FBSWorkspace");
    id workspace = MCPAXBridgeMsgSendObject(workspaceClass, NSSelectorFromString(@"_sharedWorkspaceIfExists"));
    if (!workspace) {
        workspace = MCPAXBridgeMsgSendObject(workspaceClass, NSSelectorFromString(@"sharedWorkspace"));
    }
    if (!workspace) return nil;

    id scenesValue = MCPAXBridgeMsgSendObject(workspace, @selector(scenes));
    NSMutableArray *scenes = [NSMutableArray array];
    if ([scenesValue isKindOfClass:[NSArray class]]) {
        [scenes addObjectsFromArray:(NSArray *)scenesValue];
    } else if ([scenesValue respondsToSelector:@selector(allObjects)]) {
        id objects = MCPAXBridgeMsgSendObject(scenesValue, @selector(allObjects));
        if ([objects isKindOfClass:[NSArray class]]) [scenes addObjectsFromArray:(NSArray *)objects];
    }
    if (scenes.count == 0) return nil;

    NSMutableArray<NSDictionary *> *preferred = [NSMutableArray array];
    NSMutableArray<NSDictionary *> *accessibility = [NSMutableArray array];
    NSMutableOrderedSet<NSNumber *> *seenContextIds = [NSMutableOrderedSet orderedSet];

    for (id scene in scenes) {
        if (!scene) continue;
        NSString *sceneIdentifier = MCPAXBridgeMsgSendObject(scene, @selector(identifier));
        NSString *sceneBundleId = MCPAXBridgeMsgSendObject(scene, NSSelectorFromString(@"crs_applicationBundleIdentifier"));
        NSString *sceneClass = NSStringFromClass([scene class]) ?: @"<unknown>";
        BOOL accessibilityLike =
            MCPAXBridgeStringContainsToken(sceneIdentifier, @"Accessibility") ||
            MCPAXBridgeStringContainsToken(sceneBundleId, @"Accessibility") ||
            MCPAXBridgeStringContainsToken(sceneClass, @"Accessibility") ||
            MCPAXBridgeStringContainsToken(sceneClass, @"AXUI");

        id contextsValue = MCPAXBridgeMsgSendObject(scene, @selector(contexts));
        NSArray *contexts = nil;
        if ([contextsValue isKindOfClass:[NSArray class]]) {
            contexts = (NSArray *)contextsValue;
        } else if ([contextsValue respondsToSelector:@selector(allObjects)]) {
            id objects = MCPAXBridgeMsgSendObject(contextsValue, @selector(allObjects));
            if ([objects isKindOfClass:[NSArray class]]) contexts = objects;
        }

        for (id contextObject in contexts) {
            NSNumber *contextId = MCPAXBridgeInvokeNumericSelector(contextObject, NSSelectorFromString(@"contextID"));
            if (contextId.unsignedIntValue == 0) {
                contextId = MCPAXBridgeInvokeNumericSelector(contextObject, NSSelectorFromString(@"contextId"));
            }
            if (contextId.unsignedIntValue == 0) {
                contextId = MCPAXBridgeInvokeNumericSelector(contextObject, NSSelectorFromString(@"windowContextId"));
            }
            if (contextId.unsignedIntValue == 0 || [seenContextIds containsObject:contextId]) continue;
            [seenContextIds addObject:contextId];

            NSMutableDictionary *candidate = [NSMutableDictionary dictionary];
            candidate[@"contextId"] = contextId;
            if (sceneIdentifier.length > 0) candidate[@"sceneIdentifier"] = sceneIdentifier;
            if (sceneBundleId.length > 0) candidate[@"bundleId"] = sceneBundleId;
            candidate[@"accessibilityLike"] = @(accessibilityLike);
            if (accessibilityLike) {
                [accessibility addObject:candidate];
            } else {
                [preferred addObject:candidate];
            }
        }
    }

    NSMutableArray<NSDictionary *> *result = [NSMutableArray array];
    [result addObjectsFromArray:preferred];
    [result addObjectsFromArray:accessibility];
    return result.count > 0 ? result : nil;
}

static void MCPAXBridgeApplyMessagingTimeout(AXUIElementRef element);

static void MCPAXBridgeSetRequestingClientForAutomation(void) {
    if (sMCPAXBridgeRuntime.setRequestingClient) {
        sMCPAXBridgeRuntime.setRequestingClient(2);
    }
}

static AXUIElementRef MCPAXBridgeCreateContextProbeSeed(void) {
    AXUIElementRef seedElement = NULL;
    if (sMCPAXBridgeRuntime.createAppElementWithPid) {
        seedElement = sMCPAXBridgeRuntime.createAppElementWithPid(0);
        if (seedElement) {
            MCPAXBridgeApplyMessagingTimeout(seedElement);
        }
    }
    if (!seedElement && sMCPAXBridgeRuntime.createSystemWide) {
        seedElement = sMCPAXBridgeRuntime.createSystemWide();
        if (seedElement) {
            MCPAXBridgeApplyMessagingTimeout(seedElement);
        }
    }
    return seedElement;
}

static BOOL MCPAXBridgeLoadRuntime(NSString **error) {
    static dispatch_once_t onceToken;
    static NSString *loadError = nil;
    dispatch_once(&onceToken, ^{
        BOOL (^bindSymbolsFromHandle)(void *, NSString *) = ^BOOL(void *handle, NSString *label) {
            if (!handle) return NO;

            CFTypeRef (*createAXValue)(int, const void *) =
                (CFTypeRef (*)(int, const void *))dlsym(handle, "AXValueCreate");
            AXUIElementCreateApplicationFunc createApplication =
                (AXUIElementCreateApplicationFunc)dlsym(handle, "AXUIElementCreateApplication");
            AXUIElementCreateAppElementWithPidFunc createAppElementWithPid =
                (AXUIElementCreateAppElementWithPidFunc)dlsym(handle, "_AXUIElementCreateAppElementWithPid");
            AXUIElementCreateSystemWideFunc createSystemWide =
                (AXUIElementCreateSystemWideFunc)dlsym(handle, "AXUIElementCreateSystemWide");
            AXUIElementCopyAttributeValueFunc copyAttributeValue =
                (AXUIElementCopyAttributeValueFunc)dlsym(handle, "AXUIElementCopyAttributeValue");
            AXUIElementCopyParameterizedAttributeValueFunc copyParameterizedAttributeValue =
                (AXUIElementCopyParameterizedAttributeValueFunc)dlsym(handle, "AXUIElementCopyParameterizedAttributeValue");
            AXUIElementCopyMultipleAttributeValuesFunc copyMultipleAttributeValues =
                (AXUIElementCopyMultipleAttributeValuesFunc)dlsym(handle, "AXUIElementCopyMultipleAttributeValues");
            AXUIElementCopyAttributeNamesFunc copyAttributeNames =
                (AXUIElementCopyAttributeNamesFunc)dlsym(handle, "AXUIElementCopyAttributeNames");
            AXUIElementCopyElementAtPositionFunc copyElementAtPosition =
                (AXUIElementCopyElementAtPositionFunc)dlsym(handle, "AXUIElementCopyElementAtPosition");
            AXUIElementCopyElementAtPositionWithParamsFunc copyElementAtPositionWithParams =
                (AXUIElementCopyElementAtPositionWithParamsFunc)dlsym(handle, "AXUIElementCopyElementAtPositionWithParams");
            AXUIElementCopyApplicationAtPositionFunc copyApplicationAtPosition =
                (AXUIElementCopyApplicationAtPositionFunc)dlsym(handle, "AXUIElementCopyApplicationAtPosition");
            AXUIElementCopyApplicationAndContextAtPositionFunc copyApplicationAndContextAtPosition =
                (AXUIElementCopyApplicationAndContextAtPositionFunc)dlsym(handle, "AXUIElementCopyApplicationAndContextAtPosition");
            AXUIElementSetMessagingTimeoutFunc setMessagingTimeout =
                (AXUIElementSetMessagingTimeoutFunc)dlsym(handle, "AXUIElementSetMessagingTimeout");
            AXUIElementCopyElementWithParametersFunc copyElementWithParameters =
                (AXUIElementCopyElementWithParametersFunc)dlsym(handle, "AXUIElementCopyElementWithParameters");
            AXUIElementCopyElementUsingContextIdAtPositionFunc copyElementUsingContextIdAtPosition =
                (AXUIElementCopyElementUsingContextIdAtPositionFunc)dlsym(handle, "AXUIElementCopyElementUsingContextIdAtPosition");
            AXUIElementCopyElementUsingDisplayIdAtPositionFunc copyElementUsingDisplayIdAtPosition =
                (AXUIElementCopyElementUsingDisplayIdAtPositionFunc)dlsym(handle, "AXUIElementCopyElementUsingDisplayIdAtPosition");
            AXUIElementGetPidFunc getPid =
                (AXUIElementGetPidFunc)dlsym(handle, "AXUIElementGetPid");
            AXAddAssociatedPidFunc addAssociatedPid =
                (AXAddAssociatedPidFunc)dlsym(handle, "_AXAddAssociatedPid");
            AXIsPidAssociatedFunc isPidAssociated =
                (AXIsPidAssociatedFunc)dlsym(handle, "_AXIsPidAssociated");
            AXIsPidAssociatedWithDisplayTypeFunc isPidAssociatedWithDisplayType =
                (AXIsPidAssociatedWithDisplayTypeFunc)dlsym(handle, "_AXIsPidAssociatedWithDisplayType");
            AXSetRequestingClientFunc setRequestingClient =
                (AXSetRequestingClientFunc)dlsym(handle, "__AXSetRequestingClient");
            AXOverrideRequestingClientTypeFunc overrideRequestingClientType =
                (AXOverrideRequestingClientTypeFunc)dlsym(handle, "_AXOverrideRequestingClientType");
            CFStringRef xcAttributeAutomationType = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeAutomationType");
            CFStringRef xcAttributeChildren = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeChildren");
            CFStringRef xcAttributeChildrenCount = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeChildrenCount");
            CFStringRef xcAttributeElementBaseType = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeElementBaseType");
            CFStringRef xcAttributeElementType = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeElementType");
            CFStringRef xcAttributeFrame = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeFrame");
            CFStringRef xcAttributeHorizontalSizeClass = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeHorizontalSizeClass");
            CFStringRef xcAttributeIdentifier = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeIdentifier");
            CFStringRef xcAttributeIsRemoteElement = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeIsRemoteElement");
            CFStringRef xcAttributeIsUserInteractionEnabled = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeIsUserInteractionEnabled");
            CFStringRef xcAttributeIsVisible = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeIsVisible");
            CFStringRef xcAttributeLabel = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeLabel");
            CFStringRef xcAttributeLocalizedStringKey = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeLocalizedStringKey");
            CFStringRef xcAttributeLocalizationBundleID = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeLocalizationBundleID");
            CFStringRef xcAttributeLocalizationBundlePath = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeLocalizationBundlePath");
            CFStringRef xcAttributeLocalizedStringTableName = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeLocalizedStringTableName");
            CFStringRef xcAttributeMainWindow = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeMainWindow");
            CFStringRef xcAttributeParent = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeParent");
            CFStringRef xcAttributePlaceholderValue = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributePlaceholderValue");
            CFStringRef xcAttributeTraits = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeTraits");
            CFStringRef xcAttributeUserTestingElements = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeUserTestingElements");
            CFStringRef xcAttributeUserTestingSnapshot = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeUserTestingSnapshot");
            CFStringRef xcAttributeValue = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeValue");
            CFStringRef xcAttributeVisibleFrame = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeVisibleFrame");
            CFStringRef xcAttributeViewControllerClassName = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeViewControllerClassName");
            CFStringRef xcAttributeViewControllerTitle = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeViewControllerTitle");
            CFStringRef xcAttributeVerticalSizeClass = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeVerticalSizeClass");
            CFStringRef xcAttributeWindowContextId = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeWindowContextId");
            CFStringRef xcAttributeWindowDisplayId = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCAttributeWindowDisplayId");
            CFStringRef xcParameterizedChildrenWithRange = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCParameterizedAttributeChildrenWithRange");
            CFStringRef xcParameterizedUserTestingSnapshot = MCPAXBridgeCopyCFStringSymbol(handle, "kAXXCParameterizedAttributeUserTestingSnapshotParameterized");

            BOOL usedPrivateCreate = NO;
            if (!createApplication && createAppElementWithPid) {
                createApplication = (AXUIElementCreateApplicationFunc)createAppElementWithPid;
                usedPrivateCreate = YES;
            }

            if (!createApplication || !copyAttributeValue) {
                return NO;
            }

            sMCPAXBridgeRuntime.createAXValue = createAXValue;
            sMCPAXBridgeRuntime.createApplication = createApplication;
            sMCPAXBridgeRuntime.createAppElementWithPid = createAppElementWithPid;
            sMCPAXBridgeRuntime.createSystemWide = createSystemWide;
            sMCPAXBridgeRuntime.copyAttributeValue = copyAttributeValue;
            sMCPAXBridgeRuntime.copyParameterizedAttributeValue = copyParameterizedAttributeValue;
            sMCPAXBridgeRuntime.copyMultipleAttributeValues = copyMultipleAttributeValues;
            sMCPAXBridgeRuntime.copyAttributeNames = copyAttributeNames;
            sMCPAXBridgeRuntime.copyElementAtPosition = copyElementAtPosition;
            sMCPAXBridgeRuntime.copyElementAtPositionWithParams = copyElementAtPositionWithParams;
            sMCPAXBridgeRuntime.copyApplicationAtPosition = copyApplicationAtPosition;
            sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition = copyApplicationAndContextAtPosition;
            sMCPAXBridgeRuntime.setMessagingTimeout = setMessagingTimeout;
            sMCPAXBridgeRuntime.copyElementWithParameters = copyElementWithParameters;
            sMCPAXBridgeRuntime.copyElementUsingContextIdAtPosition = copyElementUsingContextIdAtPosition;
            sMCPAXBridgeRuntime.copyElementUsingDisplayIdAtPosition = copyElementUsingDisplayIdAtPosition;
            sMCPAXBridgeRuntime.getPid = getPid;
            sMCPAXBridgeRuntime.addAssociatedPid = addAssociatedPid;
            sMCPAXBridgeRuntime.isPidAssociated = isPidAssociated;
            sMCPAXBridgeRuntime.isPidAssociatedWithDisplayType = isPidAssociatedWithDisplayType;
            sMCPAXBridgeRuntime.setRequestingClient = setRequestingClient;
            sMCPAXBridgeRuntime.overrideRequestingClientType = overrideRequestingClientType;
            sMCPAXBridgeRuntime.xcAttributeAutomationType = xcAttributeAutomationType;
            sMCPAXBridgeRuntime.xcAttributeChildren = xcAttributeChildren;
            sMCPAXBridgeRuntime.xcAttributeChildrenCount = xcAttributeChildrenCount;
            sMCPAXBridgeRuntime.xcAttributeElementBaseType = xcAttributeElementBaseType;
            sMCPAXBridgeRuntime.xcAttributeElementType = xcAttributeElementType;
            sMCPAXBridgeRuntime.xcAttributeFrame = xcAttributeFrame;
            sMCPAXBridgeRuntime.xcAttributeHorizontalSizeClass = xcAttributeHorizontalSizeClass;
            sMCPAXBridgeRuntime.xcAttributeIdentifier = xcAttributeIdentifier;
            sMCPAXBridgeRuntime.xcAttributeIsRemoteElement = xcAttributeIsRemoteElement;
            sMCPAXBridgeRuntime.xcAttributeIsUserInteractionEnabled = xcAttributeIsUserInteractionEnabled;
            sMCPAXBridgeRuntime.xcAttributeIsVisible = xcAttributeIsVisible;
            sMCPAXBridgeRuntime.xcAttributeLabel = xcAttributeLabel;
            sMCPAXBridgeRuntime.xcAttributeLocalizedStringKey = xcAttributeLocalizedStringKey;
            sMCPAXBridgeRuntime.xcAttributeLocalizationBundleID = xcAttributeLocalizationBundleID;
            sMCPAXBridgeRuntime.xcAttributeLocalizationBundlePath = xcAttributeLocalizationBundlePath;
            sMCPAXBridgeRuntime.xcAttributeLocalizedStringTableName = xcAttributeLocalizedStringTableName;
            sMCPAXBridgeRuntime.xcAttributeMainWindow = xcAttributeMainWindow;
            sMCPAXBridgeRuntime.xcAttributeParent = xcAttributeParent;
            sMCPAXBridgeRuntime.xcAttributePlaceholderValue = xcAttributePlaceholderValue;
            sMCPAXBridgeRuntime.xcAttributeTraits = xcAttributeTraits;
            sMCPAXBridgeRuntime.xcAttributeUserTestingElements = xcAttributeUserTestingElements;
            sMCPAXBridgeRuntime.xcAttributeUserTestingSnapshot = xcAttributeUserTestingSnapshot;
            sMCPAXBridgeRuntime.xcAttributeValue = xcAttributeValue;
            sMCPAXBridgeRuntime.xcAttributeVisibleFrame = xcAttributeVisibleFrame;
            sMCPAXBridgeRuntime.xcAttributeViewControllerClassName = xcAttributeViewControllerClassName;
            sMCPAXBridgeRuntime.xcAttributeViewControllerTitle = xcAttributeViewControllerTitle;
            sMCPAXBridgeRuntime.xcAttributeVerticalSizeClass = xcAttributeVerticalSizeClass;
            sMCPAXBridgeRuntime.xcAttributeWindowContextId = xcAttributeWindowContextId;
            sMCPAXBridgeRuntime.xcAttributeWindowDisplayId = xcAttributeWindowDisplayId;
            sMCPAXBridgeRuntime.xcParameterizedChildrenWithRange = xcParameterizedChildrenWithRange;
            sMCPAXBridgeRuntime.xcParameterizedUserTestingSnapshot = xcParameterizedUserTestingSnapshot;
            sMCPAXBridgeRuntime.handle = handle;
            MCP_AX_BRIDGE_LOG(@"AX runtime bound from %@%@", label ?: @"(unknown)", usedPrivateCreate ? @" using _AXUIElementCreateAppElementWithPid" : @"");
            return YES;
        };

        NSArray<NSString *> *candidatePaths = @[
            @"/System/Library/Frameworks/ApplicationServices.framework/Frameworks/HIServices.framework/HIServices",
            @"/System/Library/PrivateFrameworks/AXRuntime.framework/AXRuntime",
            @"/System/Library/Frameworks/Accessibility.framework/Accessibility",
            @"/System/Library/PrivateFrameworks/Accessibility.framework/Accessibility",
            @"/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices",
            @"/System/Library/Frameworks/HIServices.framework/HIServices",
            @"/usr/lib/libAccessibility.dylib"
        ];

        if (!bindSymbolsFromHandle(RTLD_DEFAULT, @"RTLD_DEFAULT")) {
            uint32_t imageCount = _dyld_image_count();
            for (uint32_t i = 0; i < imageCount; i++) {
                const char *imageName = _dyld_get_image_name(i);
                if (!imageName) continue;

                NSString *name = [NSString stringWithUTF8String:imageName];
                if (name.length == 0) continue;

                NSString *lowercaseName = name.lowercaseString;
                if (![lowercaseName containsString:@"hiservices"] &&
                    ![lowercaseName containsString:@"applicationservices"] &&
                    ![lowercaseName containsString:@"axruntime"] &&
                    ![lowercaseName containsString:@"accessibility"]) {
                    continue;
                }

                void *handle = dlopen(imageName, RTLD_NOW | RTLD_GLOBAL | RTLD_NOLOAD);
                if (!handle) {
                    handle = dlopen(imageName, RTLD_NOW | RTLD_GLOBAL);
                }
                if (bindSymbolsFromHandle(handle, name)) break;
            }
        }

        if (!sMCPAXBridgeRuntime.createApplication || !sMCPAXBridgeRuntime.copyAttributeValue) {
            for (NSString *path in candidatePaths) {
                void *handle = dlopen(path.UTF8String, RTLD_NOW | RTLD_GLOBAL);
                if (!handle) continue;
                if (bindSymbolsFromHandle(handle, path)) break;
            }
        }

        sMCPAXBridgeRuntime.available = (sMCPAXBridgeRuntime.createApplication && sMCPAXBridgeRuntime.copyAttributeValue);
        if (!sMCPAXBridgeRuntime.available) {
            loadError = @"Direct AX runtime unavailable in SpringBoard";
        }
    });

    if (!sMCPAXBridgeRuntime.available && error) {
        *error = loadError ?: @"Direct AX runtime unavailable";
    }
    return sMCPAXBridgeRuntime.available;
}

static void MCPAXBridgeApplyMessagingTimeout(AXUIElementRef element) {
    if (!element || !sMCPAXBridgeRuntime.setMessagingTimeout) return;
    sMCPAXBridgeRuntime.setMessagingTimeout(element, 0.25f);
}

static NSDictionary *MCPAXBridgePointDictionary(CGPoint point) {
    return @{
        @"x": @((NSInteger)lrint(point.x)),
        @"y": @((NSInteger)lrint(point.y))
    };
}

static NSArray<NSValue *> *MCPAXBridgeScreenProbePoints(void) {
    CGRect bounds = UIScreen.mainScreen.bounds;
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

static BOOL MCPAXBridgeCopyContextIdForPoint(CGPoint point,
                                             uint32_t displayId,
                                             uint32_t *contextIdOut,
                                             NSString **error) {
    if (!sMCPAXBridgeRuntime.copyParameterizedAttributeValue) {
        if (error) *error = @"point->context parameterized query unavailable";
        return NO;
    }

    MCPAXBridgeSetRequestingClientForAutomation();

    AXUIElementRef seedElement = MCPAXBridgeCreateContextProbeSeed();
    if (!seedElement) {
        if (error) *error = @"Failed to create AX seed element for point->context";
        return NO;
    }

    CFTypeRef pointValue = NULL;
    if (sMCPAXBridgeRuntime.createAXValue) {
        pointValue = sMCPAXBridgeRuntime.createAXValue(kMCPAXBridgeValueTypeCGPoint, &point);
    }
    if (!pointValue) {
        pointValue = CFRetain((__bridge CFTypeRef)[NSValue valueWithCGPoint:point]);
    }
    if (!pointValue) {
        CFRelease(seedElement);
        if (error) *error = @"AXValueCreate(CGPoint) failed";
        return NO;
    }

    NSArray *parameter = @[(__bridge id)pointValue, @(displayId)];
    CFRelease(pointValue);

    CFTypeRef result = NULL;
    AXError axError = sMCPAXBridgeRuntime.copyParameterizedAttributeValue(seedElement,
                                                                          kMCPAXBridgePointAndDisplayParameterizedAttribute,
                                                                          (__bridge CFTypeRef)parameter,
                                                                          &result);
    CFRelease(seedElement);

    if (axError != kAXErrorSuccess || !result) {
        if (error) {
            *error = [NSString stringWithFormat:@"point->context display=%u failed: %@",
                      displayId,
                      [[MCPAXAttributeBridge new] errorStringForAXError:axError]];
        }
        if (result) CFRelease(result);
        return NO;
    }

    id bridged = CFBridgingRelease(result);
    if (![bridged respondsToSelector:@selector(unsignedIntValue)]) {
        if (error) *error = [NSString stringWithFormat:@"point->context display=%u returned non-number", displayId];
        return NO;
    }

    uint32_t contextId = (uint32_t)[bridged unsignedIntValue];
    if (contextId == 0) {
        if (error) *error = [NSString stringWithFormat:@"point->context display=%u returned contextId=0", displayId];
        return NO;
    }

    if (contextIdOut) *contextIdOut = contextId;
    return YES;
}

static BOOL MCPAXBridgeCopyPidForContextId(uint32_t contextId,
                                           pid_t *pidOut,
                                           NSString **error) {
    if (!sMCPAXBridgeRuntime.copyParameterizedAttributeValue ||
        !sMCPAXBridgeRuntime.createSystemWide) {
        if (error) *error = @"context->pid parameterized query unavailable";
        return NO;
    }

    MCPAXBridgeSetRequestingClientForAutomation();

    AXUIElementRef systemWide = sMCPAXBridgeRuntime.createSystemWide();
    if (!systemWide) {
        if (error) *error = @"Failed to create system-wide AX element";
        return NO;
    }
    MCPAXBridgeApplyMessagingTimeout(systemWide);

    NSDictionary *parameter = @{@"contextId": @(contextId)};
    CFTypeRef result = NULL;
    AXError axError = sMCPAXBridgeRuntime.copyParameterizedAttributeValue(systemWide,
                                                                          kMCPAXBridgePidForContextParameterizedAttribute,
                                                                          (__bridge CFTypeRef)parameter,
                                                                          &result);
    CFRelease(systemWide);

    if (axError != kAXErrorSuccess || !result) {
        if (error) {
            *error = [NSString stringWithFormat:@"context->pid context=%u failed: %@",
                      contextId,
                      [[MCPAXAttributeBridge new] errorStringForAXError:axError]];
        }
        if (result) CFRelease(result);
        return NO;
    }

    id bridged = CFBridgingRelease(result);
    if (![bridged respondsToSelector:@selector(intValue)]) {
        if (error) *error = [NSString stringWithFormat:@"context->pid context=%u returned non-number", contextId];
        return NO;
    }

    pid_t resolvedPid = (pid_t)[bridged intValue];
    if (resolvedPid <= 0) {
        if (error) *error = [NSString stringWithFormat:@"context->pid context=%u returned pid=%d", contextId, resolvedPid];
        return NO;
    }

    if (pidOut) *pidOut = resolvedPid;
    return YES;
}

static AXUIElementRef MCPAXBridgeCopyElementWithParametersAtPoint(CGPoint point,
                                                                  pid_t expectedPid,
                                                                  NSString **error) {
    if (!sMCPAXBridgeRuntime.copyElementWithParameters) {
        if (error) *error = @"AXUIElementCopyElementWithParameters unavailable";
        return NULL;
    }

    MCPAXBridgeSetRequestingClientForAutomation();

    NSMutableArray<NSDictionary *> *seedElements = [NSMutableArray array];

    if (sMCPAXBridgeRuntime.createSystemWide) {
        AXUIElementRef systemWide = sMCPAXBridgeRuntime.createSystemWide();
        if (systemWide) {
            MCPAXBridgeApplyMessagingTimeout(systemWide);
            [seedElements addObject:@{
                @"name": @"system_wide",
                @"element": (__bridge id)systemWide
            }];
            CFRelease(systemWide);
        }
    }

    if (sMCPAXBridgeRuntime.createApplication) {
        AXUIElementRef springBoardApp = sMCPAXBridgeRuntime.createApplication(getpid());
        if (springBoardApp) {
            MCPAXBridgeApplyMessagingTimeout(springBoardApp);
            [seedElements addObject:@{
                @"name": @"springboard_app",
                @"element": (__bridge id)springBoardApp
            }];
            CFRelease(springBoardApp);
        }

        if (expectedPid > 0) {
            AXUIElementRef targetApp = sMCPAXBridgeRuntime.createApplication(expectedPid);
            if (targetApp) {
                MCPAXBridgeApplyMessagingTimeout(targetApp);
                [seedElements addObject:@{
                    @"name": @"target_app",
                    @"element": (__bridge id)targetApp
                }];
                CFRelease(targetApp);
            }
        }
    }

    if (seedElements.count == 0) {
        if (error) *error = @"No AX seed available for parameterized hit-test";
        return NULL;
    }

    NSValue *pointValue = [NSValue valueWithCGPoint:point];
    NSArray<NSNumber *> *hitTestTypes = @[@0, @2];
    NSArray<NSNumber *> *displayIds = @[@1, @0];
    NSMutableArray<NSString *> *errors = [NSMutableArray array];

    for (NSDictionary *seed in seedElements) {
        NSString *seedName = seed[@"name"] ?: @"unknown";
        AXUIElementRef seedElement = (__bridge AXUIElementRef)seed[@"element"];
        AXUIElementRef appElementForParams = NULL;
        uint32_t contextId = 0;

        for (NSNumber *displayId in displayIds) {
            if (appElementForParams) {
                CFRelease(appElementForParams);
                appElementForParams = NULL;
            }
            contextId = 0;

            if (sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition) {
                AXError axError = sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition(seedElement,
                                                                                          &appElementForParams,
                                                                                          &contextId,
                                                                                          point.x,
                                                                                          point.y);
                if (axError != kAXErrorSuccess || !appElementForParams) {
                    [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyApplicationAndContextAtPosition via %@ failed: %@",
                                       seedName,
                                       [[MCPAXAttributeBridge new] errorStringForAXError:axError]]];
                    continue;
                }
            } else if (sMCPAXBridgeRuntime.copyApplicationAtPosition) {
                AXError axError = sMCPAXBridgeRuntime.copyApplicationAtPosition(seedElement,
                                                                                &appElementForParams,
                                                                                point.x,
                                                                                point.y);
                if (axError != kAXErrorSuccess || !appElementForParams) {
                    [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyApplicationAtPosition via %@ failed: %@",
                                       seedName,
                                       [[MCPAXAttributeBridge new] errorStringForAXError:axError]]];
                    continue;
                }
            } else {
                appElementForParams = (AXUIElementRef)CFRetain(seedElement);
            }

            MCPAXBridgeApplyMessagingTimeout(appElementForParams);

            if (expectedPid > 0 && sMCPAXBridgeRuntime.getPid) {
                pid_t resolvedPid = 0;
                AXError pidError = sMCPAXBridgeRuntime.getPid(appElementForParams, &resolvedPid);
                if (pidError == kAXErrorSuccess && resolvedPid > 0 && resolvedPid != expectedPid) {
                    [errors addObject:[NSString stringWithFormat:@"Parameterized app seed via %@ display=%u resolved pid %d instead of %d",
                                       seedName,
                                       displayId.unsignedIntValue,
                                       resolvedPid,
                                       expectedPid]];
                    continue;
                }
            }

            for (NSNumber *hitTestType in hitTestTypes) {
                NSMutableDictionary *params = [NSMutableDictionary dictionary];
                params[@"application"] = (__bridge id)appElementForParams;
                params[@"point"] = pointValue;
                if (displayId.unsignedIntValue > 0) params[@"displayId"] = displayId;
                if (contextId > 0) params[@"contextId"] = @(contextId);
                if (hitTestType.unsignedIntValue > 0) params[@"hitTestType"] = hitTestType;

                AXUIElementRef hitElement = NULL;
                AXError axError = sMCPAXBridgeRuntime.copyElementWithParameters(&hitElement,
                                                                                (__bridge CFDictionaryRef)params);
                if (axError != kAXErrorSuccess || !hitElement) {
                    [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyElementWithParameters via %@ display=%u ctx=%u hitType=%u failed: %@",
                                       seedName,
                                       displayId.unsignedIntValue,
                                       contextId,
                                       hitTestType.unsignedIntValue,
                                       [[MCPAXAttributeBridge new] errorStringForAXError:axError]]];
                    continue;
                }

                MCPAXBridgeApplyMessagingTimeout(hitElement);

                if (expectedPid > 0 && sMCPAXBridgeRuntime.getPid) {
                    pid_t resolvedPid = 0;
                    AXError pidError = sMCPAXBridgeRuntime.getPid(hitElement, &resolvedPid);
                    if (pidError == kAXErrorSuccess && resolvedPid > 0 && resolvedPid != expectedPid) {
                        [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyElementWithParameters via %@ display=%u ctx=%u hitType=%u resolved pid %d instead of %d",
                                           seedName,
                                           displayId.unsignedIntValue,
                                           contextId,
                                           hitTestType.unsignedIntValue,
                                           resolvedPid,
                                           expectedPid]];
                        CFRelease(hitElement);
                        continue;
                    }
                }

                MCP_AX_BRIDGE_LOG(@"Parameterized hit-test succeeded via %@ display=%u ctx=%u hitType=%u",
                                  seedName,
                                  displayId.unsignedIntValue,
                                  contextId,
                                  hitTestType.unsignedIntValue);
                if (appElementForParams) {
                    CFRelease(appElementForParams);
                    appElementForParams = NULL;
                }
                return hitElement;
            }
        }

        if (appElementForParams) {
            CFRelease(appElementForParams);
        }
    }

    if (error) {
        *error = errors.count > 0 ? [errors componentsJoinedByString:@"; "] : @"Parameterized AX hit-test returned no element";
    }
    return NULL;
}

static NSArray *MCPAXBridgeNormalizedSnapshotAttributes(id rawAttributes) {
    if (![rawAttributes isKindOfClass:[NSArray class]]) return nil;

    NSMutableArray *normalized = [NSMutableArray array];
    for (id candidate in (NSArray *)rawAttributes) {
        if (!candidate || candidate == NSNull.null) continue;

        CFStringRef attribute = NULL;
        if ([candidate isKindOfClass:[NSString class]]) {
            attribute = MCPAXBridgeXCAttributeRefForKey(candidate);
            if (!attribute) {
                attribute = (__bridge CFStringRef)candidate;
            }
        } else if (CFGetTypeID((__bridge CFTypeRef)candidate) == CFStringGetTypeID()) {
            attribute = (__bridge CFStringRef)candidate;
        }

        if (!attribute) continue;
        [normalized addObject:(__bridge NSString *)attribute];
    }

    return normalized.count > 0 ? normalized : nil;
}

static NSDictionary *MCPAXBridgeNormalizedUserTestingSnapshotOptions(NSDictionary *options) {
    if (![options isKindOfClass:[NSDictionary class]] || options.count == 0) return @{};

    NSMutableDictionary *normalized = [options mutableCopy];
    NSArray *normalizedAttributes = MCPAXBridgeNormalizedSnapshotAttributes(options[@"attributes"]);
    if (normalizedAttributes.count > 0) {
        normalized[@"attributes"] = normalizedAttributes;
    } else {
        [normalized removeObjectForKey:@"attributes"];
    }
    return normalized;
}

static NSString *MCPAXBridgeSnapshotValueClassName(id value) {
    if (!value || value == NSNull.null) return nil;
    return NSStringFromClass([value class]);
}

static NSDictionary *MCPAXBridgeSnapshotValueSummary(id value) {
    if (!value || value == NSNull.null) return @{};

    NSMutableDictionary *summary = [NSMutableDictionary dictionary];
    summary[@"class"] = MCPAXBridgeSnapshotValueClassName(value) ?: @"<unknown>";
    if ([value isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = value;
        summary[@"count"] = @(dict.count);
        NSArray *keys = dict.allKeys;
        if (keys.count > 0) {
            summary[@"keys"] = [keys subarrayWithRange:NSMakeRange(0, MIN((NSUInteger)8, keys.count))];
        }
    } else if ([value isKindOfClass:[NSArray class]]) {
        summary[@"count"] = @([(NSArray *)value count]);
    } else if ([value isKindOfClass:[NSString class]]) {
        summary[@"length"] = @([(NSString *)value length]);
    }
    return summary;
}

@implementation MCPAXAttributeBridge

- (BOOL)ensureRuntimeAvailable:(NSString * _Nullable * _Nullable)error {
    return MCPAXBridgeLoadRuntime(error);
}

- (void)performOnMainThreadSync:(dispatch_block_t)block {
    if (!block) return;
    if ([NSThread isMainThread]) {
        block();
        return;
    }
    dispatch_sync(dispatch_get_main_queue(), block);
}

- (void)ensureAssociationWithRemotePid:(pid_t)remotePid {
    if (!sMCPAXBridgeRuntime.addAssociatedPid ||
        !sMCPAXBridgeRuntime.isPidAssociated ||
        remotePid <= 0) {
        return;
    }

    pid_t localPid = getpid();
    BOOL remoteAssociated = sMCPAXBridgeRuntime.isPidAssociated(remotePid);
    BOOL localAssociated = sMCPAXBridgeRuntime.isPidAssociated(localPid);

    BOOL remoteDisplay1Associated = sMCPAXBridgeRuntime.isPidAssociatedWithDisplayType ?
        sMCPAXBridgeRuntime.isPidAssociatedWithDisplayType(remotePid, 1) : remoteAssociated;
    BOOL localDisplay1Associated = sMCPAXBridgeRuntime.isPidAssociatedWithDisplayType ?
        sMCPAXBridgeRuntime.isPidAssociatedWithDisplayType(localPid, 1) : localAssociated;

    if (!remoteDisplay1Associated) {
        sMCPAXBridgeRuntime.addAssociatedPid(localPid, remotePid, 1);
    }
    if (!localDisplay1Associated) {
        sMCPAXBridgeRuntime.addAssociatedPid(remotePid, localPid, 1);
    }
    if (!remoteAssociated) {
        sMCPAXBridgeRuntime.addAssociatedPid(localPid, remotePid, 0);
    }
    if (!localAssociated) {
        sMCPAXBridgeRuntime.addAssociatedPid(remotePid, localPid, 0);
    }
}

- (AXUIElementRef _Nullable)copyApplicationElementForPid:(pid_t)pid
                                                   error:(NSString * _Nullable * _Nullable)error {
    if (![self ensureRuntimeAvailable:error]) return NULL;
    if (!sMCPAXBridgeRuntime.createApplication || pid <= 0) {
        if (error) *error = @"AX create_application unavailable";
        return NULL;
    }

    AXUIElementRef appElement = sMCPAXBridgeRuntime.createApplication(pid);
    if (!appElement) {
        if (error) *error = [NSString stringWithFormat:@"AX create_application failed for PID %d", pid];
        return NULL;
    }
    MCPAXBridgeApplyMessagingTimeout(appElement);
    return appElement;
}

- (AXUIElementRef _Nullable)copyContextBoundApplicationElementForPid:(pid_t)expectedPid
                                                          diagnostics:(NSDictionary * _Nullable * _Nullable)diagnostics
                                                                error:(NSString * _Nullable * _Nullable)error {
    NSString *runtimeError = nil;
    if (![self ensureRuntimeAvailable:&runtimeError]) {
        if (error) *error = runtimeError;
        return NULL;
    }

    if (!sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition &&
        !sMCPAXBridgeRuntime.copyApplicationAtPosition) {
        if (error) *error = @"Context-bound application probe unavailable";
        return NULL;
    }

    NSMutableArray<NSDictionary *> *seedElements = [NSMutableArray array];
    AXUIElementRef pidZeroSeed = MCPAXBridgeCreateContextProbeSeed();
    if (pidZeroSeed) {
        [seedElements addObject:@{
            @"name": @"pid0_seed",
            @"element": (__bridge id)pidZeroSeed
        }];
        CFRelease(pidZeroSeed);
    }

    AXUIElementRef systemWide = [self copySystemWideElement];
    if (systemWide) {
        [seedElements addObject:@{
            @"name": @"system_wide",
            @"element": (__bridge id)systemWide
        }];
        CFRelease(systemWide);
    }

    AXUIElementRef springBoardApp = [self copyApplicationElementForPid:getpid() error:nil];
    if (springBoardApp) {
        [seedElements addObject:@{
            @"name": @"springboard_app",
            @"element": (__bridge id)springBoardApp
        }];
        CFRelease(springBoardApp);
    }

    if (expectedPid > 0) {
        AXUIElementRef targetApp = [self copyApplicationElementForPid:expectedPid error:nil];
        if (targetApp) {
            [seedElements addObject:@{
                @"name": @"target_app",
                @"element": (__bridge id)targetApp
            }];
            CFRelease(targetApp);
        }
    }

    if (seedElements.count == 0) {
        if (error) *error = @"No AX seed available for context-bound application probe";
        return NULL;
    }

    NSArray<NSValue *> *points = MCPAXBridgeScreenProbePoints();
    if (points.count == 0) {
        if (error) *error = @"No probe points available for context-bound application probe";
        return NULL;
    }

    NSMutableArray<NSDictionary *> *attempts = [NSMutableArray array];
    NSMutableArray<NSString *> *errors = [NSMutableArray array];

    for (NSDictionary *seed in seedElements) {
        NSString *seedName = seed[@"name"] ?: @"unknown";
        AXUIElementRef seedElement = (__bridge AXUIElementRef)seed[@"element"];

        for (NSValue *pointValue in points) {
            CGPoint point = pointValue.CGPointValue;
            AXUIElementRef appElement = NULL;
            uint32_t contextId = 0;
            AXError axError = kAXErrorSuccess;

            if (sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition) {
                axError = sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition(seedElement,
                                                                                  &appElement,
                                                                                  &contextId,
                                                                                  point.x,
                                                                                  point.y);
            } else {
                axError = sMCPAXBridgeRuntime.copyApplicationAtPosition(seedElement,
                                                                        &appElement,
                                                                        point.x,
                                                                        point.y);
            }

            NSMutableDictionary *attempt = [NSMutableDictionary dictionary];
            attempt[@"seed"] = seedName;
            attempt[@"point"] = MCPAXBridgePointDictionary(point);
            attempt[@"api"] = sMCPAXBridgeRuntime.copyApplicationAndContextAtPosition ?
                @"AXUIElementCopyApplicationAndContextAtPosition" :
                @"AXUIElementCopyApplicationAtPosition";
            attempt[@"axError"] = [self errorStringForAXError:axError];
            if (contextId > 0) {
                attempt[@"contextId"] = @(contextId);
            }

            if (axError != kAXErrorSuccess || !appElement) {
                [attempts addObject:attempt];
                [errors addObject:[NSString stringWithFormat:@"%@@(%.0f,%.0f)=%@",
                                   seedName,
                                   point.x,
                                   point.y,
                                   [self errorStringForAXError:axError]]];
                continue;
            }

            MCPAXBridgeApplyMessagingTimeout(appElement);

            pid_t resolvedPid = 0;
            BOOL hasResolvedPid = [self getPid:&resolvedPid fromElement:appElement];
            if (hasResolvedPid && resolvedPid > 0) {
                attempt[@"resolvedPid"] = @(resolvedPid);
            }

            if (expectedPid > 0 && hasResolvedPid && resolvedPid > 0 && resolvedPid != expectedPid) {
                [attempts addObject:attempt];
                [errors addObject:[NSString stringWithFormat:@"%@@(%.0f,%.0f)=pid:%d",
                                   seedName,
                                   point.x,
                                   point.y,
                                   resolvedPid]];
                CFRelease(appElement);
                continue;
            }

            attempt[@"matchedExpectedPid"] = @(expectedPid <= 0 || !hasResolvedPid || resolvedPid == expectedPid);
            [attempts addObject:attempt];

            if (diagnostics) {
                *diagnostics = @{
                    @"strategy": @"context_bound_application_probe",
                    @"api": attempt[@"api"],
                    @"seed": seedName,
                    @"point": MCPAXBridgePointDictionary(point),
                    @"contextId": contextId > 0 ? @(contextId) : @(0),
                    @"resolvedPid": hasResolvedPid && resolvedPid > 0 ? @(resolvedPid) : @(0),
                    @"attempts": attempts
                };
            }
            MCP_AX_BRIDGE_LOG(@"Context-bound application probe succeeded via %@ point=(%.1f,%.1f) ctx=%u pid=%d",
                              seedName,
                              point.x,
                              point.y,
                              contextId,
                              hasResolvedPid ? resolvedPid : 0);
            return appElement;
        }
    }

    if (diagnostics) {
        *diagnostics = @{
            @"strategy": @"context_bound_application_probe",
            @"attempts": attempts
        };
    }
    if (error) {
        *error = errors.count > 0 ?
            [errors componentsJoinedByString:@"; "] :
            @"Context-bound application probe returned no matching app element";
    }
    return NULL;
}

- (AXUIElementRef _Nullable)copyContextChainHitElementAtPoint:(CGPoint)point
                                                  expectedPid:(pid_t)expectedPid
                                                  diagnostics:(NSDictionary * _Nullable * _Nullable)diagnostics
                                                        error:(NSString * _Nullable * _Nullable)error {
    NSString *runtimeError = nil;
    if (![self ensureRuntimeAvailable:&runtimeError]) {
        if (error) *error = runtimeError;
        return NULL;
    }

    if (!sMCPAXBridgeRuntime.copyElementUsingContextIdAtPosition ||
        !sMCPAXBridgeRuntime.copyParameterizedAttributeValue ||
        (!sMCPAXBridgeRuntime.createApplication && !sMCPAXBridgeRuntime.createAppElementWithPid)) {
        if (error) *error = @"AX context-chain hit-test APIs unavailable";
        return NULL;
    }

    NSArray<NSNumber *> *displayIds = @[@1, @0];
    NSArray<NSNumber *> *options = @[@0, @1, @2];
    NSMutableArray<NSDictionary *> *attempts = [NSMutableArray array];
    NSMutableArray<NSString *> *errors = [NSMutableArray array];
    NSMutableOrderedSet<NSNumber *> *triedContextIds = [NSMutableOrderedSet orderedSet];

    for (NSNumber *displayId in displayIds) {
        uint32_t contextId = 0;
        NSString *contextError = nil;
        if (!MCPAXBridgeCopyContextIdForPoint(point, displayId.unsignedIntValue, &contextId, &contextError)) {
            NSDictionary *attempt = @{
                @"displayId": displayId,
                @"point": MCPAXBridgePointDictionary(point),
                @"stage": @"point_to_context",
                @"error": contextError ?: @"unknown"
            };
            [attempts addObject:attempt];
            if (contextError.length > 0) {
                [errors addObject:contextError];
            }
            continue;
        }
        if (contextId > 0) [triedContextIds addObject:@(contextId)];

        pid_t resolvedPid = 0;
        NSString *pidError = nil;
        if (!MCPAXBridgeCopyPidForContextId(contextId, &resolvedPid, &pidError)) {
            NSDictionary *attempt = @{
                @"displayId": displayId,
                @"point": MCPAXBridgePointDictionary(point),
                @"stage": @"context_to_pid",
                @"contextId": @(contextId),
                @"error": pidError ?: @"unknown"
            };
            [attempts addObject:attempt];
            if (pidError.length > 0) {
                [errors addObject:pidError];
            }
            continue;
        }

        if (expectedPid > 0 && resolvedPid != expectedPid) {
            NSDictionary *attempt = @{
                @"displayId": displayId,
                @"point": MCPAXBridgePointDictionary(point),
                @"stage": @"context_to_pid",
                @"contextId": @(contextId),
                @"resolvedPid": @(resolvedPid),
                @"expectedPid": @(expectedPid),
                @"error": @"pid_mismatch"
            };
            [attempts addObject:attempt];
            [errors addObject:[NSString stringWithFormat:@"context->pid display=%u ctx=%u resolved pid %d instead of %d",
                               displayId.unsignedIntValue,
                               contextId,
                               resolvedPid,
                               expectedPid]];
            continue;
        }

        AXUIElementRef appElement = sMCPAXBridgeRuntime.createApplication ?
            sMCPAXBridgeRuntime.createApplication(resolvedPid) :
            sMCPAXBridgeRuntime.createAppElementWithPid(resolvedPid);
        if (!appElement) {
            NSDictionary *attempt = @{
                @"displayId": displayId,
                @"point": MCPAXBridgePointDictionary(point),
                @"stage": @"create_application",
                @"contextId": @(contextId),
                @"resolvedPid": @(resolvedPid),
                @"error": @"create_application_failed"
            };
            [attempts addObject:attempt];
            [errors addObject:[NSString stringWithFormat:@"context->application display=%u ctx=%u failed for pid=%d",
                               displayId.unsignedIntValue,
                               contextId,
                               resolvedPid]];
            continue;
        }
        MCPAXBridgeApplyMessagingTimeout(appElement);

        for (NSNumber *option in options) {
            AXUIElementRef hitElement = NULL;
            AXError axError = sMCPAXBridgeRuntime.copyElementUsingContextIdAtPosition(appElement,
                                                                                      contextId,
                                                                                      &hitElement,
                                                                                      option.intValue,
                                                                                      point.x,
                                                                                      point.y);
            NSMutableDictionary *attempt = [@{
                @"displayId": displayId,
                @"point": MCPAXBridgePointDictionary(point),
                @"stage": @"copyElementUsingContextIdAtPosition",
                @"contextId": @(contextId),
                @"resolvedPid": @(resolvedPid),
                @"option": option,
                @"axError": [self errorStringForAXError:axError]
            } mutableCopy];
            if (axError != kAXErrorSuccess || !hitElement) {
                [attempts addObject:attempt];
                [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyElementUsingContextIdAtPosition display=%u ctx=%u option=%d failed: %@",
                                   displayId.unsignedIntValue,
                                   contextId,
                                   option.intValue,
                                   [self errorStringForAXError:axError]]];
                continue;
            }

            MCPAXBridgeApplyMessagingTimeout(hitElement);

            pid_t hitPid = 0;
            BOOL hasHitPid = [self getPid:&hitPid fromElement:hitElement];
            if (hasHitPid && hitPid > 0) {
                attempt[@"hitPid"] = @(hitPid);
            }
            if (expectedPid > 0 && hasHitPid && hitPid > 0 && hitPid != expectedPid) {
                [attempts addObject:attempt];
                [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyElementUsingContextIdAtPosition display=%u ctx=%u option=%d resolved pid %d instead of %d",
                                   displayId.unsignedIntValue,
                                   contextId,
                                   option.intValue,
                                   hitPid,
                                   expectedPid]];
                CFRelease(hitElement);
                continue;
            }

            [attempts addObject:attempt];
            CFRelease(appElement);
            if (diagnostics) {
                *diagnostics = @{
                    @"strategy": @"context_chain_numeric_param_probe",
                    @"point": MCPAXBridgePointDictionary(point),
                    @"displayId": displayId,
                    @"contextId": @(contextId),
                    @"resolvedPid": @(resolvedPid),
                    @"option": option,
                    @"attempts": attempts
                };
            }
            MCP_AX_BRIDGE_LOG(@"Context-chain hit-test succeeded point=(%.1f,%.1f) display=%u ctx=%u option=%d pid=%d",
                              point.x,
                              point.y,
                              displayId.unsignedIntValue,
                              contextId,
                              option.intValue,
                              hasHitPid ? hitPid : resolvedPid);
            return hitElement;
        }

        CFRelease(appElement);
    }

    NSArray<NSDictionary *> *workspaceCandidates = MCPAXBridgeWorkspaceContextCandidates();
    for (NSDictionary *candidate in workspaceCandidates) {
        NSNumber *contextIdValue = [candidate[@"contextId"] isKindOfClass:[NSNumber class]] ? candidate[@"contextId"] : nil;
        uint32_t contextId = contextIdValue.unsignedIntValue;
        if (contextId == 0 || [triedContextIds containsObject:contextIdValue]) continue;
        [triedContextIds addObject:contextIdValue];

        AXUIElementRef appElement = sMCPAXBridgeRuntime.createApplication ?
            sMCPAXBridgeRuntime.createApplication(expectedPid) :
            sMCPAXBridgeRuntime.createAppElementWithPid(expectedPid);
        if (!appElement) {
            [attempts addObject:@{
                @"stage": @"workspace_context_probe",
                @"contextId": contextIdValue,
                @"sceneIdentifier": candidate[@"sceneIdentifier"] ?: @"",
                @"error": @"create_application_failed"
            }];
            continue;
        }
        MCPAXBridgeApplyMessagingTimeout(appElement);

        for (NSNumber *option in options) {
            AXUIElementRef hitElement = NULL;
            AXError axError = sMCPAXBridgeRuntime.copyElementUsingContextIdAtPosition(appElement,
                                                                                      contextId,
                                                                                      &hitElement,
                                                                                      option.intValue,
                                                                                      point.x,
                                                                                      point.y);
            NSMutableDictionary *attempt = [@{
                @"stage": @"workspace_context_probe",
                @"point": MCPAXBridgePointDictionary(point),
                @"contextId": contextIdValue,
                @"resolvedPid": @(expectedPid),
                @"option": option,
                @"sceneIdentifier": candidate[@"sceneIdentifier"] ?: @"",
                @"accessibilityLike": candidate[@"accessibilityLike"] ?: @NO,
                @"axError": [self errorStringForAXError:axError]
            } mutableCopy];

            if (axError != kAXErrorSuccess || !hitElement) {
                [attempts addObject:attempt];
                [errors addObject:[NSString stringWithFormat:@"workspace ctx=%u option=%d failed: %@",
                                   contextId,
                                   option.intValue,
                                   [self errorStringForAXError:axError]]];
                continue;
            }

            MCPAXBridgeApplyMessagingTimeout(hitElement);

            pid_t hitPid = 0;
            BOOL hasHitPid = [self getPid:&hitPid fromElement:hitElement];
            if (hasHitPid && hitPid > 0) {
                attempt[@"hitPid"] = @(hitPid);
            }
            if (expectedPid > 0 && hasHitPid && hitPid > 0 && hitPid != expectedPid) {
                [attempts addObject:attempt];
                [errors addObject:[NSString stringWithFormat:@"workspace ctx=%u option=%d resolved pid %d instead of %d",
                                   contextId,
                                   option.intValue,
                                   hitPid,
                                   expectedPid]];
                CFRelease(hitElement);
                continue;
            }

            [attempts addObject:attempt];
            CFRelease(appElement);
            if (diagnostics) {
                *diagnostics = @{
                    @"strategy": @"context_chain_numeric_param_probe",
                    @"point": MCPAXBridgePointDictionary(point),
                    @"contextId": contextIdValue,
                    @"resolvedPid": @(expectedPid),
                    @"option": option,
                    @"candidateSource": @"workspace_scene_contexts",
                    @"sceneIdentifier": candidate[@"sceneIdentifier"] ?: @"",
                    @"accessibilityLike": candidate[@"accessibilityLike"] ?: @NO,
                    @"attempts": attempts
                };
            }
            MCP_AX_BRIDGE_LOG(@"Workspace-context hit-test succeeded point=(%.1f,%.1f) ctx=%u option=%d pid=%d scene=%@",
                              point.x,
                              point.y,
                              contextId,
                              option.intValue,
                              hasHitPid ? hitPid : expectedPid,
                              candidate[@"sceneIdentifier"] ?: @"");
            return hitElement;
        }

        CFRelease(appElement);
    }

    if (diagnostics) {
        *diagnostics = @{
            @"strategy": @"context_chain_numeric_param_probe",
            @"point": MCPAXBridgePointDictionary(point),
            @"attempts": attempts
        };
    }
    if (error) {
        *error = errors.count > 0 ?
            [errors componentsJoinedByString:@"; "] :
            @"AX context-chain hit-test returned no element";
    }
    return NULL;
}

- (AXUIElementRef _Nullable)copyElementAtPoint:(CGPoint)point
                              usingKnownContextId:(uint32_t)contextId
                                      expectedPid:(pid_t)expectedPid
                                      diagnostics:(NSDictionary * _Nullable * _Nullable)diagnostics
                                            error:(NSString * _Nullable * _Nullable)error {
    NSString *runtimeError = nil;
    if (![self ensureRuntimeAvailable:&runtimeError]) {
        if (error) *error = runtimeError;
        return NULL;
    }

    if (contextId == 0) {
        if (error) *error = @"Known contextId hit-test requires a non-zero contextId";
        return NULL;
    }

    if (!sMCPAXBridgeRuntime.copyElementUsingContextIdAtPosition ||
        (!sMCPAXBridgeRuntime.createApplication && !sMCPAXBridgeRuntime.createAppElementWithPid)) {
        if (error) *error = @"AX known-context hit-test APIs unavailable";
        return NULL;
    }

    if (expectedPid <= 0) {
        if (error) *error = @"Known contextId hit-test requires expectedPid";
        return NULL;
    }

    AXUIElementRef appElement = sMCPAXBridgeRuntime.createApplication ?
        sMCPAXBridgeRuntime.createApplication(expectedPid) :
        sMCPAXBridgeRuntime.createAppElementWithPid(expectedPid);
    if (!appElement) {
        if (error) *error = [NSString stringWithFormat:@"Failed to create application element for pid=%d ctx=%u",
                             expectedPid,
                             contextId];
        return NULL;
    }
    MCPAXBridgeApplyMessagingTimeout(appElement);

    NSArray<NSNumber *> *options = @[@0, @1, @2];
    NSMutableArray<NSDictionary *> *attempts = [NSMutableArray array];
    NSMutableArray<NSString *> *errors = [NSMutableArray array];

    for (NSNumber *option in options) {
        AXUIElementRef hitElement = NULL;
        AXError axError = sMCPAXBridgeRuntime.copyElementUsingContextIdAtPosition(appElement,
                                                                                  contextId,
                                                                                  &hitElement,
                                                                                  option.intValue,
                                                                                  point.x,
                                                                                  point.y);
        NSMutableDictionary *attempt = [@{
            @"point": MCPAXBridgePointDictionary(point),
            @"contextId": @(contextId),
            @"expectedPid": @(expectedPid),
            @"option": option,
            @"axError": [self errorStringForAXError:axError]
        } mutableCopy];

        if (axError != kAXErrorSuccess || !hitElement) {
            [attempts addObject:attempt];
            [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyElementUsingContextIdAtPosition ctx=%u option=%d failed: %@",
                               contextId,
                               option.intValue,
                               [self errorStringForAXError:axError]]];
            continue;
        }

        MCPAXBridgeApplyMessagingTimeout(hitElement);

        pid_t hitPid = 0;
        BOOL hasHitPid = [self getPid:&hitPid fromElement:hitElement];
        if (hasHitPid && hitPid > 0) {
            attempt[@"hitPid"] = @(hitPid);
        }
        if (hasHitPid && hitPid > 0 && hitPid != expectedPid) {
            [attempts addObject:attempt];
            [errors addObject:[NSString stringWithFormat:@"AXUIElementCopyElementUsingContextIdAtPosition ctx=%u option=%d resolved pid %d instead of %d",
                               contextId,
                               option.intValue,
                               hitPid,
                               expectedPid]];
            CFRelease(hitElement);
            continue;
        }

        [attempts addObject:attempt];
        CFRelease(appElement);
        if (diagnostics) {
            *diagnostics = @{
                @"strategy": @"known_context_hit_test",
                @"point": MCPAXBridgePointDictionary(point),
                @"contextId": @(contextId),
                @"expectedPid": @(expectedPid),
                @"option": option,
                @"attempts": attempts
            };
        }
        MCP_AX_BRIDGE_LOG(@"Known-context hit-test succeeded point=(%.1f,%.1f) ctx=%u option=%d pid=%d",
                          point.x,
                          point.y,
                          contextId,
                          option.intValue,
                          hasHitPid ? hitPid : expectedPid);
        return hitElement;
    }

    CFRelease(appElement);
    if (diagnostics) {
        *diagnostics = @{
            @"strategy": @"known_context_hit_test",
            @"point": MCPAXBridgePointDictionary(point),
            @"contextId": @(contextId),
            @"expectedPid": @(expectedPid),
            @"attempts": attempts
        };
    }
    if (error) {
        *error = errors.count > 0 ?
            [errors componentsJoinedByString:@"; "] :
            @"Known contextId hit-test returned no element";
    }
    return NULL;
}

- (AXUIElementRef _Nullable)copySystemWideElement {
    if (![self ensureRuntimeAvailable:nil] || !sMCPAXBridgeRuntime.createSystemWide) {
        return NULL;
    }
    AXUIElementRef element = sMCPAXBridgeRuntime.createSystemWide();
    if (element) MCPAXBridgeApplyMessagingTimeout(element);
    return element;
}

- (BOOL)getPid:(pid_t *)pidOut fromElement:(AXUIElementRef)element {
    if (!element || !pidOut || !sMCPAXBridgeRuntime.getPid) return NO;
    pid_t resolvedPid = 0;
    AXError axError = sMCPAXBridgeRuntime.getPid(element, &resolvedPid);
    if (axError != kAXErrorSuccess || resolvedPid <= 0) return NO;
    *pidOut = resolvedPid;
    return YES;
}

- (NSString *)errorStringForAXError:(AXError)error {
    switch (error) {
        case kAXErrorSuccess: return @"success";
        case kAXErrorFailure: return @"failure";
        case kAXErrorIllegalArgument: return @"illegal argument";
        case kAXErrorInvalidUIElement: return @"invalid UI element";
        case kAXErrorCannotComplete: return @"cannot complete";
        case kAXErrorAttributeUnsupported: return @"attribute unsupported";
        case kAXErrorNoValue: return @"no value";
        case kAXErrorNotImplemented: return @"not implemented";
        default: return [NSString stringWithFormat:@"error %d", (int)error];
    }
}

- (AXUIElementRef _Nullable)copyHitTestElementAtPoint:(CGPoint)point
                                          expectedPid:(pid_t)expectedPid
                                   allowParameterized:(BOOL)allowParameterized
                                                error:(NSString * _Nullable * _Nullable)error {
    NSString *runtimeError = nil;
    if (![self ensureRuntimeAvailable:&runtimeError]) {
        if (error) *error = runtimeError;
        return NULL;
    }

    MCPAXBridgeSetRequestingClientForAutomation();

    NSMutableArray<NSString *> *errors = [NSMutableArray array];

    if (allowParameterized) {
        NSString *parameterError = nil;
        AXUIElementRef hitElement = MCPAXBridgeCopyElementWithParametersAtPoint(point, expectedPid, &parameterError);
        if (hitElement) return hitElement;
        if (parameterError.length > 0) {
            MCP_AX_BRIDGE_LOG(@"Parameterized hit-test failed for pid=%d point=(%.1f,%.1f): %@",
                              expectedPid,
                              point.x,
                              point.y,
                              parameterError);
            [errors addObject:parameterError];
        }
    }

    if (sMCPAXBridgeRuntime.copyElementAtPositionWithParams && sMCPAXBridgeRuntime.createSystemWide) {
        AXUIElementRef systemWide = [self copySystemWideElement];
        if (systemWide) {
            AXUIElementRef hitElement = NULL;
            AXError axError = sMCPAXBridgeRuntime.copyElementAtPositionWithParams(systemWide, &hitElement, 1, point.x, point.y);
            CFRelease(systemWide);
            if (axError == kAXErrorSuccess && hitElement) {
                MCPAXBridgeApplyMessagingTimeout(hitElement);
                return hitElement;
            }
            [errors addObject:[NSString stringWithFormat:@"System-wide AX hit-test with params failed: %@",
                               [self errorStringForAXError:axError]]];
        }
    }

    if (sMCPAXBridgeRuntime.copyElementAtPosition || sMCPAXBridgeRuntime.copyElementAtPositionWithParams) {
        if (sMCPAXBridgeRuntime.copyElementAtPositionWithParams) {
            NSString *appError = nil;
            AXUIElementRef appElement = [self copyApplicationElementForPid:expectedPid error:&appError];
            if (appElement) {
                AXUIElementRef hitElement = NULL;
                AXError axError = sMCPAXBridgeRuntime.copyElementAtPositionWithParams(appElement, &hitElement, 1, point.x, point.y);
                CFRelease(appElement);
                if (axError == kAXErrorSuccess && hitElement) {
                    MCPAXBridgeApplyMessagingTimeout(hitElement);
                    return hitElement;
                }
                [errors addObject:[NSString stringWithFormat:@"Application AX hit-test with params failed: %@",
                                   [self errorStringForAXError:axError]]];
            } else if (appError.length > 0) {
                [errors addObject:appError];
            }
        }

        if (sMCPAXBridgeRuntime.copyElementAtPosition) {
            NSString *appError = nil;
            AXUIElementRef appElement = [self copyApplicationElementForPid:expectedPid error:&appError];
            if (appElement) {
                AXUIElementRef hitElement = NULL;
                AXError axError = sMCPAXBridgeRuntime.copyElementAtPosition(appElement, &hitElement, point.x, point.y);
                CFRelease(appElement);
                if (axError == kAXErrorSuccess && hitElement) {
                    MCPAXBridgeApplyMessagingTimeout(hitElement);
                    return hitElement;
                }
                [errors addObject:[NSString stringWithFormat:@"Application AX hit-test failed: %@",
                                   [self errorStringForAXError:axError]]];
            } else if (appError.length > 0) {
                [errors addObject:appError];
            }
        }
    } else {
        [errors addObject:@"AXUIElementCopyElementAtPosition unavailable"];
    }

    if (error) {
        *error = errors.count > 0 ? [errors componentsJoinedByString:@"; "] : @"AX hit-test returned no element";
    }
    return NULL;
}

- (id _Nullable)copyAttributeObject:(AXUIElementRef)element
                          attribute:(CFStringRef)attribute {
    if (!element || !sMCPAXBridgeRuntime.copyAttributeValue) return nil;
    MCPAXBridgeSetRequestingClientForAutomation();
    CFTypeRef value = NULL;
    AXError error = sMCPAXBridgeRuntime.copyAttributeValue(element, attribute, &value);
    if (error != kAXErrorSuccess || !value) return nil;
    return CFBridgingRelease(value);
}

- (NSDictionary<NSString *, id> * _Nullable)copyAttributeMap:(AXUIElementRef)element
                                                   attributes:(NSArray<NSString *> *)attributes {
    if (!element || attributes.count == 0 || !sMCPAXBridgeRuntime.copyMultipleAttributeValues) return nil;

    MCPAXBridgeSetRequestingClientForAutomation();

    CFArrayRef values = NULL;
    AXError error = sMCPAXBridgeRuntime.copyMultipleAttributeValues(element,
                                                                    (__bridge CFArrayRef)attributes,
                                                                    0,
                                                                    &values);
    if (error != kAXErrorSuccess || !values) return nil;

    NSArray *valueArray = CFBridgingRelease(values);
    if (![valueArray isKindOfClass:[NSArray class]]) return nil;

    NSMutableDictionary<NSString *, id> *result = [NSMutableDictionary dictionary];
    NSInteger count = MIN(attributes.count, valueArray.count);
    for (NSInteger idx = 0; idx < count; idx++) {
        id value = valueArray[idx];
        if (!value || value == NSNull.null) continue;
        result[attributes[idx]] = value;
    }
    return result;
}

- (NSDictionary<NSString *, id> * _Nullable)copyXCAttributeMap:(AXUIElementRef)element
                                                  attributeKeys:(NSArray<NSString *> *)attributeKeys {
    if (!element || attributeKeys.count == 0) return nil;

    MCPAXBridgeSetRequestingClientForAutomation();

    NSMutableArray<NSString *> *resolvedKeys = [NSMutableArray array];
    NSMutableArray *resolvedAttributes = [NSMutableArray array];
    for (NSString *attributeKey in attributeKeys) {
        CFStringRef attribute = MCPAXBridgeXCAttributeRefForKey(attributeKey);
        if (!attribute) continue;
        [resolvedKeys addObject:attributeKey];
        [resolvedAttributes addObject:(__bridge id)attribute];
    }
    if (resolvedKeys.count == 0) return nil;

    NSMutableDictionary<NSString *, id> *result = [NSMutableDictionary dictionary];
    if (sMCPAXBridgeRuntime.copyMultipleAttributeValues) {
        CFArrayRef values = NULL;
        AXError error = sMCPAXBridgeRuntime.copyMultipleAttributeValues(element,
                                                                        (__bridge CFArrayRef)resolvedAttributes,
                                                                        0,
                                                                        &values);
        if (error == kAXErrorSuccess && values) {
            NSArray *valueArray = CFBridgingRelease(values);
            if ([valueArray isKindOfClass:[NSArray class]]) {
                NSInteger count = MIN(resolvedKeys.count, valueArray.count);
                for (NSInteger idx = 0; idx < count; idx++) {
                    id value = valueArray[idx];
                    if (!value || value == NSNull.null) continue;
                    result[resolvedKeys[idx]] = value;
                }
            }
        }
    }

    for (NSString *attributeKey in resolvedKeys) {
        if (result[attributeKey]) continue;
        CFStringRef attribute = MCPAXBridgeXCAttributeRefForKey(attributeKey);
        if (!attribute) continue;
        id value = [self copyAttributeObject:element attribute:attribute];
        if (!value || value == NSNull.null) continue;
        result[attributeKey] = value;
    }
    return result.count > 0 ? result : nil;
}

- (id _Nullable)copyXCAttributeObject:(AXUIElementRef)element
                         attributeKey:(NSString *)attributeKey {
    CFStringRef attribute = MCPAXBridgeXCAttributeRefForKey(attributeKey);
    if (!attribute) return nil;
    return [self copyAttributeObject:element attribute:attribute];
}

- (NSDictionary<NSString *, id> * _Nullable)copyDirectAttributeMap:(AXUIElementRef)element
                                                       attributeKeys:(NSArray<NSString *> *)attributeKeys {
    if (!element || attributeKeys.count == 0) return nil;

    MCPAXBridgeSetRequestingClientForAutomation();

    NSMutableDictionary<NSString *, id> *result = [NSMutableDictionary dictionary];
    for (NSString *attributeKey in attributeKeys) {
        CFStringRef attribute = MCPAXBridgeDirectAttributeRefForKey(attributeKey);
        if (!attribute) continue;
        id value = [self copyAttributeObject:element attribute:attribute];
        if (!value || value == NSNull.null) continue;
        result[attributeKey] = value;
    }
    return result.count > 0 ? result : nil;
}

- (id _Nullable)copyDirectAttributeObject:(AXUIElementRef)element
                             attributeKey:(NSString *)attributeKey {
    CFStringRef attribute = MCPAXBridgeDirectAttributeRefForKey(attributeKey);
    if (!attribute) return nil;
    return [self copyAttributeObject:element attribute:attribute];
}

- (id _Nullable)copyXCParameterizedAttributeObject:(AXUIElementRef)element
                                      attributeKey:(NSString *)attributeKey
                                         parameter:(id _Nullable)parameter {
    if (!element || !sMCPAXBridgeRuntime.copyParameterizedAttributeValue) return nil;
    CFStringRef attribute = MCPAXBridgeXCParameterizedAttributeRefForKey(attributeKey);
    if (!attribute) return nil;

    MCPAXBridgeSetRequestingClientForAutomation();

    CFTypeRef value = NULL;
    AXError error = sMCPAXBridgeRuntime.copyParameterizedAttributeValue(element,
                                                                        attribute,
                                                                        (__bridge CFTypeRef)(parameter ?: @{}),
                                                                        &value);
    if (error != kAXErrorSuccess || !value) return nil;
    return CFBridgingRelease(value);
}

- (id _Nullable)copyUserTestingSnapshotForElement:(AXUIElementRef)element
                                          options:(NSDictionary * _Nullable)options {
    NSDictionary *normalizedOptions = MCPAXBridgeNormalizedUserTestingSnapshotOptions(options ?: @{});
    id parameterizedSnapshot = [self copyXCParameterizedAttributeObject:element
                                                           attributeKey:@"userTestingSnapshotParameterized"
                                                              parameter:normalizedOptions];
    if (parameterizedSnapshot) return parameterizedSnapshot;
    return [self copyXCAttributeObject:element attributeKey:@"userTestingSnapshot"];
}

- (NSDictionary * _Nullable)probeUserTestingSnapshotForElement:(AXUIElementRef)element
                                                       options:(NSDictionary * _Nullable)options {
    if (!element) return nil;

    MCPAXBridgeSetRequestingClientForAutomation();

    NSMutableDictionary *probe = [NSMutableDictionary dictionary];
    NSDictionary *normalizedOptions = MCPAXBridgeNormalizedUserTestingSnapshotOptions(options ?: @{});
    if (normalizedOptions.count > 0) {
        probe[@"normalizedOptions"] = normalizedOptions;
    }

    CFStringRef parameterizedAttribute = MCPAXBridgeXCParameterizedAttributeRefForKey(@"userTestingSnapshotParameterized");
    if (parameterizedAttribute && sMCPAXBridgeRuntime.copyParameterizedAttributeValue) {
        CFTypeRef value = NULL;
        AXError error = sMCPAXBridgeRuntime.copyParameterizedAttributeValue(element,
                                                                            parameterizedAttribute,
                                                                            (__bridge CFTypeRef)normalizedOptions,
                                                                            &value);
        probe[@"parameterizedErrorCode"] = @(error);
        probe[@"parameterizedError"] = [self errorStringForAXError:error];
        if (value) {
            id bridgedValue = CFBridgingRelease(value);
            probe[@"parameterizedValueSummary"] = MCPAXBridgeSnapshotValueSummary(bridgedValue);
            if ([bridgedValue isKindOfClass:[NSDictionary class]]) {
                probe[@"snapshot"] = bridgedValue;
                probe[@"snapshotSource"] = @"parameterized";
            }
        }
    }

    if (!probe[@"snapshot"]) {
        CFStringRef attribute = MCPAXBridgeXCAttributeRefForKey(@"userTestingSnapshot");
        if (attribute && sMCPAXBridgeRuntime.copyAttributeValue) {
            CFTypeRef value = NULL;
            AXError error = sMCPAXBridgeRuntime.copyAttributeValue(element, attribute, &value);
            probe[@"attributeErrorCode"] = @(error);
            probe[@"attributeError"] = [self errorStringForAXError:error];
            if (value) {
                id bridgedValue = CFBridgingRelease(value);
                probe[@"attributeValueSummary"] = MCPAXBridgeSnapshotValueSummary(bridgedValue);
                if ([bridgedValue isKindOfClass:[NSDictionary class]]) {
                    probe[@"snapshot"] = bridgedValue;
                    probe[@"snapshotSource"] = @"attribute";
                }
            }
        }
    }

    return probe;
}

- (NSDictionary<NSNumber *, id> * _Nullable)copyNumericAttributeMap:(AXUIElementRef)element
                                                         attributes:(NSArray<NSNumber *> *)attributes {
    if (!element || attributes.count == 0 || !sMCPAXBridgeRuntime.copyMultipleAttributeValues) return nil;

    MCPAXBridgeSetRequestingClientForAutomation();

    CFArrayRef values = NULL;
    AXError error = sMCPAXBridgeRuntime.copyMultipleAttributeValues(element,
                                                                    (__bridge CFArrayRef)attributes,
                                                                    0,
                                                                    &values);
    if (error != kAXErrorSuccess || !values) return nil;

    NSArray *valueArray = CFBridgingRelease(values);
    if (![valueArray isKindOfClass:[NSArray class]]) return nil;

    NSMutableDictionary<NSNumber *, id> *result = [NSMutableDictionary dictionary];
    NSInteger count = MIN(attributes.count, valueArray.count);
    for (NSInteger idx = 0; idx < count; idx++) {
        id value = valueArray[idx];
        if (!value || value == NSNull.null) continue;
        result[attributes[idx]] = value;
    }
    return result;
}

- (NSArray * _Nullable)copyNumericAttributeArray:(AXUIElementRef)element
                                     attributeId:(uint32_t)attributeId {
    id value = [self copyAttributeObject:element attribute:MCPAXBridgeNumericAttributeRef(attributeId)];
    if ([value isKindOfClass:[NSArray class]]) return value;
    if (value) return @[value];
    return nil;
}

- (NSArray * _Nullable)copyChildElementsForElement:(AXUIElementRef)element {
    NSDictionary<NSString *, id> *directValues = [self copyDirectAttributeMap:element attributeKeys:@[
        @"visibleElements",
        @"elementsWithSemanticContext",
        @"nativeFocusableElements",
        @"explorerElements",
        @"siriContentNativeFocusableElements",
        @"siriContentElementsWithSemanticContext",
        @"privateChildren"
    ]];
    NSMutableOrderedSet *mergedChildren = [NSMutableOrderedSet orderedSet];
    for (NSString *attributeKey in @[
        @"visibleElements",
        @"elementsWithSemanticContext",
        @"nativeFocusableElements",
        @"explorerElements",
        @"siriContentNativeFocusableElements",
        @"siriContentElementsWithSemanticContext",
        @"privateChildren"
    ]) {
        MCPAXBridgeAppendUniqueObjects(mergedChildren, directValues[attributeKey]);
    }

    NSDictionary<NSString *, id> *xcValues = [self copyXCAttributeMap:element attributeKeys:@[
        @"children",
        @"userTestingElements"
    ]];
    for (NSString *attributeKey in @[@"children", @"userTestingElements"]) {
        MCPAXBridgeAppendUniqueObjects(mergedChildren, xcValues[attributeKey]);
    }

    NSArray<NSString *> *attributes = @[
        (__bridge NSString *)kAXChildrenAttribute,
        @"AXVisibleChildren",
        @"AXWindows",
        @"AXElements",
        @"AXFocusedWindow",
        @"AXMainWindow"
    ];

    NSDictionary<NSString *, id> *batchValues = [self copyAttributeMap:element attributes:attributes];
    for (NSString *attribute in attributes) {
        MCPAXBridgeAppendUniqueObjects(mergedChildren, batchValues[attribute]);
    }
    if (mergedChildren.count == 0) {
        for (NSString *attribute in attributes) {
            MCPAXBridgeAppendUniqueObjects(mergedChildren, [self copyAttributeObject:element attribute:(__bridge CFStringRef)attribute]);
        }
    }
    return mergedChildren.count > 0 ? mergedChildren.array : nil;
}

- (NSString * _Nullable)copyStringAttribute:(AXUIElementRef)element attribute:(CFStringRef)attribute {
    id value = [self copyAttributeObject:element attribute:attribute];
    if ([value isKindOfClass:[NSString class]]) return value;
    if ([value respondsToSelector:@selector(stringValue)]) return [value stringValue];
    return nil;
}

- (NSNumber * _Nullable)copyNumberAttribute:(AXUIElementRef)element attribute:(CFStringRef)attribute {
    id value = [self copyAttributeObject:element attribute:attribute];
    if ([value isKindOfClass:[NSNumber class]]) return value;
    return nil;
}

@end
