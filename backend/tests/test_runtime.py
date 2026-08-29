import asyncio
import sys

import pytest


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific event loop policy")
def test_windows_uses_selector_event_loop_policy() -> None:
    assert isinstance(
        asyncio.get_event_loop_policy(),
        asyncio.WindowsSelectorEventLoopPolicy,
    )
