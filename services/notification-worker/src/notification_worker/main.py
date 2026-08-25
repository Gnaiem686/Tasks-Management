from __future__ import annotations

import asyncio
import signal


async def run_until_terminated() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signal_name, stop.set)
    await stop.wait()


def main() -> None:
    asyncio.run(run_until_terminated())


if __name__ == "__main__":
    main()
