"""Main entry point for backchannel-bot."""

import asyncio


def main() -> None:
    """Main entry point for the backchannel bot."""
    asyncio.run(async_main())


async def async_main() -> None:
    """Async main function."""
    print("Backchannel Bot starting...")


if __name__ == "__main__":
    main()
