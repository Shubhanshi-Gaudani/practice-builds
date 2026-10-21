import time

class TokenBucket:
    def __init__(self, capacity, rate, clock=time.monotonic) -> None:
        self.tokens = capacity
        self.capacity = capacity
        self.rate = rate
        self.clock = clock
    
    def allow(self,cost=1):
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        else:
            return False
