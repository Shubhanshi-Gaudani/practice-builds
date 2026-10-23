
from rate_limiter import TokenBucket, PerUserRateLimiter, SlidingWindowLimiter
import pytest

class FakeClock:
    def __init__(self):
        self.now = 0.0
    
    def __call__(self):
        return self.now
    
    def advance(self, seconds):
        self.now += seconds

@pytest.fixture
def clock():
    return FakeClock()

def test_allows_upto_capacity_then_rejects(clock):
    tb = TokenBucket(capacity=3, rate=1, clock=clock)
    for i in range(3):
        assert tb.allow() == True
    assert tb.allow() == False

def test_fake_clock_advances():
    fc = FakeClock()
    assert fc() == 0
    fc.advance(2.5)
    assert fc() == 2.5

def test_bucket_refills_over_time(clock):
    tb = TokenBucket(capacity=3, rate=1, clock=clock)
    for i in range(3):
        assert tb.allow()
    assert tb.allow() == False
    clock.advance(1)
    assert tb.allow() == True
    assert tb.allow() == False

def test_refill_does_not_exceed_capacity(clock):
    tb = TokenBucket(capacity=3, rate=1, clock=clock)
    clock.advance(1000)
    for i in range(3):
        assert tb.allow()
    assert tb.allow() == False

def test_partial_refill(clock):
    tb = TokenBucket(capacity=1, rate=2, clock=clock)
    tb.allow()
    clock.advance(0.25)
    assert tb.allow() == False
    clock.advance(0.25)
    assert tb.allow() == True

def test_cost_spends_multiple_tokens(clock):
    tb = TokenBucket(capacity=5, rate=1, clock=clock)
    assert tb.allow(cost=3) == True
    assert tb.allow(cost=3) == False
    assert tb.allow(cost=2) == True

def test_rejected_request_does_not_consume(clock):
    tb = TokenBucket(capacity=3, rate=1, clock=clock)
    assert tb.allow(cost=5) == False
    assert tb.allow() == True
    assert tb.allow() == True
    assert tb.allow() == True

def test_rejects_invalid_config():
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, rate=1)
    with pytest.raises(ValueError):
        TokenBucket(capacity=1, rate=0)

def test_users_are_independent(clock):
    rl = PerUserRateLimiter(capacity=2, rate=1, clock=clock)
    assert rl.allow("alice") == True
    assert rl.allow("alice") == True
    assert rl.allow("alice") == False
    assert rl.allow("bob") == True

def test_users_refill_independently(clock):
    rl = PerUserRateLimiter(capacity=1, rate=1, clock=clock)
    assert rl.allow("alice") == True
    clock.advance(0.5)
    assert rl.allow("bob") == True
    clock.advance(0.5)
    assert rl.allow("alice") == True
    assert rl.allow("bob") == False

def test_is_full(clock):
    tb = TokenBucket(capacity=1, rate=1, clock=clock)
    assert tb.is_full() == True
    tb.allow()
    assert tb.is_full() == False
    clock.advance(1)
    assert tb.is_full() == True

def test_cleanup_removes_full_buckets(clock):
    limiter = PerUserRateLimiter(capacity=2, rate=1, clock=clock)
    limiter.allow("alice")
    clock.advance(2)
    limiter.cleanup()
    assert "alice" not in limiter.buckets

def test_cleanup_keeps_partially_drained_buckets(clock):
    limiter = PerUserRateLimiter(capacity=2, rate=1, clock=clock)
    limiter.allow("alice")
    clock.advance(0.5)
    limiter.cleanup()
    assert "alice" in limiter.buckets

def test_behaviour_unchanged_after_cleanup(clock):
    limiter = PerUserRateLimiter(capacity=2, rate=1, clock=clock)
    limiter.allow("alice")
    limiter.allow("alice")
    clock.advance(10)
    limiter.cleanup()
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False

def test_sliding_allows_up_to_limit_then_rejects(clock):
    limiter = SlidingWindowLimiter(limit=2, window=1, clock=clock)
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False

def test_sliding_still_rejects_inside_window(clock):
    limiter = SlidingWindowLimiter(limit=2, window=1, clock=clock)
    limiter.allow("alice")
    limiter.allow("alice")
    clock.advance(0.5)
    assert limiter.allow("alice") is False

def test_sliding_allows_after_window_passes(clock):
    limiter = SlidingWindowLimiter(limit=2, window=1, clock=clock)
    limiter.allow("alice")
    limiter.allow("alice")
    clock.advance(1)
    assert limiter.allow("alice") is True

def test_sliding_window_rolls(clock):
    limiter = SlidingWindowLimiter(limit=2, window=1, clock=clock)
    assert limiter.allow("alice") is True    # t=0
    clock.advance(0.5)
    assert limiter.allow("alice") is True    # t=0.5
    assert limiter.allow("alice") is False
    clock.advance(0.5)                       # t=1.0: the t=0 request expires
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False   # t=0.5 and t=1.0 still count

def test_sliding_users_are_independent(clock):
    limiter = SlidingWindowLimiter(limit=1, window=1, clock=clock)
    assert limiter.allow("alice") is True
    assert limiter.allow("alice") is False
    assert limiter.allow("bob") is True