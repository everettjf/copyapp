#import <Foundation/Foundation.h>

@interface TextInputManager : NSObject

+ (instancetype)sharedInstance;

/// Bulk text input through system keyboard events
- (void)inputText:(NSString *)text completion:(void (^)(BOOL success, NSString *error))completion;

/// Character-by-character text input, with HID fallback for ASCII
- (void)typeText:(NSString *)text delayMs:(NSTimeInterval)delayMs completion:(void (^)(BOOL success, NSString *error))completion;

/// Press a special key (enter, tab, delete, backspace, space, up, down, left, right)
- (void)pressKey:(NSString *)keyName completion:(void (^)(BOOL success, NSString *error))completion;

@end
