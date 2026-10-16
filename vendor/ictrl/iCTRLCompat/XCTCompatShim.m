//
//  XCTCompatShim.m — back-compat symbol shims for older iOS XCTest runtimes.
//
//  Why this exists
//  ---------------
//  The runner's main binary is Xcode's prebuilt XCTRunner stub. Built with a
//  current Xcode, it links against a current XCTest and hard-references classes
//  that DON'T EXIST in the XCTest shipped by older iOS Developer disk images —
//  notably `XCTCommandLineToolHelper` (added after iOS 16). On such a device
//  dyld can't bind the class symbol and aborts before any of our code runs:
//
//      Symbol not found: _OBJC_CLASS_$_XCTCommandLineToolHelper
//      Expected in: /Developer/Library/Frameworks/XCTest.framework/XCTest
//
//  This dylib defines a stand-in for that class so the bind succeeds. It is
//  loaded BEFORE XCTest (its LC_LOAD_DYLIB is inserted ahead of XCTest's), so
//  on a NEW iOS — where the real class exists — dyld resolves the symbol from
//  whichever image comes first and the two definitions never conflict in a way
//  that matters: the methods below are only ever reached on the command-line
//  (`--run-as-tool`) launch path, which we never use. Our runner is started by
//  testmanagerd and takes its configuration from the environment
//  (`environmentSpecifiesTestConfiguration`), not from argv.
//
//  In other words: this is a load-time symbol filler, not a reimplementation.
//  If either method below ever actually runs, something has gone wrong — so
//  they log loudly rather than fail silently.
//

#import <Foundation/Foundation.h>

@interface XCTCommandLineToolHelper : NSObject
@end

@implementation XCTCommandLineToolHelper

/// Real XCTest parses argv into an XCTestConfiguration here. We never launch
/// via `--run-as-tool`, so returning nil is the correct "no command-line
/// configuration" answer; the caller falls back to the environment.
+ (id)configurationFromCommandLineArguments:(id)arguments
                               userDefaults:(id)userDefaults
                      requiresTestBundleURL:(BOOL)requiresTestBundleURL
                                   outError:(NSError **)outError {
    NSLog(@"[iCTRL] XCTCommandLineToolHelper shim: configurationFromCommandLineArguments "
          @"called — unexpected on the testmanagerd launch path; returning nil.");
    if (outError) { *outError = nil; }
    return nil;
}

+ (void)exitWithMessage:(id)message usage:(id)usage {
    NSLog(@"[iCTRL] XCTCommandLineToolHelper shim: exitWithMessage: %@ (usage: %@)", message, usage);
}

@end
