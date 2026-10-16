#import "MCPAXQueryContext.h"

@implementation MCPAXQueryContext

- (id)copyWithZone:(NSZone *)zone {
    MCPAXQueryContext *copy = [[[self class] allocWithZone:zone] init];
    copy.pid = self.pid;
    copy.bundleId = self.bundleId;
    copy.processName = self.processName;
    copy.sceneIdentifier = self.sceneIdentifier;
    copy.contextId = self.contextId;
    copy.displayId = self.displayId;
    copy.resolverStrategy = self.resolverStrategy;
    copy.resolutionTrace = self.resolutionTrace;
    copy.metadata = self.metadata;
    return copy;
}

- (NSDictionary *)dictionaryRepresentation {
    NSMutableDictionary *dict = [NSMutableDictionary dictionary];
    if (self.pid > 0) dict[@"pid"] = @(self.pid);
    if (self.bundleId.length > 0) dict[@"bundleId"] = self.bundleId;
    if (self.processName.length > 0) {
        dict[@"processName"] = self.processName;
        dict[@"name"] = self.processName;
    }
    if (self.sceneIdentifier.length > 0) dict[@"sceneIdentifier"] = self.sceneIdentifier;
    if (self.contextId > 0) dict[@"contextId"] = @(self.contextId);
    if (self.displayId > 0) dict[@"displayId"] = @(self.displayId);
    if (self.resolverStrategy.length > 0) dict[@"resolverStrategy"] = self.resolverStrategy;
    if (self.resolutionTrace.count > 0) dict[@"resolutionTrace"] = self.resolutionTrace;
    if (self.metadata.count > 0) dict[@"metadata"] = self.metadata;
    return dict;
}

@end
