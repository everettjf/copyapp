"""Bounded subprocess entry point for stopping one owned iCTRL runner."""

import asyncio
import sys

from copyapp.ictrl_setup import _stop_runner


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m copyapp.ictrl_runner_stop UDID BUNDLE")
    asyncio.run(_stop_runner(sys.argv[1], sys.argv[2]))
