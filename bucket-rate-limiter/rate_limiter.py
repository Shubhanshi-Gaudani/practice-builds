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
    
    def is_full(self):
        self._refill()
        return self.capacity == self.tokens

class PerUserRateLimiter:
    def __init__(self, capacity, rate, clock=time.monotonic):
        if capacity <= 0 or rate <= 0:
            raise ValueError
        self.capacity = capacity
        self.rate = rate
        self.buckets = {}
        self.clock = clock
    
    def allow(self, user_id, cost=1):
        if user_id not in self.buckets:
            self.buckets[user_id] = TokenBucket(self.capacity, self.rate, clock=self.clock)
        return self.buckets[user_id].allow(cost)

    def cleanup(self):
        for user_id,bucket in list(self.buckets.items()):
            if bucket.is_full():
                del self.buckets[user_id]



