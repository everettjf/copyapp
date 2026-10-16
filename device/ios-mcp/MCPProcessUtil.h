#import <Foundation/Foundation.h>

FOUNDATION_EXPORT NSString *MCPResolvedJailbreakPath(NSString *path);
FOUNDATION_EXPORT NSDictionary<NSString *, NSString *> *MCPJailbreakEnvironment(void);
FOUNDATION_EXPORT BOOL MCPRunProcess(NSString *launchPath,
                                     NSArray<NSString *> *arguments,
                                     NSDictionary<NSString *, NSString *> *environmentOverrides,
                                     NSTimeInterval timeout,
                                     NSUInteger maxOutputBytes,
                                     NSString **output,
                                     int *exitCode,
                                     NSString **errorMessage);

/// Like MCPRunProcess but captures raw stdout/stderr bytes instead of decoding to a string.
/// Required for reading binary files (plist/db/dumps) where UTF-8 decoding would corrupt data.
FOUNDATION_EXPORT BOOL MCPRunProcessData(NSString *launchPath,
                                         NSArray<NSString *> *arguments,
                                         NSDictionary<NSString *, NSString *> *environmentOverrides,
                                         NSTimeInterval timeout,
                                         NSUInteger maxOutputBytes,
                                         NSData **outputData,
                                         BOOL *truncated,
                                         int *exitCode,
                                         NSString **errorMessage);

/// Resolve the bundled setuid mcp-root helper path, or nil/empty when unavailable.
FOUNDATION_EXPORT NSString *MCPRootHelperPath(void);

/// Run a command as root via the bundled mcp-root helper, capturing raw bytes.
/// Returns NO (with errorMessage) when no privileged helper is available.
FOUNDATION_EXPORT BOOL MCPRunRootProcessData(NSString *launchPath,
                                             NSArray<NSString *> *arguments,
                                             NSTimeInterval timeout,
                                             NSUInteger maxOutputBytes,
                                             NSData **outputData,
                                             BOOL *truncated,
                                             int *exitCode,
                                             NSString **errorMessage);
