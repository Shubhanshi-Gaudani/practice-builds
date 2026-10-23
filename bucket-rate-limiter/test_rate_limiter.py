
from rate_limiter import TokenBucket, PerUserRateLimiter
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