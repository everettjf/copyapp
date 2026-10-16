#import "MCPUIElementsFacade.h"
#import "MCPAXQueryContext.h"
#import "MCPAXRemoteContextResolver.h"
#import "MCPUIElementSerializer.h"

@interface MCPUIElementsFacade ()

@property (nonatomic, strong) MCPAXRemoteContextResolver *contextResolver;
@property (nonatomic, strong) MCPUIElementSerializer *serializer;
@property (nonatomic, copy) MCPUIElementAtPointProvider directElementProvider;

- (NSDictionary *)decorateResult:(NSDictionary *)result
                     providerUsed:(NSString *)providerUsed
               attemptedProviders:(NSArray<NSString *> *)attemptedProviders
                   providerErrors:(NSArray<NSString *> *)providerErrors
                        queryKind:(NSString *)queryKind;
- (NSString *)accessibilityStateErrorSuffixForContext:(MCPAXQueryContext *)context;

@end

@implementation MCPUIElementsFacade

- (instancetype)initWithContextResolver:(MCPAXRemoteContextResolver *)contextResolver
                              serializer:(MCPUIElementSerializer *)serializer
                   directElementProvider:(MCPUIElementAtPointProvider)directElementProvider {
    self = [super init];
    if (self) {
        _contextResolver = contextResolver;
        _serializer = serializer;
        _directElementProvider = [directElementProvider copy];
    }
    return self;
}

- (NSDictionary *)elementAtPoint:(CGPoint)point
                           error:(NSString **)error {
    MCPAXQueryContext *context = [self.contextResolver frontmostContext];
    if (context.pid <= 0) {
        if (error) *error = @"Cannot determine frontmost app PID";
        return nil;
    }

    NSMutableArray<NSString *> *errors = [NSMutableArray array];
    NSMutableArray<NSString *> *attemptedProviders = [NSMutableArray array];
    NSDictionary *rawElement = nil;

    if (self.directElementProvider) {
        [attemptedProviders addObject:@"direct_ax"];
        @try {
            NSString *directError = nil;
            rawElement = self.directElementProvider(context, point, &directError);
            if (rawElement) {
                NSDictionary *normalizedElement = [self.serializer normalizedElementFromRawElement:rawElement context:context point:point];
                return [self decorateResult:normalizedElement
                               providerUsed:@"direct_ax"
                         attemptedProviders:attemptedProviders
                             providerErrors:errors
                                  queryKind:@"hit_test"];
            }
            if (directError.length > 0) {
                [errors addObject:[NSString stringWithFormat:@"direct_ax=%@", directError]];
            }
        } @catch (NSException *exception) {
            [errors addObject:[NSString stringWithFormat:@"direct_ax_exception=%@: %@", exception.name, exception.reason ?: @"<no reason>"]];
        }
    }

    if (error) {
        NSString *providerTrace = attemptedProviders.count > 0 ?
            [NSString stringWithFormat:@"providers=%@", [attemptedProviders componentsJoinedByString:@","]] :
            @"providers=<none>";
        NSString *stateSuffix = [self accessibilityStateErrorSuffixForContext:context];
        if (errors.count > 0) {
            NSMutableArray<NSString *> *parts = [NSMutableArray arrayWithObjects:providerTrace, [errors componentsJoinedByString:@"; "], nil];
            if (stateSuffix.length > 0) [parts addObject:stateSuffix];
            *error = [parts componentsJoinedByString:@"; "];
        } else {
            NSMutableArray<NSString *> *parts = [NSMutableArray arrayWithObjects:providerTrace, @"No UI element provider returned a result", nil];
            if (stateSuffix.length > 0) [parts addObject:stateSuffix];
            *error = [parts componentsJoinedByString:@"; "];
        }
    }
    return nil;
}

- (NSDictionary *)decorateResult:(NSDictionary *)result
                     providerUsed:(NSString *)providerUsed
               attemptedProviders:(NSArray<NSString *> *)attemptedProviders
                   providerErrors:(NSArray<NSString *> *)providerErrors
                        queryKind:(NSString *)queryKind {
    if (![result isKindOfClass:[NSDictionary class]]) return result;

    NSMutableDictionary *decorated = [result mutableCopy];
    NSMutableDictionary *providerDiagnostics = [NSMutableDictionary dictionary];
    if (queryKind.length > 0) {
        providerDiagnostics[@"queryKind"] = queryKind;
    }
    if (providerUsed.length > 0) {
        providerDiagnostics[@"providerUsed"] = providerUsed;
        decorated[@"providerUsed"] = providerUsed;
    }
    if (attemptedProviders.count > 0) {
        providerDiagnostics[@"attemptedProviders"] = attemptedProviders;
    }
    if (providerErrors.count > 0) {
        providerDiagnostics[@"providerErrors"] = providerErrors;
    }
    decorated[@"providerDiagnostics"] = providerDiagnostics;

    NSMutableDictionary *semanticContext = [decorated[@"semanticContext"] isKindOfClass:[NSDictionary class]] ?
        [decorated[@"semanticContext"] mutableCopy] :
        [NSMutableDictionary dictionary];
    if (providerUsed.length > 0) {
        semanticContext[@"providerUsed"] = providerUsed;
    }
    if (attemptedProviders.count > 0) {
        semanticContext[@"attemptedProviders"] = attemptedProviders;
    }
    decorated[@"semanticContext"] = semanticContext;
    return decorated;
}

- (NSString *)accessibilityStateErrorSuffixForContext:(MCPAXQueryContext *)context {
    NSDictionary *state = [context.metadata[@"accessibilityState"] isKindOfClass:[NSDictionary class]] ?
        context.metadata[@"accessibilityState"] :
        nil;
    if (state.count == 0) return nil;

    NSNumber *voiceOverRunning = [state[@"voiceOverRunning"] respondsToSelector:@selector(boolValue)] ?
        state[@"voiceOverRunning"] :
        nil;
    NSNumber *runtimeLikelyActive = [state[@"runtimeLikelyActive"] respondsToSelector:@selector(boolValue)] ?
        state[@"runtimeLikelyActive"] :
        nil;
    NSNumber *accessibilitySceneCount = [state[@"workspaceAccessibilitySceneCount"] respondsToSelector:@selector(integerValue)] ?
        state[@"workspaceAccessibilitySceneCount"] :
        nil;
    NSNumber *voiceOverSceneCount = [state[@"workspaceVoiceOverSceneCount"] respondsToSelector:@selector(integerValue)] ?
        state[@"workspaceVoiceOverSceneCount"] :
        nil;
    NSString *registrationHeuristic = [state[@"registrationHeuristic"] isKindOfClass:[NSString class]] ?
        state[@"registrationHeuristic"] :
        nil;
    NSString *axRuntimeMode = [state[@"axRuntimeMode"] isKindOfClass:[NSString class]] ?
        state[@"axRuntimeMode"] :
        nil;
    NSString *recommendedRegistrarProcess = [state[@"recommendedRegistrarProcess"] isKindOfClass:[NSString class]] ?
        state[@"recommendedRegistrarProcess"] :
        nil;
    NSString *guidance = [state[@"guidance"] isKindOfClass:[NSString class]] ?
        state[@"guidance"] :
        nil;
    NSString *registrarGuidance = [state[@"registrarGuidance"] isKindOfClass:[NSString class]] ?
        state[@"registrarGuidance"] :
        nil;
    NSNumber *directRegisterInsufficient = [state[@"currentProcessDirectRegisterLikelyInsufficient"] respondsToSelector:@selector(boolValue)] ?
        state[@"currentProcessDirectRegisterLikelyInsufficient"] :
        nil;
    NSNumber *currentProcessLooksLikeRegistrar = [state[@"currentProcessLooksLikeVoiceOverRegistrar"] respondsToSelector:@selector(boolValue)] ?
        state[@"currentProcessLooksLikeVoiceOverRegistrar"] :
        nil;

    NSMutableArray<NSString *> *parts = [NSMutableArray array];
    NSMutableArray<NSString *> *summary = [NSMutableArray array];
    if (voiceOverRunning) [summary addObject:[NSString stringWithFormat:@"voiceOver=%d", voiceOverRunning.boolValue]];
    if (runtimeLikelyActive) [summary addObject:[NSString stringWithFormat:@"runtimeActive=%d", runtimeLikelyActive.boolValue]];
    if (accessibilitySceneCount) [summary addObject:[NSString stringWithFormat:@"axScenes=%ld", (long)accessibilitySceneCount.integerValue]];
    if (voiceOverSceneCount) [summary addObject:[NSString stringWithFormat:@"voScenes=%ld", (long)voiceOverSceneCount.integerValue]];
    if (axRuntimeMode.length > 0) [summary addObject:[NSString stringWithFormat:@"mode=%@", axRuntimeMode]];
    if (registrationHeuristic.length > 0) [summary addObject:[NSString stringWithFormat:@"registration=%@", registrationHeuristic]];
    if (recommendedRegistrarProcess.length > 0) [summary addObject:[NSString stringWithFormat:@"registrar=%@", recommendedRegistrarProcess]];
    if (currentProcessLooksLikeRegistrar) [summary addObject:[NSString stringWithFormat:@"currentRegistrarLike=%d", currentProcessLooksLikeRegistrar.boolValue]];
    if (directRegisterInsufficient) [summary addObject:[NSString stringWithFormat:@"directRegisterInsufficient=%d", directRegisterInsufficient.boolValue]];
    if (summary.count > 0) {
        [parts addObject:[NSString stringWithFormat:@"accessibilityState[%@]", [summary componentsJoinedByString:@","]]];
    }
    if (guidance.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"accessibilityHint=%@", guidance]];
    }
    if (registrarGuidance.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"registrarHint=%@", registrarGuidance]];
    }
    return parts.count > 0 ? [parts componentsJoinedByString:@"; "] : nil;
}

@end
