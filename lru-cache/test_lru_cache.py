import unittest
from lru_cache import LRUCache

class Test_LRU_Cache(unittest.TestCase):
    def test_get_missing_key(self):
        cache = LRUCache(2)
        self.assertEqual(cache.get(99), -1)
    
    def test_put_and_get(self):
        cache = LRUCache(2)
        cache.put(2,1)
        self.assertEqual(cache.get(2), 1)
    
    def test_evict_leastly_recently_used_key(self):
        cache = LRUCache(2)
        cache.put(1, 10)
        cache.put(2, 20)
        
        # Retrieve key 1
        cache.get(1)
        cache.put(3, 30)
        self.assertEqual(cache.get(2), -1)
        self.assertEqual(cache.get(1), 10)
        self.assertEqual(cache.get(3), 30)
    
    def test_update_existing_key(self):
        cache = LRUCache(2)
        cache.put(1,10)
        cache.put(1,20)
        self.assertEqual(cache.get(1), 20)
    
    def test_capacity_limit(self):
        cache = LRUCache(1)
        cache.put(1,10)
        cache.put(2,20)
        self.assertEqual(cache.get(1), -1)
        self.assertEqual(cache.get(2), 20)

if __name__ == "__main__":
    unittest.main()