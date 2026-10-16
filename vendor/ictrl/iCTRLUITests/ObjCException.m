#import "ObjCException.h"
#import <objc/message.h>
#import <CoreGraphics/CoreGraphics.h>
#import <objc/runtime.h>
#import <XCTest/XCTest.h>

// performSelector on a runtime-resolved selector: ARC cannot see the
// ownership convention, and these all follow the standard one.
#pragma clang diagnostic ignored "-Warc-performSelector-leaks"

@implementation ObjCException

+ (nullable NSString *)catching:(void (^)(void))block {
    @try {
        block();
        return nil;
    } @catch (NSException *e) {
        NSString *reason = e.reason ?: e.name ?: @"unknown Obj-C exception";
        NSLog(@"iCTRL: caught Obj-C exception: %@", reason);
        return reason;
    }
}


+ (nullable id)screenshotOf:(id)screen encoding:(id)encoding {
    @try {
        NSError *err = nil;
        SEL three = NSSelectorFromString(@"screenshotWithPreferredEncoding:rect:error:");
        if ([screen respondsToSelector:three]) {
            id (*fn)(id, SEL, id, CGRect, NSError **) = (id (*)(id, SEL, id, CGRect, NSError **))objc_msgSend;
            return fn(screen, three, encoding, CGRectNull, &err);
        }
        SEL four = NSSelectorFromString(@"screenshotWithPreferredEncoding:rect:options:error:");
        if ([screen respondsToSelector:four]) {
            id (*fn)(id, SEL, id, CGRect, id, NSError **) = (id (*)(id, SEL, id, CGRect, id, NSError **))objc_msgSend;
            return fn(screen, four, encoding, CGRectNull, nil, &err);
        }
    } @catch (__unused NSException *e) {}
    return nil;
}

+ (nullable NSData *)daemonScreenshotWithEncoding:(id)encoding
                                          timeout:(double)timeout
                                              why:(NSString * _Nullable * _Nullable)why {
    @try {
        Class sessionClass = NSClassFromString(@"XCTRunnerDaemonSession");
        Class requestClass = NSClassFromString(@"XCTScreenshotRequest");
        SEL shared = NSSelectorFromString(@"sharedSession");
        SEL request = NSSelectorFromString(@"requestScreenshotWithRequest:withReply:");
        if (!sessionClass || !requestClass || ![sessionClass respondsToSelector:shared]) {
            if (why) { *why = @"XCTRunnerDaemonSession / XCTScreenshotRequest missing"; }
            return nil;
        }
        id session = [sessionClass performSelector:shared];
        if (![session respondsToSelector:request]) {
            if (why) { *why = @"session lacks requestScreenshotWithRequest:withReply:"; }
            return nil;
        }
        long long screenID = 1;
        @try { screenID = [[XCUIScreen.mainScreen valueForKey:@"displayID"] longLongValue]; } @catch (__unused NSException *e) {}
        id req = nil;
        SEL init4 = NSSelectorFromString(@"initWithScreenID:rect:encoding:options:");
        SEL init3 = NSSelectorFromString(@"initWithScreenID:rect:encoding:");
        if ([requestClass instancesRespondToSelector:init4]) {
            id (*f)(id, SEL, long long, CGRect, id, id) = (id (*)(id, SEL, long long, CGRect, id, id))objc_msgSend;
            req = f([requestClass alloc], init4, screenID, CGRectNull, encoding, nil);
        } else if ([requestClass instancesRespondToSelector:init3]) {
            id (*f)(id, SEL, long long, CGRect, id) = (id (*)(id, SEL, long long, CGRect, id))objc_msgSend;
            req = f([requestClass alloc], init3, screenID, CGRectNull, encoding);
        }
        if (!req) {
            if (why) { *why = @"XCTScreenshotRequest init failed"; }
            return nil;
        }
        dispatch_semaphore_t done = dispatch_semaphore_create(0);
        __block id image = nil;
        __block NSError *error = nil;
        void (*send)(id, SEL, id, id) = (void (*)(id, SEL, id, id))objc_msgSend;
        send(session, request, req, ^(id img, NSError *err) {
            image = img; error = err;
            dispatch_semaphore_signal(done);
        });
        if (dispatch_semaphore_wait(done, dispatch_time(DISPATCH_TIME_NOW, (int64_t)(timeout * NSEC_PER_SEC))) != 0) {
            if (why) { *why = @"no reply in time"; }
            return nil;
        }
        if (error || ![image respondsToSelector:@selector(data)]) {
            if (why) { *why = error.localizedDescription ?: @"reply carried no image data"; }
            return nil;
        }
        NSData *data = [image performSelector:@selector(data)];
        if (!data.length && why) { *why = @"empty image data"; }
        return data.length ? data : nil;
    } @catch (NSException *e) {
        if (why) { *why = e.reason ?: e.name; }
        return nil;
    }
}

+ (nullable id)makeImageEncoding:(Class)encodingClass
                             uti:(NSString *)uti
                         quality:(double)quality
                        diagnosis:(NSString * _Nullable * _Nullable)diagnosis {
    // Three ways in, cheapest and most reliable first. Hand-rolling
    // objc_msgSend against a private initializer is the fragile one, so it is
    // the last resort rather than the first attempt.
    NSMutableArray<NSString *> *tried = [NSMutableArray array];

    // 1. Dictionary init — plain object types, no calling-convention guesswork.
    SEL dictSel = NSSelectorFromString(@"initWithDictionary:");
    if ([encodingClass instancesRespondToSelector:dictSel]) {
        NSDictionary *spec = @{
            @"uniformTypeIdentifier": uti,
            @"compressionQuality": @(quality),
        };
        id obj = [[encodingClass alloc] performSelector:dictSel withObject:spec];
        // Xcode 27 renamed the keys: the object comes back with a nil type
        // and quality 0, which encodes nothing. Only keep it if it took.
        BOOL took = NO;
        @try { took = [obj valueForKey:@"uniformTypeIdentifier"] != nil; } @catch (__unused NSException *e) {}
        if (obj && took) {
            if (diagnosis) { *diagnosis = @"via initWithDictionary:"; }
            return obj;
        }
        [tried addObject:obj ? @"initWithDictionary:->empty" : @"initWithDictionary:->nil"];
    }

    // 2. The class's own factory. No arguments, so nothing can be mis-marshalled;
    //    it fixes the quality rather than taking ours, which is fine — the point
    //    is a compressed capture, not one specific ratio.
    SEL maxSel = NSSelectorFromString(@"maximumCompression");
    if ([encodingClass respondsToSelector:maxSel]) {
        id obj = [encodingClass performSelector:maxSel];
        // On Xcode 27 this returns the class itself, not an instance; XPC
        // then refuses to send it ("Class objects may not be encoded").
        if (obj && !class_isMetaClass(object_getClass(obj))) {
            if (diagnosis) { *diagnosis = @"via +maximumCompression"; }
            return obj;
        }
        [tried addObject:@"+maximumCompression->no instance"];
    }

    // 3. Designated initializer through objc_msgSend, typed from the runtime's
    //    own signature (the quality argument is not double on every OS).
    SEL sel = NSSelectorFromString(@"initWithUniformTypeIdentifier:compressionQuality:");
    if ([encodingClass instancesRespondToSelector:sel]) {
        NSMethodSignature *sig = [encodingClass instanceMethodSignatureForSelector:sel];
        const char *qType = sig ? [sig getArgumentTypeAtIndex:3] : NULL;
        void *(*msgAlloc)(Class, SEL) = (void *(*)(Class, SEL))objc_msgSend;
        void *allocated = msgAlloc(encodingClass, @selector(alloc));
        void *created = NULL;
        if (allocated && qType && strcmp(qType, @encode(float)) == 0) {
            void *(*f)(void *, SEL, void *, float) = (void *(*)(void *, SEL, void *, float))objc_msgSend;
            created = f(allocated, sel, (__bridge void *)uti, (float)quality);
        } else if (allocated && qType && strcmp(qType, @encode(double)) == 0) {
            void *(*f)(void *, SEL, void *, double) = (void *(*)(void *, SEL, void *, double))objc_msgSend;
            created = f(allocated, sel, (__bridge void *)uti, quality);
        }
        if (created) {
            if (diagnosis) { *diagnosis = @"via initWithUniformTypeIdentifier:"; }
            return (__bridge_transfer id)created;
        }
        [tried addObject:[NSString stringWithFormat:@"init(uti:quality)->nil qType='%s'", qType ?: "?"]];
    }

    if (diagnosis) { *diagnosis = [tried componentsJoinedByString:@", "] ?: @"no path available"; }
    return nil;
}




@end
