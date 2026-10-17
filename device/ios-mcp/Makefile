THEOS_PACKAGE_SCHEME ?= rootless
ifeq ($(THEOS_PACKAGE_SCHEME),roothide)
ARCHS = arm64e
copyapp-mcp_CFLAGS += -DMCP_ROOTHIDE=1
copyapp-mcp_LIBRARIES = roothide
else
ARCHS = arm64 arm64e
copyapp-mcp_CFLAGS += -DMCP_ROOTLESS=1
endif
TARGET = iphone:clang:16.5:15.0

include $(THEOS)/makefiles/common.mk

TWEAK_NAME = copyapp-mcp
copyapp-mcp_FILES = Tweak.x MCPServer.m MCPLogger.m HIDManager.m ScreenManager.m ClipboardManager.m AppManager.m AccessibilityManager.m TextInputManager.m FileSystemManager.m LogManager.m OCRManager.m MCPProcessUtil.m MCPAXQueryContext.m MCPAXRemoteContextResolver.m MCPUIElementSerializer.m MCPUIElementsFacade.m MCPAXAttributeBridge.m MCPAXNodeSource.m VisionOCREngine.m PaddleOCRManager.m MCPOCRRequestContext.m
copyapp-mcp_CFLAGS += -fobjc-arc -Wno-unused-function -Wno-deprecated-declarations -I.
copyapp-mcp_FRAMEWORKS = IOKit UIKit CoreGraphics QuartzCore MobileCoreServices AVFoundation Security Vision

include $(THEOS_MAKE_PATH)/tweak.mk

after-stage::
	$(ECHO_NOTHING)mkdir -p "$(THEOS_STAGING_DIR)/usr/share/doc/copyapp-mcp"$(ECHO_END)
	$(ECHO_NOTHING)cp LICENSE NOTICE "$(THEOS_STAGING_DIR)/usr/share/doc/copyapp-mcp/"$(ECHO_END)
