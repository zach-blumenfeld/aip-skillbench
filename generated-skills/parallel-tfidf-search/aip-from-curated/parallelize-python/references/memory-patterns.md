# Memory optimization patterns

Load these when memory is the goal, when worker copies threaten the memory limit, or when `plan.memory_tactics` names a transformation. Comes from the memory-optimization skill and its advanced patterns. The decision tree is encoded in `assets/strategy_rules.json` → `memory_tactics` and repeated here for lookup.

## Memory Optimization Decision Tree

```
What's consuming memory?

Large collections:
├── List of objects → __slots__, namedtuple, or dataclass(slots=True)
├── List built all at once → Generator/iterator pattern
├── Storing strings → String interning, categorical encoding
└── Numeric data → NumPy arrays instead of lists

Data processing:
├── Loading full file → Chunked reading, memory-mapped files
├── Intermediate copies → In-place operations, views
├── Keeping processed data → Process-and-discard pattern
└── DataFrame operations → Downcast dtypes, sparse arrays

Object lifecycle:
├── Objects never freed → Check circular refs, use weakref
├── Cache growing unbounded → LRU cache with maxsize
├── Global accumulation → Explicit cleanup, context managers
└── Large temporary objects → Delete explicitly, gc.collect()
```

## Transformation Patterns

### Pattern 1: Class to __slots__

Reduces per-instance memory by 40-60%:

**Before:**
```python
class Point:
    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
```

**After:**
```python
class Point:
    __slots__ = ('x', 'y', 'z')

    def __init__(self, x, y, z):
        self.x = x
        self.y = y
        self.z = z
```

### Pattern 2: List to Generator

Avoid materializing entire sequences:

**Before:**
```python
def get_all_records(files):
    records = []
    for f in files:
        records.extend(parse_file(f))
    return records

all_data = get_all_records(files)
for record in all_data:
    process(record)
```

**After:**
```python
def get_all_records(files):
    for f in files:
        yield from parse_file(f)

for record in get_all_records(files):
    process(record)
```

### Pattern 3: Downcast Numeric Types

Reduce NumPy/Pandas memory by 2-8x:

**Before:**
```python
df = pd.read_csv('data.csv')  # Default int64, float64
```

**After:**
```python
def optimize_dtypes(df):
    for col in df.select_dtypes(include=['int']):
        df[col] = pd.to_numeric(df[col], downcast='integer')
    for col in df.select_dtypes(include=['float']):
        df[col] = pd.to_numeric(df[col], downcast='float')
    return df

df = optimize_dtypes(pd.read_csv('data.csv'))
```

### Pattern 4: String Deduplication

For repeated strings:

**Before:**
```python
records = [{'status': 'active', 'type': 'user'} for _ in range(1000000)]
```

**After:**
```python
import sys

STATUS_ACTIVE = sys.intern('active')
TYPE_USER = sys.intern('user')

records = [{'status': STATUS_ACTIVE, 'type': TYPE_USER} for _ in range(1000000)]
```

Or with Pandas:
```python
df['status'] = df['status'].astype('category')
```

### Pattern 5: Memory-Mapped File Processing

Process files larger than RAM:

```python
import mmap
import numpy as np

# For binary data
with open('large_file.bin', 'rb') as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    # Process chunks without loading entire file

# For NumPy arrays
arr = np.memmap('large_array.dat', dtype='float32', mode='r', shape=(1000000, 100))
```

### Pattern 6: Chunked DataFrame Processing

```python
def process_large_csv(filepath, chunksize=10000):
    results = []
    for chunk in pd.read_csv(filepath, chunksize=chunksize):
        result = process_chunk(chunk)
        results.append(result)
        del chunk  # Explicit cleanup
    return pd.concat(results)
```

## Data Structure Memory Comparison

| Structure | Memory per item | Use case |
|-----------|----------------|----------|
| `list` of `dict` | ~400+ bytes | Flexible, small datasets |
| `list` of `class` | ~300 bytes | Object-oriented, small |
| `list` of `__slots__` class | ~120 bytes | Many similar objects |
| `namedtuple` | ~80 bytes | Immutable records |
| `numpy.ndarray` | 8 bytes (float64) | Numeric, vectorized ops |
| `pandas.DataFrame` | ~10-50 bytes/cell | Tabular, analysis |

## Memory Leak Detection

Common leak patterns and fixes:

| Pattern | Cause | Fix |
|---------|-------|-----|
| Growing cache | No eviction policy | `@lru_cache(maxsize=1000)` |
| Event listeners | Not unregistered | Weak references or explicit removal |
| Circular references | Objects reference each other | `weakref`, break cycles |
| Global lists | Append without cleanup | Bounded deque, periodic clear |
| Closures | Capture large objects | Capture only needed values |

## Profiling Commands

```python
# Object size
import sys
sys.getsizeof(obj)  # Shallow size only

# Deep size with pympler
from pympler import asizeof
asizeof.asizeof(obj)  # Includes referenced objects

# Memory profiler decorator
from memory_profiler import profile
@profile
def my_function():
    pass

# Tracemalloc for allocation tracking
import tracemalloc
tracemalloc.start()
# ... code ...
snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')
```


---

## Advanced Memory Patterns

### Object Pool Pattern

Reuse objects instead of creating new ones:

```python
class ObjectPool:
    def __init__(self, factory, max_size=100):
        self._factory = factory
        self._pool = []
        self._max_size = max_size

    def acquire(self):
        if self._pool:
            return self._pool.pop()
        return self._factory()

    def release(self, obj):
        if len(self._pool) < self._max_size:
            self._pool.append(obj)

# Usage
pool = ObjectPool(lambda: bytearray(1024))
buffer = pool.acquire()
# ... use buffer ...
pool.release(buffer)
```

### Weak Reference Caching

Cache without preventing garbage collection:

```python
import weakref

class WeakCache:
    def __init__(self):
        self._cache = weakref.WeakValueDictionary()

    def get_or_create(self, key, factory):
        obj = self._cache.get(key)
        if obj is None:
            obj = factory(key)
            self._cache[key] = obj
        return obj
```

### Copy-on-Write Pattern

Share data until modification:

```python
class COWList:
    def __init__(self, data=None):
        self._data = data if data is not None else []
        self._shared = data is not None

    def _ensure_writable(self):
        if self._shared:
            self._data = self._data.copy()
            self._shared = False

    def append(self, item):
        self._ensure_writable()
        self._data.append(item)

    def __iter__(self):
        return iter(self._data)

    def copy(self):
        """Create a shallow copy that shares data."""
        return COWList(self._data)
```

### Array-of-Structs to Struct-of-Arrays

Better memory locality and smaller footprint:

**Before (AoS):**
```python
particles = [
    {'x': 1.0, 'y': 2.0, 'mass': 1.0},
    {'x': 3.0, 'y': 4.0, 'mass': 2.0},
    # ... millions more
]
```

**After (SoA):**
```python
import numpy as np

particles = {
    'x': np.array([1.0, 3.0, ...]),
    'y': np.array([2.0, 4.0, ...]),
    'mass': np.array([1.0, 2.0, ...])
}
```

### Flyweight Pattern

Share common state across instances:

```python
class CharacterFlyweight:
    _cache = {}

    def __new__(cls, char):
        if char not in cls._cache:
            instance = super().__new__(cls)
            instance.char = char
            instance.glyph = load_glyph(char)  # Expensive
            cls._cache[char] = instance
        return cls._cache[char]

# All 'a' characters share the same glyph data
chars = [CharacterFlyweight(c) for c in "aaabbbccc"]
```

### Sparse Data Structures

For mostly-empty data:

```python
from scipy.sparse import csr_matrix, dok_matrix
import numpy as np

# Dense: 80MB for 10000x1000 float64
dense = np.zeros((10000, 1000))

# Sparse: Only stores non-zero values
sparse = dok_matrix((10000, 1000))
sparse[0, 0] = 1.0
sparse[5000, 500] = 2.0
# Convert to efficient format for computation
sparse_csr = sparse.tocsr()
```

### Pandas Memory Optimization

```python
def optimize_dataframe(df):
    """Comprehensive DataFrame memory optimization."""

    # Downcast integers
    for col in df.select_dtypes(include=['int64']).columns:
        df[col] = pd.to_numeric(df[col], downcast='integer')

    # Downcast floats
    for col in df.select_dtypes(include=['float64']).columns:
        df[col] = pd.to_numeric(df[col], downcast='float')

    # Convert low-cardinality strings to category
    for col in df.select_dtypes(include=['object']).columns:
        num_unique = df[col].nunique()
        num_total = len(df[col])
        if num_unique / num_total < 0.5:  # Less than 50% unique
            df[col] = df[col].astype('category')

    # Use nullable integer types for columns with NaN
    for col in df.select_dtypes(include=['float']).columns:
        if df[col].dropna().apply(float.is_integer).all():
            df[col] = df[col].astype('Int64')

    return df
```

### Context Manager for Memory Cleanup

```python
import gc
from contextlib import contextmanager

@contextmanager
def memory_scope():
    """Ensure cleanup of allocations within scope."""
    try:
        yield
    finally:
        gc.collect()

# Usage
with memory_scope():
    large_data = load_huge_dataset()
    result = process(large_data)
    del large_data
# large_data guaranteed to be collected here
```

### Streaming JSON Processing

Process large JSON without loading into memory:

```python
import ijson

def process_large_json(filepath):
    """Stream process JSON array items."""
    with open(filepath, 'rb') as f:
        for item in ijson.items(f, 'records.item'):
            yield process_item(item)
```

### Memory-Efficient String Building

```python
# Bad: O(n²) memory for string concatenation
result = ""
for chunk in chunks:
    result += chunk

# Good: O(n) memory
result = "".join(chunks)

# Better for large data: write to file or StringIO
from io import StringIO
buffer = StringIO()
for chunk in chunks:
    buffer.write(chunk)
result = buffer.getvalue()
```
