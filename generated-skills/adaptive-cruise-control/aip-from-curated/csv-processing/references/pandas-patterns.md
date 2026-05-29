# Pandas Patterns for Simulation CSV I/O

Verbatim idioms the simulation code copies and adapts. Originally compiled in
the curated source `SKILL.md`; preserved here so the AIP body stays lean.

## Reading

```python
import pandas as pd

df = pd.read_csv('data.csv')

# View structure
print(df.head())
print(df.columns.tolist())
print(len(df))
```

### With explicit NA tokens (preferred for sensor data)

```python
df = pd.read_csv('data.csv', na_values=['', 'NA', 'null'])
```

## Handling Missing Values

```python
# Check for missing values
print(df.isnull().sum())

# Check if specific value is NaN (use on row dict from iterrows / iloc)
if pd.isna(row['column']):
    # Handle missing value (e.g., no lead vehicle → switch to 'cruise')
    pass
```

## Accessing Data

```python
# Single column
values = df['column_name']

# Multiple columns
subset = df[['col1', 'col2']]

# Filter rows
filtered = df[df['column'] > 10]
filtered = df[(df['time'] >= 30) & (df['time'] < 60)]

# Rows where column is not null
valid = df[df['column'].notna()]

# Row by position (use inside a fixed-timestep simulation loop)
row = df.iloc[i]
```

## Writing

```python
# From dictionary
data = {
    'time': [0.0, 0.1, 0.2],
    'value': [1.0, 2.0, 3.0],
    'label': ['a', 'b', 'c']
}
df = pd.DataFrame(data)
df.to_csv('output.csv', index=False)
```

## Building Results Incrementally

```python
results = []

for item in items:
    row = {
        'time': item.time,
        'value': item.value,
        'status': item.status if item.valid else None,  # None → empty cell
    }
    results.append(row)

df = pd.DataFrame(results)
df.to_csv('results.csv', index=False)
```

Key points:
- Construct each row dict with keys in the **exact column order** the spec
  requires. `pd.DataFrame(list_of_dicts)` preserves insertion order.
- `None` (or `float('nan')`) renders as an empty cell when written; do **not**
  substitute `0` or `-1` for "not applicable" fields.
- Always pass `index=False` to suppress pandas' auto-index column.

## Common Operations

```python
# Statistics (useful for the performance metrics in acc_report.md)
mean_val = df['column'].mean()
max_val  = df['column'].max()
min_val  = df['column'].min()
std_val  = df['column'].std()

# Add computed column
df['diff'] = df['col1'] - df['col2']

# Iterate rows (prefer .iloc[i] inside a fixed-index simulation loop)
for index, row in df.iterrows():
    process(row['col1'], row['col2'])
```
