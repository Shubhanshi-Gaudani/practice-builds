# Implement an in-memory key-value store in Python. 

class KVStore:
    def __init__(self):
        self.store = {}
        self.transaction = None

    def get(self, key: str):
        if self.transaction != None:
            if key in self.transaction:
                return self.transaction[key]
        if key in self.store:
            return self.store[key]
        return None
        
    def set(self, key: str, val):
        if self.transaction != None:
            self.transaction[key] = val
            return
        self.store[key] = val
    
    def delete(self, key: str):
        if self.transaction != None:
            self.transaction[key] = None
            return
        if key in self.store:
            del self.store[key]
    
    def begin(self):
        if self.transaction != None:
            raise Exception("A transaction is already in progress")
        else:
            self.transaction = {}

    def rollback(self):
        if self.transaction == None:
            raise Exception("Non transaction is in process")
        else:
            self.transaction = None
    
    def commit(self):
        if self.transaction == None:
            raise Exception("Non transaction is in process")
        else:
            for key, val in self.transaction.items():
                if val != None:
                    self.store[key] = val
                elif key in self.store:
                    del self.store[key]
            
            self.transaction = None

        
