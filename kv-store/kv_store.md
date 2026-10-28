# Transactional Key-Value Store: Notes

## What a transaction is

A transaction groups changes so they take effect **all together or not at all**.

- `begin()` opens a transaction. Changes after this point are tentative.
- `commit()` makes the tentative changes permanent.
- `rollback()` discards them, restoring the state from before `begin()`.

While a transaction is open, reads must **see its own tentative changes**. If you set `a = 20` inside a transaction, `get("a")` returns 20, even though the permanent value is still 10.

Analogy: editing a document without saving. You see your edits as you type, but closing without saving puts everything back.

## Core idea: a change buffer

Keep the permanent data and the tentative changes in **separate places**:

- `store`: the permanent data.
- a **buffer** dict: only the keys changed in the current transaction.

Then each operation is simple:

| Operation | Behavior |
|---|---|
| `set` / `delete` | write to the buffer if a transaction is open, otherwise to the store |
| `get` | check the buffer first; if the key isn't there, fall back to the store |
| `commit` | apply each buffered change to the store, then drop the buffer |
| `rollback` | drop the buffer; the store was never touched |

The store is never modified during a transaction, so rollback costs nothing.

## Tombstones: representing deletes

A delete inside a transaction **can't just remove the key from the buffer**. The key still exists in the store, so `get` would fall through and find it.

Instead, write a **tombstone**: a special marker meaning "this key is deleted in this transaction."

```python
_DELETED = object()   # unique sentinel; can't collide with any real value
```

- `get`: if the buffer holds the tombstone, return `None` without checking the store.
- `commit`: a tombstone becomes a real delete, `store.pop(key, None)`.
- Compare with `is _DELETED`. A unique `object()` is safer than `None`, because `None` (or any ordinary value) could be something a user actually stores.

## Nested transactions: a stack of buffers

To allow `begin()` inside an open transaction, replace the single buffer with a **stack** (a list of dicts), one per open transaction.

```
store:      {a: 1, b: 2}
stack[0]:   {a: 2}            ← outer transaction
stack[1]:   {a: 3, b: DEL}    ← inner transaction (top)
get("a") → 3, get("b") → None
```

| Operation | Behavior |
|---|---|
| `begin` | push an empty dict |
| `set` / `delete` | write to the top dict |
| `get` | search from top to bottom; first hit wins (tombstone → `None`); then the store |
| `rollback` | pop the top dict and discard it |
| `commit` | pop the top dict and merge it into the next one down; if none remain, apply it to the store |

**When merging an inner commit into its parent, keep tombstones as tombstones.** The parent can still roll back, and until it commits, the deletion must keep hiding the store's value. Only the outermost commit turns tombstones into real deletes.

An empty stack means no transaction is open, which is clearer than a flag or `None` check.

## Reference implementation

```python
_DELETED = object()


class NoTransactionError(Exception):
    pass


class KVStore:
    def __init__(self):
        self.store = {}
        self.transactions = []

    def get(self, key):
        for txn in reversed(self.transactions):
            if key in txn:
                val = txn[key]
                return None if val is _DELETED else val
        return self.store.get(key)

    def set(self, key, val):
        if self.transactions:
            self.transactions[-1][key] = val
        else:
            self.store[key] = val

    def delete(self, key):
        if self.transactions:
            self.transactions[-1][key] = _DELETED
        else:
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
            self.transactions[-1].update(top)   # tombstones stay tombstones
            return
        for key, val in top.items():
            if val is _DELETED:
                self.store.pop(key, None)
            else:
                self.store[key] = val
```

## Cost

| Operation | Time |
|---|---|
| `set`, `delete`, `begin`, `rollback` | O(1) |
| `get` | O(depth of nesting) |
| `commit` | O(keys changed in that transaction) |

Memory grows with the number of keys changed, not the size of the store.

## Alternative designs

- **Copy on begin:** clone the whole store at `begin()`, work on the copy, then swap it in on commit or discard it on rollback. Very simple, but O(n) time and memory per `begin`, even if only one key changes.
- **Undo log:** write changes straight to the store, but record each key's old value (or "didn't exist") in a log. Rollback replays the log backwards. Reads are O(1), since there's no buffer to search, but rollback does work proportional to the changes.
- **Commit closes everything:** some designs make `commit()` apply *all* open transactions at once instead of just the innermost. Collapse the whole stack into the store.

The buffer approach makes rollback cheap; the undo log makes reads cheap. Which is better depends on whether rollbacks or reads are more common.

## Pitfalls

- **An empty dict is falsy.** `if self.transaction:` is `False` right after `begin()`, so the first write leaks into the store. Check `is not None`, or use a list and check its length.
- **Don't use truthiness to detect deletes.** `if val:` treats `0`, `""`, and `False` as deleted. Compare against the tombstone with `is`.
- **Reads must fall through.** A key untouched in the transaction still needs to be found in the store; don't stop at the buffer check.
- **Deleting a missing key on commit.** Use `pop(key, None)` rather than `del`, since the key may never have existed in the store.

## Where this shows up in practice

- **Databases** use the same ideas. Uncommitted writes are kept apart from committed data, and nested transactions appear as *savepoints* (`SAVEPOINT` / `ROLLBACK TO SAVEPOINT` in SQL).
- **Log-structured storage** (LSM trees, as in LevelDB/RocksDB/Cassandra) uses tombstones to record deletes in layers that are later merged, just like the buffer stack.
- **Editors and apps** implement undo with an undo log.