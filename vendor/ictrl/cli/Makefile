# Static aarch64 musl binary for the Minis sandbox (Alpine 3.21 arm64).
#
# Built and tested inside the same container image the target runs, so "it
# compiles" and "it runs there" are the same check.

IMAGE   := ictrl-cli-build
SRC     := main.c sha256.c x25519.c util.c
CFLAGS  := -O2 -std=c11 -Wall -Wextra -static -fno-strict-aliasing
OUT     := ictrl

.PHONY: all build test clean shell

all: build

## Cross-compile in Alpine arm64, emitting ./ictrl on the host.
build:
	docker build --platform linux/arm64 -t $(IMAGE) .
	docker run --rm --platform linux/arm64 -v "$(PWD):/out" $(IMAGE) \
		sh -c 'cp /build/$(OUT) /out/$(OUT)'
	@file $(OUT) 2>/dev/null || true
	@ls -lh $(OUT)

## Run the self-test in the target environment.
test: build
	docker run --rm --platform linux/arm64 -v "$(PWD):/w" -w /w $(IMAGE) \
		sh -c './ictrl 2>&1 | head -3; echo "--- selftest ---"; ./selftest'

## Interactive shell in the build image, for poking at things.
shell:
	docker run --rm -it --platform linux/arm64 -v "$(PWD):/w" -w /w $(IMAGE) sh

clean:
	rm -f $(OUT) selftest
	docker rmi $(IMAGE) 2>/dev/null || true
