# Implement a class called LRUCache.
# __init__(capacity)	Initialize a cache with a positive capacity
# get(key)	Return the value, or -1 if missing; mark hits as recently used
# put(key, value)	Insert or update; evict the least recently used entry when full

# get: O(1) average time
# put: O(1) average time
# Space: O(capacity)

class Node:
    def __init__(self, key=None, value=None):
        # Store the current key value:
        self.key = key
        self.value = value
        # Initialize the prev and next pointers
        self.prev = None
        self.next = None

class LRUCache:
    def __init__(self, capacity:int):
        # Validate capacity
        if capacity <= 0:
            raise ValueError("Capacity must be positive")
        self.capacity = capacity
        # Create a dictionary mapping key -> Node
        self.cache = {}
        # Create sentinel head and tail nodes.
        self.head = Node()
        self.tail = Node()
        # Connect the sentinels.
        self.head.next = self.tail
        self.tail.prev = self.head

    def remove(self, node: Node) -> None:
        prev_node = node.prev 
        next_node = node.next 

        prev_node.next = next_node
        next_node.prev = prev_node
    
    def add_to_tail(self, node: Node) -> None: 
        node.next = self.tail
        node.prev = self.tail.prev

        self.tail.prev.next = node
        self.tail.prev = node
    
    def get(self, key: int) -> int:
        # Check if key in cache
        if key in self.cache:
            self.remove(self.cache[key])
            self.add_to_tail(self.cache[key])
            return self.cache[key].value
        else:
            return -1
    
    def put(self, key: int, val: int) -> None:
        # Check if key exists: 
        if key in self.cache:
            # If exists, update value
            self.cache[key].value = val
            # Remove and add to tail to update recent usage
            self.remove(self.cache[key])
            self.add_to_tail(self.cache[key])
        # If doesn't exist:
        else:
            # Check capacity
            if len(self.cache.keys()) == self.capacity:
                # If at capacity, evict LR key to make space
                key_to_evict = self.head.next.key
                self.cache.pop(key_to_evict)
                self.remove(self.head.next)
            node = Node(key, val)
            self.add_to_tail(node)
            self.cache[key] = node