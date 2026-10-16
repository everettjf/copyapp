#import <UIKit/UIKit.h>
#import <CoreFoundation/CoreFoundation.h>
#import "MCPServer.h"
#import "MCPLogger.h"
#import "IOSMCPPreferences.h"

#define IOS_MCP_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *message = [NSString stringWithFormat:(fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp] %@", message); \
        [MCPLogger logMessage:message]; \
    } \
} while (0)

static BOOL ios_mcp_enabled_preference(void) {
    CFPropertyListRef value = CFPreferencesCopyAppValue((__bridge CFStringRef)IOS_MCP_ENABLED_PREFERENCE_KEY,
                                                        (__bridge CFStringRef)IOS_MCP_PREFERENCES_DOMAIN);
    if (!value) {
        return YES;
    }

    BOOL enabled = YES;
    CFTypeID typeID = CFGetTypeID(value);
    if (typeID == CFBooleanGetTypeID()) {
        enabled = CFBooleanGetValue((CFBooleanRef)value);
    } else if (typeID == CFNumberGetTypeID()) {
        int numericValue = 0;
        CFNumberGetValue((CFNumberRef)value, kCFNumberIntType, &numericValue);
        enabled = numericValue != 0;
    }

    CFRelease(value);
    return enabled;
}

static void ios_mcp_write_enabled_preference(BOOL enabled) {
    CFPreferencesSetAppValue((__bridge CFStringRef)IOS_MCP_ENABLED_PREFERENCE_KEY,
                             enabled ? kCFBooleanTrue : kCFBooleanFalse,
                             (__bridge CFStringRef)IOS_MCP_PREFERENCES_DOMAIN);
    CFPreferencesAppSynchronize((__bridge CFStringRef)IOS_MCP_PREFERENCES_DOMAIN);
}

static BOOL ios_mcp_is_springboard_process(void) {
    NSString *processName = [[NSProcessInfo processInfo] processName];
    if ([processName isEqualToString:@"SpringBoard"]) {
        return YES;
    }

    NSString *bundleIdentifier = [[NSBundle mainBundle] bundleIdentifier];
    return [bundleIdentifier isEqualToString:@"com.apple.springboard"];
}

static uint16_t ios_mcp_start_server(void) {
    uint16_t port = IOSMCPConfiguredPort();
    // A Settings START is also the recovery path when the listener still
    // exists but its HTTP workers are wedged. Force a serialized restart.
    [[MCPServer sharedInstance] restartOnPort:port];
    return port;
}

static void ios_mcp_stop_server(void) {
    [[MCPServer sharedInstance] stop];
}

static void ios_mcp_handle_control_notification(CFNotificationCenterRef center,
                                                void *observer,
                                                CFStringRef name,
                                                const void *object,
                                                CFDictionaryRef userInfo) {
    if (!name) {
        return;
    }

    if (CFEqual(name, IOS_MCP_DARWIN_NOTIFICATION_START)) {
        ios_mcp_write_enabled_preference(YES);
        uint16_t port = ios_mcp_start_server();
        IOS_MCP_LOG(@"Received start request from Settings on port %u", (unsigned int)port);
        return;
    }

    if (CFEqual(name, IOS_MCP_DARWIN_NOTIFICATION_STOP)) {
        ios_mcp_write_enabled_preference(NO);
        ios_mcp_stop_server();
        IOS_MCP_LOG(@"Received stop request from Settings");
    }
}

static void ios_mcp_autostart_if_needed(NSString *reason) {
    if (!ios_mcp_is_springboard_process()) {
        return;
    }

    if (!ios_mcp_enabled_preference()) {
        IOS_MCP_LOG(@"Auto-start skipped (%@): disabled in Settings", reason ?: @"unknown");
        return;
    }

    uint16_t port = IOSMCPConfiguredPort();
    MCPServer *server = [MCPServer sharedInstance];
    if (server.isRunning && server.port == port) {
        IOS_MCP_LOG(@"Auto-start skipped (%@): already running on port %d",
                    reason ?: @"unknown",
                    server.port);
        return;
    }

    IOS_MCP_LOG(@"Auto-start attempt (%@) on port %u...",
                reason ?: @"unknown",
                (unsigned int)port);
    [[MCPServer sharedInstance] startOnPort:port];

    if (!server.isRunning) {
        IOS_MCP_LOG(@"Auto-start attempt (%@) did not start server; later retry may recover",
                    reason ?: @"unknown");
    }
}

static void ios_mcp_schedule_autostart_attempt(NSString *reason, NSTimeInterval delay) {
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * (NSTimeInterval)NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        ios_mcp_autostart_if_needed(reason);
    });
}

static void ios_mcp_schedule_bootstrap_autostart(NSString *reason) {
    if (!ios_mcp_is_springboard_process()) {
        return;
    }

    /*
     Do not rely only on -[SpringBoard applicationDidFinishLaunching:].
     On some jailbreak/iOS combinations after sbreload the tweak can be loaded
     before the hook-driven launch callback is useful, and the first UI action
     (for example Home) becomes the accidental trigger.  Schedule several
     idempotent attempts from the constructor/runloop/lifecycle path so the
     socket is brought up as soon as the new SpringBoard is alive.
     */
    const NSTimeInterval delays[] = {0.2, 1.0, 2.0, 5.0, 10.0, 20.0};
    const size_t count = sizeof(delays) / sizeof(delays[0]);
    for (size_t i = 0; i < count; i++) {
        NSString *attemptReason = [NSString stringWithFormat:@"%@#%zu", reason ?: @"bootstrap", i + 1];
        ios_mcp_schedule_autostart_attempt(attemptReason, delays[i]);
    }
}

static void ios_mcp_register_lifecycle_notifications(void) {
    if (!ios_mcp_is_springboard_process()) {
        return;
    }

    static BOOL registered = NO;
    if (registered) {
        return;
    }
    registered = YES;

    NSNotificationCenter *center = [NSNotificationCenter defaultCenter];
    [center addObserverForName:UIApplicationDidFinishLaunchingNotification
                        object:nil
                         queue:[NSOperationQueue mainQueue]
                    usingBlock:^(__unused NSNotification *notification) {
        IOS_MCP_LOG(@"UIApplicationDidFinishLaunchingNotification observed");
        ios_mcp_schedule_bootstrap_autostart(@"UIApplicationDidFinishLaunching");
    }];

    [center addObserverForName:UIApplicationDidBecomeActiveNotification
                        object:nil
                         queue:[NSOperationQueue mainQueue]
                    usingBlock:^(__unused NSNotification *notification) {
        IOS_MCP_LOG(@"UIApplicationDidBecomeActiveNotification observed");
        ios_mcp_schedule_autostart_attempt(@"UIApplicationDidBecomeActive", 0.1);
    }];
}

static void ios_mcp_register_control_notifications(void) {
    CFNotificationCenterRef center = CFNotificationCenterGetDarwinNotifyCenter();
    CFNotificationCenterAddObserver(center,
                                    NULL,
                                    ios_mcp_handle_control_notification,
                                    IOS_MCP_DARWIN_NOTIFICATION_START,
                                    NULL,
                                    CFNotificationSuspensionBehaviorDeliverImmediately);
    CFNotificationCenterAddObserver(center,
                                    NULL,
                                    ios_mcp_handle_control_notification,
                                    IOS_MCP_DARWIN_NOTIFICATION_STOP,
                                    NULL,
                                    CFNotificationSuspensionBehaviorDeliverImmediately);
}

// Log immediately when dylib is loaded into process
__attribute__((constructor)) static void ios_mcp_init(void) {
    IOS_MCP_LOG(@"dylib loaded into process: %@", [[NSProcessInfo processInfo] processName]);
    ios_mcp_register_control_notifications();

    if (ios_mcp_is_springboard_process()) {
        ios_mcp_register_lifecycle_notifications();
        /*
         Start once directly from the constructor as well.  The delayed
         dispatch_after retries are still kept as a safety net, but on some
         rootful/Substitute iOS 14 devices SpringBoard may not deliver the
         lifecycle notifications until after the first Home interaction.  A
         synchronous constructor start keeps the MCP socket available
         immediately after sbreload/respring.
         */
        ios_mcp_autostart_if_needed(@"constructor-immediate");
        ios_mcp_schedule_bootstrap_autostart(@"constructor");
    }
}

%hook SpringBoard

- (void)applicationDidFinishLaunching:(id)application {
    %orig;

    IOS_MCP_LOG(@"SpringBoard applicationDidFinishLaunching fired");

    ios_mcp_schedule_bootstrap_autostart(@"SpringBoard.applicationDidFinishLaunching");
}

%end
