
from rate_limiter import TokenBucket

class FakeClock:
    def __init__(self):
        self.now = 0.0
    
    def __call__(self):
        return self.now
    
    def advance(self, seconds):
        self.now += seconds

def test_fake_clock_advances():
    fc = FakeClock()
    assert fc() == 0
    fc.advance(2.5)
    assert fc() == 2.5

