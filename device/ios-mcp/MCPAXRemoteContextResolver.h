#import <Foundation/Foundation.h>

@class MCPAXQueryContext;

@interface MCPAXRemoteContextResolver : NSObject

- (MCPAXQueryContext *)frontmostContext;
- (NSDictionary *)frontmostContextDictionary;

@end
