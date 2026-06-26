from __future__ import annotations

from src.core.rate_limit import RateLimiter


def test_allows_up_to_limit_then_blocks() -> None:
    rl = RateLimiter(max_attempts=3, window_seconds=60.0)
    assert rl.allow("k", now=0.0)
    assert rl.allow("k", now=1.0)
    assert rl.allow("k", now=2.0)
    assert not rl.allow("k", now=3.0)  # 4th within the window → blocked


def test_window_slides() -> None:
    rl = RateLimiter(max_attempts=1, window_seconds=10.0)
    assert rl.allow("k", now=0.0)
    assert not rl.allow("k", now=5.0)
    assert rl.allow("k", now=11.0)  # first hit aged out


def test_reset_clears_history() -> None:
    rl = RateLimiter(max_attempts=1, window_seconds=10.0)
    assert rl.allow("k", now=0.0)
    rl.reset("k")
    assert rl.allow("k", now=1.0)


def test_keys_are_independent() -> None:
    rl = RateLimiter(max_attempts=1, window_seconds=10.0)
    assert rl.allow("a", now=0.0)
    assert rl.allow("b", now=0.0)
