#import <Foundation/Foundation.h>

/// Filesystem access for reverse-engineering workflows: list directories, read files
/// (text or binary via base64), and write files. Falls back to the mcp-root helper
/// when the sandboxed server process lacks permission (e.g. other apps' containers,
/// system paths). All paths are resolved through the jailbreak root prefix.
@interface FileSystemManager : NSObject

+ (instancetype)sharedInstance;

/// List directory entries. Returns a dict with "path" and "entries" (name/type/size/mode/mtime),
/// or nil with *error on failure.
- (NSDictionary *)listDirectoryAtPath:(NSString *)path
                                error:(NSString **)error;

/// Read a file. maxBytes caps the payload (0 = default). When the content is valid UTF-8
/// and not forced binary, returns encoding "utf8"; otherwise "base64".
/// Returns a dict with path/size/encoding/content/truncated, or nil with *error.
- (NSDictionary *)readFileAtPath:(NSString *)path
                        maxBytes:(NSUInteger)maxBytes
                     forceBinary:(BOOL)forceBinary
                           error:(NSString **)error;

/// Write a file. content is interpreted per encoding ("utf8" or "base64").
/// Returns a dict with path/bytes_written, or nil with *error.
- (NSDictionary *)writeFileAtPath:(NSString *)path
                          content:(NSString *)content
                         encoding:(NSString *)encoding
                            error:(NSString **)error;

/// Resolve a file for HTTP download. Returns the on-disk path the server can stream
/// (may be a temp copy staged via mcp-root for privileged sources), and whether it is temporary.
/// Returns nil with *error on failure.
- (NSString *)resolveDownloadPath:(NSString *)path
                      isTemporary:(BOOL *)isTemporary
                            error:(NSString **)error;

@end
