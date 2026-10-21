
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

def test_allows_uptp_capacity_then_rejects(clock):
    tb = TokenBucket(capacity=3, rate=1, clock=clock)
    for i in range(3):
        assert tb.allow() == True
    assert tb.allow() == False


def test_fake_clock_advances():
    fc = FakeClock()
    assert fc() == 0
    fc.advance(2.5)
    assert fc() == 2.5

