import time

class TokenBucket:
    def __init__(self, capacity, rate, clock=time.monotonic) -> None:
        if capacity <= 0 or rate <= 0:
            raise ValueError
        self.tokens = capacity
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
        self.last = clock()
    
    def allow(self,cost=1):
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        else:
            return False

    def _refill(self):
        now = self.clock()
        elapsed = now - self.last
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last = now


