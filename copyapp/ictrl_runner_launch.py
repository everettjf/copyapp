"""Bounded subprocess entry point for launching the paired iCTRL runner."""

import asyncio
import sys

from copyapp.usb_tunnel import _launch_ictrl_runner


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python -m copyapp.ictrl_runner_launch UDID")
    asyncio.run(_launch_ictrl_runner(sys.argv[1]))
