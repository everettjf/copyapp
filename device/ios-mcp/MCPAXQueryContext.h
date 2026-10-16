#import <Foundation/Foundation.h>
#import <stdint.h>
#import <sys/types.h>

@interface MCPAXQueryContext : NSObject <NSCopying>

@property (nonatomic, assign) pid_t pid;
@property (nonatomic, copy) NSString *bundleId;
@property (nonatomic, copy) NSString *processName;
@property (nonatomic, copy) NSString *sceneIdentifier;
@property (nonatomic, assign) uint32_t contextId;
@property (nonatomic, assign) uint32_t displayId;
@property (nonatomic, copy) NSString *resolverStrategy;
@property (nonatomic, copy) NSArray<NSString *> *resolutionTrace;
@property (nonatomic, copy) NSDictionary *metadata;

- (NSDictionary *)dictionaryRepresentation;

@end
