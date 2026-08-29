import asyncio
import sys


def configure_asyncio_runtime() -> None:
    """Select an event loop supported by Psycopg's async driver on Windows."""
    if sys.platform != "win32":
        return

    selector_policy = asyncio.WindowsSelectorEventLoopPolicy()
    current_policy = asyncio.get_event_loop_policy()

    if not isinstance(current_policy, type(selector_policy)):
        asyncio.set_event_loop_policy(selector_policy)
