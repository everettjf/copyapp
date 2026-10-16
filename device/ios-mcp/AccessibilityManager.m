#import "AccessibilityManager.h"
#import "MCPLogger.h"
#import "MCPAXQueryContext.h"
#import "MCPAXAttributeBridge.h"
#import "MCPAXNodeSource.h"
#import "MCPAXRemoteContextResolver.h"
#import "MCPUIElementSerializer.h"
#import "MCPUIElementsFacade.h"
#import "SpringBoardPrivate.h"
#import "AXPrivate.h"
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import <objc/message.h>
#import <dlfcn.h>
#import <mach-o/dyld.h>
#import <sys/sysctl.h>
#import <unistd.h>

extern char **environ;

@interface MCPAXUIClientDelegateBridge : NSObject
@property (atomic, assign) BOOL uiServerReady;
@property (atomic, copy) NSString *lastInitializationMessageClass;
@property (atomic, copy) NSString *lastInitializationMessageDescription;
@property (atomic, copy) NSString *lastServerMessageClass;
@property (atomic, copy) NSString *lastServerMessageDescription;
@property (atomic, strong) NSNumber *lastServerMessageIdentifier;
@property (atomic, copy) NSArray<NSDictionary *> *initializationHistory;
@property (atomic, copy) NSArray<NSDictionary *> *serverMessageHistory;
@end

@implementation MCPAXUIClientDelegateBridge

- (void)mcp_appendHistoryEntry:(NSDictionary *)entry
                    forKeyPath:(NSString *)keyPath
                     maxLength:(NSUInteger)maxLength {
    if (!entry || keyPath.length == 0) return;
    @synchronized (self) {
        NSArray *current = [self valueForKey:keyPath];
        NSMutableArray *next = [current isKindOfClass:[NSArray class]] ? [current mutableCopy] : [NSMutableArray array];
        [next addObject:entry];
        if (next.count > maxLength) {
            [next removeObjectsInRange:NSMakeRange(0, next.count - maxLength)];
        }
        [self setValue:[next copy] forKey:keyPath];
    }
}

- (void)userInterfaceClient:(id)client willActivateUserInterfaceServiceWithInitializationMessage:(id)message {
    self.uiServerReady = YES;
    self.lastInitializationMessageClass = message ? NSStringFromClass([message class]) : nil;
    self.lastInitializationMessageDescription = [message description] ?: nil;
    NSMutableDictionary *entry = [NSMutableDictionary dictionary];
    entry[@"timestamp"] = @([[NSDate date] timeIntervalSince1970]);
    if (self.lastInitializationMessageClass.length > 0) {
        entry[@"class"] = self.lastInitializationMessageClass;
    }
    if (self.lastInitializationMessageDescription.length > 0) {
        entry[@"description"] = self.lastInitializationMessageDescription;
    }
    [self mcp_appendHistoryEntry:entry forKeyPath:@"initializationHistory" maxLength:12];
    (void)client;
}

- (id)userInterfaceClient:(id)client processMessageFromServer:(id)message withIdentifier:(id)identifier error:(id *)error {
    self.lastServerMessageClass = message ? NSStringFromClass([message class]) : nil;
    self.lastServerMessageDescription = [message description] ?: nil;
    if ([identifier isKindOfClass:[NSNumber class]]) {
        self.lastServerMessageIdentifier = identifier;
    } else if ([identifier respondsToSelector:@selector(integerValue)]) {
        self.lastServerMessageIdentifier = @([identifier integerValue]);
    } else {
        self.lastServerMessageIdentifier = nil;
    }
    NSMutableDictionary *entry = [NSMutableDictionary dictionary];
    entry[@"timestamp"] = @([[NSDate date] timeIntervalSince1970]);
    if (self.lastServerMessageClass.length > 0) {
        entry[@"class"] = self.lastServerMessageClass;
    }
    if (self.lastServerMessageDescription.length > 0) {
        entry[@"description"] = self.lastServerMessageDescription;
    }
    if (self.lastServerMessageIdentifier) {
        entry[@"identifier"] = self.lastServerMessageIdentifier;
    } else if (identifier) {
        entry[@"identifierDescription"] = [identifier description];
    }
    [self mcp_appendHistoryEntry:entry forKeyPath:@"serverMessageHistory" maxLength:24];
    if (error) *error = nil;
    (void)client;
    return nil;
}

@end

@interface AccessibilityManager ()
- (NSDictionary *)activateVoiceOverRuntimeForContext:(MCPAXQueryContext *)context
                                              reason:(NSString *)reason;
- (BOOL)shouldAttemptAXUIClientBootstrapForContext:(MCPAXQueryContext *)context;
- (void)refreshQueryContext:(MCPAXQueryContext *)target fromContext:(MCPAXQueryContext *)source;
- (NSDictionary * _Nullable)compactPayloadForContext:(MCPAXQueryContext *)context
                                         maxElements:(NSInteger)maxElements
                                         visibleOnly:(BOOL)visibleOnly
                                       clickableOnly:(BOOL)clickableOnly
                                               error:(NSString * _Nullable * _Nullable)error;
@end

static id MCPMsgSendObject(id target, SEL selector) {
    if (!target || !selector) return nil;
    return ((id (*)(id, SEL))objc_msgSend)(target, selector);
}

#define AX_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[AX] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)
static const BOOL MCPEnableAXParameterizedHitTest = YES;
static const BOOL MCPEnableAXUIClientBootstrap = YES;
#pragma mark - Geometry Helpers

static BOOL MCPAXProcessHasLoadedImageToken(NSString *token) {
    if (token.length == 0) return NO;
    uint32_t imageCount = _dyld_image_count();
    for (uint32_t i = 0; i < imageCount; i++) {
        const char *imageName = _dyld_get_image_name(i);
        if (!imageName) continue;
        NSString *name = [NSString stringWithUTF8String:imageName];
        if (name.length == 0) continue;
        if ([name rangeOfString:token options:NSCaseInsensitiveSearch].location != NSNotFound) {
            return YES;
        }
    }
    return NO;
}

static NSDictionary *MCPAXBundleInfo(NSString *bundleDir, NSString *fallbackExecutableName) {
    if (bundleDir.length == 0) return @{};

    NSString *plistPath = [bundleDir stringByAppendingPathComponent:@"Info.plist"];
    NSFileManager *fm = NSFileManager.defaultManager;
    NSMutableDictionary *info = [NSMutableDictionary dictionary];
    info[@"bundlePath"] = bundleDir;
    info[@"infoPlistPath"] = plistPath;
    info[@"bundleExists"] = @([fm fileExistsAtPath:bundleDir]);
    info[@"infoPlistExists"] = @([fm fileExistsAtPath:plistPath]);

    NSDictionary *plist = [NSDictionary dictionaryWithContentsOfFile:plistPath];
    NSString *bundleIdentifier = nil;
    NSString *principalClass = nil;
    NSString *executableName = fallbackExecutableName;
    if ([plist isKindOfClass:[NSDictionary class]]) {
        bundleIdentifier = [plist[@"CFBundleIdentifier"] isKindOfClass:[NSString class]] ? plist[@"CFBundleIdentifier"] : nil;
        principalClass = [plist[@"NSPrincipalClass"] isKindOfClass:[NSString class]] ? plist[@"NSPrincipalClass"] : nil;
        NSString *plistExecutable = [plist[@"CFBundleExecutable"] isKindOfClass:[NSString class]] ? plist[@"CFBundleExecutable"] : nil;
        if (plistExecutable.length > 0) {
            executableName = plistExecutable;
        }
    }

    if (bundleIdentifier.length > 0) info[@"bundleIdentifier"] = bundleIdentifier;
    if (principalClass.length > 0) info[@"principalClass"] = principalClass;
    if (executableName.length > 0) {
        info[@"executableName"] = executableName;
        NSString *binaryPath = [bundleDir stringByAppendingPathComponent:executableName];
        info[@"binaryPath"] = binaryPath;
        info[@"binaryExists"] = @([fm fileExistsAtPath:binaryPath]);
    } else {
        info[@"binaryExists"] = @NO;
    }

    return [info copy];
}

static NSDictionary *MCPAXAccessibilityUIFrameworkInfo(void) {
    static NSDictionary *cached;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        cached = MCPAXBundleInfo(@"/System/Library/PrivateFrameworks/AccessibilityUI.framework",
                                 @"AccessibilityUI");
    });
    return cached;
}

static id gMCPAXUICurrentClient = nil;
static MCPAXUIClientDelegateBridge *gMCPAXUICurrentDelegate = nil;
static NSDate *gMCPAXUICurrentLastActivationDate = nil;
static NSString *gMCPAXUICurrentLastActivationError = nil;
static NSArray<NSNumber *> *gMCPAXUICurrentSentMessageIdentifiers = nil;
static NSNumber *gMCPAXCurrentProcessAppAccessibilityEnabled = nil;
static NSNumber *gMCPAXCurrentProcessVoiceOverUsageConfirmed = nil;
static BOOL gMCPAXCurrentProcessDidPrimeDisplayManager = NO;

typedef BOOL (*MCPAXSApplicationAccessibilityEnabledFunc)(void);
typedef void (*MCPAXSApplicationAccessibilitySetEnabledFunc)(BOOL enabled);
typedef BOOL (*MCPAXSVoiceOverTouchUsageConfirmedFunc)(void);
typedef void (*MCPAXSVoiceOverTouchSetUsageConfirmedFunc)(BOOL confirmed);
typedef void (*MCPAXDevicePrimeDisplayManagerFunc)(void);

typedef struct {
    BOOL resolved;
    BOOL available;
    void *libAccessibilityHandle;
    void *accessibilityUtilitiesHandle;
    MCPAXSApplicationAccessibilityEnabledFunc applicationAccessibilityEnabled;
    MCPAXSApplicationAccessibilitySetEnabledFunc applicationAccessibilitySetEnabled;
    MCPAXSVoiceOverTouchUsageConfirmedFunc voiceOverTouchUsageConfirmed;
    MCPAXSVoiceOverTouchSetUsageConfirmedFunc voiceOverTouchSetUsageConfirmed;
    MCPAXDevicePrimeDisplayManagerFunc devicePrimeDisplayManager;
    __unsafe_unretained NSString *libAccessibilitySource;
    __unsafe_unretained NSString *accessibilityUtilitiesSource;
} MCPAXVoiceOverWorkspaceRuntime;

static MCPAXVoiceOverWorkspaceRuntime sMCPAXVoiceOverWorkspaceRuntime;

static BOOL MCPAXEnsureAccessibilityUIFrameworkLoaded(void) {
    if (NSClassFromString(@"AXUIClient")) {
        return YES;
    }

    NSDictionary *frameworkInfo = MCPAXAccessibilityUIFrameworkInfo();
    NSString *binaryPath = [frameworkInfo[@"binaryPath"] isKindOfClass:[NSString class]] ? frameworkInfo[@"binaryPath"] : nil;
    if (binaryPath.length == 0) {
        return (NSClassFromString(@"AXUIClient") != Nil);
    }

    void *handle = dlopen(binaryPath.UTF8String, RTLD_NOW | RTLD_GLOBAL);
    if (!handle) {
        const char *error = dlerror();
        AX_LOG(@"AccessibilityUI.framework dlopen failed for %@: %s", binaryPath, error ?: "(unknown)");
    }
    return (NSClassFromString(@"AXUIClient") != Nil);
}

static void *MCPAXDlopenFirstAvailable(const char **paths, size_t count) {
    for (size_t index = 0; index < count; index++) {
        const char *path = paths[index];
        if (!path || path[0] == '\0') continue;
        /*
         On iOS 14 many private/public frameworks only exist as dyld shared
         cache images.  Their canonical install-name paths are valid for
         dlopen(), but access(2) can still report ENOENT because no standalone
         file is present on the filesystem.  Do not pre-filter with access()
         here; let dyld decide whether the install-name can be loaded.
         */
        void *handle = dlopen(path, RTLD_NOW | RTLD_GLOBAL);
        if (handle) return handle;
    }
    return NULL;
}

static void *MCPAXDlsymFirst(void *handle, const char *nameA, const char *nameB) {
    if (!handle) return NULL;
    void *symbol = NULL;
    if (nameA) symbol = dlsym(handle, nameA);
    if (!symbol && nameB) symbol = dlsym(handle, nameB);
    return symbol;
}

static MCPAXVoiceOverWorkspaceRuntime *MCPAXResolveVoiceOverWorkspaceRuntime(void) {
    if (sMCPAXVoiceOverWorkspaceRuntime.resolved) {
        return sMCPAXVoiceOverWorkspaceRuntime.available ? &sMCPAXVoiceOverWorkspaceRuntime : NULL;
    }

    sMCPAXVoiceOverWorkspaceRuntime.resolved = YES;

    BOOL (^bindLibAccessibilityFromHandle)(void *, NSString *) = ^BOOL(void *handle, NSString *label) {
        if (!handle) return NO;
        BOOL foundAny = NO;
        MCPAXSApplicationAccessibilityEnabledFunc applicationAccessibilityEnabled =
            (MCPAXSApplicationAccessibilityEnabledFunc)MCPAXDlsymFirst(handle, "_AXSApplicationAccessibilityEnabled", "__AXSApplicationAccessibilityEnabled");
        MCPAXSApplicationAccessibilitySetEnabledFunc applicationAccessibilitySetEnabled =
            (MCPAXSApplicationAccessibilitySetEnabledFunc)MCPAXDlsymFirst(handle, "_AXSApplicationAccessibilitySetEnabled", "__AXSApplicationAccessibilitySetEnabled");
        MCPAXSVoiceOverTouchUsageConfirmedFunc voiceOverTouchUsageConfirmed =
            (MCPAXSVoiceOverTouchUsageConfirmedFunc)MCPAXDlsymFirst(handle, "_AXSVoiceOverTouchUsageConfirmed", "__AXSVoiceOverTouchUsageConfirmed");
        MCPAXSVoiceOverTouchSetUsageConfirmedFunc voiceOverTouchSetUsageConfirmed =
            (MCPAXSVoiceOverTouchSetUsageConfirmedFunc)MCPAXDlsymFirst(handle, "_AXSVoiceOverTouchSetUsageConfirmed", "__AXSVoiceOverTouchSetUsageConfirmed");
        if (applicationAccessibilityEnabled) {
            sMCPAXVoiceOverWorkspaceRuntime.applicationAccessibilityEnabled = applicationAccessibilityEnabled;
            foundAny = YES;
        }
        if (applicationAccessibilitySetEnabled) {
            sMCPAXVoiceOverWorkspaceRuntime.applicationAccessibilitySetEnabled = applicationAccessibilitySetEnabled;
            foundAny = YES;
        }
        if (voiceOverTouchUsageConfirmed) {
            sMCPAXVoiceOverWorkspaceRuntime.voiceOverTouchUsageConfirmed = voiceOverTouchUsageConfirmed;
            foundAny = YES;
        }
        if (voiceOverTouchSetUsageConfirmed) {
            sMCPAXVoiceOverWorkspaceRuntime.voiceOverTouchSetUsageConfirmed = voiceOverTouchSetUsageConfirmed;
            foundAny = YES;
        }
        if (!foundAny) return NO;
        sMCPAXVoiceOverWorkspaceRuntime.libAccessibilityHandle = handle;
        sMCPAXVoiceOverWorkspaceRuntime.libAccessibilitySource = label;
        return YES;
    };

    BOOL (^bindAccessibilityUtilitiesFromHandle)(void *, NSString *) = ^BOOL(void *handle, NSString *label) {
        if (!handle) return NO;
        MCPAXDevicePrimeDisplayManagerFunc devicePrimeDisplayManager =
            (MCPAXDevicePrimeDisplayManagerFunc)dlsym(handle, "_AXDevicePrimeDisplayManager");
        if (!devicePrimeDisplayManager) {
            return NO;
        }
        sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesHandle = handle;
        sMCPAXVoiceOverWorkspaceRuntime.devicePrimeDisplayManager = devicePrimeDisplayManager;
        sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesSource = label;
        return YES;
    };

    const char *libAccessibilityPaths[] = {
        "/System/Library/Frameworks/Accessibility.framework/Accessibility",
        "/var/jb/System/Library/Frameworks/Accessibility.framework/Accessibility",
        "/usr/lib/libAccessibility.dylib",
        "/var/jb/usr/lib/libAccessibility.dylib"
    };
    const char *accessibilityUtilitiesPaths[] = {
        "/System/Library/PrivateFrameworks/AccessibilityUtilities.framework/AccessibilityUtilities",
        "/var/jb/System/Library/PrivateFrameworks/AccessibilityUtilities.framework/AccessibilityUtilities"
    };

    bindLibAccessibilityFromHandle(RTLD_DEFAULT, @"RTLD_DEFAULT");
    bindAccessibilityUtilitiesFromHandle(RTLD_DEFAULT, @"RTLD_DEFAULT");

    uint32_t imageCount = _dyld_image_count();
    for (uint32_t i = 0; i < imageCount; i++) {
        const char *imageName = _dyld_get_image_name(i);
        if (!imageName) continue;

        NSString *name = [NSString stringWithUTF8String:imageName];
        if (name.length == 0) continue;
        NSString *lowercaseName = name.lowercaseString;

        void *handle = NULL;
        if (!sMCPAXVoiceOverWorkspaceRuntime.libAccessibilityHandle &&
            [lowercaseName containsString:@"libaccessibility"]) {
            handle = dlopen(imageName, RTLD_NOW | RTLD_GLOBAL | RTLD_NOLOAD);
            if (!handle) handle = dlopen(imageName, RTLD_NOW | RTLD_GLOBAL);
            bindLibAccessibilityFromHandle(handle, name);
        }

        if (!sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesHandle &&
            [lowercaseName containsString:@"accessibilityutilities"]) {
            handle = dlopen(imageName, RTLD_NOW | RTLD_GLOBAL | RTLD_NOLOAD);
            if (!handle) handle = dlopen(imageName, RTLD_NOW | RTLD_GLOBAL);
            bindAccessibilityUtilitiesFromHandle(handle, name);
        }

        if (sMCPAXVoiceOverWorkspaceRuntime.libAccessibilityHandle &&
            sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesHandle) {
            break;
        }
    }

    if (!sMCPAXVoiceOverWorkspaceRuntime.libAccessibilityHandle) {
        void *handle = MCPAXDlopenFirstAvailable(libAccessibilityPaths, sizeof(libAccessibilityPaths) / sizeof(libAccessibilityPaths[0]));
        bindLibAccessibilityFromHandle(handle, handle ? @"fallback_path" : nil);
    }
    if (!sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesHandle) {
        void *handle = MCPAXDlopenFirstAvailable(accessibilityUtilitiesPaths, sizeof(accessibilityUtilitiesPaths) / sizeof(accessibilityUtilitiesPaths[0]));
        bindAccessibilityUtilitiesFromHandle(handle, handle ? @"fallback_path" : nil);
    }

    sMCPAXVoiceOverWorkspaceRuntime.available =
        (sMCPAXVoiceOverWorkspaceRuntime.applicationAccessibilityEnabled != NULL ||
         sMCPAXVoiceOverWorkspaceRuntime.applicationAccessibilitySetEnabled != NULL ||
         sMCPAXVoiceOverWorkspaceRuntime.voiceOverTouchUsageConfirmed != NULL ||
         sMCPAXVoiceOverWorkspaceRuntime.voiceOverTouchSetUsageConfirmed != NULL ||
         sMCPAXVoiceOverWorkspaceRuntime.devicePrimeDisplayManager != NULL);

    return sMCPAXVoiceOverWorkspaceRuntime.available ? &sMCPAXVoiceOverWorkspaceRuntime : NULL;
}

static NSDictionary *MCPAXPrimeVoiceOverWorkspaceState(void) {
    NSMutableDictionary *status = [NSMutableDictionary dictionary];
    MCPAXVoiceOverWorkspaceRuntime *runtime = MCPAXResolveVoiceOverWorkspaceRuntime();
    status[@"runtimeResolved"] = @(runtime != NULL);

    if (!runtime) {
        status[@"ok"] = @NO;
        status[@"error"] = @"VoiceOver workspace runtime symbols unavailable";
        return status;
    }

    BOOL canReadAppAccessibility = (runtime->applicationAccessibilityEnabled != NULL);
    BOOL canWriteAppAccessibility = (runtime->applicationAccessibilitySetEnabled != NULL);
    BOOL canReadVoiceOverUsage = (runtime->voiceOverTouchUsageConfirmed != NULL);
    BOOL canWriteVoiceOverUsage = (runtime->voiceOverTouchSetUsageConfirmed != NULL);
    BOOL canPrimeDisplayManager = (runtime->devicePrimeDisplayManager != NULL);

    status[@"canReadApplicationAccessibilityEnabled"] = @(canReadAppAccessibility);
    status[@"canWriteApplicationAccessibilityEnabled"] = @(canWriteAppAccessibility);
    status[@"canReadVoiceOverTouchUsageConfirmed"] = @(canReadVoiceOverUsage);
    status[@"canWriteVoiceOverTouchUsageConfirmed"] = @(canWriteVoiceOverUsage);
    status[@"canPrimeDisplayManager"] = @(canPrimeDisplayManager);

    if (!canReadAppAccessibility &&
        !canWriteAppAccessibility &&
        !canReadVoiceOverUsage &&
        !canWriteVoiceOverUsage &&
        !canPrimeDisplayManager) {
        status[@"ok"] = @NO;
        status[@"error"] = @"VoiceOver workspace runtime exposes no usable capabilities";
        return status;
    }

    BOOL appAccessibilityEnabledBefore = canReadAppAccessibility ? runtime->applicationAccessibilityEnabled() : NO;
    BOOL voiceOverUsageConfirmedBefore = canReadVoiceOverUsage ? runtime->voiceOverTouchUsageConfirmed() : NO;

    if (canPrimeDisplayManager) {
        runtime->devicePrimeDisplayManager();
        gMCPAXCurrentProcessDidPrimeDisplayManager = YES;
    }

    if (canWriteAppAccessibility && (!canReadAppAccessibility || !appAccessibilityEnabledBefore)) {
        runtime->applicationAccessibilitySetEnabled(YES);
    }
    if (canWriteVoiceOverUsage && (!canReadVoiceOverUsage || !voiceOverUsageConfirmedBefore)) {
        runtime->voiceOverTouchSetUsageConfirmed(YES);
    }

    BOOL appAccessibilityEnabledAfter = canReadAppAccessibility ? runtime->applicationAccessibilityEnabled() : NO;
    BOOL voiceOverUsageConfirmedAfter = canReadVoiceOverUsage ? runtime->voiceOverTouchUsageConfirmed() : NO;

    if (canReadAppAccessibility) {
        gMCPAXCurrentProcessAppAccessibilityEnabled = @(appAccessibilityEnabledAfter);
    }
    if (canReadVoiceOverUsage) {
        gMCPAXCurrentProcessVoiceOverUsageConfirmed = @(voiceOverUsageConfirmedAfter);
    }

    status[@"ok"] = @YES;
    status[@"primedDisplayManager"] = @(canPrimeDisplayManager);
    if (canReadAppAccessibility) {
        status[@"appAccessibilityEnabledBefore"] = @(appAccessibilityEnabledBefore);
        status[@"appAccessibilityEnabledAfter"] = @(appAccessibilityEnabledAfter);
    }
    if (canReadVoiceOverUsage) {
        status[@"voiceOverUsageConfirmedBefore"] = @(voiceOverUsageConfirmedBefore);
        status[@"voiceOverUsageConfirmedAfter"] = @(voiceOverUsageConfirmedAfter);
    }
    return status;
}

static void MCPAXPerformOnMainThreadSync(dispatch_block_t block);

static NSDictionary *MCPAXCurrentProcessAXUIClientStatus(void) {
    NSMutableDictionary *status = [NSMutableDictionary dictionary];
    status[@"ok"] = @YES;
    status[@"processName"] = NSProcessInfo.processInfo.processName ?: @"<unknown>";
    status[@"pid"] = @(getpid());
    status[@"loadedAccessibilityUIFrameworkImage"] = @(MCPAXProcessHasLoadedImageToken(@"AccessibilityUI.framework"));
    status[@"hasAXUIClientClass"] = @(NSClassFromString(@"AXUIClient") != Nil);
    status[@"hasAXUIClientConnectionClass"] = @(NSClassFromString(@"AXUIClientConnection") != Nil);
    status[@"workspaceRuntimeResolved"] = @(MCPAXResolveVoiceOverWorkspaceRuntime() != NULL);
    status[@"didPrimeDisplayManager"] = @(gMCPAXCurrentProcessDidPrimeDisplayManager);
    if (sMCPAXVoiceOverWorkspaceRuntime.libAccessibilitySource.length > 0) {
        status[@"libAccessibilitySource"] = sMCPAXVoiceOverWorkspaceRuntime.libAccessibilitySource;
    }
    if (sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesSource.length > 0) {
        status[@"accessibilityUtilitiesSource"] = sMCPAXVoiceOverWorkspaceRuntime.accessibilityUtilitiesSource;
    }
    status[@"canReadApplicationAccessibilityEnabled"] = @(sMCPAXVoiceOverWorkspaceRuntime.applicationAccessibilityEnabled != NULL);
    status[@"canWriteApplicationAccessibilityEnabled"] = @(sMCPAXVoiceOverWorkspaceRuntime.applicationAccessibilitySetEnabled != NULL);
    status[@"canReadVoiceOverTouchUsageConfirmed"] = @(sMCPAXVoiceOverWorkspaceRuntime.voiceOverTouchUsageConfirmed != NULL);
    status[@"canWriteVoiceOverTouchUsageConfirmed"] = @(sMCPAXVoiceOverWorkspaceRuntime.voiceOverTouchSetUsageConfirmed != NULL);
    status[@"canPrimeDisplayManager"] = @(sMCPAXVoiceOverWorkspaceRuntime.devicePrimeDisplayManager != NULL);
    if (gMCPAXCurrentProcessAppAccessibilityEnabled) {
        status[@"applicationAccessibilityEnabled"] = gMCPAXCurrentProcessAppAccessibilityEnabled;
    }
    if (gMCPAXCurrentProcessVoiceOverUsageConfirmed) {
        status[@"voiceOverTouchUsageConfirmed"] = gMCPAXCurrentProcessVoiceOverUsageConfirmed;
    }
    status[@"clientCreated"] = @(gMCPAXUICurrentClient != nil);
    status[@"delegateCreated"] = @(gMCPAXUICurrentDelegate != nil);
    status[@"uiServerReady"] = @(gMCPAXUICurrentDelegate.uiServerReady);
    if (gMCPAXUICurrentClient) {
        status[@"clientClass"] = NSStringFromClass([gMCPAXUICurrentClient class]) ?: @"<unknown>";
        status[@"clientDescription"] = [gMCPAXUICurrentClient description] ?: @"<nil>";
        if ([gMCPAXUICurrentClient respondsToSelector:@selector(clientIdentifier)]) {
            id identifier = MCPMsgSendObject(gMCPAXUICurrentClient, @selector(clientIdentifier));
            if (identifier) status[@"clientIdentifier"] = [identifier description];
        }
        if ([gMCPAXUICurrentClient respondsToSelector:@selector(serviceBundleName)]) {
            id serviceBundleName = MCPMsgSendObject(gMCPAXUICurrentClient, @selector(serviceBundleName));
            if (serviceBundleName) status[@"serviceBundleName"] = [serviceBundleName description];
        }
    }
    if (gMCPAXUICurrentDelegate.lastInitializationMessageClass.length > 0) {
        status[@"lastInitializationMessageClass"] = gMCPAXUICurrentDelegate.lastInitializationMessageClass;
    }
    if (gMCPAXUICurrentDelegate.lastInitializationMessageDescription.length > 0) {
        status[@"lastInitializationMessageDescription"] = gMCPAXUICurrentDelegate.lastInitializationMessageDescription;
    }
    if (gMCPAXUICurrentDelegate.lastServerMessageClass.length > 0) {
        status[@"lastServerMessageClass"] = gMCPAXUICurrentDelegate.lastServerMessageClass;
    }
    if (gMCPAXUICurrentDelegate.lastServerMessageDescription.length > 0) {
        status[@"lastServerMessageDescription"] = gMCPAXUICurrentDelegate.lastServerMessageDescription;
    }
    if (gMCPAXUICurrentDelegate.lastServerMessageIdentifier) {
        status[@"lastServerMessageIdentifier"] = gMCPAXUICurrentDelegate.lastServerMessageIdentifier;
    }
    if (gMCPAXUICurrentDelegate.initializationHistory.count > 0) {
        status[@"initializationHistory"] = gMCPAXUICurrentDelegate.initializationHistory;
        status[@"initializationCount"] = @(gMCPAXUICurrentDelegate.initializationHistory.count);
    }
    if (gMCPAXUICurrentDelegate.serverMessageHistory.count > 0) {
        status[@"serverMessageHistory"] = gMCPAXUICurrentDelegate.serverMessageHistory;
        status[@"serverMessageCount"] = @(gMCPAXUICurrentDelegate.serverMessageHistory.count);
    }
    if (gMCPAXUICurrentSentMessageIdentifiers.count > 0) {
        status[@"sentMessageIdentifiers"] = gMCPAXUICurrentSentMessageIdentifiers;
    }
    if (gMCPAXUICurrentLastActivationDate) {
        status[@"lastActivationTime"] = @([gMCPAXUICurrentLastActivationDate timeIntervalSince1970]);
    }
    if (gMCPAXUICurrentLastActivationError.length > 0) {
        status[@"lastActivationError"] = gMCPAXUICurrentLastActivationError;
    }
    return status;
}

static void MCPAXUIClientSendMessage(id client, NSDictionary *message, NSUInteger identifier, NSMutableArray<NSNumber *> *sentIdentifiers) {
    if (!client) return;
    SEL sendSelector = @selector(sendAsynchronousMessage:withIdentifier:targetAccessQueue:completion:);
    if (![client respondsToSelector:sendSelector]) return;
    ((void (*)(id, SEL, id, NSUInteger, id, id))objc_msgSend)(client, sendSelector, message ?: @{}, identifier, nil, nil);
    if (sentIdentifiers) {
        [sentIdentifiers addObject:@(identifier)];
    }
}

static void MCPAXPerformOnMainThreadSync(dispatch_block_t block) {
    if (!block) return;
    if ([NSThread isMainThread]) {
        block();
        return;
    }

    dispatch_sync(dispatch_get_main_queue(), block);
}

static NSDictionary *MCPAXActivateCurrentProcessAXUIClientBootstrap(BOOL sendCursorMessage,
                                                                    NSString *reason) {
    __block NSMutableDictionary *result = [MCPAXCurrentProcessAXUIClientStatus() mutableCopy];
    if (!result) result = [NSMutableDictionary dictionary];
    __block NSString *activationError = nil;
    __block BOOL loadedAccessibilityUI = NO;
    __block BOOL createdDelegate = NO;
    __block BOOL createdClient = NO;
    __block BOOL setDelegate = NO;
    __block BOOL sentRegisterMessage = NO;
    __block BOOL sentCaptionMessage = NO;
    __block BOOL sentCurtainMessage = NO;
    __block BOOL sentCursorMessage = NO;
    __block NSDictionary *workspaceBootstrap = nil;
    __block NSString *workspaceBootstrapWarning = nil;
    __block NSMutableArray<NSNumber *> *sentIdentifiers = [NSMutableArray array];

    MCPAXPerformOnMainThreadSync(^{
        loadedAccessibilityUI = MCPAXEnsureAccessibilityUIFrameworkLoaded();
        if (!loadedAccessibilityUI) {
            activationError = @"AccessibilityUI.framework could not be loaded in current process";
            return;
        }

        workspaceBootstrap = MCPAXPrimeVoiceOverWorkspaceState();
        if (![workspaceBootstrap[@"ok"] boolValue]) {
            workspaceBootstrapWarning = [workspaceBootstrap[@"error"] isKindOfClass:[NSString class]] ?
                workspaceBootstrap[@"error"] :
                @"Failed to prime VoiceOver workspace state";
        }

        Class axuiClientClass = NSClassFromString(@"AXUIClient");
        if (!axuiClientClass) {
            activationError = @"AXUIClient class unavailable";
            return;
        }

        if (!gMCPAXUICurrentDelegate) {
            gMCPAXUICurrentDelegate = [MCPAXUIClientDelegateBridge new];
            createdDelegate = (gMCPAXUICurrentDelegate != nil);
        }
        gMCPAXUICurrentDelegate.initializationHistory = nil;
        gMCPAXUICurrentDelegate.serverMessageHistory = nil;
        gMCPAXUICurrentDelegate.lastInitializationMessageClass = nil;
        gMCPAXUICurrentDelegate.lastInitializationMessageDescription = nil;
        gMCPAXUICurrentDelegate.lastServerMessageClass = nil;
        gMCPAXUICurrentDelegate.lastServerMessageDescription = nil;
        gMCPAXUICurrentDelegate.lastServerMessageIdentifier = nil;

        if (!gMCPAXUICurrentClient) {
            id allocated = ((id (*)(id, SEL))objc_msgSend)(axuiClientClass, @selector(alloc));
            gMCPAXUICurrentClient =
                ((id (*)(id, SEL, id, id))objc_msgSend)(allocated,
                                                         @selector(initWithIdentifier:serviceBundleName:),
                                                         @"VOTAXUIClientIdentifier",
                                                         @"VoiceOver");
            createdClient = (gMCPAXUICurrentClient != nil);
        }

        if (!gMCPAXUICurrentClient) {
            activationError = @"Failed to instantiate AXUIClient(VOTAXUIClientIdentifier, VoiceOver)";
            return;
        }

        if ([gMCPAXUICurrentClient respondsToSelector:@selector(setDelegate:)]) {
            ((void (*)(id, SEL, id))objc_msgSend)(gMCPAXUICurrentClient,
                                                  @selector(setDelegate:),
                                                  gMCPAXUICurrentDelegate);
            setDelegate = YES;
        }

        NSDictionary *registerMessage = @{@"register": @YES};
        MCPAXUIClientSendMessage(gMCPAXUICurrentClient, registerMessage, 25, sentIdentifiers);
        sentRegisterMessage = YES;

        NSDictionary *captionMessage = @{};
        MCPAXUIClientSendMessage(gMCPAXUICurrentClient, captionMessage, 8, sentIdentifiers);
        sentCaptionMessage = YES;

        NSDictionary *curtainMessage = @{@"enabled": @NO};
        MCPAXUIClientSendMessage(gMCPAXUICurrentClient, curtainMessage, 7, sentIdentifiers);
        sentCurtainMessage = YES;

        if (sendCursorMessage) {
            CGRect bounds = UIScreen.mainScreen ? UIScreen.mainScreen.bounds : CGRectMake(0, 0, 24, 24);
            CGRect cursorFrame = CGRectIsEmpty(bounds) || CGRectIsNull(bounds)
                ? CGRectMake(0, 0, 24, 24)
                : CGRectMake(CGRectGetMidX(bounds) - 12.0, CGRectGetMidY(bounds) - 12.0, 24.0, 24.0);
            NSDictionary *cursorMessage = @{
                @"animate": @NO,
                @"frame": NSStringFromCGRect(cursorFrame)
            };
            MCPAXUIClientSendMessage(gMCPAXUICurrentClient, cursorMessage, 1, sentIdentifiers);
            sentCursorMessage = YES;
        }

        gMCPAXUICurrentSentMessageIdentifiers = [sentIdentifiers copy];
    });

    if (activationError.length > 0) {
        gMCPAXUICurrentLastActivationError = activationError;
        result[@"ok"] = @NO;
        result[@"error"] = activationError;
    } else {
        gMCPAXUICurrentLastActivationDate = [NSDate date];
        gMCPAXUICurrentLastActivationError = nil;
        [result addEntriesFromDictionary:MCPAXCurrentProcessAXUIClientStatus()];
        result[@"ok"] = @YES;
        result[@"activated"] = @YES;
    }

    result[@"source"] = @"current_process_axui_client_bootstrap";
    result[@"reason"] = reason.length > 0 ? reason : @"ui_tree_retry";
    result[@"loadedAccessibilityUI"] = @(loadedAccessibilityUI);
    if (workspaceBootstrap.count > 0) {
        result[@"workspaceBootstrap"] = workspaceBootstrap;
    }
    if (workspaceBootstrapWarning.length > 0) {
        result[@"workspaceBootstrapWarning"] = workspaceBootstrapWarning;
    }
    result[@"createdDelegate"] = @(createdDelegate);
    result[@"createdClient"] = @(createdClient);
    result[@"setDelegate"] = @(setDelegate);
    result[@"sentRegisterMessage"] = @(sentRegisterMessage);
    result[@"sentCaptionMessage"] = @(sentCaptionMessage);
    result[@"sentCurtainMessage"] = @(sentCurtainMessage);
    result[@"sendCursorMessage"] = @(sendCursorMessage);
    result[@"sentCursorMessage"] = @(sentCursorMessage);
    return result;
}

@implementation AccessibilityManager {
    dispatch_queue_t _axQueue;
    MCPAXAttributeBridge *_axAttributeBridge;
    MCPAXNodeSource *_axNodeSource;
    MCPAXRemoteContextResolver *_contextResolver;
    MCPUIElementSerializer *_uiElementSerializer;
    MCPUIElementsFacade *_uiElementsFacade;
}

+ (instancetype)sharedInstance {
    static AccessibilityManager *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[AccessibilityManager alloc] init];
    });
    return instance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _axQueue = dispatch_queue_create("com.witchan.ios-mcp.ax", DISPATCH_QUEUE_SERIAL);
        _axAttributeBridge = [MCPAXAttributeBridge new];
        _axNodeSource = [[MCPAXNodeSource alloc] initWithAttributeBridge:_axAttributeBridge];
        _contextResolver = [MCPAXRemoteContextResolver new];
        _uiElementSerializer = [MCPUIElementSerializer new];
        __weak typeof(self) weakSelf = self;
        _uiElementsFacade = [[MCPUIElementsFacade alloc] initWithContextResolver:_contextResolver
                                                                      serializer:_uiElementSerializer
                                                        directElementProvider:^NSDictionary *(MCPAXQueryContext *context, CGPoint point, NSString **error) {
            __strong typeof(weakSelf) self = weakSelf;
            if (!self) {
                if (error) *error = @"AccessibilityManager unavailable";
                return nil;
            }
            NSString *directError = nil;
            NSDictionary *element = [self directAXElementAtPoint:point
                                                             pid:context.pid
                                                       contextId:context.contextId
                                                       displayId:context.displayId
                                                           error:&directError];
            if (element) {
                if (error) *error = nil;
                return element;
            }

            if (MCPEnableAXUIClientBootstrap &&
                [self shouldAttemptAXUIClientBootstrapForContext:context]) {
                NSDictionary *bootstrapResult = [self activateVoiceOverRuntimeForContext:context
                                                                                  reason:@"hit_test_retry"];
                if ([bootstrapResult[@"ok"] boolValue]) {
                    NSArray<NSNumber *> *retryDelays = @[@0.15, @0.45, @0.9, @1.5];
                    NSMutableArray<NSString *> *retryErrors = [NSMutableArray array];
                    NSUInteger attemptIndex = 0;
                    for (NSNumber *delayNumber in retryDelays) {
                        attemptIndex++;
                        NSTimeInterval retryDelay = [delayNumber doubleValue];
                        if (retryDelay > 0) {
                            [NSThread sleepForTimeInterval:retryDelay];
                        }

                        MCPAXQueryContext *refreshedContext = [self->_contextResolver frontmostContext];
                        if (refreshedContext) {
                            [self refreshQueryContext:context fromContext:refreshedContext];
                        }

                        NSString *retryError = nil;
                        NSDictionary *retryElement = [self directAXElementAtPoint:point
                                                                              pid:context.pid
                                                                        contextId:context.contextId
                                                                        displayId:context.displayId
                                                                            error:&retryError];
                        if (retryElement) {
                            NSMutableDictionary *mutableElement = [retryElement mutableCopy];
                            mutableElement[@"axRuntimeBootstrap"] = bootstrapResult;
                            mutableElement[@"axRuntimeBootstrapRetryAttempt"] = @(attemptIndex);
                            mutableElement[@"axRuntimeBootstrapRetryDelay"] = @(retryDelay);
                            if (error) *error = nil;
                            return mutableElement;
                        }

                        if (retryError.length > 0) {
                            [retryErrors addObject:[NSString stringWithFormat:@"attempt%lu_after_%.2fs=%@",
                                                    (unsigned long)attemptIndex,
                                                    retryDelay,
                                                    retryError]];
                        }
                    }

                    directError = [NSString stringWithFormat:@"%@; bootstrap=%@; retries=%@",
                                   directError ?: @"direct_ax_failed",
                                   bootstrapResult[@"why"] ?: @"activation attempted",
                                   retryErrors.count > 0 ? [retryErrors componentsJoinedByString:@" | "] : @"no retry diagnostics"];
                } else if ([bootstrapResult[@"error"] isKindOfClass:[NSString class]]) {
                    directError = [NSString stringWithFormat:@"%@; bootstrap=%@",
                                   directError ?: @"direct_ax_failed",
                                   bootstrapResult[@"error"]];
                }
            }

            if (error) *error = directError;
            return nil;
        }];
    }
    return self;
}

- (BOOL)shouldAttemptAXUIClientBootstrapForContext:(MCPAXQueryContext *)context {
    if (!MCPEnableAXUIClientBootstrap || !context) return NO;
    NSDictionary *state = [context.metadata[@"accessibilityState"] isKindOfClass:[NSDictionary class]] ?
        context.metadata[@"accessibilityState"] :
        nil;
    if (state.count == 0) return NO;

    NSString *axRuntimeMode = [state[@"axRuntimeMode"] isKindOfClass:[NSString class]] ?
        state[@"axRuntimeMode"] :
        nil;
    NSNumber *runtimeLikelyActive = [state[@"runtimeLikelyActive"] respondsToSelector:@selector(boolValue)] ?
        state[@"runtimeLikelyActive"] :
        nil;
    NSString *recommendedRegistrarProcess = [state[@"recommendedRegistrarProcess"] isKindOfClass:[NSString class]] ?
        state[@"recommendedRegistrarProcess"] :
        nil;
    NSNumber *voiceOverRunning = [state[@"voiceOverRunning"] respondsToSelector:@selector(boolValue)] ?
        state[@"voiceOverRunning"] :
        nil;
    NSNumber *currentProcessLooksLikeVoiceOverRegistrar = [state[@"currentProcessLooksLikeVoiceOverRegistrar"] respondsToSelector:@selector(boolValue)] ?
        state[@"currentProcessLooksLikeVoiceOverRegistrar"] :
        nil;

    if ([axRuntimeMode isEqualToString:@"inactive"]) {
        return YES;
    }
    if (recommendedRegistrarProcess.length > 0 &&
        ![recommendedRegistrarProcess isEqualToString:@"AccessibilityUIServer"]) {
        return NO;
    }
    if (runtimeLikelyActive && !runtimeLikelyActive.boolValue) {
        return YES;
    }
    if ([axRuntimeMode isEqualToString:@"voiceover_registered"] ||
        [axRuntimeMode isEqualToString:@"active_but_nonregistrar_process"]) {
        return YES;
    }
    if (voiceOverRunning.boolValue && !currentProcessLooksLikeVoiceOverRegistrar.boolValue) {
        return YES;
    }
    return NO;
}


- (NSDictionary *)activateVoiceOverRuntimeForContext:(MCPAXQueryContext *)context
                                              reason:(NSString *)reason {
    NSMutableDictionary *result = [NSMutableDictionary dictionary];
    NSString *normalizedReason = reason.length > 0 ? reason : @"ui_tree_retry";
    result[@"reason"] = normalizedReason;
    if (context.bundleId.length > 0) result[@"bundleId"] = context.bundleId;
    if (context.pid > 0) result[@"frontmostPid"] = @(context.pid);
    if (context.contextId > 0) result[@"contextId"] = @(context.contextId);
    if (context.displayId > 0) result[@"displayId"] = @(context.displayId);

    NSDictionary *currentProcessAXUI = MCPAXActivateCurrentProcessAXUIClientBootstrap(NO, normalizedReason);
    if ([currentProcessAXUI isKindOfClass:[NSDictionary class]]) {
        result[@"currentProcessAXUIClient"] = currentProcessAXUI;
    }

    NSDictionary *workspaceBootstrap =
        [currentProcessAXUI[@"workspaceBootstrap"] isKindOfClass:[NSDictionary class]] ?
        currentProcessAXUI[@"workspaceBootstrap"] :
        nil;
    BOOL workspaceReady = [workspaceBootstrap[@"ok"] boolValue] ||
        [currentProcessAXUI[@"applicationAccessibilityEnabled"] boolValue] ||
        [currentProcessAXUI[@"voiceOverTouchUsageConfirmed"] boolValue];
    BOOL clientReady = [currentProcessAXUI[@"clientCreated"] boolValue] ||
        [currentProcessAXUI[@"activated"] boolValue] ||
        [currentProcessAXUI[@"sentRegisterMessage"] boolValue];
    BOOL currentProcessReady = [currentProcessAXUI[@"ok"] boolValue] && workspaceReady && clientReady;

    if (currentProcessReady) {
        result[@"currentProcessAXUIReady"] = @YES;
        result[@"axRuntimeReady"] = @YES;
        result[@"voiceOverTouchReady"] = @NO;
        result[@"ok"] = @YES;
        result[@"why"] = @"Current-process AXUIClient/workspace bootstrap looks primed for direct AXRuntime UI tree queries.";
        return result;
    }

    if ([currentProcessAXUI isKindOfClass:[NSDictionary class]]) {
        result[@"currentProcessAXUIReady"] = @NO;
    }
    result[@"ok"] = @NO;
    result[@"axRuntimeReady"] = @NO;
    result[@"voiceOverTouchReady"] = @NO;
    result[@"error"] = [currentProcessAXUI[@"error"] isKindOfClass:[NSString class]] ?
        currentProcessAXUI[@"error"] :
        @"Current-process AXUIClient/workspace bootstrap did not report a ready AX state";
    return result;
}

- (void)refreshQueryContext:(MCPAXQueryContext *)target fromContext:(MCPAXQueryContext *)source {
    if (!target || !source) return;
    target.pid = source.pid;
    target.bundleId = source.bundleId;
    target.processName = source.processName;
    target.sceneIdentifier = source.sceneIdentifier;
    target.contextId = source.contextId;
    target.displayId = source.displayId;
    target.resolverStrategy = source.resolverStrategy;
    target.resolutionTrace = source.resolutionTrace;
    target.metadata = source.metadata;
}

#pragma mark - Direct AX Runtime

- (NSDictionary *)directAXElementAtPoint:(CGPoint)point
                                     pid:(pid_t)pid
                               contextId:(uint32_t)contextId
                               displayId:(uint32_t)displayId
                                   error:(NSString **)error {
    return [_axNodeSource elementAtPoint:point
                                     pid:pid
                               contextId:contextId
                               displayId:displayId
              allowParameterizedHitTest:MCPEnableAXParameterizedHitTest
                                   error:error];
}

#pragma mark - Get UI Elements

- (NSDictionary * _Nullable)compactPayloadForContext:(MCPAXQueryContext *)context
                                         maxElements:(NSInteger)maxElements
                                         visibleOnly:(BOOL)visibleOnly
                                       clickableOnly:(BOOL)clickableOnly
                                               error:(NSString * _Nullable * _Nullable)error {
    if (!context || context.pid <= 0) {
        if (error) *error = @"No frontmost application context available";
        return nil;
    }

    NSString *compactError = nil;
    NSDictionary *payload = [_axNodeSource compactElementsForPid:context.pid
                                                       bundleId:context.bundleId
                                                      contextId:context.contextId
                                                      displayId:context.displayId
                                                    maxElements:maxElements
                                                    visibleOnly:visibleOnly
                                                  clickableOnly:clickableOnly
                                                          error:&compactError];
    if (![payload isKindOfClass:[NSDictionary class]]) {
        if (error) *error = compactError ?: @"No compact UI elements available";
        return nil;
    }

    NSMutableDictionary *mutablePayload = [payload mutableCopy];
    if (context.processName.length > 0) {
        mutablePayload[@"processName"] = context.processName;
    }
    NSDictionary *contextDictionary = [context dictionaryRepresentation];
    if (contextDictionary.count > 0) {
        mutablePayload[@"frontmostContext"] = contextDictionary;
    }
    if (error) *error = nil;
    return mutablePayload;
}

- (void)getCompactUIElementsWithMaxElements:(NSInteger)maxElements
                                visibleOnly:(BOOL)visibleOnly
                              clickableOnly:(BOOL)clickableOnly
                                 completion:(void (^)(NSDictionary *, NSString *))completion {
    if (maxElements <= 0) maxElements = 2000;

    dispatch_async(_axQueue, ^{
        @try {
            MCPAXQueryContext *context = [self->_contextResolver frontmostContext];
            if (!context || context.pid <= 0) {
                if (completion) completion(nil, @"No frontmost application context available");
                return;
            }

            NSString *compactError = nil;
            NSDictionary *payload = [self compactPayloadForContext:context
                                                       maxElements:maxElements
                                                       visibleOnly:visibleOnly
                                                     clickableOnly:clickableOnly
                                                             error:&compactError];
            if (payload) {
                if (completion) completion(payload, nil);
                return;
            }

            NSDictionary *bootstrapResult = nil;
            BOOL attemptedBootstrap = NO;
            if (MCPEnableAXUIClientBootstrap &&
                [self shouldAttemptAXUIClientBootstrapForContext:context]) {
                attemptedBootstrap = YES;
                bootstrapResult = [self activateVoiceOverRuntimeForContext:context
                                                                     reason:@"compact_ui_elements_retry"];
            }

            NSArray<NSNumber *> *retryDelays = attemptedBootstrap ?
                @[@0.15, @0.45, @0.9, @1.5] :
                @[@0.15, @0.45];
            NSMutableArray<NSString *> *retryErrors = [NSMutableArray array];
            NSUInteger attemptIndex = 0;
            for (NSNumber *delayNumber in retryDelays) {
                attemptIndex++;
                NSTimeInterval retryDelay = delayNumber.doubleValue;
                if (retryDelay > 0) {
                    [NSThread sleepForTimeInterval:retryDelay];
                }

                MCPAXQueryContext *refreshedContext = [self->_contextResolver frontmostContext];
                if (refreshedContext) {
                    [self refreshQueryContext:context fromContext:refreshedContext];
                }

                NSString *retryError = nil;
                NSDictionary *retryPayload = [self compactPayloadForContext:context
                                                                 maxElements:maxElements
                                                                 visibleOnly:visibleOnly
                                                               clickableOnly:clickableOnly
                                                                       error:&retryError];
                if (retryPayload) {
                    NSMutableDictionary *mutablePayload = [retryPayload mutableCopy];
                    if ([bootstrapResult isKindOfClass:[NSDictionary class]]) {
                        mutablePayload[@"axRuntimeBootstrap"] = bootstrapResult;
                    }
                    mutablePayload[@"compactAXRetryAttempt"] = @(attemptIndex);
                    mutablePayload[@"compactAXRetryDelay"] = @(retryDelay);
                    if (completion) completion(mutablePayload, nil);
                    return;
                }

                if (retryError.length > 0) {
                    [retryErrors addObject:[NSString stringWithFormat:@"attempt%lu_after_%.2fs=%@",
                                            (unsigned long)attemptIndex,
                                            retryDelay,
                                            retryError]];
                }
            }

            if ([bootstrapResult isKindOfClass:[NSDictionary class]]) {
                NSString *bootstrapSummary = [bootstrapResult[@"ok"] boolValue] ?
                    (bootstrapResult[@"why"] ?: @"activation attempted") :
                    (bootstrapResult[@"error"] ?: @"activation did not report ready");
                compactError = [NSString stringWithFormat:@"%@; bootstrap=%@; retries=%@",
                                compactError ?: @"compact_ax_failed",
                                bootstrapSummary,
                                retryErrors.count > 0 ? [retryErrors componentsJoinedByString:@" | "] : @"no retry diagnostics"];
            } else if (retryErrors.count > 0) {
                compactError = [NSString stringWithFormat:@"%@; retries=%@",
                                compactError ?: @"compact_ax_failed",
                                [retryErrors componentsJoinedByString:@" | "]];
            }

            if (completion) completion(nil, compactError ?: @"No compact UI elements available");
        } @catch (NSException *exception) {
            NSString *exceptionError = [NSString stringWithFormat:@"get_compact_ui_elements exception: %@: %@",
                                        exception.name,
                                        exception.reason ?: @"<no reason>"];
            if (completion) completion(nil, exceptionError);
        }
    });
}

#pragma mark - Get Element At Point

- (void)getElementAtPoint:(CGPoint)point
               completion:(void (^)(NSDictionary *, NSString *))completion {
    dispatch_async(_axQueue, ^{
        @try {
            NSString *facadeError = nil;
            NSDictionary *element = [_uiElementsFacade elementAtPoint:point error:&facadeError];
            if (element) {
                if (completion) completion(element, nil);
                return;
            }
            if (completion) completion(nil, facadeError ?: @"No element found");
        } @catch (NSException *exception) {
            NSString *exceptionError = [NSString stringWithFormat:@"get_element_at_point exception: %@: %@",
                                        exception.name,
                                        exception.reason ?: @"<no reason>"];
            if (completion) completion(nil, exceptionError);
        }
    });
}

#pragma mark - Frontmost App

- (NSDictionary *)frontmostApplicationInfo {
    return [_contextResolver frontmostContextDictionary] ?: @{};
}

@end
