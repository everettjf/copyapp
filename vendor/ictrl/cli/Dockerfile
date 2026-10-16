# Alpine 3.21 arm64 — the same distro/arch/libc as the Minis sandbox rootfs, so
# building and testing here exercises the actual target environment.
FROM --platform=linux/arm64 alpine:3.21

RUN apk add --no-cache build-base

WORKDIR /build
COPY ictrl.h main.c sha256.c x25519.c util.c selftest.c ./

# -static so the binary carries no loader dependency: the Minis guest resolves
# ELF interpreters through an emulation layer over a SQLite-backed filesystem,
# and a fully static image sidesteps that path entirely.
RUN cc -O2 -std=c11 -Wall -Wextra -static -o ictrl \
        main.c sha256.c x25519.c util.c && \
    cc -O2 -std=c11 -Wall -Wextra -static -o selftest \
        selftest.c sha256.c x25519.c util.c && \
    strip ictrl selftest
