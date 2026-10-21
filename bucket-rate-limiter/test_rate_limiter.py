
from rate_limiter import TokenBucket
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
