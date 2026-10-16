#import "MCPUIElementSerializer.h"
#import "MCPAXQueryContext.h"
#import <UIKit/UIKit.h>

static BOOL MCPUIRectFromObject(id object, CGRect *frame) {
    if (!object || !frame) return NO;

    if ([object isKindOfClass:[NSValue class]]) {
        @try {
            *frame = [object CGRectValue];
            return YES;
        } @catch (__unused NSException *exception) {
        }
    }

    if ([object isKindOfClass:[NSDictionary class]]) {
        NSDictionary *dict = object;
        NSNumber *x = dict[@"x"] ?: dict[@"X"];
        NSNumber *y = dict[@"y"] ?: dict[@"Y"];
        NSNumber *width = dict[@"width"] ?: dict[@"Width"];
        NSNumber *height = dict[@"height"] ?: dict[@"Height"];
        if (x && y && width && height) {
            *frame = CGRectMake(x.doubleValue, y.doubleValue, width.doubleValue, height.doubleValue);
            return YES;
        }
    }

    if ([object isKindOfClass:[NSString class]]) {
        CGRect parsed = CGRectFromString(object);
        if (!CGRectEqualToRect(parsed, CGRectZero) || [object containsString:@"0"]) {
            *frame = parsed;
            return YES;
        }
    }

    if ([object isKindOfClass:[NSArray class]]) {
        NSArray *values = object;
        if (values.count >= 4) {
            *frame = CGRectMake([values[0] doubleValue],
                                [values[1] doubleValue],
                                [values[2] doubleValue],
                                [values[3] doubleValue]);
            return YES;
        }
    }

    return NO;
}

static NSDictionary *MCPUIFrameDictionary(CGRect frame) {
    return @{
        @"x": @((int)CGRectGetMinX(frame)),
        @"y": @((int)CGRectGetMinY(frame)),
        @"width": @((int)CGRectGetWidth(frame)),
        @"height": @((int)CGRectGetHeight(frame))
    };
}

static NSString *MCPUICompactFrameString(NSDictionary *frame) {
    if (![frame isKindOfClass:[NSDictionary class]]) return nil;
    return [NSString stringWithFormat:@"%.0f,%.0f,%.0f,%.0f",
            [frame[@"x"] doubleValue],
            [frame[@"y"] doubleValue],
            [frame[@"width"] doubleValue],
            [frame[@"height"] doubleValue]];
}

static NSNumber *MCPUIUnsignedNumberFromValue(id value) {
    if (!value || value == NSNull.null) return nil;
    if ([value isKindOfClass:[NSNumber class]]) return value;
    if ([value isKindOfClass:[NSString class]]) {
        NSString *stringValue = [(NSString *)value stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]];
        if (stringValue.length == 0) return nil;
        BOOL isHex = [stringValue hasPrefix:@"0x"] || [stringValue hasPrefix:@"0X"];
        unsigned long long parsed = isHex ? strtoull(stringValue.UTF8String, NULL, 16) : strtoull(stringValue.UTF8String, NULL, 10);
        return @(parsed);
    }
    if ([value respondsToSelector:@selector(unsignedLongLongValue)]) {
        return @([value unsignedLongLongValue]);
    }
    return nil;
}

static NSString *MCPUIPrimarySemanticLabel(NSDictionary *node) {
    if (![node isKindOfClass:[NSDictionary class]]) return nil;
    for (NSString *key in @[@"identifier", @"label", @"title", @"placeholder", @"description"]) {
        NSString *value = [node[key] isKindOfClass:[NSString class]] ? [node[key] stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] : nil;
        if (value.length > 0) return value;
    }
    NSArray *userInputLabels = [node[@"user_input_labels"] isKindOfClass:[NSArray class]] ? node[@"user_input_labels"] : nil;
    for (id item in userInputLabels) {
        NSString *value = [item isKindOfClass:[NSString class]] ? [item stringByTrimmingCharactersInSet:[NSCharacterSet whitespaceAndNewlineCharacterSet]] : nil;
        if (value.length > 0) return value;
    }
    return nil;
}

static NSArray<NSString *> *MCPUITraitNames(id traitsValue) {
    NSNumber *traitsNumber = MCPUIUnsignedNumberFromValue(traitsValue);
    if (!traitsNumber) return nil;

    UIAccessibilityTraits traits = (UIAccessibilityTraits)traitsNumber.unsignedLongLongValue;
    if (traits == UIAccessibilityTraitNone) return nil;

    NSMutableArray<NSString *> *names = [NSMutableArray array];
    struct {
        UIAccessibilityTraits trait;
        __unsafe_unretained NSString *name;
    } entries[] = {
        { UIAccessibilityTraitButton, @"button" },
        { UIAccessibilityTraitLink, @"link" },
        { UIAccessibilityTraitImage, @"image" },
        { UIAccessibilityTraitSearchField, @"search_field" },
        { UIAccessibilityTraitKeyboardKey, @"keyboard_key" },
        { UIAccessibilityTraitStaticText, @"static_text" },
        { UIAccessibilityTraitHeader, @"header" },
        { UIAccessibilityTraitTabBar, @"tab_bar" },
        { UIAccessibilityTraitAdjustable, @"adjustable" },
        { UIAccessibilityTraitSelected, @"selected" },
        { UIAccessibilityTraitNotEnabled, @"disabled" },
        { UIAccessibilityTraitSummaryElement, @"summary" },
        { UIAccessibilityTraitAllowsDirectInteraction, @"direct_interaction" },
    };

    for (NSUInteger idx = 0; idx < sizeof(entries) / sizeof(entries[0]); idx++) {
        if ((traits & entries[idx].trait) == entries[idx].trait) {
            [names addObject:entries[idx].name];
        }
    }
    return names.count > 0 ? names : nil;
}

static NSDictionary<NSString *, NSString *> *MCPUIInferredElementTypeInfo(NSDictionary *node) {
    if (![node isKindOfClass:[NSDictionary class]]) return nil;

    NSString *rawRole = [node[@"role"] isKindOfClass:[NSString class]] ? node[@"role"] : @"AXElement";
    NSString *snapshotElementType = [node[@"snapshot_element_type"] isKindOfClass:[NSString class]] ? node[@"snapshot_element_type"] : nil;
    NSString *primaryLabel = MCPUIPrimarySemanticLabel(node);
    NSArray<NSString *> *traitNames = MCPUITraitNames(node[@"traits"]);
    NSArray *children = [node[@"children"] isKindOfClass:[NSArray class]] ? node[@"children"] : nil;
    NSNumber *childCount = MCPUIUnsignedNumberFromValue(node[@"child_count"]) ?: @0;
    BOOL hasChildren = children.count > 0 || childCount.integerValue > 0;
    BOOL hittable = [node[@"hittable"] respondsToSelector:@selector(boolValue)] ? [node[@"hittable"] boolValue] : NO;
    BOOL isRemoteElement = [node[@"is_remote_element"] respondsToSelector:@selector(boolValue)] ? [node[@"is_remote_element"] boolValue] : NO;
    BOOL hasContainerHints = (node[@"container_type"] != nil) || ([node[@"container_types"] isKindOfClass:[NSArray class]] && [node[@"container_types"] count] > 0);

    NSString *elementType = nil;
    NSString *source = nil;

    if (snapshotElementType.length > 0) {
        elementType = snapshotElementType;
        source = @"snapshot_element_type";
    } else if (isRemoteElement) {
        elementType = @"remote_element";
        source = @"is_remote_element";
    } else if ([traitNames containsObject:@"button"]) {
        elementType = @"button";
        source = @"traits";
    } else if ([traitNames containsObject:@"search_field"]) {
        elementType = @"search_field";
        source = @"traits";
    } else if ([traitNames containsObject:@"keyboard_key"]) {
        elementType = @"keyboard_key";
        source = @"traits";
    } else if ([traitNames containsObject:@"link"]) {
        elementType = @"link";
        source = @"traits";
    } else if ([traitNames containsObject:@"image"]) {
        elementType = @"image";
        source = @"traits";
    } else if ([traitNames containsObject:@"header"]) {
        elementType = @"header";
        source = @"traits";
    } else if ([traitNames containsObject:@"adjustable"]) {
        elementType = @"adjustable";
        source = @"traits";
    } else if (node[@"placeholder"]) {
        elementType = @"text_field";
        source = @"placeholder";
    } else if ((node[@"url"] || node[@"path"]) && primaryLabel.length > 0) {
        elementType = @"link";
        source = @"url_path";
    } else if (hasChildren && hasContainerHints) {
        elementType = @"container";
        source = @"container_hints";
    } else if (hasChildren) {
        elementType = @"group";
        source = @"children";
    } else if ([primaryLabel isEqualToString:@"Image"]) {
        elementType = @"image";
        source = @"user_input_labels";
    } else if (primaryLabel.length > 0 && hittable) {
        elementType = @"control";
        source = @"interactive_label";
    } else if (primaryLabel.length > 0) {
        elementType = @"text";
        source = @"semantic_label";
    }

    if (elementType.length == 0) return nil;
    return @{
        @"elementType": elementType,
        @"source": source ?: @"heuristic",
        @"rawRole": rawRole ?: @"AXElement"
    };
}

static NSDictionary *MCPUIAXRuntimeSummaryFromState(NSDictionary *state) {
    if (![state isKindOfClass:[NSDictionary class]] || state.count == 0) return nil;

    NSString *mode = [state[@"axRuntimeMode"] isKindOfClass:[NSString class]] ? state[@"axRuntimeMode"] : nil;
    NSString *registrar = [state[@"recommendedRegistrarProcess"] isKindOfClass:[NSString class]] ? state[@"recommendedRegistrarProcess"] : nil;
    NSNumber *directRegisterLikelyInsufficient = [state[@"currentProcessDirectRegisterLikelyInsufficient"] respondsToSelector:@selector(boolValue)] ?
        state[@"currentProcessDirectRegisterLikelyInsufficient"] :
        nil;
    NSString *why = [state[@"axRuntimeModeExplanation"] isKindOfClass:[NSString class]] ?
        state[@"axRuntimeModeExplanation"] :
        ([state[@"registrarGuidance"] isKindOfClass:[NSString class]] ? state[@"registrarGuidance"] : nil);

    NSMutableDictionary *summary = [NSMutableDictionary dictionary];
    if (mode.length > 0) summary[@"mode"] = mode;
    if (registrar.length > 0) summary[@"registrar"] = registrar;
    if (directRegisterLikelyInsufficient) summary[@"directRegisterLikelyInsufficient"] = @([directRegisterLikelyInsufficient boolValue]);
    if (why.length > 0) summary[@"why"] = why;

    return summary.count > 0 ? [summary copy] : nil;
}

static void MCPUIApplyElementType(NSMutableDictionary *node, NSString *elementType, NSString *source) {
    if (![node isKindOfClass:[NSMutableDictionary class]] || elementType.length == 0) return;

    NSString *currentRole = [node[@"role"] isKindOfClass:[NSString class]] ? node[@"role"] : @"AXElement";
    if (![currentRole isEqualToString:elementType]) {
        if (![node[@"rawRole"] isKindOfClass:[NSString class]] || [((NSString *)node[@"rawRole"]) length] == 0) {
            node[@"rawRole"] = currentRole;
        }
        node[@"role"] = elementType;
    }
    node[@"elementType"] = elementType;

    NSMutableDictionary *semanticContext = [node[@"semanticContext"] isKindOfClass:[NSDictionary class]] ? [node[@"semanticContext"] mutableCopy] : [NSMutableDictionary dictionary];
    if (source.length > 0) {
        semanticContext[@"elementTypeSource"] = source;
    }
    node[@"semanticContext"] = semanticContext;
}

static BOOL MCPUINodeHasChildren(NSDictionary *node) {
    NSArray *children = [node[@"children"] isKindOfClass:[NSArray class]] ? node[@"children"] : nil;
    return children.count > 0;
}

static void MCPUIRefineChildrenSemantics(NSMutableDictionary *node) {
    if (![node isKindOfClass:[NSMutableDictionary class]]) return;

    NSMutableArray<NSMutableDictionary *> *children = [node[@"children"] isKindOfClass:[NSArray class]] ? [node[@"children"] mutableCopy] : nil;
    if (children.count == 0) return;

    NSMutableArray<NSMutableDictionary *> *shortLeafControls = [NSMutableArray array];
    BOOL hasImageChild = NO;
    BOOL hasTextualLeafChild = NO;

    for (NSDictionary *childNode in children) {
        if (![childNode isKindOfClass:[NSDictionary class]]) continue;
        NSString *childType = [childNode[@"elementType"] isKindOfClass:[NSString class]] ? childNode[@"elementType"] : nil;
        if ([childType isEqualToString:@"image"]) {
            hasImageChild = YES;
        }
        if (!MCPUINodeHasChildren(childNode)) {
            NSString *primaryLabel = MCPUIPrimarySemanticLabel(childNode);
            if (primaryLabel.length > 0) {
                hasTextualLeafChild = YES;
            }
        }

        BOOL leaf = !MCPUINodeHasChildren(childNode);
        BOOL hittable = [childNode[@"hittable"] respondsToSelector:@selector(boolValue)] ? [childNode[@"hittable"] boolValue] : NO;
        NSString *primaryLabel = MCPUIPrimarySemanticLabel(childNode);
        if (leaf &&
            hittable &&
            [childType isEqualToString:@"control"] &&
            primaryLabel.length > 0 &&
            primaryLabel.length <= 8) {
            [shortLeafControls addObject:(NSMutableDictionary *)childNode];
        }
    }

    if (shortLeafControls.count >= 3 && children.count <= 6) {
        for (NSMutableDictionary *childNode in shortLeafControls) {
            MCPUIApplyElementType(childNode, @"tab_item", @"sibling_short_controls");
        }
    }

    NSString *nodeType = [node[@"elementType"] isKindOfClass:[NSString class]] ? node[@"elementType"] : nil;
    if (([nodeType isEqualToString:@"container"] || [nodeType isEqualToString:@"group"]) &&
        hasImageChild &&
        hasTextualLeafChild &&
        children.count >= 2 &&
        children.count <= 6) {
        MCPUIApplyElementType(node, @"collection_item", @"child_mix_image_text");
    }

    node[@"children"] = children;
}

@interface MCPUIElementSerializer ()

- (NSDictionary *)normalizedNodeFromRawNode:(NSDictionary *)rawNode
                                 stablePath:(NSString *)stablePath
                                   parentId:(NSString *)parentId
                        inheritedContextId:(uint32_t)inheritedContextId
                        inheritedDisplayId:(uint32_t)inheritedDisplayId
                                rootSource:(NSString *)rootSource
                                   context:(MCPAXQueryContext *)context;

- (uint32_t)contextIdentifierForNode:(NSDictionary *)node inheritedContextId:(uint32_t)inheritedContextId context:(MCPAXQueryContext *)context;
- (uint32_t)displayIdentifierForNode:(NSDictionary *)node inheritedDisplayId:(uint32_t)inheritedDisplayId context:(MCPAXQueryContext *)context;
- (NSString *)elementIdentifierForNode:(NSDictionary *)node stablePath:(NSString *)stablePath context:(MCPAXQueryContext *)context contextId:(uint32_t)contextId;
- (NSDictionary *)normalizedFrameFromObject:(id)object;

@end

@implementation MCPUIElementSerializer

- (NSDictionary *)normalizedElementFromRawElement:(NSDictionary *)rawElement
                                          context:(MCPAXQueryContext *)context
                                            point:(CGPoint)point {
    if (![rawElement isKindOfClass:[NSDictionary class]] || !context) return nil;

    NSString *rootSource = [rawElement[@"source"] isKindOfClass:[NSString class]] ? rawElement[@"source"] : @"direct_ax_hit_test";
    NSMutableDictionary *element = [[self normalizedNodeFromRawNode:rawElement
                                                         stablePath:@"hit"
                                                           parentId:nil
                                                inheritedContextId:context.contextId
                                                inheritedDisplayId:context.displayId
                                                        rootSource:rootSource
                                                           context:context] mutableCopy];
    if (!element) return nil;

    element[@"architecture"] = @"ax_runtime_facade_v1";
    element[@"queryContext"] = [context dictionaryRepresentation];
    element[@"queryPoint"] = @{
        @"x": @((int)point.x),
        @"y": @((int)point.y)
    };
    if (context.metadata.count > 0) {
        element[@"resolverMetadata"] = context.metadata;
        NSDictionary *accessibilityState = [context.metadata[@"accessibilityState"] isKindOfClass:[NSDictionary class]] ?
            context.metadata[@"accessibilityState"] :
            nil;
        if (accessibilityState.count > 0) {
            element[@"accessibilityState"] = accessibilityState;
            NSString *axRuntimeMode = [accessibilityState[@"axRuntimeMode"] isKindOfClass:[NSString class]] ?
                accessibilityState[@"axRuntimeMode"] :
                nil;
            if (axRuntimeMode.length > 0) {
                element[@"axRuntimeMode"] = axRuntimeMode;
            }
            NSDictionary *axRuntimeSummary = MCPUIAXRuntimeSummaryFromState(accessibilityState);
            if (axRuntimeSummary.count > 0) {
                element[@"axRuntimeSummary"] = axRuntimeSummary;
            }
        }
    }
    return element;
}

- (NSDictionary *)normalizedNodeFromRawNode:(NSDictionary *)rawNode
                                 stablePath:(NSString *)stablePath
                                   parentId:(NSString *)parentId
                        inheritedContextId:(uint32_t)inheritedContextId
                        inheritedDisplayId:(uint32_t)inheritedDisplayId
                                rootSource:(NSString *)rootSource
                                   context:(MCPAXQueryContext *)context {
    if (![rawNode isKindOfClass:[NSDictionary class]]) return nil;

    NSMutableDictionary *node = [rawNode mutableCopy];
    NSString *role = [node[@"role"] isKindOfClass:[NSString class]] ? node[@"role"] : @"AXElement";
    node[@"role"] = role;

    NSArray<NSString *> *traitNames = MCPUITraitNames(node[@"traits"]);
    if (traitNames.count > 0) {
        node[@"trait_names"] = traitNames;
    }

    NSDictionary *frame = [self normalizedFrameFromObject:node[@"frame"]];
    NSDictionary *visibleFrame = [self normalizedFrameFromObject:node[@"visibleFrame"]];
    if (frame) {
        node[@"frame"] = frame;
    }
    if (visibleFrame) {
        node[@"visibleFrame"] = visibleFrame;
    } else if (frame) {
            node[@"visibleFrame"] = frame;
    }

    NSNumber *hidden = [node[@"hidden"] isKindOfClass:[NSNumber class]] ? node[@"hidden"] : nil;
    if (!node[@"visible"]) {
        BOOL visible = hidden ? !hidden.boolValue : YES;
        if (!visible && frame) {
            visible = ([frame[@"width"] doubleValue] > 0.0 && [frame[@"height"] doubleValue] > 0.0);
        }
        node[@"visible"] = @(visible);
    }

    if (!node[@"hittable"]) {
        NSNumber *enabled = [node[@"enabled"] isKindOfClass:[NSNumber class]] ? node[@"enabled"] : nil;
        BOOL hittable = [node[@"visible"] boolValue] && (!enabled || enabled.boolValue);
        node[@"hittable"] = @(hittable);
    }

    uint32_t contextId = [self contextIdentifierForNode:node inheritedContextId:inheritedContextId context:context];
    uint32_t displayId = [self displayIdentifierForNode:node inheritedDisplayId:inheritedDisplayId context:context];
    if (contextId > 0) node[@"contextId"] = @(contextId);
    if (displayId > 0) node[@"displayId"] = @(displayId);

    if (context.pid > 0 && !node[@"pid"]) node[@"pid"] = @(context.pid);
    if (context.bundleId.length > 0 && !node[@"bundleId"]) node[@"bundleId"] = context.bundleId;
    if (context.processName.length > 0 && !node[@"processName"]) node[@"processName"] = context.processName;

    node[@"stablePath"] = stablePath ?: @"0";
    NSString *elementId = [self elementIdentifierForNode:node stablePath:stablePath context:context contextId:contextId];
    node[@"id"] = elementId;
    node[@"element_id"] = elementId;
    if (parentId.length > 0) {
        node[@"parent"] = parentId;
        node[@"parentId"] = parentId;
    }

    NSMutableDictionary *semanticContext = [NSMutableDictionary dictionary];
    NSDictionary *existingSemanticContext = [node[@"semanticContext"] isKindOfClass:[NSDictionary class]] ? node[@"semanticContext"] : nil;
    if (existingSemanticContext.count > 0) {
        [semanticContext addEntriesFromDictionary:existingSemanticContext];
    }
    if (rootSource.length > 0) semanticContext[@"source"] = rootSource;
    if (context.resolverStrategy.length > 0) semanticContext[@"resolverStrategy"] = context.resolverStrategy;
    if (context.sceneIdentifier.length > 0) semanticContext[@"sceneIdentifier"] = context.sceneIdentifier;
    if (contextId > 0) semanticContext[@"contextId"] = @(contextId);
    if (displayId > 0) semanticContext[@"displayId"] = @(displayId);

    NSDictionary<NSString *, NSString *> *typeInfo = MCPUIInferredElementTypeInfo(node);
    NSString *elementType = [typeInfo[@"elementType"] isKindOfClass:[NSString class]] ? typeInfo[@"elementType"] : nil;
    NSString *rawRole = [typeInfo[@"rawRole"] isKindOfClass:[NSString class]] ? typeInfo[@"rawRole"] : nil;
    if (elementType.length > 0) {
        node[@"elementType"] = elementType;
        semanticContext[@"elementTypeSource"] = typeInfo[@"source"] ?: @"heuristic";
        if ([role isEqualToString:@"AXElement"] || [role isEqualToString:@"AXSnapshotElement"]) {
            node[@"rawRole"] = rawRole ?: role;
            node[@"role"] = elementType;
        }
    }

    node[@"semanticContext"] = semanticContext;

    NSArray *rawChildren = [rawNode[@"children"] isKindOfClass:[NSArray class]] ? rawNode[@"children"] : nil;
    NSMutableArray *children = [NSMutableArray array];
    [rawChildren enumerateObjectsUsingBlock:^(id child, NSUInteger idx, BOOL *stop) {
        if (![child isKindOfClass:[NSDictionary class]]) return;
        NSString *childPath = [NSString stringWithFormat:@"%@.%lu", stablePath ?: @"0", (unsigned long)idx];
        NSDictionary *normalizedChild = [self normalizedNodeFromRawNode:child
                                                             stablePath:childPath
                                                               parentId:elementId
                                                    inheritedContextId:contextId
                                                    inheritedDisplayId:displayId
                                                            rootSource:rootSource
                                                               context:context];
        if (normalizedChild) {
            [children addObject:normalizedChild];
        }
    }];
    node[@"children"] = children;
    MCPUIRefineChildrenSemantics(node);
    return node;
}

- (uint32_t)contextIdentifierForNode:(NSDictionary *)node inheritedContextId:(uint32_t)inheritedContextId context:(MCPAXQueryContext *)context {
    id values[] = {
        node[@"contextId"],
        node[@"window_context_id"],
        inheritedContextId > 0 ? @(inheritedContextId) : nil,
        context.contextId > 0 ? @(context.contextId) : nil
    };
    for (NSUInteger idx = 0; idx < sizeof(values) / sizeof(values[0]); idx++) {
        id value = values[idx];
        if ([value respondsToSelector:@selector(unsignedIntValue)]) {
            uint32_t candidate = (uint32_t)[value unsignedIntValue];
            if (candidate > 0) return candidate;
        }
    }
    return 0;
}

- (uint32_t)displayIdentifierForNode:(NSDictionary *)node inheritedDisplayId:(uint32_t)inheritedDisplayId context:(MCPAXQueryContext *)context {
    id values[] = {
        node[@"displayId"],
        node[@"window_display_id"],
        inheritedDisplayId > 0 ? @(inheritedDisplayId) : nil,
        context.displayId > 0 ? @(context.displayId) : nil
    };
    for (NSUInteger idx = 0; idx < sizeof(values) / sizeof(values[0]); idx++) {
        id value = values[idx];
        if ([value respondsToSelector:@selector(unsignedIntValue)]) {
            uint32_t candidate = (uint32_t)[value unsignedIntValue];
            if (candidate > 0) return candidate;
        }
    }
    return 0;
}

- (NSString *)elementIdentifierForNode:(NSDictionary *)node stablePath:(NSString *)stablePath context:(MCPAXQueryContext *)context contextId:(uint32_t)contextId {
    NSString *existing = [node[@"id"] isKindOfClass:[NSString class]] ? node[@"id"] : nil;
    if (existing.length > 0) return existing;

    NSMutableArray<NSString *> *parts = [NSMutableArray array];
    if (context.pid > 0) [parts addObject:[NSString stringWithFormat:@"pid:%d", context.pid]];
    if (contextId > 0) [parts addObject:[NSString stringWithFormat:@"ctx:%u", contextId]];
    if (stablePath.length > 0) [parts addObject:[NSString stringWithFormat:@"path:%@", stablePath]];

    NSString *role = [node[@"role"] isKindOfClass:[NSString class]] ? node[@"role"] : @"AXElement";
    [parts addObject:[NSString stringWithFormat:@"role:%@", role]];

    for (NSString *key in @[@"identifier", @"label", @"title", @"value"]) {
        NSString *value = [node[key] isKindOfClass:[NSString class]] ? node[key] : nil;
        if (value.length > 0) {
            [parts addObject:[NSString stringWithFormat:@"%@:%@", key, value]];
            break;
        }
    }

    NSDictionary *frame = [node[@"frame"] isKindOfClass:[NSDictionary class]] ? node[@"frame"] : nil;
    NSString *frameString = MCPUICompactFrameString(frame);
    if (frameString.length > 0) {
        [parts addObject:[NSString stringWithFormat:@"frame:%@", frameString]];
    }
    return [parts componentsJoinedByString:@"|"];
}

- (NSDictionary *)normalizedFrameFromObject:(id)object {
    if ([object isKindOfClass:[NSDictionary class]]) return object;

    CGRect frame = CGRectZero;
    if (!MCPUIRectFromObject(object, &frame)) return nil;
    return MCPUIFrameDictionary(frame);
}

@end
