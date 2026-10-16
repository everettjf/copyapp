#import <Foundation/Foundation.h>
#import <CoreGraphics/CoreGraphics.h>   // CGRect in renderBoundedSnapshot:visibleRect:

NS_ASSUME_NONNULL_BEGIN

/// Resolves the bundle identifier of the app currently in the foreground.
/// Uses private XCTest accessibility APIs (same approach as WebDriverAgent).
/// Returns nil if it cannot be determined.
@interface ForegroundApp : NSObject

+ (nullable NSString *)currentBundleID;
/// pid of the app in front (SpringBoard at the home screen), from the
/// accessibility client's activeApplications; 0 if unavailable. Readable
/// where currentBundleID can't name the app: Xcode 27's XCTest dropped the
/// -[XCUIApplication initWithProcessID:] that pid → bundle id lookup used.
+ (pid_t)frontmostPID;
/// Cap how long one accessibility message to an app may take (XCTest's
/// AX timeout). Returns the previous value, or a negative number if the
/// private API is missing.
+ (double)setAXTimeout:(double)seconds;
/// pid XCTest knows for an app (0 if not running or not tracked). Used for
/// SpringBoard, which XCTest always tracks.
+ (pid_t)processIDForBundleID:(NSString *)bundleId;

/// Lists installed apps as [{bundle_id, name}] via the private
/// LSApplicationWorkspace API. Returns nil if unavailable. `userOnly` filters
/// out system apps when possible.
+ (nullable NSArray<NSDictionary *> *)installedAppsUserOnly:(BOOL)userOnly;

/// Opens an app by bundle id WITHOUT blocking (LSApplicationWorkspace, same as
/// WebDriverAgent). Returns NO immediately if the app can't be opened — no hang.
+ (BOOL)openBundleID:(NSString *)bundleId;
+ (nullable NSDictionary *)visibleListParts:(NSString *)bundleId screen:(CGRect)screen maxElements:(NSInteger)maxElements;

/// Opens an arbitrary URL (any scheme, with query) from inside the XCTest runner,
/// where UIApplication.openURL is unreliable. Uses LSApplicationWorkspace's
/// openSensitiveURL:/openURL: private APIs. Returns YES on success.
+ (BOOL)openURL:(NSURL *)url;

/// Activate an app by bundle id, catching any XCTest NSException (which Swift
/// cannot catch and which would otherwise abort the whole runner). Returns YES if
/// activation was attempted without throwing. Must be safe to call off-main.
+ (BOOL)safeActivateBundleID:(NSString *)bundleId;

/// Bring an app to the front, launching it if it isn't running.
///
/// `activate` alone is a no-op on a process that isn't up yet, which is the case
/// for SpringBoard after a reboot. WebDriverAgent branches the same way for its
/// home-screen route; this mirrors that.
+ (BOOL)activateOrLaunchBundleID:(NSString *)bundleId;

/// Terminate an app by bundle id, catching any XCTest NSException. Returns YES if
/// termination was attempted without throwing.
+ (BOOL)safeTerminateBundleID:(NSString *)bundleId;

/// Returns the XCUIApplicationState raw value for a bundle id, caught safely:
///   0 = unknown, 1 = notRunning, 2 = runningBackgroundSuspended,
///   3 = runningBackground, 4 = runningForeground.
/// Used to tell "app crashed/closed" from "app just not frontmost".
+ (NSInteger)appStateForBundleID:(NSString *)bundleId;

/// The app's display name as the home screen shows it (its Application
/// element's accessibility label), caught safely. nil if the app isn't running
/// or the read throws. Costs one accessibility round-trip to the target app.
+ (nullable NSString *)safeLabelForBundleID:(NSString *)bundleId;

/// Whether a system alert / permission dialog is currently on screen (owned by
/// SpringBoard, covering the app). When true, actions should target the system
/// UI to dismiss it first. Caught safely; returns NO on any error.
+ (BOOL)hasSystemAlert;

/// Benchmarks the two ways XCTest can fetch an accessibility tree, on the same
/// live UI, so we can tell where page_source's cost actually is.
///
/// `XCUIElement.snapshot()` (what page_source uses) resolves to
/// `snapshotForElement:attributes:parameters:` with `defaultParameters` — no
/// depth limit — so the target app walks and serializes its ENTIRE tree before
/// anything crosses the IPC boundary. Our max_depth/max_elements then trim the
/// already-materialized result, which cannot recover that cost.
///
/// XCUIAutomation exposes `maxDepth`/`maxChildren`/`maxArrayCount` parameter
/// keys that ride along with the request and are applied by the AX server on the
/// far side. Whether the server actually honours them is the open question this
/// answers empirically — the key existing in the binary is not proof it is
/// implemented on iOS 26.
///
/// Returns a dictionary of timings/sizes per variant, or nil if the private API
/// is unavailable. Never throws.
/// Takes `-[XCUIElement snapshotWithError:]` without letting it kill the runner.
///
/// XCTest raises an Obj-C NSException from snapshot() in states Swift cannot
/// intercept — `try?` only catches Swift `throws`, so the exception reaches
/// XCTest's terminate handler and the process dies with SIGABRT. That is exactly
/// what happened when the snapshot walk was promoted to find_element's primary
/// path: it aborted on the first call, before a single phase was logged.
///
/// Returns nil when the snapshot is unavailable, so callers can fall back.
+ (nullable id)safeSnapshotOfElement:(id)element;

/// Reads a BOOL property of an element without letting it kill the runner.
///
/// `exists` and `isHittable` look like plain property reads, but each one asks
/// the target app to resolve the query across IPC — and XCTest raises an Obj-C
/// NSException when that resolution fails. Swift cannot intercept it: `try?`
/// only catches Swift `throws`, so the exception unwinds into XCTest's
/// terminate handler and the process dies with SIGABRT.
///
/// Seen on iOS 16.1: `-[XCUIElement exists]` threw from inside
/// `-[XCTActivityRecordStack didFinishActivity:]` while the caller was on a
/// background queue, killing the runner outright. Older XCTest builds record
/// an activity per query and are stricter about the stack being balanced, so
/// this is far likelier off the main queue and on older systems.
///
/// `fallback` is returned when the read throws, letting the caller treat an
/// unanswerable query as "no" rather than as a crash.
+ (BOOL)safeBoolProperty:(NSString *)name ofElement:(id)element fallback:(BOOL)fallback;

/// As `safeBoolProperty:`, but tells a real NO apart from a read that threw:
/// returns 1 / 0, or -1 with the exception's reason in `outReason`.
///
/// The distinction is the whole point. `exists` throwing means XCTest could
/// not answer at all — the app is busy or backgrounded — and reporting that as
/// "element gone" sent a real incident's post-mortem down the wrong path.
+ (NSInteger)boolPropertyState:(NSString *)name ofElement:(id)element
                        reason:(NSString * _Nullable * _Nullable)outReason;

/// Fetches an accessibility snapshot with the traversal bounded ON THE DEVICE.
///
/// `XCUIElement.snapshot()` asks the target app to walk and serialise its whole
/// tree before anything crosses the IPC boundary, so a long-scrolled feed costs
/// seconds no matter what the caller intends to keep. XCTest's underlying
/// request accepts `maxDepth`/`maxChildren`, which the app applies while
/// walking — measured at 1.6s versus 6.5-8.5s for the same X timeline, with the
/// feed's text intact.
///
/// Returns an `XCUIElementSnapshot`-conforming root, or nil if any part of the
/// private path is unavailable (it moved four times on iOS 26 alone) — callers
/// must fall back to `snapshot()` rather than treating nil as an empty screen.
+ (nullable id)boundedSnapshotForBundleID:(NSString *)bundleId
                                 maxDepth:(NSInteger)maxDepth
                              maxChildren:(NSInteger)maxChildren;

/// Every match for `query` in a bounded snapshot, ranked for acting on.
///
/// Returns @{candidates, visited, content_top, content_bottom, fingerprint,
/// scroll_container?}. Each candidate is @{how, label, identifier, type, x, y,
/// w, h, visibility ("in_view" | "partial" | "offscreen"), key ("label" |
/// "identifier"), ordinal, container?}. `ordinal` is the index a live
/// `label == X` (or identifier) query over the same `types` would give this
/// node, so the caller can re-resolve THIS element rather than the first one
/// that happens to share its label.
///
/// Ranking: in view > partly visible > off screen, then exact > id > contains,
/// then contains-hits on a token boundary, then shorter labels. `types` are
/// XCUIElementType raw values and must mirror the live query's type filter;
/// nil means any type. `fingerprint` summarises what is on screen, for telling
/// whether a scroll moved anything. Walks in Obj-C for the same reason as the
/// renderer below.
+ (nullable NSDictionary *)locateInBoundedSnapshot:(id)root
                                             query:(NSString *)query
                                          contains:(BOOL)contains
                                             types:(nullable NSArray<NSNumber *> *)types
                                          viewport:(CGRect)viewport
                                          maxDepth:(NSInteger)maxDepth;

/// Renders a bounded snapshot tree to the same one-line-per-node text
/// `page_source` produces.
///
/// Done here rather than in Swift because the returned object is an
/// `XCElementSnapshot`, and casting it to the `XCUIElementSnapshot` protocol
/// yields a value whose `frame` reads {{0,0},{0,0}} and whose `children` stops
/// after the first level — the tree looks 16 nodes deep and empty when it
/// actually holds hundreds. Reading the same properties through the runtime
/// returns the real values.
+ (nullable NSString *)renderBoundedSnapshot:(id)root
                                    maxDepth:(NSInteger)maxDepth
                                 maxElements:(NSInteger)maxElements
                                 nodesWritten:(NSInteger *)outCount
                                    truncated:(BOOL *)outTruncated;

/// As above, but emits only nodes intersecting `visibleRect` (plus the ancestor
/// path of each, so the result is still a tree). Pass CGRectNull for no culling.
///
/// On a recycling list this is the difference between a usable tree and a
/// useless one: WeChat's chat list returns 1500 nodes of which ~91% sit
/// offscreen (measured y from -9115 to +13204), and those exhaust maxElements
/// before the visible rows are reached. Culling during the walk — rather than
/// afterwards — means the element budget bounds VISIBLE content.
///
/// Note this cannot prune subtrees: a container's frame does not bound its
/// children in a recycling list, so every node is still visited.
+ (nullable NSString *)renderBoundedSnapshot:(id)root
                                    maxDepth:(NSInteger)maxDepth
                                 maxElements:(NSInteger)maxElements
                                 visibleRect:(CGRect)visibleRect
                                 nodesWritten:(NSInteger *)outCount
                                    truncated:(BOOL *)outTruncated;

/// What the snapshot API on THIS XCTest build accepts — class metadata only, no
/// snapshot taken, so it cannot hang the accessibility channel.
+ (NSDictionary *)snapshotAPICapabilities;

/// Selects the single snapshot property `benchmarkSnapshotForBundleID:` samples.
/// Undocumented getters can crash the process outright (SIGBUS, which @catch
/// cannot intercept), so exactly one is read per call and it is named here.
+ (void)setProbeSelectorName:(nullable NSString *)name;

+ (nullable NSDictionary *)benchmarkSnapshotForBundleID:(NSString *)bundleId
                                               maxDepth:(NSInteger)maxDepth;

@end

NS_ASSUME_NONNULL_END
