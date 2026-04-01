"""Streamlit 환경에서 asyncio.run() 대신 사용하는 헬퍼."""
from __future__ import annotations

import asyncio
from typing import Any, Coroutine, TypeVar

import nest_asyncio

nest_asyncio.apply()

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """새 이벤트 루프를 생성해 코루틴을 실행한다.

    Streamlit은 자체 이벤트 루프를 유지하므로 asyncio.run()을 직접 쓰면
    'Event loop is closed' 오류가 발생한다. nest_asyncio.apply() 후
    새 루프를 만들어 실행하면 중첩 실행이 허용된다.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
