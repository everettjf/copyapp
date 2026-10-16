#import <Foundation/Foundation.h>

/// Log collection for reverse-engineering / debugging: query the unified system log
/// (via the `log` CLI through the mcp-root helper) and enumerate / read crash reports.
@interface LogManager : NSObject

+ (instancetype)sharedInstance;

/// Query the unified system log. process filters by process name/image (optional),
/// lastSeconds bounds the time window, maxLines caps returned lines.
/// Returns a dict with lines/count/truncated, or nil with *error.
- (NSDictionary *)syslogWithProcess:(NSString *)process
                              level:(NSString *)level
                        lastSeconds:(NSInteger)lastSeconds
                           maxLines:(NSInteger)maxLines
                              error:(NSString **)error;

/// List crash reports, optionally filtered by bundle id / process name prefix.
/// Returns a dict with "reports" (name/path/date/size), or nil with *error.
- (NSDictionary *)crashLogsForBundleId:(NSString *)bundleId
                                 limit:(NSInteger)limit
                                 error:(NSString **)error;

/// Read a single crash report's full text by path. Returns dict with path/content, or nil with *error.
- (NSDictionary *)crashLogContentAtPath:(NSString *)path
                                  error:(NSString **)error;

@end
