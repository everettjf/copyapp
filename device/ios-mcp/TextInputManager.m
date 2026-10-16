#import "TextInputManager.h"
#import "AccessibilityManager.h"
#import "IOHIDPrivate.h"
#import <mach/mach_time.h>
#import <dlfcn.h>
#import <stdint.h>
#import <sys/types.h>
#import <unistd.h>
#import "MCPLogger.h"

#define TI_LOG(fmt, ...) do { \
    if ([MCPLogger isDebugLoggingEnabled]) { \
        NSString *_iosmcp_log = [NSString stringWithFormat:(@"[TextInput] " fmt), ##__VA_ARGS__]; \
        NSLog(@"[witchan][ios-mcp]%@", _iosmcp_log); \
        [MCPLogger logMessage:_iosmcp_log]; \
    } \
} while (0)

// Keep this aligned with HIDManager.m. iOS filters synthetic events by sender
// metadata; this sender is already proven by the touch/button path.
#define SYNTHETIC_SENDER_ID 0x8000000817319372ULL

// ============================================================
// ASCII to HID usage mapping (US keyboard layout)
// ============================================================

typedef struct {
    uint32_t usage;
    BOOL     shift;
} KeyMapping;

typedef IOHIDEventRef (*MCPIOHIDEventCreateUnicodeEventFunc)(CFAllocatorRef allocator,
                                                             uint64_t timeStamp,
                                                             const uint8_t *payload,
                                                             uint32_t length,
                                                             uint32_t encoding,
                                                             IOOptionBits options);

typedef void (*MCPBKSHIDEventSendToProcessFunc)(IOHIDEventRef event, pid_t pid);

typedef struct {
    BOOL resolved;
    BOOL available;
    void *handle;
    MCPIOHIDEventCreateUnicodeEventFunc createUnicodeEvent;
} MCPIoKitUnicodeRuntime;

typedef struct {
    BOOL resolved;
    BOOL available;
    void *handle;
    MCPBKSHIDEventSendToProcessFunc sendToProcess;
} MCPBackBoardHIDRuntime;

static KeyMapping _asciiToHID[128];
static BOOL _mappingInitialized = NO;
static MCPIoKitUnicodeRuntime sIOKitUnicodeRuntime;
static MCPBackBoardHIDRuntime sBackBoardHIDRuntime;
static NSString *sIOKitUnicodeRuntimeSource = nil;
static NSString *sIOKitUnicodeRuntimeError = nil;
static NSString *sBackBoardHIDRuntimeSource = nil;
static NSString *sBackBoardHIDRuntimeError = nil;

static void initKeyMapping(void) {
    if (_mappingInitialized) return;
    _mappingInitialized = YES;

    memset(_asciiToHID, 0, sizeof(_asciiToHID));

    // Lowercase letters a-z
    for (char c = 'a'; c <= 'z'; c++) {
        _asciiToHID[(int)c] = (KeyMapping){kHIDUsage_Kbd_A + (c - 'a'), NO};
    }
    // Uppercase letters A-Z (shift + letter)
    for (char c = 'A'; c <= 'Z'; c++) {
        _asciiToHID[(int)c] = (KeyMapping){kHIDUsage_Kbd_A + (c - 'A'), YES};
    }
    // Digits 1-9
    for (char c = '1'; c <= '9'; c++) {
        _asciiToHID[(int)c] = (KeyMapping){kHIDUsage_Kbd_1 + (c - '1'), NO};
    }
    _asciiToHID['0'] = (KeyMapping){kHIDUsage_Kbd_0, NO};

    // Shift+digit symbols
    _asciiToHID['!'] = (KeyMapping){kHIDUsage_Kbd_1 + 0, YES};  // Shift+1
    _asciiToHID['@'] = (KeyMapping){kHIDUsage_Kbd_1 + 1, YES};  // Shift+2
    _asciiToHID['#'] = (KeyMapping){kHIDUsage_Kbd_1 + 2, YES};  // Shift+3
    _asciiToHID['$'] = (KeyMapping){kHIDUsage_Kbd_1 + 3, YES};  // Shift+4
    _asciiToHID['%'] = (KeyMapping){kHIDUsage_Kbd_1 + 4, YES};  // Shift+5
    _asciiToHID['^'] = (KeyMapping){kHIDUsage_Kbd_1 + 5, YES};  // Shift+6
    _asciiToHID['&'] = (KeyMapping){kHIDUsage_Kbd_1 + 6, YES};  // Shift+7
    _asciiToHID['*'] = (KeyMapping){kHIDUsage_Kbd_1 + 7, YES};  // Shift+8
    _asciiToHID['('] = (KeyMapping){kHIDUsage_Kbd_1 + 8, YES};  // Shift+9
    _asciiToHID[')'] = (KeyMapping){kHIDUsage_Kbd_0, YES};       // Shift+0

    // Special characters
    _asciiToHID[' ']  = (KeyMapping){kHIDUsage_Kbd_Spacebar, NO};
    _asciiToHID['\n'] = (KeyMapping){kHIDUsage_Kbd_ReturnOrEnter, NO};
    _asciiToHID['\t'] = (KeyMapping){kHIDUsage_Kbd_Tab, NO};
    _asciiToHID['-']  = (KeyMapping){kHIDUsage_Kbd_Hyphen, NO};
    _asciiToHID['_']  = (KeyMapping){kHIDUsage_Kbd_Hyphen, YES};
    _asciiToHID['=']  = (KeyMapping){kHIDUsage_Kbd_EqualSign, NO};
    _asciiToHID['+']  = (KeyMapping){kHIDUsage_Kbd_EqualSign, YES};
    _asciiToHID['[']  = (KeyMapping){kHIDUsage_Kbd_OpenBracket, NO};
    _asciiToHID['{']  = (KeyMapping){kHIDUsage_Kbd_OpenBracket, YES};
    _asciiToHID[']']  = (KeyMapping){kHIDUsage_Kbd_CloseBracket, NO};
    _asciiToHID['}']  = (KeyMapping){kHIDUsage_Kbd_CloseBracket, YES};
    _asciiToHID['\\'] = (KeyMapping){kHIDUsage_Kbd_Backslash, NO};
    _asciiToHID['|']  = (KeyMapping){kHIDUsage_Kbd_Backslash, YES};
    _asciiToHID[';']  = (KeyMapping){kHIDUsage_Kbd_Semicolon, NO};
    _asciiToHID[':']  = (KeyMapping){kHIDUsage_Kbd_Semicolon, YES};
    _asciiToHID['\''] = (KeyMapping){kHIDUsage_Kbd_Quote, NO};
    _asciiToHID['"']  = (KeyMapping){kHIDUsage_Kbd_Quote, YES};
    _asciiToHID['`']  = (KeyMapping){kHIDUsage_Kbd_GraveAccent, NO};
    _asciiToHID['~']  = (KeyMapping){kHIDUsage_Kbd_GraveAccent, YES};
    _asciiToHID[',']  = (KeyMapping){kHIDUsage_Kbd_Comma, NO};
    _asciiToHID['<']  = (KeyMapping){kHIDUsage_Kbd_Comma, YES};
    _asciiToHID['.']  = (KeyMapping){kHIDUsage_Kbd_Period, NO};
    _asciiToHID['>']  = (KeyMapping){kHIDUsage_Kbd_Period, YES};
    _asciiToHID['/']  = (KeyMapping){kHIDUsage_Kbd_Slash, NO};
    _asciiToHID['?']  = (KeyMapping){kHIDUsage_Kbd_Slash, YES};
}

static BOOL textCanUseHIDKeyboard(NSString *text) {
    initKeyMapping();

    for (NSUInteger i = 0; i < text.length; i++) {
        unichar ch = [text characterAtIndex:i];
        if (ch >= 128 || _asciiToHID[ch].usage == 0) {
            return NO;
        }
    }
    return YES;
}

static NSString *lastDLErrorString(void) {
    const char *error = dlerror();
    return error ? [NSString stringWithUTF8String:error] : @"unknown dlopen error";
}

static void *openFrameworkAtPath(NSString *path) {
    if (path.length == 0) return NULL;
    void *handle = dlopen(path.UTF8String, RTLD_LAZY | RTLD_NOLOAD);
    if (!handle) {
        handle = dlopen(path.UTF8String, RTLD_LAZY);
    }
    return handle;
}

static MCPIOHIDEventCreateUnicodeEventFunc resolveUnicodeCreateSymbol(void *handle) {
    if (!handle) return NULL;

    MCPIOHIDEventCreateUnicodeEventFunc createUnicode =
        (MCPIOHIDEventCreateUnicodeEventFunc)dlsym(handle, "IOHIDEventCreateUnicodeEvent");
    if (!createUnicode) {
        createUnicode = (MCPIOHIDEventCreateUnicodeEventFunc)dlsym(handle, "_IOHIDEventCreateUnicodeEvent");
    }
    return createUnicode;
}

static MCPIoKitUnicodeRuntime *resolveIOKitUnicodeRuntime(void) {
    if (sIOKitUnicodeRuntime.resolved) {
        return sIOKitUnicodeRuntime.available ? &sIOKitUnicodeRuntime : NULL;
    }

    sIOKitUnicodeRuntime.resolved = YES;

    MCPIOHIDEventCreateUnicodeEventFunc defaultCreate = resolveUnicodeCreateSymbol(RTLD_DEFAULT);
    if (defaultCreate) {
        sIOKitUnicodeRuntime.createUnicodeEvent = defaultCreate;
        sIOKitUnicodeRuntimeSource = @"RTLD_DEFAULT";
        sIOKitUnicodeRuntime.available = YES;
        TI_LOG(@"Resolved IOHID Unicode runtime from %@", sIOKitUnicodeRuntimeSource);
        return &sIOKitUnicodeRuntime;
    }

    NSArray<NSString *> *paths = @[
        @"/System/Library/Frameworks/IOKit.framework/IOKit",
        @"/rootfs/System/Library/Frameworks/IOKit.framework/IOKit"
    ];
    NSMutableArray<NSString *> *errors = [NSMutableArray array];

    for (NSString *path in paths) {
        void *handle = openFrameworkAtPath(path);
        if (!handle) {
            [errors addObject:[NSString stringWithFormat:@"%@: %@", path, lastDLErrorString()]];
            continue;
        }

        MCPIOHIDEventCreateUnicodeEventFunc createUnicode = resolveUnicodeCreateSymbol(handle);
        if (createUnicode) {
            sIOKitUnicodeRuntime.handle = handle;
            sIOKitUnicodeRuntime.createUnicodeEvent = createUnicode;
            sIOKitUnicodeRuntimeSource = [path copy];
            sIOKitUnicodeRuntime.available = YES;
            TI_LOG(@"Resolved IOHID Unicode runtime from %@", path);
            return &sIOKitUnicodeRuntime;
        }

        [errors addObject:[NSString stringWithFormat:@"%@: missing IOHIDEventCreateUnicodeEvent", path]];
    }

    sIOKitUnicodeRuntimeError = errors.count > 0 ?
        [errors componentsJoinedByString:@"; "] :
        @"IOKit.framework unavailable";
    TI_LOG(@"IOHID Unicode runtime unavailable: %@", sIOKitUnicodeRuntimeError);
    return NULL;
}

static MCPBKSHIDEventSendToProcessFunc resolveBackBoardSendSymbol(void *handle) {
    if (!handle) return NULL;

    MCPBKSHIDEventSendToProcessFunc sendToProcess =
        (MCPBKSHIDEventSendToProcessFunc)dlsym(handle, "BKSHIDEventSendToProcess");
    if (!sendToProcess) {
        sendToProcess = (MCPBKSHIDEventSendToProcessFunc)dlsym(handle, "_BKSHIDEventSendToProcess");
    }
    return sendToProcess;
}

static MCPBackBoardHIDRuntime *resolveBackBoardHIDRuntime(void) {
    if (sBackBoardHIDRuntime.resolved) {
        return sBackBoardHIDRuntime.available ? &sBackBoardHIDRuntime : NULL;
    }

    sBackBoardHIDRuntime.resolved = YES;

    MCPBKSHIDEventSendToProcessFunc defaultSend = resolveBackBoardSendSymbol(RTLD_DEFAULT);
    if (defaultSend) {
        sBackBoardHIDRuntime.sendToProcess = defaultSend;
        sBackBoardHIDRuntimeSource = @"RTLD_DEFAULT";
        sBackBoardHIDRuntime.available = YES;
        TI_LOG(@"Resolved BackBoard HID runtime from %@", sBackBoardHIDRuntimeSource);
        return &sBackBoardHIDRuntime;
    }

    NSArray<NSString *> *paths = @[
        @"/System/Library/PrivateFrameworks/BackBoardServices.framework/BackBoardServices",
        @"/rootfs/System/Library/PrivateFrameworks/BackBoardServices.framework/BackBoardServices"
    ];
    NSMutableArray<NSString *> *errors = [NSMutableArray array];

    for (NSString *path in paths) {
        void *handle = openFrameworkAtPath(path);
        if (!handle) {
            [errors addObject:[NSString stringWithFormat:@"%@: %@", path, lastDLErrorString()]];
            continue;
        }

        MCPBKSHIDEventSendToProcessFunc sendToProcess = resolveBackBoardSendSymbol(handle);
        if (sendToProcess) {
            sBackBoardHIDRuntime.handle = handle;
            sBackBoardHIDRuntime.sendToProcess = sendToProcess;
            sBackBoardHIDRuntimeSource = [path copy];
            sBackBoardHIDRuntime.available = YES;
            TI_LOG(@"Resolved BackBoard HID runtime from %@", path);
            return &sBackBoardHIDRuntime;
        }

        [errors addObject:[NSString stringWithFormat:@"%@: missing BKSHIDEventSendToProcess", path]];
    }

    sBackBoardHIDRuntimeError = errors.count > 0 ?
        [errors componentsJoinedByString:@"; "] :
        @"BackBoardServices.framework unavailable";
    TI_LOG(@"BackBoard HID runtime unavailable: %@", sBackBoardHIDRuntimeError);
    return NULL;
}

static pid_t frontmostTextTargetPid(void) {
    NSDictionary *frontmostInfo = [[AccessibilityManager sharedInstance] frontmostApplicationInfo];
    id pidValue = frontmostInfo[@"pid"] ?: frontmostInfo[@"frontmostPid"];
    if ([pidValue respondsToSelector:@selector(intValue)]) {
        return (pid_t)[pidValue intValue];
    }
    return 0;
}

static NSArray<NSString *> *textChunks(NSString *text, NSUInteger maxUTF16Units) {
    if (maxUTF16Units == 0) maxUTF16Units = 32;

    NSMutableArray<NSString *> *chunks = [NSMutableArray array];
    __block NSMutableString *current = [NSMutableString string];
    [text enumerateSubstringsInRange:NSMakeRange(0, text.length)
                              options:NSStringEnumerationByComposedCharacterSequences
                           usingBlock:^(NSString *substring, NSRange substringRange, NSRange enclosingRange, BOOL *stop) {
        (void)substringRange;
        (void)enclosingRange;
        (void)stop;

        if (substring.length > maxUTF16Units) {
            if (current.length > 0) {
                [chunks addObject:[current copy]];
                [current setString:@""];
            }
            [chunks addObject:substring];
            return;
        }

        if (current.length > 0 && current.length + substring.length > maxUTF16Units) {
            [chunks addObject:[current copy]];
            [current setString:@""];
        }
        [current appendString:substring];
    }];

    if (current.length > 0) {
        [chunks addObject:[current copy]];
    }
    return chunks;
}

@implementation TextInputManager {
    IOHIDEventSystemClientRef _hidClient;
    dispatch_queue_t _inputQueue;
}

+ (instancetype)sharedInstance {
    static TextInputManager *instance;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        instance = [[TextInputManager alloc] init];
    });
    return instance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _inputQueue = dispatch_queue_create("com.witchan.ios-mcp.textinput", DISPATCH_QUEUE_SERIAL);
        _hidClient = IOHIDEventSystemClientCreate(kCFAllocatorDefault);
        initKeyMapping();
    }
    return self;
}

#pragma mark - Text Input

- (BOOL)typeTextViaHID:(NSString *)text delayMs:(NSTimeInterval)delayMs {
    if (!_hidClient || !textCanUseHIDKeyboard(text)) {
        return NO;
    }

    if (delayMs <= 0) delayMs = 50;
    useconds_t delay = (useconds_t)(delayMs * 1000);

    for (NSUInteger i = 0; i < text.length; i++) {
        unichar ch = [text characterAtIndex:i];
        KeyMapping mapping = _asciiToHID[ch];

        if (mapping.shift) {
            [self sendKeyEvent:kHIDPage_KeyboardOrKeypad usage:kHIDUsage_Kbd_LeftShift down:YES];
            usleep(20000);
        }

        [self sendKeyEvent:kHIDPage_KeyboardOrKeypad usage:mapping.usage down:YES];
        usleep(20000);
        [self sendKeyEvent:kHIDPage_KeyboardOrKeypad usage:mapping.usage down:NO];

        if (mapping.shift) {
            usleep(20000);
            [self sendKeyEvent:kHIDPage_KeyboardOrKeypad usage:kHIDUsage_Kbd_LeftShift down:NO];
        }

        usleep(delay);
    }

    return YES;
}

- (BOOL)dispatchUnicodeTextChunk:(NSString *)chunk targetPid:(pid_t)targetPid error:(NSString **)error {
    MCPIoKitUnicodeRuntime *unicodeRuntime = resolveIOKitUnicodeRuntime();
    if (!unicodeRuntime || !unicodeRuntime->createUnicodeEvent) {
        if (error) *error = sIOKitUnicodeRuntimeError ?: @"IOHID Unicode runtime unavailable";
        return NO;
    }

    NSData *payload = [chunk dataUsingEncoding:NSUTF16LittleEndianStringEncoding];
    if (payload.length == 0 || payload.length > UINT32_MAX) {
        if (error) *error = @"Failed to encode text chunk as UTF-16LE";
        return NO;
    }

    IOHIDEventRef event = unicodeRuntime->createUnicodeEvent(
        kCFAllocatorDefault,
        mach_absolute_time(),
        payload.bytes,
        (uint32_t)payload.length,
        kIOHIDUnicodeEncodingTypeUTF16LE,
        0
    );
    if (!event) {
        if (error) *error = @"IOHIDEventCreateUnicodeEvent returned nil";
        return NO;
    }

    IOHIDEventSetIntegerValue(event, 4, 1);
    IOHIDEventSetSenderID(event, SYNTHETIC_SENDER_ID);

    if (_hidClient) {
        IOHIDEventSystemClientDispatchEvent(_hidClient, event);
        CFRelease(event);
        return YES;
    }

    MCPBackBoardHIDRuntime *backBoardRuntime = resolveBackBoardHIDRuntime();
    if (backBoardRuntime && backBoardRuntime->sendToProcess && targetPid > 0) {
        backBoardRuntime->sendToProcess(event, targetPid);
        CFRelease(event);
        return YES;
    }

    NSString *backBoardError = sBackBoardHIDRuntimeError ?: @"BackBoardServices runtime unavailable";
    if (error) {
        *error = [NSString stringWithFormat:@"%@; no IOHIDEventSystemClient fallback", backBoardError];
    }
    CFRelease(event);
    return NO;
}

- (BOOL)sendTextUsingUnicodeHID:(NSString *)text
                        delayMs:(NSTimeInterval)delayMs
           characterByCharacter:(BOOL)characterByCharacter
                           error:(NSString **)error {
    NSUInteger chunkSize = characterByCharacter ? 1 : 64;
    NSArray<NSString *> *chunks = textChunks(text, chunkSize);
    if (chunks.count == 0) {
        if (error) *error = @"Text split produced no input chunks";
        return NO;
    }

    pid_t targetPid = frontmostTextTargetPid();
    useconds_t delay = (useconds_t)(MAX(delayMs, 0) * 1000);

    for (NSString *chunk in chunks) {
        NSString *chunkError = nil;
        if (![self dispatchUnicodeTextChunk:chunk targetPid:targetPid error:&chunkError]) {
            if (error) *error = chunkError ?: @"Failed to dispatch IOHID Unicode text event";
            return NO;
        }

        if (delay > 0) {
            usleep(delay);
        }
    }

    return YES;
}

- (void)inputText:(NSString *)text completion:(void (^)(BOOL, NSString *))completion {
    if (!text.length) {
        if (completion) completion(NO, @"Empty text");
        return;
    }

    dispatch_async(_inputQueue, ^{
        NSString *unicodeError = nil;
        if ([self sendTextUsingUnicodeHID:text delayMs:0 characterByCharacter:NO error:&unicodeError]) {
            if (completion) completion(YES, nil);
            return;
        }

        if ([self typeTextViaHID:text delayMs:10]) {
            if (completion) completion(YES, @"Used HID fallback for ASCII text");
            return;
        }

        NSString *error = [NSString stringWithFormat:@"IOHID Unicode text input failed: %@; HID fallback only supports ASCII keyboard characters",
                           unicodeError ?: @"unknown error"];
        if (completion) completion(NO, error);
    });
}

- (void)typeText:(NSString *)text delayMs:(NSTimeInterval)delayMs completion:(void (^)(BOOL, NSString *))completion {
    if (!text.length) {
        if (completion) completion(NO, @"Empty text");
        return;
    }

    if (delayMs <= 0) delayMs = 50;

    dispatch_async(_inputQueue, ^{
        NSString *unicodeError = nil;
        if ([self sendTextUsingUnicodeHID:text delayMs:delayMs characterByCharacter:YES error:&unicodeError]) {
            if (completion) completion(YES, @"Used IOHID Unicode text events");
            return;
        }

        if ([self typeTextViaHID:text delayMs:delayMs]) {
            if (completion) completion(YES, @"Used HID fallback for ASCII text");
            return;
        }

        NSString *error = [NSString stringWithFormat:@"IOHID Unicode text input failed: %@; HID fallback only supports ASCII keyboard characters",
                           unicodeError ?: @"unknown error"];
        if (completion) completion(NO, error);
    });
}

#pragma mark - Special Key Press

- (void)pressKey:(NSString *)keyName completion:(void (^)(BOOL, NSString *))completion {
    NSString *key = keyName.lowercaseString;
    uint32_t usage = 0;

    if ([key isEqualToString:@"enter"] || [key isEqualToString:@"return"]) {
        usage = kHIDUsage_Kbd_ReturnOrEnter;
    } else if ([key isEqualToString:@"tab"]) {
        usage = kHIDUsage_Kbd_Tab;
    } else if ([key isEqualToString:@"delete"] || [key isEqualToString:@"del"]) {
        usage = kHIDUsage_Kbd_DeleteForward;
    } else if ([key isEqualToString:@"backspace"]) {
        usage = kHIDUsage_Kbd_DeleteOrBackspace;
    } else if ([key isEqualToString:@"space"]) {
        usage = kHIDUsage_Kbd_Spacebar;
    } else if ([key isEqualToString:@"up"]) {
        usage = kHIDUsage_Kbd_UpArrow;
    } else if ([key isEqualToString:@"down"]) {
        usage = kHIDUsage_Kbd_DownArrow;
    } else if ([key isEqualToString:@"left"]) {
        usage = kHIDUsage_Kbd_LeftArrow;
    } else if ([key isEqualToString:@"right"]) {
        usage = kHIDUsage_Kbd_RightArrow;
    } else {
        if (completion) completion(NO, [NSString stringWithFormat:@"Unknown key: %@", keyName]);
        return;
    }

    dispatch_async(_inputQueue, ^{
        [self sendKeyEvent:kHIDPage_KeyboardOrKeypad usage:usage down:YES];
        usleep(50000);
        [self sendKeyEvent:kHIDPage_KeyboardOrKeypad usage:usage down:NO];

        if (completion) completion(YES, nil);
    });
}

#pragma mark - HID Key Event

- (void)sendKeyEvent:(uint32_t)usagePage usage:(uint32_t)usage down:(BOOL)down {
    if (!_hidClient) return;

    IOHIDEventRef event = IOHIDEventCreateKeyboardEvent(
        kCFAllocatorDefault,
        mach_absolute_time(),
        usagePage,
        usage,
        down,
        0
    );
    if (!event) return;

    IOHIDEventSetIntegerValue(event, 4, 1);
    IOHIDEventSetSenderID(event, SYNTHETIC_SENDER_ID);
    IOHIDEventSystemClientDispatchEvent(_hidClient, event);
    CFRelease(event);
}

@end
