#ifndef AXPrivate_h
#define AXPrivate_h

#import <CoreFoundation/CoreFoundation.h>
#import <CoreGraphics/CoreGraphics.h>
#import <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// ============================================================
// AXUIElement — cross-process accessibility element handle
// ============================================================

typedef const struct __AXUIElement *AXUIElementRef;
typedef int32_t AXError;

enum {
    kAXErrorSuccess                  = 0,
    kAXErrorFailure                  = -25200,
    kAXErrorIllegalArgument          = -25201,
    kAXErrorInvalidUIElement         = -25202,
    kAXErrorCannotComplete           = -25204,
    kAXErrorAttributeUnsupported     = -25205,
    kAXErrorNoValue                  = -25212,
    kAXErrorNotImplemented           = -25208,
};

// ============================================================
// AXUIElement creation
// ============================================================

// Create a root AX element for a given PID (cross-process)
typedef AXUIElementRef (*AXUIElementCreateApplicationFunc)(pid_t pid);

// Private fallback used on some iOS versions where the public create symbol is
// not exported from SpringBoard.
typedef AXUIElementRef (*AXUIElementCreateAppElementWithPidFunc)(pid_t pid);

// Create system-wide AX element
typedef AXUIElementRef (*AXUIElementCreateSystemWideFunc)(void);

// ============================================================
// AXUIElement attribute access
// ============================================================

// Copy the value of an attribute
typedef AXError (*AXUIElementCopyAttributeValueFunc)(AXUIElementRef element, CFStringRef attribute, CFTypeRef *value);

// Copy the value of a parameterized attribute.
typedef AXError (*AXUIElementCopyParameterizedAttributeValueFunc)(AXUIElementRef element, CFStringRef attribute, CFTypeRef parameter, CFTypeRef *value);

// Copy multiple attributes in one IPC round-trip.
typedef AXError (*AXUIElementCopyMultipleAttributeValuesFunc)(AXUIElementRef element, CFArrayRef attributes, uint64_t options, CFArrayRef *values);

// Copy the list of attribute names
typedef AXError (*AXUIElementCopyAttributeNamesFunc)(AXUIElementRef element, CFArrayRef *names);

// Get element at position. On this runtime the out-element pointer is the
// second argument; coordinates remain in s0/s1.
typedef AXError (*AXUIElementCopyElementAtPositionFunc)(AXUIElementRef application, AXUIElementRef *element, float x, float y);

// Variant used by XCTest's XCAXManager_iOS. The third argument is a small
// integer flag; non-zero values are normalized inside AXRuntime before the
// shared implementation handles the hit-test.
typedef AXError (*AXUIElementCopyElementAtPositionWithParamsFunc)(AXUIElementRef application, AXUIElementRef *element, int flags, float x, float y);

// Get application element at position. Same ABI as AXUIElementCopyElementAtPosition.
typedef AXError (*AXUIElementCopyApplicationAtPositionFunc)(AXUIElementRef application, AXUIElementRef *element, float x, float y);

// Get application element plus the remote context id at position.
typedef AXError (*AXUIElementCopyApplicationAndContextAtPositionFunc)(AXUIElementRef application, AXUIElementRef *element, uint32_t *contextId, float x, float y);

// Private internal helper reached by the public wrapper above. Unlike the
// public wrapper, it accepts an explicit displayId and returns the application
// element directly while filling the remote context id.
typedef AXUIElementRef (*AXInternalCopyApplicationAtPositionFunc)(AXUIElementRef application, uint32_t *contextId, uint32_t displayId, float x, float y);

// Reduce AX IPC wait time for a specific element.
typedef AXError (*AXUIElementSetMessagingTimeoutFunc)(AXUIElementRef element, float timeout);

// Higher-level hit-testing entry that accepts a parameter dictionary. The first
// argument is the out-element pointer; the second is an NSDictionary-like
// object carrying keys such as application/point/displayId/contextId/hitTestType.
typedef AXError (*AXUIElementCopyElementWithParametersFunc)(AXUIElementRef *element, CFDictionaryRef parameters);

// Private hit-testing entry that takes an explicit context id.
typedef AXError (*AXUIElementCopyElementUsingContextIdAtPositionFunc)(AXUIElementRef application, uint32_t contextId, AXUIElementRef *element, int options, float x, float y);

// Private hit-testing entry that derives context from display id.
typedef AXError (*AXUIElementCopyElementUsingDisplayIdAtPositionFunc)(AXUIElementRef application, uint32_t displayId, AXUIElementRef *element, int options, float x, float y);

// Get pid associated with an AX element.
typedef AXError (*AXUIElementGetPidFunc)(AXUIElementRef element, pid_t *pid);

// iOS private helpers used by AXRuntime to associate remote PIDs before
// cross-process queries.
typedef void (*AXAddAssociatedPidFunc)(pid_t pid, pid_t associatedPid, int displayType);
typedef bool (*AXIsPidAssociatedFunc)(pid_t pid);
typedef bool (*AXIsPidAssociatedWithDisplayTypeFunc)(pid_t pid, int displayType);

// Match XCTest's `_setAXRequestingClient`, which calls __AXSetRequestingClient(2).
typedef void (*AXSetRequestingClientFunc)(uint32_t clientType);

// Temporarily override AXRuntime's inferred requesting client type.
// Returns the previously resolved client type.
typedef uint64_t (*AXOverrideRequestingClientTypeFunc)(uint64_t clientType);

// ============================================================
// Common AX attribute name constants
// ============================================================

#define kAXRoleAttribute           CFSTR("AXRole")
#define kAXSubroleAttribute        CFSTR("AXSubrole")
#define kAXLabelAttribute          CFSTR("AXLabel")
#define kAXValueAttribute          CFSTR("AXValue")
#define kAXTitleAttribute          CFSTR("AXTitle")
#define kAXDescriptionAttribute    CFSTR("AXDescription")
#define kAXFrameAttribute          CFSTR("AXFrame")
#define kAXEnabledAttribute        CFSTR("AXEnabled")
#define kAXChildrenAttribute       CFSTR("AXChildren")
#define kAXIdentifierAttribute     CFSTR("AXIdentifier")
#define kAXPlaceholderAttribute    CFSTR("AXPlaceholderValue")
#define kAXTraitsAttribute         CFSTR("AXTraits")
#define kAXFocusedAttribute        CFSTR("AXFocused")
#define kAXSelectedAttribute       CFSTR("AXSelected")

#ifdef __cplusplus
}
#endif

#endif /* AXPrivate_h */
