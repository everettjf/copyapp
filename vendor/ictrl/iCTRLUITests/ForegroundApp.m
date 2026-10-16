#include <signal.h>
#include <errno.h>
#import "ForegroundApp.h"
#import <XCTest/XCTest.h>
#import <objc/message.h>
#import <objc/runtime.h>

// Private XCTest accessibility client (present in the XCTest framework loaded
// from the device's /Developer at runtime). We declare only what we call.
@interface XCAXClient_iOS : NSObject
+ (instancetype)sharedClient;
// Returns an array of XCAccessibilityElement for running apps; the first is
// typically the frontmost/active application.
- (id)activeApplications;
- (id)systemApplication;
@end

// XCAccessibilityElement exposes the process id of an app element.
@interface XCAccessibilityElement : NSObject
@property (nonatomic, readonly) pid_t processIdentifier;
@end

// Bridge from pid → bundle id via the device info service used by XCTest.
// Also exposes openDefaultApplicationForURL:completion: — the XCTest-sanctioned
// way to open a URL from the runner process (iOS 16.4+), which UIApplication and
// LSApplicationWorkspace both refuse to do from inside XCTest.
@interface XCTRunnerDaemonSession : NSObject
+ (instancetype)sharedSession;
- (void)openDefaultApplicationForURL:(NSURL *)url completion:(void (^)(BOOL result, NSError *error))completion;
@end

// Private MobileCoreServices API listing/opening installed applications.
@interface LSApplicationWorkspace : NSObject
+ (instancetype)defaultWorkspace;
- (NSArray *)allApplications;
- (NSArray *)allInstalledApplications;
- (BOOL)openApplicationWithBundleID:(NSString *)bundleId;  // non-blocking launch
- (BOOL)openURL:(id)url;
- (BOOL)openURL:(id)url withOptions:(id)options;
- (BOOL)openSensitiveURL:(id)url withOptions:(id)options;
@end

// LSApplicationProxy exposes bundle id / display name / type.
@interface LSApplicationProxy : NSObject
@property (nonatomic, readonly) NSString *applicationIdentifier;   // bundle id
@property (nonatomic, readonly) NSString *localizedName;
@property (nonatomic, readonly) NSString *applicationType;          // "User" / "System"
@end

@implementation ForegroundApp

+ (double)setAXTimeout:(double)seconds {
    @try {
        Class deviceClass = NSClassFromString(@"XCUIDevice");
        id device = [deviceClass performSelector:NSSelectorFromString(@"sharedDevice")];
        SEL ifaceSel = NSSelectorFromString(@"accessibilityInterface");
        if (![device respondsToSelector:ifaceSel]) { return -1; }
        id client = [device performSelector:ifaceSel];
        double previous = -1;
        SEL getSel = NSSelectorFromString(@"AXTimeout");
        if ([client respondsToSelector:getSel]) {
            double (*getFn)(id, SEL) = (double (*)(id, SEL))objc_msgSend;
            previous = getFn(client, getSel);
        }
        SEL setSel = NSSelectorFromString(@"_setAXTimeout:error:");
        if ([client respondsToSelector:setSel]) {
            NSError *err = nil;
            BOOL (*setFn)(id, SEL, double, NSError **) = (BOOL (*)(id, SEL, double, NSError **))objc_msgSend;
            if (!setFn(client, setSel, seconds, &err)) { return -2; }
            return previous;
        }
        SEL plainSel = NSSelectorFromString(@"setAXTimeout:");
        if ([client respondsToSelector:plainSel]) {
            void (*fn)(id, SEL, double) = (void (*)(id, SEL, double))objc_msgSend;
            fn(client, plainSel, seconds);
            return previous;
        }
        return -1;
    } @catch (__unused NSException *e) {
        return -3;
    }
}

+ (pid_t)frontmostPID {
    @try {
        Class deviceClass = NSClassFromString(@"XCUIDevice");
        SEL sharedSel = NSSelectorFromString(@"sharedDevice");
        SEL ifaceSel = NSSelectorFromString(@"accessibilityInterface");
        if (![deviceClass respondsToSelector:sharedSel]) { return 0; }
        id device = [deviceClass performSelector:sharedSel];
        if (![device respondsToSelector:ifaceSel]) { return 0; }
        id client = [device performSelector:ifaceSel];
        SEL sel = NSSelectorFromString(@"activeApplications");
        if (![client respondsToSelector:sel]) { return 0; }
        NSArray *apps = [client performSelector:sel];
        if (![apps isKindOfClass:[NSArray class]] || apps.count == 0) { return 0; }
        // iOS 27 lists exactly one element, the app in front (SpringBoard at
        // the home screen). Its pid is readable even where its bundle id isn't.
        id element = apps.firstObject;
        SEL pidSel = NSSelectorFromString(@"processIdentifier");
        // A crashed app can stay first in the list, sending every later read
        // to its dead pid. Skip pids that no longer exist
        // (kill(pid, 0) only checks; ESRCH = no such process).
        for (id a in apps) {
            if (![a respondsToSelector:pidSel]) { continue; }
            pid_t p = [[a valueForKey:@"processIdentifier"] intValue];
            if (p > 0 && (kill(p, 0) == 0 || errno != ESRCH)) { element = a; break; }
        }
        if (apps.count > 1) {
            // Diagnostic: which order does a multi-app list come in? Reads
            // landing on a stale app suggest firstObject is not always front.
            NSMutableArray *pids = [NSMutableArray array];
            for (id a in apps) {
                if ([a respondsToSelector:pidSel]) { [pids addObject:[a valueForKey:@"processIdentifier"] ?: @0]; }
            }
            static NSString *lastLogged;
            NSString *line = [pids componentsJoinedByString:@","];
            if (![line isEqualToString:lastLogged]) {
                lastLogged = line;
                NSLog(@"🔎 activeApplications count=%lu pids=[%@]", (unsigned long)apps.count, line);
            }
        }
        if (![element respondsToSelector:pidSel]) { return 0; }
        NSMethodSignature *sig = [element methodSignatureForSelector:pidSel];
        NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
        inv.selector = pidSel;
        [inv invokeWithTarget:element];
        pid_t pid = 0;
        [inv getReturnValue:&pid];
        return pid;
    } @catch (__unused NSException *e) {
        return 0;
    }
}

+ (pid_t)processIDForBundleID:(NSString *)bundleId {
    if (bundleId.length == 0) { return 0; }
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return 0; }
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id app = initFn([appClass alloc], @selector(initWithBundleIdentifier:), bundleId);
        SEL pidSel = NSSelectorFromString(@"processID");
        if (!app || ![app respondsToSelector:pidSel]) { return 0; }
        pid_t (*pidFn)(id, SEL) = (pid_t (*)(id, SEL))objc_msgSend;
        return pidFn(app, pidSel);
    } @catch (__unused NSException *e) {
        return 0;
    }
}

+ (nullable NSString *)currentBundleID {
    @try {
        // +sharedClient is gone on newer iOS: XCAXClient_iOS exposes no class
        // methods at all there, so the old call threw "unrecognized selector",
        // was swallowed below, and this returned nil — which surfaced as
        // foreground_app:null and a stream of bogus "app is in the background"
        // errors even with the app plainly on screen. Reach the client the way
        // XCUIElementQuery does (device -> accessibilityInterface) and keep
        // +sharedClient only as the legacy fallback.
        id client = nil;
        @try {
            Class deviceClass = NSClassFromString(@"XCUIDevice");
            SEL sharedSel = NSSelectorFromString(@"sharedDevice");
            if ([deviceClass respondsToSelector:sharedSel]) {
                id device = [deviceClass performSelector:sharedSel];
                SEL ifaceSel = NSSelectorFromString(@"accessibilityInterface");
                if ([device respondsToSelector:ifaceSel]) {
                    client = [device performSelector:ifaceSel];
                }
            }
        } @catch (__unused NSException *e) {}

        if (!client) {
            Class clientClass = NSClassFromString(@"XCAXClient_iOS");
            if (!clientClass) { return nil; }
            SEL sharedClientSel = NSSelectorFromString(@"sharedClient");
            if (![clientClass respondsToSelector:sharedClientSel]) { return nil; }
            client = [clientClass performSelector:sharedClientSel];
        }
        if (!client) { return nil; }

        // activeApplications: first element is the frontmost app.
        SEL sel = NSSelectorFromString(@"activeApplications");
        if (![client respondsToSelector:sel]) { return nil; }

        NSArray *apps = [client performSelector:sel];
        if (![apps isKindOfClass:[NSArray class]] || apps.count == 0) { return nil; }

        // SpringBoard is always in this list, so it is skipped in favour of a
        // real app — but only an app that says it is in front. When SpringBoard
        // itself is what's showing (a system alert, the home screen), the next
        // entry can be an app already sent to the background; returning it made
        // callers query a window-less app, which on iOS 16 spun XCTest at 100%
        // CPU until the system killed the runner. state is answered by
        // testmanagerd without touching the accessibility tree — milliseconds.
        NSString *springboard = nil;
        for (id element in apps) {
            NSString *bid = [self bundleIDForElement:element];
            if (bid.length == 0) { continue; }
            if ([bid isEqualToString:@"com.apple.springboard"]) { springboard = bid; continue; }
            NSInteger state = [self appStateForBundleID:bid];
            if (state == 4 || state == 0) { return bid; }   // runningForeground, or unknown
        }
        if (springboard) { return springboard; }
        // Fallback: return whatever the first element resolves to.
        return [self bundleIDForElement:apps.firstObject];
    } @catch (__unused NSException *e) {
        return nil;
    }
}

+ (nullable NSString *)bundleIDForElement:(id)element {
    @try {
        // Try a direct bundleID-ish selector first.
        for (NSString *name in @[@"bundleIdentifier", @"bundleID"]) {
            SEL s = NSSelectorFromString(name);
            if ([element respondsToSelector:s]) {
                id v = [element performSelector:s];
                if ([v isKindOfClass:[NSString class]]) { return v; }
            }
        }
        // Otherwise resolve via process identifier.
        SEL pidSel = NSSelectorFromString(@"processIdentifier");
        if ([element respondsToSelector:pidSel]) {
            NSMethodSignature *sig = [element methodSignatureForSelector:pidSel];
            NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
            inv.selector = pidSel;
            [inv invokeWithTarget:element];
            pid_t pid = 0;
            [inv getReturnValue:&pid];
            if (pid > 0) {
                return [self bundleIDForPID:pid];
            }
        }
    } @catch (__unused NSException *e) {}
    return nil;
}

+ (nullable NSString *)bundleIDForPID:(pid_t)pid {
    @try {
        // XCUIApplication can be constructed by pid via a private initializer in
        // some XCTest versions; if unavailable, we can't resolve here.
        Class appClass = NSClassFromString(@"XCUIApplication");
        SEL initSel = NSSelectorFromString(@"initWithProcessID:");
        if (appClass && [appClass instancesRespondToSelector:initSel]) {
            id app = [appClass alloc];
            NSMethodSignature *sig = [app methodSignatureForSelector:initSel];
            NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
            inv.selector = initSel;
            [inv setArgument:&pid atIndex:2];
            [inv invokeWithTarget:app];
            void *result = NULL;
            [inv getReturnValue:&result];
            id appInstance = (__bridge id)result;
            if ([appInstance respondsToSelector:NSSelectorFromString(@"bundleID")]) {
                id bid = [appInstance performSelector:NSSelectorFromString(@"bundleID")];
                if ([bid isKindOfClass:[NSString class]]) { return bid; }
            }
        }
    } @catch (__unused NSException *e) {}
    return nil;
}

+ (nullable NSArray<NSDictionary *> *)installedAppsUserOnly:(BOOL)userOnly {
    @try {
        Class wsClass = NSClassFromString(@"LSApplicationWorkspace");
        if (!wsClass) { return nil; }
        id ws = [wsClass performSelector:@selector(defaultWorkspace)];
        if (!ws) { return nil; }

        NSArray *apps = nil;
        // WDA uses allApplications; try it first, fall back to allInstalledApplications.
        if ([ws respondsToSelector:@selector(allApplications)]) {
            apps = [ws performSelector:@selector(allApplications)];
        }
        if (![apps isKindOfClass:[NSArray class]] || apps.count == 0) {
            if ([ws respondsToSelector:@selector(allInstalledApplications)]) {
                apps = [ws performSelector:@selector(allInstalledApplications)];
            }
        }
        if (![apps isKindOfClass:[NSArray class]]) { return nil; }

        NSMutableArray *out = [NSMutableArray array];
        for (id proxy in apps) {
            @try {
                NSString *bid = nil, *name = nil, *type = nil;
                if ([proxy respondsToSelector:@selector(applicationIdentifier)]) {
                    bid = [proxy performSelector:@selector(applicationIdentifier)];
                }
                if ([proxy respondsToSelector:@selector(localizedName)]) {
                    name = [proxy performSelector:@selector(localizedName)];
                }
                if ([proxy respondsToSelector:@selector(applicationType)]) {
                    type = [proxy performSelector:@selector(applicationType)];
                }
                if (bid.length == 0) { continue; }
                if (userOnly && type && ![type isEqualToString:@"User"]) { continue; }
                [out addObject:@{
                    @"bundle_id": bid ?: @"",
                    @"name": name ?: @"",
                    @"type": type ?: @"",
                }];
            } @catch (__unused NSException *e) {}
        }
        // Sort by name for stable, readable output.
        [out sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
            return [a[@"name"] localizedCaseInsensitiveCompare:b[@"name"]];
        }];
        return out;
    } @catch (__unused NSException *e) {
        return nil;
    }
}

+ (BOOL)activateOrLaunchBundleID:(NSString *)bundleId {
    if (bundleId.length == 0) { return NO; }
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return NO; }
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id app = initFn([appClass alloc], @selector(initWithBundleIdentifier:), bundleId);
        if (!app) { return NO; }
        // `running` distinguishes the two cases; activate does nothing to a
        // process that hasn't started, and launch on a running app restarts it.
        BOOL running = NO;
        if ([app respondsToSelector:@selector(running)]) {
            BOOL (*runningFn)(id, SEL) = (BOOL (*)(id, SEL))objc_msgSend;
            running = runningFn(app, @selector(running));
        }
        SEL sel = running ? @selector(activate) : @selector(launch);
        if ([app respondsToSelector:sel]) {
            [app performSelector:sel];
            return YES;
        }
        return NO;
    } @catch (NSException *e) {
        NSLog(@"iCTRL: activateOrLaunch caught exception for %@: %@", bundleId, e.reason);
        return NO;
    }
}

+ (BOOL)safeActivateBundleID:(NSString *)bundleId {
    if (bundleId.length == 0) { return NO; }
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return NO; }
        // -[XCUIApplication initWithBundleIdentifier:]
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id app = initFn([appClass alloc], @selector(initWithBundleIdentifier:), bundleId);
        if (!app) { return NO; }
        // -[XCUIApplication activate] can throw an XCTest NSException (e.g. the app
        // isn't installed / can't be brought up). Swallow it here so it never
        // reaches the XCTest terminate handler and aborts the runner.
        if ([app respondsToSelector:@selector(activate)]) {
            [app performSelector:@selector(activate)];
        }
        return YES;
    } @catch (NSException *e) {
        NSLog(@"iCTRL: safeActivate caught exception for %@: %@", bundleId, e.reason);
        return NO;
    }
}

+ (id)axInterface {
    id device = [NSClassFromString(@"XCUIDevice") performSelector:NSSelectorFromString(@"sharedDevice")];
    return [device performSelector:NSSelectorFromString(@"accessibilityInterface")];
}

+ (nullable NSDictionary *)visibleListParts:(NSString *)bundleId screen:(CGRect)screen maxElements:(NSInteger)maxElements {
    // The visible part of a list without walking the rows scrolled past: a
    // shallow snapshot (few children a node) finds the list, the list names
    // its visible cells, and only those are snapshotted. Its cost stays flat
    // however far the list has scrolled, while a full read keeps growing.
    @try {
        CFAbsoluteTime t0 = CFAbsoluteTimeGetCurrent();
        id root = [self boundedSnapshotForBundleID:bundleId maxDepth:30 maxChildren:12];
        double shallowMs = (CFAbsoluteTimeGetCurrent() - t0) * 1000;
        if (!root) { return nil; }
        id iface = [self axInterface];
        SEL attrSel = NSSelectorFromString(@"attributesForElement:attributes:error:");
        SEL reqSel = NSSelectorFromString(@"requestSnapshotForElement:attributes:parameters:error:");
        if (![iface respondsToSelector:attrSel] || ![iface respondsToSelector:reqSel]) { return nil; }
        id (*attrFn)(id, SEL, id, id, NSError **) = (id (*)(id, SEL, id, id, NSError **))objc_msgSend;
        id (*reqFn)(id, SEL, id, id, id, NSError **) = (id (*)(id, SEL, id, id, id, NSError **))objc_msgSend;
        // The innermost tall table / collection view with visible cells:
        // deepest first, then smallest. A feed's table can sit in a cell of a
        // full-screen pager the same size; reading the pager's one page cell
        // instead would lose the inner table's lower rows.
        NSArray *bestCells = nil; id bestNode = nil; double bestArea = 0; id bestCount = nil; NSInteger bestDepth = -1;
        NSMutableArray *stack = [NSMutableArray arrayWithObject:@[root, @0]];
        while (stack.count) {
            NSArray *top = stack.lastObject; [stack removeLastObject];
            id n = top[0]; NSInteger depth = [top[1] integerValue];
            for (id c in [n valueForKey:@"children"] ?: @[]) [stack addObject:@[c, @(depth + 1)]];
            NSUInteger type = [[n valueForKey:@"elementType"] unsignedIntegerValue];
            if (type != 26 && type != 32) continue;
            CGRect f = [[n valueForKey:@"frame"] CGRectValue];
            if (f.size.height < screen.size.height * 0.4 || !CGRectIntersectsRect(f, screen)) continue;
            NSError *err = nil;
            NSDictionary *vals = attrFn(iface, attrSel, [n valueForKey:@"accessibilityElement"],
                                        @[@"XC_kAXXCAttributeVisibleCells", @"XC_kAXXCAttributeChildrenCount"], &err);
            id cells = nil, count = nil;
            for (id k in vals) {
                if ([[k description] containsString:@"VisibleCells"]) cells = vals[k];
                if ([[k description] containsString:@"ChildrenCount"]) count = vals[k];
            }
            double area = f.size.width * f.size.height;
            if ([cells isKindOfClass:[NSArray class]] && [cells count] > 0
                && (bestNode == nil || depth > bestDepth || (depth == bestDepth && area < bestArea))) {
                bestCells = cells; bestNode = n; bestArea = area; bestCount = count; bestDepth = depth;
            }
        }
        if (!bestNode) { return nil; }
        NSInteger n = 0; BOOL trunc = NO;
        NSString *rootBody = [self renderBoundedSnapshot:root maxDepth:30 maxElements:maxElements visibleRect:screen
                                            nodesWritten:&n truncated:&trunc] ?: @"";
        NSArray *attrs = @[@"XC_kAXXCAttributeLabel", @"XC_kAXXCAttributeValue", @"XC_kAXXCAttributeFrame",
                           @"XC_kAXXCAttributeElementType", @"XC_kAXXCAttributeIdentifier",
                           @"XC_kAXXCAttributePlaceholderValue"];
        NSMutableArray *bodies = [NSMutableArray array];
        t0 = CFAbsoluteTimeGetCurrent();
        for (id cell in bestCells) {
            NSError *e2 = nil;
            // 24 levels: a feed cell can hold a list nested more than a dozen
            // levels deep, whose labels a shallower snapshot cuts off.
            id res = reqFn(iface, reqSel, cell, attrs, @{@"maxDepth": @24, @"maxChildren": @50, @"maxArrayCount": @50}, &e2);
            id snap = nil;
            @try { snap = [res valueForKey:@"rootElementSnapshot"]; } @catch (__unused NSException *x) { snap = res; }
            if (!snap) continue;
            NSInteger m = 0; BOOL t2 = NO;
            NSString *body = [self renderBoundedSnapshot:snap maxDepth:24 maxElements:400 visibleRect:screen
                                            nodesWritten:&m truncated:&t2];
            if (body.length) [bodies addObject:body];
        }
        double cellsMs = (CFAbsoluteTimeGetCurrent() - t0) * 1000;
        NSUInteger type = [[bestNode valueForKey:@"elementType"] unsignedIntegerValue];
        return @{
            @"root_body": rootBody,
            @"container_type": type == 26 ? @"Table" : @"CollectionView",
            @"container_frame": [bestNode valueForKey:@"frame"],
            @"cell_bodies": bodies,
            @"children_count": bestCount ?: @(-1),
            @"shallow_ms": @(shallowMs),
            @"cells_ms": @(cellsMs),
        };
    } @catch (NSException *e) {
        NSLog(@"iCTRL: visibleListParts exception: %@", e.reason);
        return nil;
    }
}

+ (BOOL)safeTerminateBundleID:(NSString *)bundleId {
    if (bundleId.length == 0) { return NO; }
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return NO; }
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id app = initFn([appClass alloc], @selector(initWithBundleIdentifier:), bundleId);
        if (!app) { return NO; }
        if ([app respondsToSelector:@selector(terminate)]) {
            [app performSelector:@selector(terminate)];
        }
        return YES;
    } @catch (NSException *e) {
        NSLog(@"iCTRL: safeTerminate caught exception for %@: %@", bundleId, e.reason);
        return NO;
    }
}

+ (NSInteger)appStateForBundleID:(NSString *)bundleId {
    if (bundleId.length == 0) { return 0; }
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return 0; }
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id app = initFn([appClass alloc], @selector(initWithBundleIdentifier:), bundleId);
        if (!app || ![app respondsToSelector:@selector(state)]) { return 0; }
        NSInteger (*stateFn)(id, SEL) = (NSInteger (*)(id, SEL))objc_msgSend;
        return stateFn(app, @selector(state));
    } @catch (__unused NSException *e) {
        return 0;
    }
}

+ (nullable NSString *)safeLabelForBundleID:(NSString *)bundleId {
    if (bundleId.length == 0) { return nil; }
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return nil; }
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id app = initFn([appClass alloc], @selector(initWithBundleIdentifier:), bundleId);
        if (!app || ![app respondsToSelector:@selector(label)]) { return nil; }
        id label = [app performSelector:@selector(label)];
        return [label isKindOfClass:[NSString class]] && [label length] > 0 ? label : nil;
    } @catch (__unused NSException *e) {
        return nil;
    }
}

+ (BOOL)hasSystemAlert {
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return NO; }
        // -[XCUIApplication springboardApplication] / systemApplication varies by
        // OS; construct SpringBoard directly and look for an alert element.
        id (*initFn)(id, SEL, id) = (id (*)(id, SEL, id))objc_msgSend;
        id sb = initFn([appClass alloc], @selector(initWithBundleIdentifier:), @"com.apple.springboard");
        if (!sb) { return NO; }
        // sb.alerts.count > 0  → a system alert is present.
        id alerts = [sb performSelector:@selector(alerts)];
        if (alerts && [alerts respondsToSelector:@selector(count)]) {
            NSUInteger (*countFn)(id, SEL) = (NSUInteger (*)(id, SEL))objc_msgSend;
            return countFn(alerts, @selector(count)) > 0;
        }
        return NO;
    } @catch (__unused NSException *e) {
        return NO;
    }
}

+ (BOOL)openURL:(NSURL *)url {
    // 1) XCTest daemon session — the sanctioned path from a runner (iOS 16.4+).
    //    This is what WebDriverAgent uses; UIApplication/LSApplicationWorkspace
    //    both refuse to open URLs from inside XCTest.
    @try {
        Class sessionClass = NSClassFromString(@"XCTRunnerDaemonSession");
        if (sessionClass) {
            id session = [sessionClass performSelector:@selector(sharedSession)];
            SEL sel = @selector(openDefaultApplicationForURL:completion:);
            if (session && [session respondsToSelector:sel]) {
                __block BOOL ok = NO;
                dispatch_semaphore_t sem = dispatch_semaphore_create(0);
                [session openDefaultApplicationForURL:url completion:^(BOOL result, NSError *err) {
                    ok = result && (err == nil);
                    dispatch_semaphore_signal(sem);
                }];
                dispatch_semaphore_wait(sem, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(5 * NSEC_PER_SEC)));
                if (ok) { return YES; }
            }
        }
    } @catch (__unused NSException *e) {}

    // 2) Fallback: LSApplicationWorkspace (works on some OS versions).
    @try {
        Class wsClass = NSClassFromString(@"LSApplicationWorkspace");
        if (!wsClass) { return NO; }
        id ws = [wsClass performSelector:@selector(defaultWorkspace)];
        if (!ws) { return NO; }
        if ([ws respondsToSelector:@selector(openSensitiveURL:withOptions:)]) {
            BOOL (*fn)(id, SEL, id, id) = (BOOL (*)(id, SEL, id, id))objc_msgSend;
            if (fn(ws, @selector(openSensitiveURL:withOptions:), url, nil)) { return YES; }
        }
        if ([ws respondsToSelector:@selector(openURL:)]) {
            BOOL (*fn)(id, SEL, id) = (BOOL (*)(id, SEL, id))objc_msgSend;
            return fn(ws, @selector(openURL:), url);
        }
    } @catch (__unused NSException *e) {}
    return NO;
}

+ (BOOL)openBundleID:(NSString *)bundleId {
    @try {
        Class wsClass = NSClassFromString(@"LSApplicationWorkspace");
        if (!wsClass) { return NO; }
        id ws = [wsClass performSelector:@selector(defaultWorkspace)];
        if (![ws respondsToSelector:@selector(openApplicationWithBundleID:)]) { return NO; }
        // Non-blocking: returns immediately with success/failure.
        BOOL (*openFn)(id, SEL, id) = (BOOL (*)(id, SEL, id))objc_msgSend;
        return openFn(ws, @selector(openApplicationWithBundleID:), bundleId);
    } @catch (__unused NSException *e) {
        return NO;
    }
}

#pragma mark - Snapshot cost probe

/// Counts nodes in a snapshot tree by walking `children`, so we can tell a
/// server-side depth limit (fewer nodes) from a no-op (identical node count).
static NSUInteger ICTRLCountSnapshotNodes(id snapshot, NSUInteger depth) {
    if (!snapshot || depth > 200) { return 0; }
    NSUInteger n = 1;
    @try {
        SEL childrenSel = NSSelectorFromString(@"children");
        if ([snapshot respondsToSelector:childrenSel]) {
            id kids = [snapshot performSelector:childrenSel];
            if ([kids isKindOfClass:[NSArray class]]) {
                for (id k in (NSArray *)kids) {
                    n += ICTRLCountSnapshotNodes(k, depth + 1);
                }
            }
        }
    } @catch (__unused NSException *e) {}
    return n;
}

/// Counts nodes carrying a non-empty label — the part a caller actually reads.
static NSUInteger ICTRLCountLabelledNodes(id snapshot, NSUInteger depth) {
    if (!snapshot || depth > 200) { return 0; }
    NSUInteger n = 0;
    @try {
        SEL labelSel = NSSelectorFromString(@"label");
        if ([snapshot respondsToSelector:labelSel]) {
            id label = [snapshot performSelector:labelSel];
            if ([label isKindOfClass:[NSString class]] && [(NSString *)label length] > 0) { n = 1; }
        }
        SEL childrenSel = NSSelectorFromString(@"children");
        if ([snapshot respondsToSelector:childrenSel]) {
            id kids = [snapshot performSelector:childrenSel];
            if ([kids isKindOfClass:[NSArray class]]) {
                for (id k in (NSArray *)kids) { n += ICTRLCountLabelledNodes(k, depth + 1); }
            }
        }
    } @catch (__unused NSException *e) {}
    return n;
}

/// Gathers every non-empty label in a snapshot tree, for sampling what content
/// a bounded fetch actually returned.
static void ICTRLCollectLabels(id snapshot, NSUInteger depth, NSMutableArray *into) {
    if (!snapshot || depth > 200) { return; }
    @try {
        SEL labelSel = NSSelectorFromString(@"label");
        if ([snapshot respondsToSelector:labelSel]) {
            id label = [snapshot performSelector:labelSel];
            if ([label isKindOfClass:[NSString class]] && [(NSString *)label length] > 0) {
                [into addObject:label];
            }
        }
        SEL childrenSel = NSSelectorFromString(@"children");
        if ([snapshot respondsToSelector:childrenSel]) {
            id kids = [snapshot performSelector:childrenSel];
            if ([kids isKindOfClass:[NSArray class]]) {
                for (id k in (NSArray *)kids) { ICTRLCollectLabels(k, depth + 1, into); }
            }
        }
    } @catch (__unused NSException *e) {}
}

/// Finds the node carrying the longest label — on a feed that is a content row
/// rather than a layout container, so probing it says something about whether
/// the fetch returned real text.
static id ICTRLDeepestLabelledNode(id snapshot, NSUInteger depth) {
    if (!snapshot || depth > 200) { return nil; }
    id best = nil;
    NSUInteger bestLen = 0;
    @try {
        SEL labelSel = NSSelectorFromString(@"label");
        if ([snapshot respondsToSelector:labelSel]) {
            id label = [snapshot performSelector:labelSel];
            if ([label isKindOfClass:[NSString class]] && [(NSString *)label length] > 0) {
                best = snapshot;
                bestLen = [(NSString *)label length];
            }
        }
        SEL childrenSel = NSSelectorFromString(@"children");
        if ([snapshot respondsToSelector:childrenSel]) {
            id kids = [snapshot performSelector:childrenSel];
            if ([kids isKindOfClass:[NSArray class]]) {
                for (id k in (NSArray *)kids) {
                    id sub = ICTRLDeepestLabelledNode(k, depth + 1);
                    if (!sub) { continue; }
                    id subLabel = [sub performSelector:NSSelectorFromString(@"label")];
                    NSUInteger len = [subLabel isKindOfClass:[NSString class]] ? [(NSString *)subLabel length] : 0;
                    if (len > bestLen) { best = sub; bestLen = len; }
                }
            }
        }
    } @catch (__unused NSException *e) {}
    return best;
}

+ (nullable id)safeSnapshotOfElement:(id)element {
    if (!element) { return nil; }
    @try {
        SEL sel = NSSelectorFromString(@"snapshotWithError:");
        if (![element respondsToSelector:sel]) { return nil; }
        NSError *err = nil;
        id (*fn)(id, SEL, NSError **) = (id (*)(id, SEL, NSError **))objc_msgSend;
        id snap = fn(element, sel, &err);
        if (err) {
            NSLog(@"iCTRL: safeSnapshot error: %@", err.localizedDescription);
            return nil;
        }
        return snap;
    } @catch (NSException *e) {
        NSLog(@"iCTRL: safeSnapshot caught exception: %@", e.reason);
        return nil;
    }
}

+ (BOOL)safeBoolProperty:(NSString *)name ofElement:(id)element fallback:(BOOL)fallback {
    if (!element) { return fallback; }
    @try {
        SEL sel = NSSelectorFromString(name);
        if (![element respondsToSelector:sel]) { return fallback; }
        BOOL (*fn)(id, SEL) = (BOOL (*)(id, SEL))objc_msgSend;
        return fn(element, sel);
    } @catch (NSException *e) {
        // Answering "no" is the safe reading: a query XCTest can't resolve is
        // not one the caller should act on.
        NSLog(@"iCTRL: safeBoolProperty(%@) caught exception: %@", name, e.reason);
        return fallback;
    }
}

+ (NSInteger)boolPropertyState:(NSString *)name ofElement:(id)element
                        reason:(NSString * _Nullable * _Nullable)outReason {
    if (!element) { return 0; }
    @try {
        SEL sel = NSSelectorFromString(name);
        if (![element respondsToSelector:sel]) { return 0; }
        BOOL (*fn)(id, SEL) = (BOOL (*)(id, SEL))objc_msgSend;
        return fn(element, sel) ? 1 : 0;
    } @catch (NSException *e) {
        if (outReason) { *outReason = e.reason ?: e.name; }
        return -1;
    }
}

+ (nullable id)boundedSnapshotForBundleID:(NSString *)bundleId
                                 maxDepth:(NSInteger)maxDepth
                              maxChildren:(NSInteger)maxChildren {
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return nil; }
        id app = [[appClass alloc] performSelector:NSSelectorFromString(@"initWithBundleIdentifier:")
                                        withObject:bundleId];
        if (!app) { return nil; }

        // The request takes the app's XCAccessibilityElement, not the XCUIElement.
        id axElement = nil;
        for (NSString *sel in @[@"accessibilityElement", @"element"]) {
            SEL s = NSSelectorFromString(sel);
            if ([app respondsToSelector:s]) {
                axElement = [app performSelector:s];
                if (axElement) { break; }
            }
        }
        if (!axElement) { return nil; }

        // Reached via XCUIDevice — XCAXClient_iOS has no class methods on iOS 26,
        // so +sharedClient throws "unrecognized selector".
        id client = nil;
        Class deviceClass = NSClassFromString(@"XCUIDevice");
        id device = [deviceClass performSelector:NSSelectorFromString(@"sharedDevice")];
        SEL ifaceSel = NSSelectorFromString(@"accessibilityInterface");
        if ([device respondsToSelector:ifaceSel]) { client = [device performSelector:ifaceSel]; }
        if (!client) { return nil; }

        SEL reqSel = NSSelectorFromString(@"requestSnapshotForElement:attributes:parameters:error:");
        if (![client respondsToSelector:reqSel]) { return nil; }

        // Must be an NSArray: the sanitizer's first act is +[NSSet setWithArray:],
        // which throws on a set. +standardAttributeNames returns a set.
        id attrs = nil;
        Class elemClass = NSClassFromString(@"XCUIElement");
        SEL attrSel = NSSelectorFromString(@"standardAttributeNames");
        if ([elemClass respondsToSelector:attrSel]) { attrs = [elemClass performSelector:attrSel]; }
        if ([attrs isKindOfClass:[NSSet class]]) { attrs = [(NSSet *)attrs allObjects]; }
        if (![attrs isKindOfClass:[NSArray class]]) { return nil; }
        // standardAttributeNames alone fetches STRUCTURE ONLY through this raw
        // request. Its entries are snapshot-domain names ("label", "frame");
        // snapshotWithError converts them to AX wire keys before sending
        // (axAttributesForSnapshotAttributes:), but this request skips that step,
        // the far side silently ignores names it doesn't know, and the tree comes
        // back with every label empty and every frame zero — 472 nodes of shape
        // with no content, which is worse than useless for a caller who taps by
        // frame. Appending the wire-format keys is what flipped snapshot_bench's
        // labelled count from 0 to 116, with cells carrying full tweet text.
        NSMutableArray *wanted = [NSMutableArray arrayWithArray:(NSArray *)attrs];
        for (NSString *key in @[@"XC_kAXXCAttributeLabel", @"XC_kAXXCAttributeValue",
                                @"XC_kAXXCAttributeIdentifier",
                                @"XC_kAXXCAttributePlaceholderValue",
                                @"XC_kAXXCAttributeFrame"]) {
            if (![wanted containsObject:key]) { [wanted addObject:key]; }
        }
        attrs = wanted;

        NSError *err = nil;
        id (*fn)(id, SEL, id, id, id, NSError **) = (id (*)(id, SEL, id, id, id, NSError **))objc_msgSend;
        id result = fn(client, reqSel, axElement, attrs,
                       @{ @"maxDepth": @(maxDepth),
                          @"maxChildren": @(maxChildren),
                          @"maxArrayCount": @(maxChildren) }, &err);
        if (err || !result) { return nil; }

        // The call returns a request-result wrapper, not the snapshot itself.
        SEL rootSel = NSSelectorFromString(@"rootElementSnapshot");
        if (![result respondsToSelector:rootSel]) { return nil; }
        return [result performSelector:rootSel];
    } @catch (__unused NSException *e) {
        return nil;
    }
}

/// Human-readable element type name. Values are XCUIElementType's REAL raw
/// values, verified against live trees — an earlier guessed mapping rendered
/// X's 156 cells as "Switch" and every Other as "Application", which broke any
/// caller grepping for "Cell, label:". Names mirror the Swift renderer exactly
/// so the bounded and full paths are indistinguishable to a parser.
static NSString *ICTRLTypeName(NSInteger t) {
    switch (t) {
        case 0: return @"Any";           case 1: return @"Other";
        case 2: return @"Application";   case 3: return @"Group";
        case 4: return @"Window";        case 5: return @"Sheet";
        case 7: return @"Alert";         case 9: return @"Button";
        case 19: return @"Keyboard";     case 20: return @"Key";
        case 21: return @"NavigationBar"; case 22: return @"TabBar";
        case 24: return @"Toolbar";      case 26: return @"Table";
        case 32: return @"CollectionView"; case 33: return @"Slider";
        case 36: return @"ActivityIndicator"; case 37: return @"SegmentedControl";
        case 38: return @"Picker";       case 39: return @"PickerWheel";
        case 40: return @"Switch";       case 42: return @"Link";
        case 43: return @"Image";        case 44: return @"Icon";
        case 45: return @"SearchField";  case 46: return @"ScrollView";
        case 48: return @"StaticText";   case 49: return @"TextField";
        case 50: return @"SecureTextField"; case 52: return @"TextView";
        case 57: return @"Map";          case 58: return @"WebView";
        case 75: return @"Cell";
        default: return [NSString stringWithFormat:@"Type%ld", (long)t];
    }
}

/// Viewport for `visibleOnly` culling. CGRectNull disables it.
///
/// Why this is a per-node test and not subtree pruning: in a recycling list a
/// container's frame does NOT bound its children. WeChat's chat Table reports
/// exactly the screen rect {{0,0},{402,874}} while its cells live at y=-3659
/// through y=+5225 — measured 89% of parent/child pairs violate containment. So
/// an offscreen parent may hold visible children and vice versa; the only sound
/// approach is to test every node and keep walking regardless.
static NSMutableString *ICTRLBuildLine(NSInteger depth, NSInteger type, NSString *label,
                                       NSString *value, NSString *ident, CGRect frame) {
    NSMutableString *line = [NSMutableString string];
    for (NSInteger i = 0; i < depth; i++) { [line appendString:@"  "]; }
    [line appendString:ICTRLTypeName(type)];
    if (label.length) { [line appendFormat:@", label: '%@'", label]; }
    if (value.length) { [line appendFormat:@", value: '%@'", value]; }
    if (ident.length) { [line appendFormat:@", id: '%@'", ident]; }
    [line appendFormat:@", {{%d, %d}, {%d, %d}}",
        (int)frame.origin.x, (int)frame.origin.y, (int)frame.size.width, (int)frame.size.height];
    return line;
}

/// Element types that are never content: the scroll indicators UIKit overlays on
/// top of a list. They sit INSIDE the content band, carry a label
/// ("垂直滚动条, 16页" / "Vertical scroll bar"), and so survive every
/// geometry-based filter — measured, they were 3 of 18 junk entries harvested
/// from a feed. Dropping them by type is the only reliable way.
static BOOL ICTRLIsScrollIndicator(NSInteger type) {
    return type == 47;   // XCUIElementTypeScrollBar (per XCUIElementTypes.h)
}

static BOOL ICTRLRectVisible(CGRect f, CGRect viewport) {
    if (CGRectIsNull(viewport)) { return YES; }
    if (f.size.width <= 0 || f.size.height <= 0) { return NO; }   // zero-size: no hit target
    return CGRectIntersectsRect(f, viewport);
}

/// Reads the properties the renderer and the locator need off one snapshot
/// node — one reader, so a fix to how a property is read lands in both.
static void ICTRLReadNode(id node, NSString **label, NSString **ident, NSString **value,
                          NSInteger *type, CGRect *frame) {
    SEL s;
    s = NSSelectorFromString(@"label");
    if ([node respondsToSelector:s]) { id v = [node performSelector:s]; if ([v isKindOfClass:[NSString class]]) *label = v; }
    s = NSSelectorFromString(@"identifier");
    if ([node respondsToSelector:s]) { id v = [node performSelector:s]; if ([v isKindOfClass:[NSString class]]) *ident = v; }
    s = NSSelectorFromString(@"value");
    if ([node respondsToSelector:s]) { id v = [node performSelector:s]; if ([v isKindOfClass:[NSString class]]) *value = v; }
    s = NSSelectorFromString(@"elementType");
    if ([node respondsToSelector:s]) {
        NSMethodSignature *sig = [node methodSignatureForSelector:s];
        NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
        inv.selector = s; [inv invokeWithTarget:node];
        NSUInteger raw = 0; [inv getReturnValue:&raw]; *type = (NSInteger)raw;
    }
    s = NSSelectorFromString(@"frame");
    if ([node respondsToSelector:s]) {
        NSMethodSignature *sig = [node methodSignatureForSelector:s];
        NSInvocation *inv = [NSInvocation invocationWithMethodSignature:sig];
        inv.selector = s; [inv invokeWithTarget:node];
        [inv getReturnValue:frame];
    }
}

static BOOL ICTRLRenderNode(id node, NSInteger depth, NSInteger maxDepth,
                            NSInteger maxElements, NSMutableArray *lines,
                            NSInteger *count, BOOL *truncated, CGRect viewport) {
    if (!node || *count >= maxElements) { if (*count >= maxElements) { *truncated = YES; } return NO; }
    @try {
        NSString *label = nil, *ident = nil, *value = nil;
        NSInteger type = 0;
        CGRect frame = CGRectZero;
        ICTRLReadNode(node, &label, &ident, &value, &type, &frame);

        // A scroll indicator is chrome that happens to live inside the content
        // area and to carry a label, so no geometry filter can exclude it.
        BOOL selfVisible = ICTRLRectVisible(frame, viewport) && !ICTRLIsScrollIndicator(type);
        BOOL culling = !CGRectIsNull(viewport);

        // Build the line ONLY when it can still be emitted. On a recycling list
        // this is most of the win: WeChat walks 1500 nodes of which ~1370 are
        // offscreen, and each skipped node saves an NSMutableString alloc plus
        // four -appendFormat: calls. An invisible node can still be needed as the
        // ancestor of a visible one, so defer rather than decide now.
        NSMutableString *line = nil;
        NSUInteger slot = NSNotFound;
        if (!culling) {
            line = ICTRLBuildLine(depth, type, label, value, ident, frame);
            [lines addObject:line];
            (*count)++;
        } else if (selfVisible) {
            line = ICTRLBuildLine(depth, type, label, value, ident, frame);
            slot = lines.count;
            [lines addObject:[NSNull null]];   // resolved below
        } else {
            // Not visible: reserve a slot but build nothing. If a descendant
            // turns out visible we build the line then (see below).
            slot = lines.count;
            [lines addObject:[NSNull null]];
        }

        BOOL keptAnything = selfVisible;
        // A cell clips its content, so its children are on screen only where
        // the cell is. Some apps report the children of off-screen (recycled)
        // cells at a placeholder y inside the viewport; taken at face value
        // they would drag off-screen rows into a visible_only read.
        CGRect childViewport = viewport;
        if (culling && type == 75 && frame.size.width > 0 && frame.size.height > 0) {
            CGRect clip = CGRectIntersection(viewport, frame);
            childViewport = CGRectIsNull(clip) ? CGRectMake(-100000, -100000, 1, 1) : clip;
        }
        if (depth < maxDepth) {
            SEL s = NSSelectorFromString(@"children");
            if ([node respondsToSelector:s]) {
                id kids = [node performSelector:s];
                if ([kids isKindOfClass:[NSArray class]]) {
                    for (id k in (NSArray *)kids) {
                        if (*count >= maxElements) { *truncated = YES; break; }
                        // Always recurse: an offscreen container can hold visible
                        // children (see ICTRLRectVisible). Pruning here is what a
                        // naive implementation gets wrong.
                        if (ICTRLRenderNode(k, depth + 1, maxDepth, maxElements,
                                            lines, count, truncated, childViewport)) {
                            keptAnything = YES;
                        }
                    }
                }
            }
        }

        if (culling) {
            if (keptAnything) {
                // An invisible ancestor of a visible node skipped its line build
                // above — do it now, once, only for the few that survive.
                if (!line) { line = ICTRLBuildLine(depth, type, label, value, ident, frame); }
                lines[slot] = line;
                // Budget counts only what is actually returned, so the element
                // cap now bounds VISIBLE content rather than being exhausted by
                // thousands of recycled offscreen rows.
                (*count)++;
            }
            // Dropped nodes keep their NSNull placeholder rather than being
            // removed here: an ancestor higher up the stack is still holding a
            // `slot` index into this same array, and removing would shift every
            // later element and corrupt those. All placeholders are stripped
            // once at the end (see renderBoundedSnapshot).
        }
        return culling ? keptAnything : YES;
    } @catch (__unused NSException *e) {}
    return NO;
}

// XCUIElementType raw values used below (XCUIElementTypes.h).
static BOOL ICTRLIsChromeBar(NSInteger t) { return t == 21 || t == 22 || t == 24 || t == 25; } // Nav, Tab, Toolbar, Status
static BOOL ICTRLIsScrollable(NSInteger t) { return t == 26 || t == 32 || t == 46; }            // Table, Collection, ScrollView

/// Whether a `contains` hit sits on a token boundary. "25" inside "9月25日" is
/// a real hit; inside "2025年" it is an accident of digits. Only same-class
/// neighbours (digit next to digit, ASCII letter next to ASCII letter) break a
/// boundary — CJK text has no spaces, so a CJK neighbour never does.
static BOOL ICTRLSameClass(unichar a, unichar b) {
    BOOL ad = a >= '0' && a <= '9', bd = b >= '0' && b <= '9';
    if (ad && bd) { return YES; }
    BOOL al = (a | 0x20) >= 'a' && (a | 0x20) <= 'z', bl = (b | 0x20) >= 'a' && (b | 0x20) <= 'z';
    return al && bl;
}

/// 0 = prefix, 1 = on a token boundary, 2 = anywhere else.
static NSInteger ICTRLContainsQuality(NSString *hay, NSString *needle, NSRange r) {
    if (r.location == 0) { return 0; }
    unichar before = [hay characterAtIndex:r.location - 1];
    BOOL leftOK = !ICTRLSameClass(before, [needle characterAtIndex:0]);
    NSUInteger after = NSMaxRange(r);
    BOOL rightOK = after >= hay.length
        || !ICTRLSameClass([hay characterAtIndex:after], [needle characterAtIndex:needle.length - 1]);
    return (leftOK && rightOK) ? 1 : 2;
}

typedef struct {
    __unsafe_unretained NSString *needle;
    BOOL contains;
    __unsafe_unretained NSSet<NSNumber *> *types;   // nil = any type
    NSInteger maxDepth;
    NSInteger maxVisit;
    NSInteger visited;
    CGRect viewport;
} ICTRLLocateCtx;

/// Collects EVERY match instead of returning the first. The first-in-DFS
/// answer was wrong exactly when it mattered: a calendar month view keeps the
/// previous month's cells in the tree above the screen, so `contains:"25"`
/// returned an off-screen "8月25日" while "9月25日" sat in plain view.
static void ICTRLCollect(id node, NSInteger depth, ICTRLLocateCtx *ctx,
                         BOOL inChrome, NSValue *scrollAncestor,
                         NSMutableDictionary<NSString *, NSNumber *> *labelSeen,
                         NSMutableDictionary<NSString *, NSNumber *> *identSeen,
                         NSMutableArray<NSMutableDictionary *> *out,
                         NSMutableArray<NSArray *> *chromeBars,
                         NSMutableArray<NSValue *> *scrollables,
                         NSMutableArray<NSString *> *fingerprint) {
    if (!node || ctx->visited >= ctx->maxVisit) { return; }
    @try {
        ctx->visited++;
        NSString *label = nil, *ident = nil, *value = nil;
        NSInteger type = 0;
        CGRect frame = CGRectZero;
        ICTRLReadNode(node, &label, &ident, &value, &type, &frame);

        if (ICTRLIsChromeBar(type)) { [chromeBars addObject:@[@(type), [NSValue valueWithCGRect:frame]]]; }
        if (ICTRLIsScrollable(type) && ICTRLRectVisible(frame, ctx->viewport)) {
            [scrollables addObject:[NSValue valueWithCGRect:frame]];
        }
        if (fingerprint.count < 40 && label.length && ICTRLRectVisible(frame, ctx->viewport)) {
            [fingerprint addObject:[NSString stringWithFormat:@"%@@%d", label, (int)frame.origin.y]];
        }

        // The root is the Application; XCUIElementQuery.descendants excludes
        // it, so it must not count toward the ordinal a live query re-resolves.
        BOOL typeOK = depth > 0 && (!ctx->types || [ctx->types containsObject:@(type)]);
        if (typeOK) {
            NSInteger labelOrdinal = label.length ? [labelSeen[label] integerValue] : 0;
            NSInteger identOrdinal = ident.length ? [identSeen[ident] integerValue] : 0;
            if (label.length) { labelSeen[label] = @(labelOrdinal + 1); }
            if (ident.length) { identSeen[ident] = @(identOrdinal + 1); }

            NSInteger tier = -1, quality = 0;
            if (label.length && [label isEqualToString:ctx->needle]) { tier = 0; }
            else if (ident.length && [ident isEqualToString:ctx->needle]) { tier = 1; }
            // Text some apps put only in `value` (tab titles, calendar
            // days): matched exactly too, as its own tier.
            else if (value.length && [value isEqualToString:ctx->needle]) { tier = 3; }
            else if (ctx->contains) {
                NSString *hay = [NSString stringWithFormat:@"%@ %@", label ?: @"", value ?: @""];
                NSRange r = [hay rangeOfString:ctx->needle options:NSCaseInsensitiveSearch];
                if (r.location != NSNotFound) { tier = 2; quality = ICTRLContainsQuality(hay, ctx->needle, r); }
            }
            // A hit with no label can't be re-resolved by label; its identifier
            // is the only handle a live query has.
            // A hit with only a value can't be re-resolved live; it is kept
            // keyed by value, and callers act on its frame.
            BOOL valueOnly = !label.length && !ident.length && value.length && (tier == 2 || tier == 3);
            if (tier >= 0 && (label.length || ident.length || valueOnly)) {
                BOOL byLabel = label.length > 0 && tier != 1;
                NSMutableDictionary *c = [@{
                    @"how": tier == 0 ? @"exact" : (tier == 1 ? @"id" : (tier == 3 ? @"value" : @"contains")),
                    @"tier": @(tier), @"quality": @(quality),
                    @"label": label ?: @"", @"identifier": ident ?: @"",
                    @"value": value ?: @"",
                    @"type": @(type),
                    @"key": valueOnly ? @"value" : (byLabel ? @"label" : @"identifier"),
                    @"ordinal": @(byLabel ? labelOrdinal : identOrdinal),
                    @"order": @(out.count),
                    @"in_chrome": @(inChrome),
                    @"x": @(frame.origin.x), @"y": @(frame.origin.y),
                    @"w": @(frame.size.width), @"h": @(frame.size.height),
                } mutableCopy];
                if (scrollAncestor) {
                    CGRect a = scrollAncestor.CGRectValue;
                    c[@"container"] = @{ @"x": @(a.origin.x), @"y": @(a.origin.y),
                                          @"w": @(a.size.width), @"h": @(a.size.height) };
                }
                if (out.count < 200) { [out addObject:c]; }
            }
        }

        if (depth >= ctx->maxDepth) { return; }
        BOOL childChrome = inChrome || ICTRLIsChromeBar(type);
        NSValue *childScroll = ICTRLIsScrollable(type) ? [NSValue valueWithCGRect:frame] : scrollAncestor;
        SEL s = NSSelectorFromString(@"children");
        if ([node respondsToSelector:s]) {
            id kids = [node performSelector:s];
            if ([kids isKindOfClass:[NSArray class]]) {
                for (id k in (NSArray *)kids) {
                    ICTRLCollect(k, depth + 1, ctx, childChrome, childScroll, labelSeen, identSeen,
                                 out, chromeBars, scrollables, fingerprint);
                }
            }
        }
    } @catch (__unused NSException *e) {}
}

+ (nullable NSDictionary *)locateInBoundedSnapshot:(id)root
                                             query:(NSString *)query
                                          contains:(BOOL)contains
                                             types:(nullable NSArray<NSNumber *> *)types
                                          viewport:(CGRect)viewport
                                          maxDepth:(NSInteger)maxDepth {
    if (!root || !query.length) { return nil; }
    // Held in a strong local for the whole walk: the context's field is
    // __unsafe_unretained (C structs can't own objects here), so assigning a
    // freshly made set straight into it left ARC free to release the set at
    // once — and the first typed lookup crashed reading a freed object.
    __attribute__((objc_precise_lifetime)) NSSet<NSNumber *> *typeSet =
        types ? [NSSet setWithArray:types] : nil;
    ICTRLLocateCtx ctx = {
        .needle = query, .contains = contains,
        .types = typeSet,
        .maxDepth = maxDepth, .maxVisit = 6000, .visited = 0, .viewport = viewport,
    };
    NSMutableArray<NSMutableDictionary *> *cands = [NSMutableArray array];
    NSMutableArray<NSArray *> *bars = [NSMutableArray array];
    NSMutableArray<NSValue *> *scrollables = [NSMutableArray array];
    NSMutableArray<NSString *> *fp = [NSMutableArray array];
    ICTRLCollect(root, 0, &ctx, NO, nil, [NSMutableDictionary dictionary], [NSMutableDictionary dictionary],
                 cands, bars, scrollables, fp);

    // Content band = screen minus nav/status bars on top and tab/toolbars at the
    // bottom — same rules as page_source's coverage measure, read from the tree
    // because the bars differ per device and per app.
    CGFloat h = viewport.size.height;
    CGFloat top = 0, bottom = h;
    for (NSArray *b in bars) {
        NSInteger t = [b[0] integerValue];
        CGRect f = [b[1] CGRectValue];
        if (f.size.height <= 0 || f.size.height >= h * 0.4 || !ICTRLRectVisible(f, viewport)) { continue; }
        BOOL topBar = (t == 21 || t == 25);
        if (topBar && CGRectGetMaxY(f) > top && f.origin.y < h * 0.3) { top = CGRectGetMaxY(f); }
        if (!topBar && f.origin.y < bottom && CGRectGetMaxY(f) > h * 0.7) { bottom = f.origin.y; }
    }

    // Visibility: 0 = centre inside the content band (or on a bar, where it is
    // chrome and genuinely reachable), 1 = partly on screen, 2 = off screen.
    for (NSMutableDictionary *c in cands) {
        CGRect f = CGRectMake([c[@"x"] doubleValue], [c[@"y"] doubleValue], [c[@"w"] doubleValue], [c[@"h"] doubleValue]);
        NSInteger vis = 2;
        if (ICTRLRectVisible(f, viewport)) {
            CGFloat mx = CGRectGetMidX(f), my = CGRectGetMidY(f);
            BOOL centreOn = mx >= 0 && mx <= viewport.size.width && my >= 0 && my <= h;
            BOOL inBand = my > top && my < bottom;
            vis = (centreOn && (inBand || [c[@"in_chrome"] boolValue])) ? 0 : 1;
        }
        c[@"vis"] = @(vis);
        c[@"visibility"] = vis == 0 ? @"in_view" : (vis == 1 ? @"partial" : @"offscreen");
    }
    // Reachable beats textually closer: an exact match you cannot tap is worth
    // less than a contains-match you can. Within a visibility class the old
    // ranking holds (exact > id > contains), then boundary hits, then the
    // shorter label, then tree order.
    [cands sortUsingComparator:^NSComparisonResult(NSDictionary *a, NSDictionary *b) {
        for (NSString *k in @[@"vis", @"tier", @"quality"]) {
            NSComparisonResult r = [a[k] compare:b[k]];
            if (r != NSOrderedSame) { return r; }
        }
        NSUInteger la = [a[@"label"] length], lb = [b[@"label"] length];
        if (la != lb) { return la < lb ? NSOrderedAscending : NSOrderedDescending; }
        return [a[@"order"] compare:b[@"order"]];
    }];

    // The scroll container to drag in when nothing matched: the largest
    // scrollable on screen, which is the page body rather than a carousel.
    CGRect container = CGRectNull;
    CGFloat best = 0;
    for (NSValue *v in scrollables) {
        CGRect f = CGRectIntersection(v.CGRectValue, viewport);
        CGFloat area = f.size.width * f.size.height;
        if (area > best) { best = area; container = f; }
    }
    NSMutableDictionary *result = [@{
        @"candidates": cands,
        @"visited": @(ctx.visited),
        @"content_top": @(top), @"content_bottom": @(bottom),
        @"fingerprint": [fp componentsJoinedByString:@"|"],
    } mutableCopy];
    if (!CGRectIsNull(container)) {
        result[@"scroll_container"] = @{ @"x": @(container.origin.x), @"y": @(container.origin.y),
                                          @"w": @(container.size.width), @"h": @(container.size.height) };
    }
    return result;
}

+ (nullable NSString *)renderBoundedSnapshot:(id)root
                                    maxDepth:(NSInteger)maxDepth
                                 maxElements:(NSInteger)maxElements
                                 nodesWritten:(NSInteger *)outCount
                                    truncated:(BOOL *)outTruncated {
    return [self renderBoundedSnapshot:root maxDepth:maxDepth maxElements:maxElements
                           visibleRect:CGRectNull nodesWritten:outCount truncated:outTruncated];
}

+ (nullable NSString *)renderBoundedSnapshot:(id)root
                                    maxDepth:(NSInteger)maxDepth
                                 maxElements:(NSInteger)maxElements
                                 visibleRect:(CGRect)visibleRect
                                 nodesWritten:(NSInteger *)outCount
                                    truncated:(BOOL *)outTruncated {
    if (!root) { return nil; }
    NSMutableArray *lines = [NSMutableArray array];
    NSInteger count = 0; BOOL trunc = NO;
    ICTRLRenderNode(root, 0, maxDepth, maxElements, lines, &count, &trunc, visibleRect);
    if (outCount) { *outCount = count; }
    if (outTruncated) { *outTruncated = trunc; }
    if (!CGRectIsNull(visibleRect)) {
        [lines removeObjectIdenticalTo:[NSNull null]];   // drop culled placeholders
    }
    return [lines componentsJoinedByString:@"\n"];
}

/// Which single property `snapshot_bench` should read off a sample node.
/// Set per call; reading undocumented getters can hard-crash the runner, so only
/// one is attempted at a time (see probe_selector in the result).
static NSString *ICTRLProbeSelectorName = nil;

+ (void)setProbeSelectorName:(nullable NSString *)name {
    ICTRLProbeSelectorName = [name copy];
}

/// Pure class-metadata introspection: what snapshot parameters does THIS XCTest
/// build accept, and what snapshot-ish entry points exist?
///
/// Deliberately separate from benchmarkSnapshotForBundleID: it takes no snapshot
/// and touches no live element. Mixing the two is what repeatedly hung the AX
/// connection — any call that fetches can wedge the channel, and then the
/// introspection results are lost with it. This only reads class metadata, so it
/// cannot hang and always returns.
///
/// The question it exists to answer: is there a RECT/viewport parameter? Every
/// knob we have today trims what is RETURNED, but ~85% of page_source is the
/// fetch, so only a fetch-time filter can actually make it faster.
+ (NSDictionary *)snapshotAPICapabilities {
    NSMutableDictionary *out = [NSMutableDictionary dictionary];
    @try {
        // Guessing class names failed (none of the *RequestParameters spellings
        // exist on this build), so enumerate the whole runtime instead and keep
        // anything that looks like snapshot parameters. This is how we find the
        // real class rather than assuming its name.
        NSMutableArray *candidates = [NSMutableArray array];
        @try {
            unsigned int total = 0;
            Class *all = objc_copyClassList(&total);
            for (unsigned int i = 0; i < total; i++) {
                NSString *nm = NSStringFromClass(all[i]);
                NSString *low = nm.lowercaseString;
                if (([low containsString:@"snapshot"] || [low containsString:@"axsettings"])
                    && ([low containsString:@"param"] || [low containsString:@"request"]
                        || [low containsString:@"option"] || [low containsString:@"setting"])) {
                    [candidates addObject:nm];
                }
            }
            if (all) { free(all); }
            [candidates sortUsingSelector:@selector(compare:)];
            out[@"candidate_classes"] = [candidates componentsJoinedByString:@","];
        } @catch (NSException *e) { out[@"classlist_exception"] = e.reason ?: @"?"; }

        for (NSString *cls in candidates) {
            Class c = NSClassFromString(cls);
            if (!c) { continue; }
            unsigned int pn = 0;
            objc_property_t *props = class_copyPropertyList(c, &pn);
            NSMutableArray *names = [NSMutableArray array];
            for (unsigned int i = 0; i < pn; i++) {
                [names addObject:@(property_getName(props[i]))];
            }
            if (props) { free(props); }
            if (names.count) {
                out[[@"props_" stringByAppendingString:cls]] =
                    [names componentsJoinedByString:@","];
            }
            // Class methods too — defaultParameters and friends name the keys
            // XCTest itself passes.
            unsigned int mn = 0;
            Method *ms = class_copyMethodList(object_getClass(c), &mn);
            NSMutableArray *cms = [NSMutableArray array];
            for (unsigned int i = 0; i < mn; i++) {
                [cms addObject:NSStringFromSelector(method_getName(ms[i]))];
            }
            if (ms) { free(ms); }
            if (cms.count) {
                out[[@"classmethods_" stringByAppendingString:cls]] =
                    [cms componentsJoinedByString:@","];
            }
        }
        // Snapshot-related selectors on the AX client class. Reading the CLASS's
        // method list needs no instance, so nothing can block.
        for (NSString *cls in @[@"XCAXClient_iOS", @"XCUIApplication", @"XCUIElementQuery"]) {
            Class c = NSClassFromString(cls);
            if (!c) { continue; }
            unsigned int mn = 0;
            Method *ms = class_copyMethodList(c, &mn);
            NSMutableArray *hits = [NSMutableArray array];
            for (unsigned int i = 0; i < mn; i++) {
                NSString *nm = NSStringFromSelector(method_getName(ms[i]));
                NSString *low = nm.lowercaseString;
                if ([low containsString:@"snapshot"] || [low containsString:@"visib"]
                    || [low containsString:@"rect"] || [low containsString:@"viewport"]
                    || [low containsString:@"bounds"] || [low containsString:@"hittable"]) {
                    // Include the type encoding: it reveals whether a method takes
                    // a CGRect ({CGRect={CGPoint=dd}{CGSize=dd}}), which is what a
                    // fetch-time viewport filter would look like.
                    const char *enc = method_getTypeEncoding(ms[i]);
                    [hits addObject:enc ? [NSString stringWithFormat:@"%@ %s", nm, enc] : nm];
                }
            }
            if (ms) { free(ms); }
            [hits sortUsingSelector:@selector(compare:)];
            if (hits.count) {
                out[[@"methods_" stringByAppendingString:cls]] =
                    [hits componentsJoinedByString:@","];
            }
        }
    } @catch (NSException *e) { out[@"exception"] = e.reason ?: @"?"; }
    return out;
}

+ (nullable NSDictionary *)benchmarkSnapshotForBundleID:(NSString *)bundleId
                                               maxDepth:(NSInteger)maxDepth {
    NSMutableDictionary *out = [NSMutableDictionary dictionary];
    @try {
        Class appClass = NSClassFromString(@"XCUIApplication");
        if (!appClass) { return nil; }
        id app = [[appClass alloc] performSelector:NSSelectorFromString(@"initWithBundleIdentifier:")
                                        withObject:bundleId];
        if (!app) { return nil; }

        // --- Variant A: the path page_source uses today (no server-side limit).
        // OPT-IN ONLY (pass a positive max_depth). This is an unbounded snapshot:
        // on a long list it does not merely take seconds, it can hang the AX
        // connection so hard that only restarting the runner recovers it. A
        // diagnostic must not be able to kill the service it is measuring, so the
        // default (negative/absent max_depth) skips it.
        if (maxDepth >= 0) {
            NSDate *t0 = [NSDate date];
            id snapA = nil;
            @try {
                SEL snapSel = NSSelectorFromString(@"snapshotWithError:");
                if ([app respondsToSelector:snapSel]) {
                    NSError *err = nil;
                    id (*fn)(id, SEL, NSError **) = (id (*)(id, SEL, NSError **))objc_msgSend;
                    snapA = fn(app, snapSel, &err);
                    if (err) { out[@"default_error"] = err.localizedDescription ?: @"?"; }
                }
            } @catch (NSException *e) { out[@"default_exception"] = e.reason ?: @"?"; }
            out[@"default_ms"] = @((NSInteger)([[NSDate date] timeIntervalSinceDate:t0] * 1000));
            out[@"default_nodes"] = @(ICTRLCountSnapshotNodes(snapA, 0));
        }
        // A negative max_depth means "skip the baseline"; use its magnitude.
        if (maxDepth < 0) { maxDepth = -maxDepth; }

        // --- Variant B: same fetch, but ask the AX server to bound the walk.
        // Resolve the app's accessibility element, which is what the low-level
        // request takes (it does not accept an XCUIElement).
        id axElement = nil;
        for (NSString *sel in @[@"accessibilityElement", @"element"]) {
            SEL s = NSSelectorFromString(sel);
            if ([app respondsToSelector:s]) {
                axElement = [app performSelector:s];
                if (axElement) { break; }
            }
        }
        if (!axElement) {
            out[@"param_skipped"] = @"could not resolve accessibilityElement";
            return out;
        }

        // The AX client is reached through XCUIDevice, not a shared singleton:
        // on iOS 26 XCAXClient_iOS exposes no class methods at all, so
        // +sharedClient throws "unrecognized selector". XCUIElementQuery's own
        // snapshot path goes device -> accessibilityInterface, so mirror that.
        id client = nil;
        @try {
            Class deviceClass = NSClassFromString(@"XCUIDevice");
            id device = [deviceClass performSelector:NSSelectorFromString(@"sharedDevice")];
            SEL ifaceSel = NSSelectorFromString(@"accessibilityInterface");
            if ([device respondsToSelector:ifaceSel]) {
                client = [device performSelector:ifaceSel];
            }
        } @catch (NSException *e) { out[@"client_exception"] = e.reason ?: @"?"; }
        if (!client) { out[@"param_skipped"] = @"no accessibilityInterface"; return out; }
        out[@"client_class"] = NSStringFromClass([client class]);
        SEL reqSel = NSSelectorFromString(@"requestSnapshotForElement:attributes:parameters:error:");
        if (![client respondsToSelector:reqSel]) {
            out[@"param_skipped"] = @"no requestSnapshotForElement:...";
            return out;
        }

        // Standard attribute set, so the two variants return comparable nodes.
        // +standardAttributeNames lives on XCUIElement (XCElementSnapshot is gone
        // in this XCTest version — the snapshot class is XCUIElementSnapshot).
        // `attributes:` is an NSSet, not an NSArray: +standardAttributeNames is
        // built with +setWithObjects:, and passing an array throws
        // "-[NSSet initWithArray:range:copyItems:]: array argument is not an NSArray"
        // from inside the request. Normalise whatever we get to a set.
        id attrs = nil;
        @try {
            for (NSString *cls in @[@"XCUIElement", @"XCElementSnapshot"]) {
                Class c = NSClassFromString(cls);
                SEL attrSel = NSSelectorFromString(@"standardAttributeNames");
                if ([c respondsToSelector:attrSel]) {
                    attrs = [c performSelector:attrSel];
                    if (attrs) { out[@"attrs_from"] = cls; break; }
                }
            }
        } @catch (__unused NSException *e) {}
        // `attributes:` must be an NSArray. The sanitizer's first act is
        // +[NSSet setWithArray:attrs], which throws
        // "array argument is not an NSArray" when handed a set — so
        // +standardAttributeNames returning a set has to be flattened back to an
        // array before the call.
        if ([attrs isKindOfClass:[NSSet class]]) {
            attrs = [(NSSet *)attrs allObjects];
        }
        if (![attrs isKindOfClass:[NSArray class]]) {
            attrs = @[@"XC_kAXXCAttributeIdentifier", @"XC_kAXXCAttributeValue",
                      @"XC_kAXXCAttributeLabel", @"XC_kAXXCAttributeFrame",
                      @"XC_kAXXCAttributeElementType", @"XC_kAXXCAttributeChildren"];
            out[@"attrs_from"] = @"fallback";
        }
        out[@"attrs_count"] = @([attrs count]);
        out[@"attrs_class"] = NSStringFromClass([attrs class]);
        // Which attributes we actually asked for. A snapshot fetched without
        // XC_kAXXCAttributeLabel comes back correctly shaped but with empty
        // labels — indistinguishable from "the app exposes nothing" unless the
        // requested set is visible here.
        out[@"attrs_list"] = [[attrs valueForKey:@"description"] componentsJoinedByString:@","] ?: @"?";
        out[@"ax_class"] = NSStringFromClass([axElement class]);
        // Sanity-check the attribute set the same way the request will, so a bad
        // element vs. a bad attribute set are distinguishable in the result.
        @try {
            Class snapClass = NSClassFromString(@"XCElementSnapshot");
            SEL sanSel = NSSelectorFromString(@"sanitizedElementSnapshotHierarchyAttributesForAttributes:isMacOS:");
            if ([snapClass respondsToSelector:sanSel]) {
                id (*fn)(id, SEL, id, BOOL) = (id (*)(id, SEL, id, BOOL))objc_msgSend;
                id sanitized = fn(snapClass, sanSel, attrs, NO);
                out[@"attrs_sanitized_ok"] = @([sanitized count]);
                // XCTest expands the requested set (14 -> 20 here). Record what
                // it added: those are attributes the snapshot always carries, so
                // asking for them explicitly is redundant, while anything absent
                // from this list is genuinely not fetched.
                @try {
                    NSArray *all = [sanitized respondsToSelector:@selector(allObjects)]
                        ? [sanitized allObjects] : (NSArray *)sanitized;
                    out[@"attrs_sanitized_list"] = [all componentsJoinedByString:@","];
                } @catch (__unused NSException *e) {}
            } else {
                out[@"attrs_sanitized_ok"] = @"selector missing";
            }
        } @catch (NSException *e) { out[@"attrs_sanitize_exception"] = e.reason ?: @"?"; }

        // Explicitly include the text-bearing attributes. +standardAttributeNames
        // is what the default path uses, but the depth-limited request appears to
        // return structure only — if that is because label was never requested,
        // naming it here fixes it; if labels are still empty, the AX server does
        // not populate them in bounded mode and this route is unusable.
        NSMutableArray *wanted = [NSMutableArray arrayWithArray:(NSArray *)attrs];
        for (NSString *key in @[@"XC_kAXXCAttributeLabel", @"XC_kAXXCAttributeValue",
                                @"XC_kAXXCAttributeIdentifier",
                                @"XC_kAXXCAttributePlaceholderValue"]) {
            // Asking for more than this is pointless: the AX server returns a
            // fixed set (label, title, identifier, frame, elementType, enabled,
            // selected, hasFocus, children, displayID, windowContextID, and the
            // two size classes) no matter what is requested. traits, value,
            // visiblePoint and truncatedValue were all requested and none came
            // back, while the extra keys measurably slowed the call.
            if (![wanted containsObject:key]) { [wanted addObject:key]; }
        }
        attrs = wanted;
        out[@"attrs_count_final"] = @(wanted.count);

        NSDictionary *params = @{ @"maxDepth": @(maxDepth),
                                  @"maxChildren": @(100),
                                  @"maxArrayCount": @(100) };

        NSDate *t1 = [NSDate date];
        id snapB = nil;
        @try {
            NSError *err = nil;
            id (*fn)(id, SEL, id, id, id, NSError **) =
                (id (*)(id, SEL, id, id, id, NSError **))objc_msgSend;
            snapB = fn(client, reqSel, axElement, attrs, params, &err);
            if (err) { out[@"param_error"] = err.localizedDescription ?: @"?"; }
        } @catch (NSException *e) { out[@"param_exception"] = e.reason ?: @"?"; }
        out[@"param_ms"] = @((NSInteger)([[NSDate date] timeIntervalSinceDate:t1] * 1000));
        out[@"param_nodes"] = @(ICTRLCountSnapshotNodes(snapB, 0));
        out[@"param_max_depth"] = @(maxDepth);
        // The request returns a wrapper, not the snapshot itself: counting
        // `children` on it yields 1 regardless of maxDepth. Record what we
        // actually got so the node count can be read against the right object.
        out[@"param_class"] = snapB ? NSStringFromClass([snapB class]) : @"nil";
        // Node count alone does not prove the tree is usable: a snapshot fetched
        // with the wrong attribute set still has the right shape but empty
        // labels, which is worthless to a caller. Count labelled nodes too.
        @try {
            SEL rootSel = NSSelectorFromString(@"rootElementSnapshot");
            if ([snapB respondsToSelector:rootSel]) {
                id root = [snapB performSelector:rootSel];
                out[@"param_labelled"] = @(ICTRLCountLabelledNodes(root, 0));
                // Node counts don't prove usefulness: sample the longest labels
                // so we can see whether real content (feed rows) came through or
                // only chrome like tab titles.
                NSMutableArray *samples = [NSMutableArray array];
                ICTRLCollectLabels(root, 0, samples);
                [samples sortUsingComparator:^NSComparisonResult(NSString *a, NSString *b) {
                    return b.length > a.length ? NSOrderedAscending : NSOrderedDescending;
                }];
                NSMutableArray *top = [NSMutableArray array];
                for (NSUInteger i = 0; i < MIN(3u, samples.count); i++) {
                    NSString *s = samples[i];
                    [top addObject:s.length > 120 ? [s substringToIndex:120] : s];
                }
                out[@"param_label_samples"] = [top componentsJoinedByString:@" ⏐ "];

                // Runtime dump of one real node instead of guessing which
                // attribute carries the text. XCElementSnapshot loads properties
                // lazily (see -_isFaultedIn:/faultedInProperties), so a value can
                // be absent simply because it was never faulted in — which looks
                // identical to "the app exposes nothing".
                // Sample a node that actually carries text. Walking down the
                // first child each time lands on a layout container, whose empty
                // label says nothing about whether the fetch returned content —
                // the earlier run reported 116 labelled nodes while this probe
                // read blanks. Pick the longest-labelled node instead: on a feed
                // that is a real row, which is what we need to inspect.
                id probe = ICTRLDeepestLabelledNode(root, 0);
                out[@"probe_found_labelled"] = @(probe != nil);
                if (!probe) { probe = root; }
                // Read ONE property per call, named by the caller. Reading a set
                // of undocumented getters in a loop killed the runner with SIGBUS
                // (not an NSException — @catch cannot stop it), and a batch dump
                // gives no clue which getter did it. One at a time means a crash
                // identifies its own culprit, and the safe ones stay usable.
                NSString *probeSel = ICTRLProbeSelectorName ?: @"label";
                out[@"probe_selector"] = probeSel;
                // -faultedInProperties reads the lazy-loading bookkeeping itself
                // and killed the runner with SIGBUS on iOS 26. @catch cannot stop
                // that, so the only safe handling is never to call it.
                static NSSet *banned;
                static dispatch_once_t once;
                dispatch_once(&once, ^{ banned = [NSSet setWithObjects:@"faultedInProperties", nil]; });
                if ([banned containsObject:probeSel]) {
                    out[@"probe_value"] = @"<refused: crashes the runner (SIGBUS)>";
                    probeSel = nil;
                }
                if (probeSel) @try {
                    SEL s = NSSelectorFromString(probeSel);
                    if (![probe respondsToSelector:s]) {
                        out[@"probe_value"] = @"<no-sel>";
                    } else {
                        id v = [probe performSelector:s];
                        NSString *desc = v ? [NSString stringWithFormat:@"%@", v] : @"nil";
                        if (desc.length > 200) { desc = [[desc substringToIndex:200] stringByAppendingString:@"…"]; }
                        out[@"probe_value"] = desc;
                    }
                } @catch (NSException *e) {
                    out[@"probe_value"] = [NSString stringWithFormat:@"<throws:%@>", e.name];
                }
                out[@"probe_class"] = NSStringFromClass([probe class]);
                // What the returned snapshot actually holds, as opposed to what
                // we asked for. -dictionaryRepresentation is the snapshot's own
                // serialisation, so its keys are the definitive answer to "which
                // attributes came back" — a requested attribute missing here was
                // dropped, and a key here we never requested came for free.
                @try {
                    SEL dictSel = NSSelectorFromString(@"dictionaryRepresentation");
                    if ([probe respondsToSelector:dictSel]) {
                        id dict = [probe performSelector:dictSel];
                        if ([dict isKindOfClass:[NSDictionary class]]) {
                            NSArray *keys = [[(NSDictionary *)dict allKeys]
                                sortedArrayUsingSelector:@selector(compare:)];
                            out[@"returned_keys"] = [keys componentsJoinedByString:@","];
                            out[@"returned_key_count"] = @(keys.count);
                        } else {
                            out[@"returned_keys"] = dict ? NSStringFromClass([dict class]) : @"nil";
                        }
                    } else {
                        out[@"returned_keys"] = @"<no dictionaryRepresentation>";
                    }
                } @catch (NSException *e) {
                    out[@"returned_keys"] = [NSString stringWithFormat:@"<throws:%@>", e.name];
                }

                // Enumerate what this class really has on THIS iOS build — the
                // Mac-side framework we disassembled may not match the device's.
                @try {
                    unsigned int n = 0;
                    objc_property_t *props = class_copyPropertyList([probe class], &n);
                    NSMutableArray *names = [NSMutableArray array];
                    for (unsigned int i = 0; i < n && i < 60; i++) {
                        [names addObject:@(property_getName(props[i]))];
                    }
                    if (props) { free(props); }
                    out[@"probe_properties"] = [names componentsJoinedByString:@","];
                } @catch (__unused NSException *e) {}
                // Second-pass probe: if the bounded tree carries no text, can a
                // node be re-hydrated on its own? A snapshot node exposes the
                // accessibility element it came from, so re-requesting just that
                // subtree would let us fetch structure cheaply and fill in text
                // only where needed.
                id deepest = root;
                for (int i = 0; i < 6; i++) {
                    SEL kidsSel = NSSelectorFromString(@"children");
                    if (![deepest respondsToSelector:kidsSel]) { break; }
                    NSArray *kids = [deepest performSelector:kidsSel];
                    if (![kids isKindOfClass:[NSArray class]] || kids.count == 0) { break; }
                    deepest = kids.firstObject;
                }
                for (NSString *sel in @[@"accessibilityElement", @"element"]) {
                    SEL s = NSSelectorFromString(sel);
                    if ([deepest respondsToSelector:s]) {
                        id leafAX = [deepest performSelector:s];
                        if (!leafAX) { continue; }
                        out[@"rehydrate_ax_class"] = NSStringFromClass([leafAX class]);
                        NSError *e2 = nil;
                        id (*fn2)(id, SEL, id, id, id, NSError **) =
                            (id (*)(id, SEL, id, id, id, NSError **))objc_msgSend;
                        id one = fn2(client, reqSel, leafAX, attrs,
                                     @{@"maxDepth": @(1)}, &e2);
                        SEL rs = NSSelectorFromString(@"rootElementSnapshot");
                        id oneRoot = [one respondsToSelector:rs] ? [one performSelector:rs] : nil;
                        out[@"rehydrate_labelled"] = @(ICTRLCountLabelledNodes(oneRoot, 0));
                        break;
                    }
                }
            }
        } @catch (NSException *e) { out[@"rehydrate_exception"] = e.reason ?: @"?"; }
        @try {
            for (NSString *sel in @[@"rootElementSnapshot", @"snapshot", @"value"]) {
                SEL s = NSSelectorFromString(sel);
                if ([snapB respondsToSelector:s]) {
                    id inner = [snapB performSelector:s];
                    if (inner) {
                        out[[@"unwrap_" stringByAppendingString:sel]] =
                            [NSString stringWithFormat:@"%@:%lu",
                             NSStringFromClass([inner class]),
                             (unsigned long)ICTRLCountSnapshotNodes(inner, 0)];
                    }
                }
            }
        } @catch (NSException *e) { out[@"unwrap_exception"] = e.reason ?: @"?"; }

        // --- Variant C: ask XCTest for its own rendered description instead of
        // fetching attributes and formatting them ourselves. Appium exposes this
        // as `mobile: source format=description` and reports it as much faster,
        // the claim being that the expensive part is resolving per-node
        // attributes, which this skips entirely.
        //
        // ONLY the snapshot's own -debugDescription is safe here. Do NOT call it
        // on the XCUIApplication: that goes through XCUIElement, which triggers a
        // fresh UNBOUNDED snapshot and first waits for app quiescence with no
        // timeout we control. Measured: it hung the AX connection outright on a
        // 173-node Settings tree (a normal page_source there is 652ms), and the
        // only recovery was restarting the runner — reset could not clear it.
        for (NSString *spec in @[@"snapshot:debugDescription"]) {
            NSArray *parts = [spec componentsSeparatedByString:@":"];
            id target = snapB;
            if (!target) { continue; }
            SEL s = NSSelectorFromString(parts[1]);
            if (![target respondsToSelector:s]) {
                out[[@"descr_" stringByAppendingString:spec]] = @"<no selector>";
                continue;
            }
            NSDate *t2 = [NSDate date];
            NSString *text = nil;
            @try {
                id (*fn)(id, SEL) = (id (*)(id, SEL))objc_msgSend;
                id v = fn(target, s);
                if ([v isKindOfClass:[NSString class]]) { text = v; }
            } @catch (NSException *e) {
                out[[@"descr_" stringByAppendingString:spec]] =
                    [NSString stringWithFormat:@"<throws:%@>", e.name];
                continue;
            }
            NSInteger ms = (NSInteger)([[NSDate date] timeIntervalSinceDate:t2] * 1000);
            out[[NSString stringWithFormat:@"descr_%@_ms", spec]] = @(ms);
            out[[NSString stringWithFormat:@"descr_%@_bytes", spec]] = @(text.length);
            out[[NSString stringWithFormat:@"descr_%@_lines", spec]] =
                @(text ? [[text componentsSeparatedByString:@"\n"] count] : 0);
            // A description that carries no labels is useless to us regardless of
            // speed — the whole point is locating elements by their text.
            if (text.length) {
                NSUInteger head = MIN((NSUInteger)400, text.length);
                out[[NSString stringWithFormat:@"descr_%@_head", spec]] = [text substringToIndex:head];
            }
        }

        // --- Variant D: same request as B, but with the MINIMAL attribute set
        // we actually render (label/value/identifier/frame/elementType/children).
        // B asks for 14 and XCTest expands that to ~20; if attribute resolution
        // is what costs the seconds, this should be measurably cheaper on the
        // very same tree. Isolates "too many attributes" from "too many nodes".
        @try {
            NSArray *minimal = @[@"XC_kAXXCAttributeLabel", @"XC_kAXXCAttributeValue",
                                 @"XC_kAXXCAttributeIdentifier", @"XC_kAXXCAttributeFrame",
                                 @"XC_kAXXCAttributeElementType", @"XC_kAXXCAttributeChildren"];
            NSDate *t3 = [NSDate date];
            NSError *err = nil;
            id (*fn)(id, SEL, id, id, id, NSError **) =
                (id (*)(id, SEL, id, id, id, NSError **))objc_msgSend;
            id snapD = fn(client, reqSel, axElement, minimal, params, &err);
            out[@"minattr_ms"] = @((NSInteger)([[NSDate date] timeIntervalSinceDate:t3] * 1000));
            out[@"minattr_count"] = @(minimal.count);
            if (err) { out[@"minattr_error"] = err.localizedDescription ?: @"?"; }
            SEL rootSel2 = NSSelectorFromString(@"rootElementSnapshot");
            if ([snapD respondsToSelector:rootSel2]) {
                id r2 = [snapD performSelector:rootSel2];
                out[@"minattr_nodes"] = @(ICTRLCountSnapshotNodes(r2, 0));
                out[@"minattr_labelled"] = @(ICTRLCountLabelledNodes(r2, 0));
            }
        } @catch (NSException *e) { out[@"minattr_exception"] = e.reason ?: @"?"; }
    } @catch (NSException *e) {
        out[@"fatal"] = e.reason ?: @"?";
    }
    return out;
}

@end
