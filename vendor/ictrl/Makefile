.PHONY: build ipa clean help

PROJECT       = iCTRL.xcodeproj
SCHEME        = iCTRL
DERIVED_DATA  = build
BUILD_DIR     = $(DERIVED_DATA)/Build/Products/Debug-iphoneos

MAIN_APP      = iCTRL.app
MAIN_IPA      = iCTRL.ipa

RUNNER_APP    = iCTRLUITests-Runner.app
RUNNER_BIN    = iCTRLUITests-Runner
XCTEST_BUNDLE = iCTRLUITests.xctest
RUNNER_IPA    = iCTRLUITests-Runner.ipa

# Signing identity is read from the freshly-built app (below, in `ipa`) so the
# re-sign uses EXACTLY what xcodebuild chose from the Xcode project's automatic
# signing — never a guessed keychain identity. Do NOT hardcode it here.

# ──────────────────────────────────────────────
# Build both targets with Xcode signing
# ──────────────────────────────────────────────
# A fresh clone has neither: the project is generated (gitignored) and the
# signing config is per developer. Both are produced on demand, so
# `git clone` → `make ipa` works with nothing else set up.
Config/Local.xcconfig:
	@./Scripts/setup-signing.sh

$(PROJECT)/project.pbxproj: project.yml Config/Signing.xcconfig Config/Local.xcconfig
	@command -v xcodegen >/dev/null || { echo "❌ xcodegen not found — brew install xcodegen"; exit 1; }
	xcodegen generate --quiet

build: Frameworks/IDevice.xcframework $(PROJECT)/project.pbxproj
build:
	@# Stamp BEFORE xcodebuild, not inside it. As an Xcode pre-build phase the
	@# generated file is written after the Swift compile has already read it, so
	@# the binary ships the PREVIOUS stamp — exactly the "is my change deployed?"
	@# ambiguity this is meant to remove.
	@./Scripts/stamp-build.sh
	xcodebuild build-for-testing \
		-project $(PROJECT) \
		-derivedDataPath $(DERIVED_DATA) \
		-scheme $(SCHEME) \
		-destination "generic/platform=iOS" \
		-allowProvisioningUpdates \
		ARCHS=arm64
	@echo ""
	@echo "✅ Build completed"
	@echo "   $(BUILD_DIR)/$(MAIN_APP)"
	@echo "   $(BUILD_DIR)/$(RUNNER_APP)"

# ──────────────────────────────────────────────
# Package both IPAs
#
#   iCTRL.ipa                — Main app (settings & control UI)
#   iCTRLUITests-Runner.ipa  — XCTest runner (automation engine)
# ──────────────────────────────────────────────
ipa: build
	@echo ""
	@# === Runner IPA ===
	@echo "🎨 Adding the app icon to Runner..."
	@# The XCTRunner template declares no icon (no CFBundleIcons, no
	@# Assets.car), so iOS shows a placeholder. Ship plain PNGs and point at
	@# them with CFBundleIconFiles only: a CFBundleIconName would send iOS to
	@# an Assets.car the Runner doesn't have, and it would fall back to the
	@# placeholder (notifications included). Icons: Scripts/make-runner-icons.py.
	@set -e; \
	APP="$(BUILD_DIR)/$(RUNNER_APP)"; PLIST="$$APP/Info.plist"; PB=/usr/libexec/PlistBuddy; \
	rm -f "$$APP"/AppIcon*.png; \
	cp Config/RunnerIcon/*.png "$$APP/"; \
	$$PB -c "Delete :CFBundleIcons" "$$PLIST" 2>/dev/null || true; \
	$$PB -c "Delete :CFBundleIcons~ipad" "$$PLIST" 2>/dev/null || true; \
	$$PB -c "Add :CFBundleIcons:CFBundlePrimaryIcon:CFBundleIconFiles array" "$$PLIST"; \
	i=0; for n in AppIcon20x20 AppIcon29x29 AppIcon40x40 AppIcon60x60; do \
		$$PB -c "Add :CFBundleIcons:CFBundlePrimaryIcon:CFBundleIconFiles:$$i string $$n" "$$PLIST"; i=$$((i+1)); \
	done; \
	$$PB -c "Add :CFBundleIcons~ipad:CFBundlePrimaryIcon:CFBundleIconFiles array" "$$PLIST"; \
	i=0; for n in AppIcon20x20 AppIcon29x29 AppIcon40x40 AppIcon76x76 AppIcon83.5x83.5; do \
		$$PB -c "Add :CFBundleIcons~ipad:CFBundlePrimaryIcon:CFBundleIconFiles:$$i string $$n" "$$PLIST"; i=$$((i+1)); \
	done
	@echo "🔧 Stripping XCTest frameworks from Runner..."
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/XCTAutomationSupport.framework"
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/XCTest.framework"
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/XCTestCore.framework"
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/XCTestSupport.framework"
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/XCUIAutomation.framework"
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/XCUnit.framework"
	rm -rf "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/Testing.framework"
	rm -f  "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks/libXCTestSwiftSupport.dylib"
	@rmdir "$(BUILD_DIR)/$(RUNNER_APP)/Frameworks" 2>/dev/null || true
	@# ── Back-compat shim for older iOS (see iCTRLCompat/XCTCompatShim.m) ──
	@# Xcode's prebuilt XCTRunner stub hard-binds classes that don't exist in the
	@# XCTest shipped by older Developer disk images, so the runner dies at launch
	@# with "Symbol not found: _OBJC_CLASS_$$_XCTCommandLineToolHelper" on e.g.
	@# iOS 16. We ship a dylib defining the missing class and re-point just that
	@# one bind record at it — the symbol is only touched on the --run-as-tool
	@# path, which testmanagerd-launched runs never take.
	@echo "🩹 Building + inserting the older-iOS compat shim..."
	@# Both steps below are one-shot: insert-dylib.py would refuse a second load command,
	@# and the bind record is already re-pointed, so retarget-bind-ordinal.py
	@# finds nothing to change and fails the build. That happens whenever `make
	@# ipa` runs twice without the runner being rebuilt in between, which reads
	@# as a broken build rather than as work already done. The patching runs on
	@# a copy that only replaces the binary once every step has succeeded — a
	@# half-patched runner (shim loaded, symbol not retargeted) would otherwise
	@# be mistaken for a finished one by the check below and shipped.
	@set -e; \
	APP="$(BUILD_DIR)/$(RUNNER_APP)"; \
	if otool -L "$$APP/$(RUNNER_BIN)" | grep -q libXCTCompatShim; then \
		echo "   ✅ shim already present — skipping"; \
		exit 0; \
	fi; \
	SDK="$$(xcrun --sdk iphoneos --show-sdk-path)"; \
	mkdir -p "$$APP/Frameworks"; \
	xcrun -sdk iphoneos clang -dynamiclib -arch arm64 -isysroot "$$SDK" \
		-mios-version-min=16.0 -install_name "@rpath/libXCTCompatShim.dylib" \
		-framework Foundation -o "$$APP/Frameworks/libXCTCompatShim.dylib" \
		iCTRLCompat/XCTCompatShim.m; \
	BIN="$$APP/$(RUNNER_BIN)"; TMP="$$BIN.patching"; \
	cp "$$BIN" "$$TMP"; \
	trap 'rm -f "$$TMP"' EXIT; \
	python3 Scripts/insert-dylib.py "$$TMP" "@rpath/libXCTCompatShim.dylib"; \
	ORD="$$(python3 Scripts/dylib-ordinal.py "$$TMP" libXCTCompatShim)"; \
	python3 Scripts/retarget-bind-ordinal.py "$$TMP" \
		'_OBJC_CLASS_$$_XCTCommandLineToolHelper' "$$ORD"; \
	python3 Scripts/retarget-undef-symbol.py "$$TMP" \
		'_OBJC_CLASS_$$_XCTCommandLineToolHelper' libXCTCompatShim; \
	mv "$$TMP" "$$BIN"
	@echo "🧹 Removing dSYM debug symbols from the app..."
	@# build-for-testing embeds a .dSYM inside the app; it is debug-symbol data,
	@# not needed at runtime, and bloats the IPA (~3MB). Strip it before packaging.
	@find "$(BUILD_DIR)/$(RUNNER_APP)" -name "*.dSYM" -exec rm -rf {} + 2>/dev/null || true
	@echo "🔗 Registering ictrl:// URL scheme..."
	@PLIST="$(BUILD_DIR)/$(RUNNER_APP)/Info.plist"; \
	/usr/libexec/PlistBuddy -c "Delete :CFBundleURLTypes" "$$PLIST" 2>/dev/null || true; \
	/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes array" "$$PLIST"; \
	/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0 dict" "$$PLIST"; \
	/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLName string com.copyapp.ictrl" "$$PLIST"; \
	/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes array" "$$PLIST"; \
	/usr/libexec/PlistBuddy -c "Add :CFBundleURLTypes:0:CFBundleURLSchemes:0 string ictrl" "$$PLIST"
	@echo "📡 Declaring the nearby Bonjour service type..."
	@# Advertising _ictrl._tcp (nearby discovery) fails with NoAuth unless the
	@# app declares the type. Only the nearby listener depends on it.
	@PLIST="$(BUILD_DIR)/$(RUNNER_APP)/Info.plist"; \
	/usr/libexec/PlistBuddy -c "Delete :NSBonjourServices" "$$PLIST" 2>/dev/null || true; \
	/usr/libexec/PlistBuddy -c "Add :NSBonjourServices array" "$$PLIST"; \
	/usr/libexec/PlistBuddy -c "Add :NSBonjourServices:0 string _ictrl._tcp" "$$PLIST"
	@echo "🏷  Aligning .xctest bundle id with the Runner..."
	@# Rewrite the embedded .xctest CFBundleIdentifier to match the Runner app id,
	@# so the plugin and its host share one identifier. Done BEFORE the re-sign so
	@# the new plist is covered by the signature. Runner id is read at runtime
	@# (not hardcoded).
	@set -e; \
	RUNNER_PLIST="$(BUILD_DIR)/$(RUNNER_APP)/Info.plist"; \
	XCTEST_PLIST="$(BUILD_DIR)/$(RUNNER_APP)/PlugIns/$(XCTEST_BUNDLE)/Info.plist"; \
	RUNNER_ID="$$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$$RUNNER_PLIST")"; \
	OLD_ID="$$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$$XCTEST_PLIST")"; \
	/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $$RUNNER_ID" "$$XCTEST_PLIST"; \
	echo "   .xctest: $$OLD_ID -> $$RUNNER_ID"
	@# Copy APP iOS 16 compatibility: Xcode 27's prebuilt outer XCTRunner
	@# advertises iOS 17 even though the project and nested test target use 16.
	@# Do this before upstream's normal inside-out signing block below.
	@if [ "$(COPYAPP_IOS_TARGET)" = "16.0" ]; then \
		APP="$(BUILD_DIR)/$(RUNNER_APP)"; BIN="$$APP/$(RUNNER_BIN)"; \
		MIN="$$(xcrun vtool -show-build "$$BIN" | sed -n 's/^[[:space:]]*minos[[:space:]]*//p' | head -1)"; \
		SDK="$$(xcrun vtool -show-build "$$BIN" | sed -n 's/^[[:space:]]*sdk[[:space:]]*//p' | head -1)"; \
		if [ -z "$$MIN" ] || [ -z "$$SDK" ]; then echo "Cannot read runner LC_BUILD_VERSION" >&2; exit 1; fi; \
		if [ "$$MIN" != "16.0" ]; then \
			xcrun vtool -set-build-version ios 16.0 "$$SDK" -replace -output "$$BIN.copyapp" "$$BIN" || exit 1; \
			mv "$$BIN.copyapp" "$$BIN" || exit 1; \
		fi; \
		/usr/libexec/PlistBuddy -c 'Set :MinimumOSVersion 16.0' "$$APP/Info.plist" || exit 1; \
		echo "Copy APP iOS 16 runner minimum: $$MIN -> 16.0 (SDK $$SDK)"; \
	fi
	@echo "🔏 Re-signing Runner (identity read back from what xcodebuild signed)..."
	@# Read the signing identity xcodebuild actually used, straight off the built
	@# app — this reflects the Xcode project's automatic signing (team + cert),
	@# so the re-sign can never drift from the build. Match by the cert's SHA-1 in
	@# the keychain to pin the exact identity.
	@set -e; \
	APP="$(BUILD_DIR)/$(RUNNER_APP)"; \
	AUTH="$$(codesign -dvv "$$APP" 2>&1 | sed -n 's/^Authority=//p' | head -1)"; \
	if [ -z "$$AUTH" ]; then echo "🔴 could not read signing identity from $$APP"; exit 1; fi; \
	SHA="$$(security find-identity -v -p codesigning 2>/dev/null | grep -F "$$AUTH" | head -1 | awk '{print $$2}')"; \
	IDENT="$${SHA:-$$AUTH}"; \
	echo "   using: $$AUTH ($$IDENT)"; \
	for dylib in "$$APP/Frameworks/"*.dylib; do \
		[ -f "$$dylib" ] || continue; \
		echo "   signing $$(basename "$$dylib")"; \
		codesign --force --sign "$$IDENT" "$$dylib"; \
	done; \
	codesign --force --sign "$$IDENT" "$$APP/PlugIns/$(XCTEST_BUNDLE)"; \
	codesign --force --sign "$$IDENT" --preserve-metadata=entitlements "$$APP"
	@# Everything dyld loads must carry a signature — an unsigned dylib in
	@# Frameworks/ makes the runner die at launch with "mapped file has no
	@# cdhash", which looks nothing like a signing problem from the device side.
	@echo "🔍 Verifying every embedded binary is signed..."
	@set -e; \
	APP="$(BUILD_DIR)/$(RUNNER_APP)"; \
	for f in "$$APP/Frameworks/"*.dylib "$$APP/PlugIns/$(XCTEST_BUNDLE)" "$$APP"; do \
		[ -e "$$f" ] || continue; \
		codesign -v "$$f" 2>/dev/null || { echo "🔴 unsigned: $$f"; exit 1; }; \
	done; \
	echo "   ✅ all embedded binaries signed"
	@echo "📦 Packaging $(RUNNER_IPA)..."
	rm -rf "$(BUILD_DIR)/Payload"
	mkdir -p "$(BUILD_DIR)/Payload"
	cp -R "$(BUILD_DIR)/$(RUNNER_APP)" "$(BUILD_DIR)/Payload/"
	cd "$(BUILD_DIR)" && zip -qr "$(RUNNER_IPA)" Payload/
	mv "$(BUILD_DIR)/$(RUNNER_IPA)" ./
	rm -rf "$(BUILD_DIR)/Payload"
	@echo "✅ $(RUNNER_IPA)"
	@echo ""
	@# === Main App IPA ===
	@echo "📦 Packaging $(MAIN_IPA)..."
	rm -rf "$(BUILD_DIR)/Payload"
	mkdir -p "$(BUILD_DIR)/Payload"
	cp -R "$(BUILD_DIR)/$(MAIN_APP)" "$(BUILD_DIR)/Payload/"
	cd "$(BUILD_DIR)" && zip -qr "$(MAIN_IPA)" Payload/
	mv "$(BUILD_DIR)/$(MAIN_IPA)" ./
	rm -rf "$(BUILD_DIR)/Payload"
	@echo "✅ $(MAIN_IPA)"
	@ls -lh $(MAIN_IPA)
	@ls -lh $(RUNNER_IPA)
	@echo ""
	@echo "════════════════════════════════════════"
	@echo "  $(MAIN_IPA)  — Settings & control UI"
	@echo "  $(RUNNER_IPA)  — XCTest automation engine"
	@echo "════════════════════════════════════════"

# ──────────────────────────────────────────────
clean:
	rm -rf $(DERIVED_DATA)
	rm -f $(MAIN_IPA) $(RUNNER_IPA)
	@echo "✅ Cleaned"

help:
	@echo "iCTRL Build System"
	@echo ""
	@echo "  make build   Build both apps with Xcode signing"
	@echo "  make ipa     Build + package both IPAs"
	@echo "  make clean   Remove build artifacts"

# The idevice xcframework is a 215MB release asset, not vendored (see
# Scripts/fetch-idevice.sh). Fetch it on demand so a fresh clone builds.
# Phony so the script runs every build: it is a no-op when the pinned version
# is already there, and replaces an older copy after a version bump.
.PHONY: Frameworks/IDevice.xcframework
Frameworks/IDevice.xcframework:
	@bash Scripts/fetch-idevice.sh
