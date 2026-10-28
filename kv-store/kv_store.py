# Implement an in-memory key-value store in Python, with nested transactions.

_DELETED = object()  # tombstone: marks a key deleted inside a transaction


class NoTransactionError(Exception):
    pass


class KVStore:
    def __init__(self):
        self.store = {}
        self.transactions = []  # stack of change buffers; empty = no transaction

    def get(self, key: str):
        # Innermost transaction wins, then outer ones, then the store.
        for txn in reversed(self.transactions):
            if key in txn:
                val = txn[key]
                return None if val is _DELETED else val
        return self.store.get(key)

    def set(self, key: str, val):
        if self.transactions:
            self.transactions[-1][key] = val
            return
        self.store[key] = val

    def delete(self, key: str):
        if self.transactions:
            self.transactions[-1][key] = _DELETED
            return
        self.store.pop(key, None)

    def begin(self):
        self.transactions.append({})

    def rollback(self):
        if not self.transactions:
            raise NoTransactionError("No transaction in progress")
        self.transactions.pop()

    def commit(self):
        if not self.transactions:
            raise NoTransactionError("No transaction in progress")
        top = self.transactions.pop()
        if self.transactions:
            # Merge into the parent, keeping tombstones as tombstones:
            # the parent may still roll back.
            self.transactions[-1].update(top)
            return
        for key, val in top.items():
            if val is _DELETED:
                self.store.pop(key, None)
            else:
                self.store[key] = val