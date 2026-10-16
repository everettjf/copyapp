#import "MCPAXRemoteContextResolver.h"
#import "MCPAXQueryContext.h"
#import "SpringBoardPrivate.h"
#import <UIKit/UIKit.h>
#import <dispatch/dispatch.h>
#import <mach-o/dyld.h>
#import <objc/message.h>
#import <objc/runtime.h>
#import <dlfcn.h>
#import <string.h>
#import <unistd.h>

@interface UIApplication (MCPPrivateAXFrontmost)
- (id)_accessibilityFrontMostApplication;
@end

typedef CFTypeRef (*MCPAXFrontBoardCopyTypeFunc)(void);
typedef pid_t (*MCPAXFrontBoardCopyPidFunc)(void);

typedef struct {
    BOOL available;
    void *handle;
    MCPAXFrontBoardCopyPidFunc focusedAppPID;
    MCPAXFrontBoardCopyTypeFunc focusedAppPIDs;
    MCPAXFrontBoardCopyTypeFunc focusedAppPIDsIgnoringSiri;
    MCPAXFrontBoardCopyTypeFunc focusedApps;
    MCPAXFrontBoardCopyTypeFunc focusedAppProcess;
    MCPAXFrontBoardCopyTypeFunc focusedAppProcesses;
    MCPAXFrontBoardCopyTypeFunc visibleAppProcesses;
    MCPAXFrontBoardCopyTypeFunc fbSceneManager;
} MCPAXFrontBoardRuntime;

static MCPAXFrontBoardRuntime sMCPAXFrontBoardRuntime;

static id MCPAXResolverMsgSendObject(id target, SEL selector) {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(target, selector);
}

static NSArray *MCPAXResolverArrayFromCollection(id value) {
    if (!value || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSArray class]]) return value;
    if ([value isKindOfClass:[NSSet class]]) return [(NSSet *)value allObjects];
    if ([value respondsToSelector:@selector(allObjects)]) {
        id objects = ((id (*)(id, SEL))objc_msgSend)(value, @selector(allObjects));
        if ([objects isKindOfClass:[NSArray class]]) return objects;
    }
    return nil;
}

static BOOL MCPAXResolverProcessHasLoadedImageToken(NSString *token) {
    if (token.length == 0) return NO;
    uint32_t imageCount = _dyld_image_count();
    for (uint32_t i = 0; i < imageCount; i++) {
        const char *imageName = _dyld_get_image_name(i);
        if (!imageName) continue;
        NSString *name = [NSString stringWithUTF8String:imageName];
        if ([name rangeOfString:token options:NSCaseInsensitiveSearch].location != NSNotFound) {
            return YES;
        }
    }
    return NO;
}

static const char *MCPAXResolverSkipTypeQualifiers(const char *typeEncoding) {
    if (!typeEncoding) return "";
    while (*typeEncoding == 'r' ||
           *typeEncoding == 'n' ||
           *typeEncoding == 'N' ||
           *typeEncoding == 'o' ||
           *typeEncoding == 'O' ||
           *typeEncoding == 'R' ||
           *typeEncoding == 'V') {
        typeEncoding++;
    }
    return typeEncoding;
}

static void MCPAXLoadFrontBoardRuntime(void) {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        const char *path = "/System/Library/PrivateFrameworks/AXFrontBoardUtils.framework/AXFrontBoardUtils";
        void *handle = dlopen(path, RTLD_NOW | RTLD_GLOBAL);
        if (!handle) {
            handle = dlopen(path, RTLD_LAZY | RTLD_GLOBAL);
        }

        sMCPAXFrontBoardRuntime.handle = handle;
        if (!handle) {
            return;
        }

        sMCPAXFrontBoardRuntime.focusedAppPID =
            (MCPAXFrontBoardCopyPidFunc)dlsym(handle, "AXFrontBoardFocusedAppPID");
        sMCPAXFrontBoardRuntime.focusedAppPIDs =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardFocusedAppPIDs");
        sMCPAXFrontBoardRuntime.focusedAppPIDsIgnoringSiri =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardFocusedAppPIDsIgnoringSiri");
        sMCPAXFrontBoardRuntime.focusedApps =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardFocusedApps");
        sMCPAXFrontBoardRuntime.focusedAppProcess =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardFocusedAppProcess");
        sMCPAXFrontBoardRuntime.focusedAppProcesses =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardFocusedAppProcesses");
        sMCPAXFrontBoardRuntime.visibleAppProcesses =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardVisibleAppProcesses");
        sMCPAXFrontBoardRuntime.fbSceneManager =
            (MCPAXFrontBoardCopyTypeFunc)dlsym(handle, "AXFrontBoardFBSceneManager");

        sMCPAXFrontBoardRuntime.available =
            (sMCPAXFrontBoardRuntime.focusedAppPID != NULL ||
             sMCPAXFrontBoardRuntime.focusedAppPIDs != NULL ||
             sMCPAXFrontBoardRuntime.focusedAppPIDsIgnoringSiri != NULL ||
             sMCPAXFrontBoardRuntime.focusedApps != NULL ||
             sMCPAXFrontBoardRuntime.focusedAppProcess != NULL ||
             sMCPAXFrontBoardRuntime.focusedAppProcesses != NULL ||
             sMCPAXFrontBoardRuntime.visibleAppProcesses != NULL ||
             sMCPAXFrontBoardRuntime.fbSceneManager != NULL);
    });
}

static id MCPAXFrontBoardCopyObject(MCPAXFrontBoardCopyTypeFunc function) {
    if (!function) return nil;
    CFTypeRef value = function();
    if (!value) return nil;
    return (__bridge id)value;
}

static NSNumber *MCPAXResolverPreferenceBool(NSString *key) {
    if (key.length == 0) return nil;
    CFPropertyListRef value = CFPreferencesCopyAppValue((__bridge CFStringRef)key,
                                                        CFSTR("com.apple.Accessibility"));
    if (!value) return nil;
    id bridged = CFBridgingRelease(value);
    if ([bridged respondsToSelector:@selector(boolValue)]) {
        return @([bridged boolValue]);
    }
    return nil;
}

static BOOL MCPAXResolverStringContainsToken(NSString *value, NSString *token) {
    if (value.length == 0 || token.length == 0) return NO;
    return [value rangeOfString:token options:NSCaseInsensitiveSearch].location != NSNotFound;
}

static BOOL MCPAXResolverSceneLooksAccessibilityLike(NSString *sceneIdentifier,
                                                     NSString *bundleId,
                                                     NSString *className) {
    return MCPAXResolverStringContainsToken(sceneIdentifier, @"Accessibility") ||
           MCPAXResolverStringContainsToken(bundleId, @"Accessibility") ||
           MCPAXResolverStringContainsToken(className, @"Accessibility") ||
           MCPAXResolverStringContainsToken(className, @"AXUI");
}

static BOOL MCPAXResolverSceneLooksVoiceOverLike(NSString *sceneIdentifier,
                                                 NSString *bundleId,
                                                 NSString *className) {
    return MCPAXResolverStringContainsToken(sceneIdentifier, @"VoiceOver") ||
           MCPAXResolverStringContainsToken(bundleId, @"VoiceOver") ||
           MCPAXResolverStringContainsToken(className, @"VoiceOver") ||
           MCPAXResolverStringContainsToken(className, @"VOT");
}

@interface MCPAXRemoteContextResolver ()

- (BOOL)populateContext:(MCPAXQueryContext *)context
       fromAXFrontBoardWithTrace:(NSMutableArray<NSString *> *)trace
                         metadata:(NSMutableDictionary *)metadata;
- (void)populateContext:(MCPAXQueryContext *)context
   fromApplicationObject:(id)applicationObject
         resolutionTrace:(NSMutableArray<NSString *> *)trace;
- (void)populateContext:(MCPAXQueryContext *)context
                fromPid:(pid_t)pid
        resolutionTrace:(NSMutableArray<NSString *> *)trace;
- (void)populateSceneFieldsForContext:(MCPAXQueryContext *)context
                           fromTarget:(id)target
                      resolutionTrace:(NSMutableArray<NSString *> *)trace
                               prefix:(NSString *)prefix;
- (void)populateContext:(MCPAXQueryContext *)context
 fromWorkspaceScenesWithTrace:(NSMutableArray<NSString *> *)trace
               metadata:(NSMutableDictionary *)metadata;
- (void)populateAccessibilityActivationMetadata:(NSMutableDictionary *)metadata
                                        context:(MCPAXQueryContext *)context
                                          trace:(NSArray<NSString *> *)trace;
- (id)legacyFrontmostApplicationObject;
- (id)preferredApplicationObjectFromCandidateValue:(id)candidateValue;
- (id)applicationObjectForPid:(pid_t)pid resolutionTrace:(NSMutableArray<NSString *> *)trace;
- (BOOL)contextHasIdentity:(MCPAXQueryContext *)context;
- (id)invokeObjectSelector:(SEL)selector onTarget:(id)target;
- (NSNumber *)invokeNumericSelector:(SEL)selector onTarget:(id)target;
- (NSNumber *)firstPositiveNumericSelectorValueFromTarget:(id)target
                                                selectors:(NSArray<NSString *> *)selectorNames
                                          matchedSelector:(NSString * _Nullable __autoreleasing *)matchedSelector;
- (NSString *)firstNonEmptyStringSelectorValueFromTarget:(id)target
                                               selectors:(NSArray<NSString *> *)selectorNames
                                         matchedSelector:(NSString * _Nullable __autoreleasing *)matchedSelector;
- (pid_t)pidFromApplicationObject:(id)frontApp
                          bundleId:(NSString *)bundleId
                   resolutionTrace:(NSMutableArray<NSString *> *)trace;
- (NSDictionary *)axFrontBoardAvailability;

@end

@implementation MCPAXRemoteContextResolver

- (NSDictionary *)frontmostContextDictionary {
    MCPAXQueryContext *context = [self frontmostContext];
    return context ? [context dictionaryRepresentation] : @{};
}

- (MCPAXQueryContext *)frontmostContext {
    __block MCPAXQueryContext *context = [MCPAXQueryContext new];
    __block NSMutableArray<NSString *> *trace = [NSMutableArray array];
    __block NSMutableDictionary *metadata = [[self axFrontBoardAvailability] mutableCopy];

    dispatch_block_t block = ^{
        BOOL resolvedFromAXFrontBoard = [self populateContext:context
                                         fromAXFrontBoardWithTrace:trace
                                                           metadata:metadata];

        if (!resolvedFromAXFrontBoard) {
            id frontApp = [self legacyFrontmostApplicationObject];
            if (frontApp) {
                [trace addObject:@"springboard:_accessibilityFrontMostApplication"];
                [self populateContext:context fromApplicationObject:frontApp resolutionTrace:trace];
                if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
                    context.resolverStrategy = @"springboard_accessibility_frontmost";
                }
            }
        }

        if (context.pid > 0 &&
            (context.bundleId.length == 0 ||
             context.processName.length == 0 ||
             context.sceneIdentifier.length == 0 ||
             context.contextId == 0 ||
             context.displayId == 0)) {
            [self populateContext:context fromPid:context.pid resolutionTrace:trace];
        }

        if ((context.sceneIdentifier.length == 0 ||
             context.contextId == 0 ||
             context.displayId == 0) &&
            [self contextHasIdentity:context]) {
            [self populateContext:context fromWorkspaceScenesWithTrace:trace metadata:metadata];
        }

        if (context.displayId == 0) {
            Class displayClass = objc_getClass("CADisplay");
            id mainDisplay = [self invokeObjectSelector:@selector(mainDisplay) onTarget:displayClass];
            NSNumber *displayId = [self invokeNumericSelector:NSSelectorFromString(@"displayId") onTarget:mainDisplay];
            if (displayId.unsignedIntValue > 0) {
                context.displayId = displayId.unsignedIntValue;
                [trace addObject:@"fallback:CADisplay.mainDisplay.displayId"];
            }
        }

        if (context.bundleId.length == 0) {
            context.bundleId = @"com.apple.springboard";
            context.processName = @"SpringBoard";
            context.pid = getpid();
            context.resolverStrategy = @"springboard_default";
            [trace addObject:@"fallback:springboard_default"];
        }
    };

    if ([NSThread isMainThread]) {
        block();
    } else {
        dispatch_sync(dispatch_get_main_queue(), block);
    }

    [self populateAccessibilityActivationMetadata:metadata context:context trace:trace];
    context.metadata = [metadata copy];
    context.resolutionTrace = trace;
    if (context.resolverStrategy.length == 0) {
        context.resolverStrategy = [self contextHasIdentity:context] ?
            @"resolver_completed_without_explicit_strategy" :
            @"springboard_default";
    }
    return context;
}

- (BOOL)populateContext:(MCPAXQueryContext *)context
       fromAXFrontBoardWithTrace:(NSMutableArray<NSString *> *)trace
                         metadata:(NSMutableDictionary *)metadata {
    MCPAXLoadFrontBoardRuntime();
    if (!sMCPAXFrontBoardRuntime.available) {
        [trace addObject:@"axfrontboard:unavailable"];
        return NO;
    }

    id focusedApps = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.focusedApps);
    if ([focusedApps isKindOfClass:[NSArray class]]) {
        metadata[@"focusedAppsCount"] = @([(NSArray *)focusedApps count]);
    }
    id frontObject = [self preferredApplicationObjectFromCandidateValue:focusedApps];
    if (frontObject) {
        metadata[@"focusedAppsClass"] = NSStringFromClass([frontObject class]) ?: @"<unknown>";
        [trace addObject:@"axfrontboard:AXFrontBoardFocusedApps"];
        [self populateContext:context fromApplicationObject:frontObject resolutionTrace:trace];
        if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
            context.resolverStrategy = @"ax_frontboard_focused_apps";
        }
        if ([self contextHasIdentity:context]) {
            return YES;
        }
    }

    id focusedProcess = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.focusedAppProcess);
    if (focusedProcess) {
        metadata[@"focusedAppProcessClass"] = NSStringFromClass([focusedProcess class]) ?: @"<unknown>";
        [trace addObject:@"axfrontboard:AXFrontBoardFocusedAppProcess"];
        [self populateContext:context fromApplicationObject:focusedProcess resolutionTrace:trace];
        if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
            context.resolverStrategy = @"ax_frontboard_focused_app_process";
        }
        if ([self contextHasIdentity:context]) {
            return YES;
        }
    }

    id focusedProcesses = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.focusedAppProcesses);
    if ([focusedProcesses isKindOfClass:[NSArray class]]) {
        metadata[@"focusedAppProcessesCount"] = @([(NSArray *)focusedProcesses count]);
    }
    frontObject = [self preferredApplicationObjectFromCandidateValue:focusedProcesses];
    if (frontObject) {
        metadata[@"focusedAppProcessesClass"] = NSStringFromClass([frontObject class]) ?: @"<unknown>";
        [trace addObject:@"axfrontboard:AXFrontBoardFocusedAppProcesses"];
        [self populateContext:context fromApplicationObject:frontObject resolutionTrace:trace];
        if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
            context.resolverStrategy = @"ax_frontboard_focused_app_processes";
        }
        if ([self contextHasIdentity:context]) {
            return YES;
        }
    }

    id visibleProcesses = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.visibleAppProcesses);
    if ([visibleProcesses isKindOfClass:[NSArray class]]) {
        metadata[@"visibleAppProcessesCount"] = @([(NSArray *)visibleProcesses count]);
    }
    frontObject = [self preferredApplicationObjectFromCandidateValue:visibleProcesses];
    if (frontObject) {
        metadata[@"visibleAppProcessClass"] = NSStringFromClass([frontObject class]) ?: @"<unknown>";
        [trace addObject:@"axfrontboard:AXFrontBoardVisibleAppProcesses"];
        [self populateContext:context fromApplicationObject:frontObject resolutionTrace:trace];
        if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
            context.resolverStrategy = @"ax_frontboard_visible_app_processes";
        }
        if ([self contextHasIdentity:context]) {
            return YES;
        }
    }

    if (sMCPAXFrontBoardRuntime.focusedAppPID) {
        pid_t focusedPid = sMCPAXFrontBoardRuntime.focusedAppPID();
        metadata[@"focusedAppPIDResult"] = @(focusedPid);
        if (focusedPid > 0) {
            [trace addObject:@"axfrontboard:AXFrontBoardFocusedAppPID"];
            [self populateContext:context fromPid:focusedPid resolutionTrace:trace];
            if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
                context.resolverStrategy = @"ax_frontboard_focused_app_pid";
            }
            if ([self contextHasIdentity:context]) {
                return YES;
            }
        }
    }

    id focusedPIDs = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.focusedAppPIDs);
    if ([focusedPIDs isKindOfClass:[NSArray class]]) {
        metadata[@"focusedAppPIDsCount"] = @([(NSArray *)focusedPIDs count]);
        for (id value in (NSArray *)focusedPIDs) {
            if (![value isKindOfClass:[NSNumber class]]) continue;
            pid_t focusedPid = [(NSNumber *)value intValue];
            if (focusedPid <= 0) continue;
            metadata[@"focusedAppPIDsFirst"] = @(focusedPid);
            [trace addObject:@"axfrontboard:AXFrontBoardFocusedAppPIDs"];
            [self populateContext:context fromPid:focusedPid resolutionTrace:trace];
            if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
                context.resolverStrategy = @"ax_frontboard_focused_app_pids";
            }
            if ([self contextHasIdentity:context]) {
                return YES;
            }
            break;
        }
    }

    id focusedPIDsIgnoringSiri = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.focusedAppPIDsIgnoringSiri);
    if ([focusedPIDsIgnoringSiri isKindOfClass:[NSArray class]]) {
        metadata[@"focusedAppPIDsIgnoringSiriCount"] = @([(NSArray *)focusedPIDsIgnoringSiri count]);
        for (id value in (NSArray *)focusedPIDsIgnoringSiri) {
            if (![value isKindOfClass:[NSNumber class]]) continue;
            pid_t focusedPid = [(NSNumber *)value intValue];
            if (focusedPid <= 0) continue;
            metadata[@"focusedAppPIDsIgnoringSiriFirst"] = @(focusedPid);
            [trace addObject:@"axfrontboard:AXFrontBoardFocusedAppPIDsIgnoringSiri"];
            [self populateContext:context fromPid:focusedPid resolutionTrace:trace];
            if (context.resolverStrategy.length == 0 && [self contextHasIdentity:context]) {
                context.resolverStrategy = @"ax_frontboard_focused_app_pids_ignoring_siri";
            }
            if ([self contextHasIdentity:context]) {
                return YES;
            }
            break;
        }
    }

    id sceneManager = MCPAXFrontBoardCopyObject(sMCPAXFrontBoardRuntime.fbSceneManager);
    if (sceneManager) {
        metadata[@"fbSceneManagerClass"] = NSStringFromClass([sceneManager class]) ?: @"<unknown>";
        [trace addObject:@"axfrontboard:AXFrontBoardFBSceneManager"];
        [self populateSceneFieldsForContext:context
                                 fromTarget:sceneManager
                            resolutionTrace:trace
                                     prefix:@"AXFrontBoardFBSceneManager"];
    }

    return [self contextHasIdentity:context];
}

- (void)populateContext:(MCPAXQueryContext *)context
   fromApplicationObject:(id)applicationObject
         resolutionTrace:(NSMutableArray<NSString *> *)trace {
    if (!context || !applicationObject) return;

    NSString *applicationClassName = NSStringFromClass([applicationObject class]) ?: @"applicationObject";
    BOOL sourceLooksLikeAXWrapper = [applicationClassName hasPrefix:@"AX"];
    NSString *bundleId = nil;
    SEL bundleIdentifierSel = @selector(bundleIdentifier);
    if ([applicationObject respondsToSelector:bundleIdentifierSel]) {
        bundleId = MCPAXResolverMsgSendObject(applicationObject, bundleIdentifierSel);
    }
    if (bundleId.length > 0) {
        context.bundleId = bundleId;
    }

    NSString *processName = nil;
    for (NSString *selectorName in @[@"displayName", @"localizedName"]) {
        processName = [self invokeObjectSelector:NSSelectorFromString(selectorName) onTarget:applicationObject];
        if (processName.length > 0) {
            [trace addObject:[NSString stringWithFormat:@"name:%@", selectorName]];
            break;
        }
    }
    if (processName.length > 0) {
        context.processName = processName;
    }

    pid_t pid = [self pidFromApplicationObject:applicationObject bundleId:bundleId resolutionTrace:trace];

    [self populateSceneFieldsForContext:context
                             fromTarget:applicationObject
                        resolutionTrace:trace
                                 prefix:applicationClassName];

    id processState = [self invokeObjectSelector:@selector(processState) onTarget:applicationObject];
    if (processState) {
        [self populateSceneFieldsForContext:context
                                 fromTarget:processState
                            resolutionTrace:trace
                                     prefix:[NSString stringWithFormat:@"%@.processState",
                                             NSStringFromClass([applicationObject class]) ?: @"applicationObject"]];
    }

    if (bundleId.length > 0) {
        Class appControllerClass = objc_getClass("SBApplicationController");
        id controller = [self invokeObjectSelector:@selector(sharedInstance) onTarget:appControllerClass];
        id sbApp = nil;
        if ([controller respondsToSelector:@selector(applicationWithBundleIdentifier:)]) {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"
            sbApp = [controller performSelector:@selector(applicationWithBundleIdentifier:) withObject:bundleId];
#pragma clang diagnostic pop
        }
        if (sbApp) {
            [trace addObject:@"fallback:SBApplicationController"];
            if (context.bundleId.length == 0) {
                context.bundleId = bundleId;
            }
            if (context.processName.length == 0 || sourceLooksLikeAXWrapper) {
                for (NSString *selectorName in @[@"displayName", @"localizedName"]) {
                    processName = [self invokeObjectSelector:NSSelectorFromString(selectorName) onTarget:sbApp];
                    if (processName.length > 0) {
                        context.processName = processName;
                        [trace addObject:[NSString stringWithFormat:@"name:%@ via SBApplicationController", selectorName]];
                        break;
                    }
                }
            }
            if (pid <= 0) {
                pid = [self pidFromApplicationObject:sbApp bundleId:bundleId resolutionTrace:trace];
            }

            NSString *matchedStringSelector = nil;
            NSString *sbSceneIdentifier =
                [self firstNonEmptyStringSelectorValueFromTarget:sbApp
                                                       selectors:@[@"_baseSceneIdentifier",
                                                                   @"sceneIdentifier",
                                                                   @"_sceneIdentifier",
                                                                   @"identifier"]
                                                 matchedSelector:&matchedStringSelector];
            if (sbSceneIdentifier.length > 0 &&
                (context.sceneIdentifier.length == 0 ||
                 sourceLooksLikeAXWrapper ||
                 [context.sceneIdentifier isEqualToString:bundleId])) {
                context.sceneIdentifier = sbSceneIdentifier;
                [trace addObject:[NSString stringWithFormat:@"SBApplicationController.application:%@",
                                  matchedStringSelector ?: @"sceneIdentifier"]];
            }

            NSString *matchedNumericSelector = nil;
            NSNumber *sbContextId =
                [self firstPositiveNumericSelectorValueFromTarget:sbApp
                                                        selectors:@[@"_accessibilityGetContextID",
                                                                    @"contextId",
                                                                    @"contextID",
                                                                    @"windowContextId"]
                                                  matchedSelector:&matchedNumericSelector];
            if (sbContextId.unsignedIntValue > 0 &&
                (context.contextId == 0 || sourceLooksLikeAXWrapper)) {
                context.contextId = sbContextId.unsignedIntValue;
                [trace addObject:[NSString stringWithFormat:@"SBApplicationController.application:%@",
                                  matchedNumericSelector ?: @"_accessibilityGetContextID"]];
            }

            NSNumber *sbDisplayId =
                [self firstPositiveNumericSelectorValueFromTarget:sbApp
                                                        selectors:@[@"displayId",
                                                                    @"displayID",
                                                                    @"windowDisplayId"]
                                                  matchedSelector:&matchedNumericSelector];
            if (sbDisplayId.unsignedIntValue > 0 && (context.displayId == 0 || sourceLooksLikeAXWrapper)) {
                context.displayId = sbDisplayId.unsignedIntValue;
                [trace addObject:[NSString stringWithFormat:@"SBApplicationController.application:%@",
                                  matchedNumericSelector ?: @"displayId"]];
            }

            [self populateSceneFieldsForContext:context
                                     fromTarget:sbApp
                                resolutionTrace:trace
                                         prefix:@"SBApplicationController.application"];

            id sbProcessState = [self invokeObjectSelector:@selector(processState) onTarget:sbApp];
            if (sbProcessState) {
                NSNumber *processStateContextId =
                    [self firstPositiveNumericSelectorValueFromTarget:sbProcessState
                                                            selectors:@[@"_accessibilityGetContextID",
                                                                        @"contextId",
                                                                        @"contextID",
                                                                        @"windowContextId"]
                                                      matchedSelector:&matchedNumericSelector];
                if (processStateContextId.unsignedIntValue > 0 &&
                    (context.contextId == 0 || sourceLooksLikeAXWrapper)) {
                    context.contextId = processStateContextId.unsignedIntValue;
                    [trace addObject:[NSString stringWithFormat:@"SBApplicationController.application.processState:%@",
                                      matchedNumericSelector ?: @"_accessibilityGetContextID"]];
                }
                [self populateSceneFieldsForContext:context
                                         fromTarget:sbProcessState
                                    resolutionTrace:trace
                                             prefix:@"SBApplicationController.application.processState"];
            }
        }
    }

    if ([bundleId isEqualToString:@"com.apple.springboard"]) {
        if (pid <= 0) {
            pid = getpid();
            [trace addObject:@"pid:getpid"];
        }
        if (context.processName.length == 0) {
            context.processName = @"SpringBoard";
        }
    }

    if (pid > 0) {
        context.pid = pid;
    }
}

- (void)populateContext:(MCPAXQueryContext *)context
                fromPid:(pid_t)pid
        resolutionTrace:(NSMutableArray<NSString *> *)trace {
    if (!context || pid <= 0) return;

    if (context.pid <= 0) {
        context.pid = pid;
    }

    id applicationObject = [self applicationObjectForPid:pid resolutionTrace:trace];
    if (applicationObject) {
        [self populateContext:context fromApplicationObject:applicationObject resolutionTrace:trace];
        return;
    }

    if (pid == getpid()) {
        if (context.bundleId.length == 0) {
            context.bundleId = @"com.apple.springboard";
        }
        if (context.processName.length == 0) {
            context.processName = @"SpringBoard";
        }
    }
}

- (void)populateSceneFieldsForContext:(MCPAXQueryContext *)context
                           fromTarget:(id)target
                      resolutionTrace:(NSMutableArray<NSString *> *)trace
                               prefix:(NSString *)prefix {
    if (!context || !target) return;

    if (context.sceneIdentifier.length == 0) {
        for (NSString *selectorName in @[@"sceneIdentifier", @"sceneID", @"mainSceneIdentifier", @"persistentIdentifier", @"_baseSceneIdentifier", @"_sceneIdentifier", @"identifier"]) {
            id value = [self invokeObjectSelector:NSSelectorFromString(selectorName) onTarget:target];
            if ([value isKindOfClass:[NSString class]] && [value length] > 0) {
                context.sceneIdentifier = value;
                [trace addObject:[NSString stringWithFormat:@"%@:%@", prefix, selectorName]];
                break;
            }
        }
    }

    if (context.contextId == 0) {
        for (NSString *selectorName in @[@"contextId", @"contextID", @"windowContextId", @"_contextId", @"statusBarContextID", @"_accessibilityGetContextID"]) {
            NSNumber *value = [self invokeNumericSelector:NSSelectorFromString(selectorName) onTarget:target];
            if (value.unsignedIntValue > 0) {
                context.contextId = value.unsignedIntValue;
                [trace addObject:[NSString stringWithFormat:@"%@:%@", prefix, selectorName]];
                break;
            }
        }
    }

    if (context.displayId == 0) {
        for (NSString *selectorName in @[@"displayId", @"displayID", @"windowDisplayId"]) {
            NSNumber *value = [self invokeNumericSelector:NSSelectorFromString(selectorName) onTarget:target];
            if (value.unsignedIntValue > 0) {
                context.displayId = value.unsignedIntValue;
                [trace addObject:[NSString stringWithFormat:@"%@:%@", prefix, selectorName]];
                break;
            }
        }
    }

    for (NSString *selectorName in @[@"scene", @"mainScene"]) {
        id nestedTarget = [self invokeObjectSelector:NSSelectorFromString(selectorName) onTarget:target];
        if (nestedTarget && nestedTarget != target) {
            [self populateSceneFieldsForContext:context
                                     fromTarget:nestedTarget
                                resolutionTrace:trace
                                         prefix:[NSString stringWithFormat:@"%@.%@", prefix, selectorName]];
        }
    }

    for (NSString *selectorName in @[@"display", @"fbsDisplay", @"clientProcess", @"hostProcess"]) {
        id nestedTarget = [self invokeObjectSelector:NSSelectorFromString(selectorName) onTarget:target];
        if (nestedTarget && nestedTarget != target) {
            [self populateSceneFieldsForContext:context
                                     fromTarget:nestedTarget
                                resolutionTrace:trace
                                         prefix:[NSString stringWithFormat:@"%@.%@", prefix, selectorName]];
        }
    }

    id contextsValue = [self invokeObjectSelector:@selector(contexts) onTarget:target];
    NSArray *contexts = MCPAXResolverArrayFromCollection(contextsValue);
    NSUInteger contextIndex = 0;
    for (id contextTarget in contexts) {
        if (!contextTarget || contextTarget == target) continue;
        [self populateSceneFieldsForContext:context
                                 fromTarget:contextTarget
                            resolutionTrace:trace
                                     prefix:[NSString stringWithFormat:@"%@.contexts[%lu]",
                                             prefix,
                                             (unsigned long)contextIndex]];
        contextIndex++;
    }
}

- (void)populateContext:(MCPAXQueryContext *)context
 fromWorkspaceScenesWithTrace:(NSMutableArray<NSString *> *)trace
               metadata:(NSMutableDictionary *)metadata {
    if (!context) return;

    Class workspaceClass = objc_getClass("FBSWorkspace");
    id workspace = [self invokeObjectSelector:NSSelectorFromString(@"_sharedWorkspaceIfExists") onTarget:workspaceClass];
    if (!workspace) {
        workspace = [self invokeObjectSelector:NSSelectorFromString(@"sharedWorkspace") onTarget:workspaceClass];
    }
    if (!workspace) {
        [trace addObject:@"workspace:unavailable"];
        return;
    }

    NSArray *scenes = MCPAXResolverArrayFromCollection([self invokeObjectSelector:@selector(scenes) onTarget:workspace]);
    if (scenes.count == 0) {
        [trace addObject:@"workspace:scenes_empty"];
        return;
    }

    metadata[@"workspaceSceneCount"] = @(scenes.count);

    NSInteger bestScore = 0;
    id bestScene = nil;
    NSMutableDictionary *bestSceneSummary = nil;
    NSMutableArray<NSDictionary *> *candidateSummaries = [NSMutableArray array];
    NSMutableArray<NSDictionary *> *accessibilitySceneSummaries = [NSMutableArray array];
    NSUInteger accessibilitySceneCount = 0;
    NSUInteger voiceOverSceneCount = 0;

    for (id scene in scenes) {
        if (!scene) continue;

        NSString *sceneIdentifier = [self invokeObjectSelector:@selector(identifier) onTarget:scene];
        NSString *sceneBundleId = [self invokeObjectSelector:NSSelectorFromString(@"crs_applicationBundleIdentifier") onTarget:scene];
        NSString *sceneClassName = NSStringFromClass([scene class]) ?: @"<unknown>";
        id clientProcess = [self invokeObjectSelector:@selector(clientProcess) onTarget:scene];
        id hostProcess = [self invokeObjectSelector:@selector(hostProcess) onTarget:scene];
        NSNumber *clientPid = [self invokeNumericSelector:@selector(pid) onTarget:clientProcess];
        NSNumber *hostPid = [self invokeNumericSelector:@selector(pid) onTarget:hostProcess];
        id display = [self invokeObjectSelector:@selector(display) onTarget:scene] ?: [self invokeObjectSelector:@selector(fbsDisplay) onTarget:scene];
        NSNumber *displayId = [self invokeNumericSelector:NSSelectorFromString(@"displayId") onTarget:display];

        NSArray *contextObjects = MCPAXResolverArrayFromCollection([self invokeObjectSelector:@selector(contexts) onTarget:scene]);
        NSMutableArray<NSNumber *> *contextIds = [NSMutableArray array];
        for (id contextObject in contextObjects) {
            NSNumber *contextId = [self invokeNumericSelector:NSSelectorFromString(@"contextID") onTarget:contextObject];
            if (contextId.unsignedIntValue == 0) {
                contextId = [self invokeNumericSelector:NSSelectorFromString(@"contextId") onTarget:contextObject];
            }
            if (contextId.unsignedIntValue == 0) {
                contextId = [self invokeNumericSelector:NSSelectorFromString(@"windowContextId") onTarget:contextObject];
            }
            if (contextId.unsignedIntValue > 0) {
                [contextIds addObject:contextId];
            }
        }

        NSInteger score = 0;
        if (context.pid > 0 && clientPid.intValue == context.pid) score += 120;
        if (context.pid > 0 && hostPid.intValue == context.pid) score += 30;
        if (context.bundleId.length > 0 && [sceneBundleId isKindOfClass:[NSString class]] && [sceneBundleId isEqualToString:context.bundleId]) score += 100;
        if (context.sceneIdentifier.length > 0 && [sceneIdentifier isKindOfClass:[NSString class]] && [sceneIdentifier isEqualToString:context.sceneIdentifier]) score += 80;
        if (context.bundleId.length > 0 && [sceneIdentifier isKindOfClass:[NSString class]] && [sceneIdentifier isEqualToString:context.bundleId]) score += 40;
        if (context.bundleId.length == 0 && context.pid == 0 && [sceneIdentifier isKindOfClass:[NSString class]] && sceneIdentifier.length > 0) score += 1;

        NSMutableDictionary *candidateSummary = [NSMutableDictionary dictionary];
        candidateSummary[@"class"] = sceneClassName;
        if (sceneIdentifier.length > 0) candidateSummary[@"sceneIdentifier"] = sceneIdentifier;
        if (sceneBundleId.length > 0) candidateSummary[@"bundleId"] = sceneBundleId;
        if (clientPid.intValue > 0) candidateSummary[@"clientPid"] = clientPid;
        if (hostPid.intValue > 0) candidateSummary[@"hostPid"] = hostPid;
        if (displayId.unsignedIntValue > 0) candidateSummary[@"displayId"] = displayId;
        if (contextIds.count > 0) candidateSummary[@"contextIds"] = contextIds;
        candidateSummary[@"score"] = @(score);
        [candidateSummaries addObject:candidateSummary];

        if (MCPAXResolverSceneLooksAccessibilityLike(sceneIdentifier, sceneBundleId, sceneClassName)) {
            accessibilitySceneCount += 1;
            if (accessibilitySceneSummaries.count < 8) {
                [accessibilitySceneSummaries addObject:[candidateSummary copy]];
            }
        }
        if (MCPAXResolverSceneLooksVoiceOverLike(sceneIdentifier, sceneBundleId, sceneClassName)) {
            voiceOverSceneCount += 1;
        }

        if (score > bestScore) {
            bestScore = score;
            bestScene = scene;
            bestSceneSummary = candidateSummary;
        }
    }

    if (candidateSummaries.count > 0) {
        metadata[@"workspaceSceneCandidates"] = [candidateSummaries subarrayWithRange:NSMakeRange(0, MIN((NSUInteger)8, candidateSummaries.count))];
    }
    metadata[@"workspaceAccessibilitySceneCount"] = @(accessibilitySceneCount);
    metadata[@"workspaceVoiceOverSceneCount"] = @(voiceOverSceneCount);
    if (accessibilitySceneSummaries.count > 0) {
        metadata[@"workspaceAccessibilityScenes"] = accessibilitySceneSummaries;
    }

    if (!bestScene || bestScore <= 0) {
        [trace addObject:@"workspace:no_matching_scene"];
        return;
    }

    [trace addObject:@"workspace:matched_scene"];
    if (bestSceneSummary.count > 0) {
        metadata[@"workspaceMatchedScene"] = bestSceneSummary;
    }

    [self populateSceneFieldsForContext:context
                             fromTarget:bestScene
                        resolutionTrace:trace
                                 prefix:@"FBSWorkspace.scene"];

    NSString *sceneBundleId = [self invokeObjectSelector:NSSelectorFromString(@"crs_applicationBundleIdentifier") onTarget:bestScene];
    if (context.bundleId.length == 0 && sceneBundleId.length > 0) {
        context.bundleId = sceneBundleId;
    }

    id clientProcess = [self invokeObjectSelector:@selector(clientProcess) onTarget:bestScene];
    NSNumber *clientPid = [self invokeNumericSelector:@selector(pid) onTarget:clientProcess];
    if (context.pid <= 0 && clientPid.intValue > 0) {
        context.pid = clientPid.intValue;
        [trace addObject:@"workspace:clientProcess.pid"];
    }
}

- (void)populateAccessibilityActivationMetadata:(NSMutableDictionary *)metadata
                                        context:(MCPAXQueryContext *)context
                                          trace:(NSArray<NSString *> *)trace {
    if (!metadata) return;

    NSNumber *accessibilityEnabled = MCPAXResolverPreferenceBool(@"AccessibilityEnabled");
    NSNumber *voiceOverTouchEnabled = MCPAXResolverPreferenceBool(@"VoiceOverTouchEnabled");
    NSNumber *assistiveTouchEnabled = MCPAXResolverPreferenceBool(@"AssistiveTouchEnabled");
    NSNumber *assistiveTouchUIEnabled = MCPAXResolverPreferenceBool(@"AssistiveTouchUIEnabled");

    NSUInteger workspaceSceneCount = [metadata[@"workspaceSceneCount"] respondsToSelector:@selector(unsignedIntegerValue)] ?
        [metadata[@"workspaceSceneCount"] unsignedIntegerValue] :
        0;
    NSUInteger accessibilitySceneCount = [metadata[@"workspaceAccessibilitySceneCount"] respondsToSelector:@selector(unsignedIntegerValue)] ?
        [metadata[@"workspaceAccessibilitySceneCount"] unsignedIntegerValue] :
        0;
    NSUInteger voiceOverSceneCount = [metadata[@"workspaceVoiceOverSceneCount"] respondsToSelector:@selector(unsignedIntegerValue)] ?
        [metadata[@"workspaceVoiceOverSceneCount"] unsignedIntegerValue] :
        0;

    BOOL voiceOverRunning = UIAccessibilityIsVoiceOverRunning();
    BOOL runtimeLikelyActive = voiceOverRunning || voiceOverSceneCount > 0 || accessibilitySceneCount > 0;
    NSString *currentProcessName = NSProcessInfo.processInfo.processName ?: @"<unknown>";
    BOOL currentProcessHasVOTUIServerClass = (NSClassFromString(@"VOTUIServer") != Nil);
    BOOL currentProcessHasVOTScreenCurtainClass = (NSClassFromString(@"VOTUIScreenCurtainViewController") != Nil);
    BOOL currentProcessHasVoiceOverBundleImage = MCPAXResolverProcessHasLoadedImageToken(@"VoiceOver.axuiservice");
    BOOL currentProcessLooksLikeVoiceOverRegistrar = currentProcessHasVOTUIServerClass ||
        currentProcessHasVOTScreenCurtainClass ||
        currentProcessHasVoiceOverBundleImage;
    NSString *recommendedRegistrarProcess = currentProcessLooksLikeVoiceOverRegistrar ?
        currentProcessName :
        (runtimeLikelyActive ? @"AccessibilityUIServer" : @"unknown");
    NSString *axRuntimeMode = nil;
    if (!runtimeLikelyActive) {
        axRuntimeMode = @"inactive";
    } else if (currentProcessLooksLikeVoiceOverRegistrar) {
        axRuntimeMode = @"active_current_process_registrar";
    } else if (voiceOverRunning || voiceOverSceneCount > 0) {
        axRuntimeMode = @"voiceover_registered";
    } else {
        axRuntimeMode = @"active_but_nonregistrar_process";
    }

    NSMutableDictionary *state = [NSMutableDictionary dictionary];
    state[@"voiceOverRunning"] = @(voiceOverRunning);
    if (accessibilityEnabled) state[@"AccessibilityEnabled"] = accessibilityEnabled;
    if (voiceOverTouchEnabled) state[@"VoiceOverTouchEnabled"] = voiceOverTouchEnabled;
    if (assistiveTouchEnabled) state[@"AssistiveTouchEnabled"] = assistiveTouchEnabled;
    if (assistiveTouchUIEnabled) state[@"AssistiveTouchUIEnabled"] = assistiveTouchUIEnabled;
    if (workspaceSceneCount > 0) state[@"workspaceSceneCount"] = @(workspaceSceneCount);
    state[@"workspaceAccessibilitySceneCount"] = @(accessibilitySceneCount);
    state[@"workspaceVoiceOverSceneCount"] = @(voiceOverSceneCount);
    if (context.sceneIdentifier.length > 0) state[@"frontmostSceneIdentifier"] = context.sceneIdentifier;
    if (context.contextId > 0) state[@"frontmostContextId"] = @(context.contextId);
    if (context.displayId > 0) state[@"frontmostDisplayId"] = @(context.displayId);
    state[@"runtimeLikelyActive"] = @(runtimeLikelyActive);
    state[@"currentProcessName"] = currentProcessName;
    state[@"currentProcessLooksLikeVoiceOverRegistrar"] = @(currentProcessLooksLikeVoiceOverRegistrar);
    state[@"currentProcessHasVOTUIServerClass"] = @(currentProcessHasVOTUIServerClass);
    state[@"currentProcessHasVOTScreenCurtainViewControllerClass"] = @(currentProcessHasVOTScreenCurtainClass);
    state[@"currentProcessHasVoiceOverBundleImage"] = @(currentProcessHasVoiceOverBundleImage);
    state[@"recommendedRegistrarProcess"] = recommendedRegistrarProcess;
    state[@"currentProcessDirectRegisterLikelyInsufficient"] = @(!currentProcessLooksLikeVoiceOverRegistrar);
    if (axRuntimeMode.length > 0) state[@"axRuntimeMode"] = axRuntimeMode;

    NSString *registrationHeuristic = nil;
    if (voiceOverRunning || voiceOverSceneCount > 0) {
        registrationHeuristic = @"voiceover_action_handler";
    } else if (assistiveTouchEnabled.boolValue || assistiveTouchUIEnabled.boolValue) {
        registrationHeuristic = @"assistivetouch_pref_without_confirmed_runtime";
    } else {
        registrationHeuristic = @"none_observed";
    }
    state[@"registrationHeuristic"] = registrationHeuristic;

    if (trace.count > 0) {
        NSArray *tail = trace.count > 6 ? [trace subarrayWithRange:NSMakeRange(trace.count - 6, 6)] : trace;
        state[@"resolutionTraceTail"] = tail;
    }

    state[@"guidance"] = runtimeLikelyActive ?
        @"AX runtime looks active. VoiceOver-style SpringBoard action handler registration is likely present." :
        @"AX runtime does not look active. VoiceOver-style SpringBoard action handler registration has not been observed; direct AX tree queries will likely return empty candidate sets.";
    state[@"registrarGuidance"] =
        currentProcessLooksLikeVoiceOverRegistrar ?
        @"Current process already looks VoiceOver-registrar-capable. Verify its controller lifecycle before treating direct register as a production path." :
        @"Current process does not look like the VoiceOver registrar. AccessibilityUIServer/VoiceOver.axuiservice is the more likely registrar owner.";
    state[@"axRuntimeModeExplanation"] =
        [axRuntimeMode isEqualToString:@"inactive"] ?
        @"AX runtime does not currently look active; direct AX tree queries are likely to return empty candidate sets." :
        ([axRuntimeMode isEqualToString:@"voiceover_registered"] ?
         @"AX runtime looks active because a VoiceOver-style SpringBoard action handler registration has likely been established, but the current process is not the registrar owner." :
         ([axRuntimeMode isEqualToString:@"active_current_process_registrar"] ?
          @"AX runtime is active and the current process already looks registrar-capable." :
          @"AX runtime is active, but the current process does not look like the registrar owner."));

    metadata[@"accessibilityState"] = state;
}

- (id)preferredApplicationObjectFromCandidateValue:(id)candidateValue {
    NSArray *candidates = nil;
    if ([candidateValue isKindOfClass:[NSArray class]]) {
        candidates = candidateValue;
    } else if (candidateValue) {
        candidates = @[candidateValue];
    } else {
        return nil;
    }

    for (id candidate in candidates) {
        NSString *bundleId = [self invokeObjectSelector:@selector(bundleIdentifier) onTarget:candidate];
        if (bundleId.length > 0 && ![bundleId isEqualToString:@"com.apple.springboard"]) {
            return candidate;
        }
    }

    for (id candidate in candidates) {
        pid_t pid = [self pidFromApplicationObject:candidate bundleId:nil resolutionTrace:nil];
        if (pid > 0 && pid != getpid()) {
            return candidate;
        }
    }

    return candidates.firstObject;
}

- (id)applicationObjectForPid:(pid_t)pid resolutionTrace:(NSMutableArray<NSString *> *)trace {
    if (pid <= 0) return nil;

    Class appControllerClass = objc_getClass("SBApplicationController");
    id controller = [self invokeObjectSelector:@selector(sharedInstanceIfExists) onTarget:appControllerClass];
    if (!controller) {
        controller = [self invokeObjectSelector:@selector(sharedInstance) onTarget:appControllerClass];
    }
    if (!controller) return nil;

    NSArray<NSString *> *collectionSelectors = @[@"runningApplications", @"allApplications"];
    for (NSString *collectionSelectorName in collectionSelectors) {
        NSArray *applications = [self invokeObjectSelector:NSSelectorFromString(collectionSelectorName) onTarget:controller];
        if (![applications isKindOfClass:[NSArray class]]) continue;

        for (id application in applications) {
            pid_t candidatePid = [self pidFromApplicationObject:application bundleId:nil resolutionTrace:nil];
            if (candidatePid != pid) continue;

            if (trace) {
                [trace addObject:[NSString stringWithFormat:@"pid:%@ matched", collectionSelectorName]];
            }
            return application;
        }
    }

    return nil;
}

- (BOOL)contextHasIdentity:(MCPAXQueryContext *)context {
    return (context.pid > 0 || context.bundleId.length > 0);
}

- (id)legacyFrontmostApplicationObject {
    Class springBoardClass = objc_getClass("SpringBoard");
    SEL sharedApplicationSel = @selector(sharedApplication);
    if (!springBoardClass || ![springBoardClass respondsToSelector:sharedApplicationSel]) {
        return nil;
    }

    id springBoard = MCPAXResolverMsgSendObject((id)springBoardClass, sharedApplicationSel);
    SEL frontmostSel = @selector(_accessibilityFrontMostApplication);
    if (!springBoard || ![springBoard respondsToSelector:frontmostSel]) {
        return nil;
    }

    return MCPAXResolverMsgSendObject(springBoard, frontmostSel);
}

- (id)invokeObjectSelector:(SEL)selector onTarget:(id)target {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;

    NSMethodSignature *signature = [target methodSignatureForSelector:selector];
    if (!signature) return nil;

    const char *returnType = MCPAXResolverSkipTypeQualifiers(signature.methodReturnType);
    if (strcmp(returnType, @encode(id)) != 0) return nil;

    NSInvocation *invocation = [NSInvocation invocationWithMethodSignature:signature];
    invocation.target = target;
    invocation.selector = selector;
    [invocation invoke];

    __unsafe_unretained id returnValue = nil;
    [invocation getReturnValue:&returnValue];
    return returnValue;
}

- (NSNumber *)invokeNumericSelector:(SEL)selector onTarget:(id)target {
    if (!target || !selector || ![target respondsToSelector:selector]) return nil;

    NSMethodSignature *signature = [target methodSignatureForSelector:selector];
    if (!signature) return nil;

    const char *returnType = MCPAXResolverSkipTypeQualifiers(signature.methodReturnType);
    NSInvocation *invocation = [NSInvocation invocationWithMethodSignature:signature];
    invocation.target = target;
    invocation.selector = selector;
    [invocation invoke];

    switch (returnType[0]) {
        case 'c': {
            char value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'C': {
            unsigned char value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 's': {
            short value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'S': {
            unsigned short value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'i': {
            int value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'I': {
            unsigned int value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'l': {
            long value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'L': {
            unsigned long value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'q': {
            long long value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'Q': {
            unsigned long long value = 0;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case 'B': {
            BOOL value = NO;
            [invocation getReturnValue:&value];
            return @(value);
        }
        case '@': {
            __unsafe_unretained id returnValue = nil;
            [invocation getReturnValue:&returnValue];
            if ([returnValue isKindOfClass:[NSNumber class]]) {
                return returnValue;
            }
            return nil;
        }
        default:
            return nil;
    }
}

- (NSNumber *)firstPositiveNumericSelectorValueFromTarget:(id)target
                                                selectors:(NSArray<NSString *> *)selectorNames
                                          matchedSelector:(NSString * _Nullable __autoreleasing *)matchedSelector {
    for (NSString *selectorName in selectorNames) {
        NSNumber *value = [self invokeNumericSelector:NSSelectorFromString(selectorName) onTarget:target];
        if (value.unsignedIntValue > 0) {
            if (matchedSelector) {
                *matchedSelector = selectorName;
            }
            return value;
        }
    }
    return nil;
}

- (NSString *)firstNonEmptyStringSelectorValueFromTarget:(id)target
                                               selectors:(NSArray<NSString *> *)selectorNames
                                         matchedSelector:(NSString * _Nullable __autoreleasing *)matchedSelector {
    for (NSString *selectorName in selectorNames) {
        id value = [self invokeObjectSelector:NSSelectorFromString(selectorName) onTarget:target];
        if ([value isKindOfClass:[NSString class]] && [value length] > 0) {
            if (matchedSelector) {
                *matchedSelector = selectorName;
            }
            return value;
        }
    }
    return nil;
}

- (pid_t)pidFromApplicationObject:(id)frontApp
                          bundleId:(NSString *)bundleId
                   resolutionTrace:(NSMutableArray<NSString *> *)trace {
    if (!frontApp) return 0;

    for (NSString *selectorName in @[@"pid", @"processIdentifier"]) {
        NSNumber *value = [self invokeNumericSelector:NSSelectorFromString(selectorName) onTarget:frontApp];
        if (value.intValue > 0) {
            if (trace) {
                [trace addObject:[NSString stringWithFormat:@"pid:%@", selectorName]];
            }
            return value.intValue;
        }
    }

    id processState = [self invokeObjectSelector:@selector(processState) onTarget:frontApp];
    if (processState) {
        for (NSString *selectorName in @[@"pid", @"processIdentifier"]) {
            NSNumber *value = [self invokeNumericSelector:NSSelectorFromString(selectorName) onTarget:processState];
            if (value.intValue > 0) {
                if (trace) {
                    [trace addObject:[NSString stringWithFormat:@"pid:processState.%@", selectorName]];
                }
                return value.intValue;
            }
        }
    }

    if (bundleId.length > 0) {
        Class fbsClass = objc_getClass("FBSSystemService");
        id service = [self invokeObjectSelector:@selector(sharedService) onTarget:fbsClass];
        SEL selector = @selector(pidForApplication:);
        if ([service respondsToSelector:selector]) {
            NSMethodSignature *signature = [service methodSignatureForSelector:selector];
            NSInvocation *invocation = [NSInvocation invocationWithMethodSignature:signature];
            invocation.target = service;
            invocation.selector = selector;
            NSString *bid = bundleId;
            [invocation setArgument:&bid atIndex:2];
            [invocation invoke];

            pid_t pid = 0;
            [invocation getReturnValue:&pid];
            if (pid > 0) {
                if (trace) {
                    [trace addObject:@"pid:FBSSystemService.pidForApplication"];
                }
                return pid;
            }
        }
    }

    return 0;
}

- (NSDictionary *)axFrontBoardAvailability {
    MCPAXLoadFrontBoardRuntime();

    NSMutableDictionary *dict = [NSMutableDictionary dictionary];
    dict[@"frameworkPath"] = @"/System/Library/PrivateFrameworks/AXFrontBoardUtils.framework/AXFrontBoardUtils";
    dict[@"frameworkLoaded"] = @(sMCPAXFrontBoardRuntime.handle != NULL);
    dict[@"runtimeReady"] = @(sMCPAXFrontBoardRuntime.available);
    dict[@"AXFrontBoardFocusedAppPID"] = @(sMCPAXFrontBoardRuntime.focusedAppPID != NULL);
    dict[@"AXFrontBoardFocusedAppPIDs"] = @(sMCPAXFrontBoardRuntime.focusedAppPIDs != NULL);
    dict[@"AXFrontBoardFocusedAppPIDsIgnoringSiri"] = @(sMCPAXFrontBoardRuntime.focusedAppPIDsIgnoringSiri != NULL);
    dict[@"AXFrontBoardFocusedApps"] = @(sMCPAXFrontBoardRuntime.focusedApps != NULL);
    dict[@"AXFrontBoardFocusedAppProcess"] = @(sMCPAXFrontBoardRuntime.focusedAppProcess != NULL);
    dict[@"AXFrontBoardFocusedAppProcesses"] = @(sMCPAXFrontBoardRuntime.focusedAppProcesses != NULL);
    dict[@"AXFrontBoardVisibleAppProcesses"] = @(sMCPAXFrontBoardRuntime.visibleAppProcesses != NULL);
    dict[@"AXFrontBoardFBSceneManager"] = @(sMCPAXFrontBoardRuntime.fbSceneManager != NULL);
    return [dict copy];
}

@end
