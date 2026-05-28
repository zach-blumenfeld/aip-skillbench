# Visualizing the Pareto frontier

Load when the user asks for a plot. Two-objective case shown; for
higher dimensions, use a parallel-coordinates plot or pairwise scatter
panels.

```python
import matplotlib.pyplot as plt

# `all_points` is the (filtered) candidate set; `frontier` is the
# Pareto subset returned by compute_pareto_frontier().
plt.scatter(
    all_points["latency_ms"], all_points["accuracy"],
    alpha=0.5, label="All candidates",
)
plt.scatter(
    frontier["latency_ms"], frontier["accuracy"],
    color="red", s=100, marker="s", label="Pareto frontier",
)
plt.xlabel("Latency (ms) — minimize")
plt.ylabel("Accuracy — maximize")
plt.legend()
plt.tight_layout()
plt.savefig("pareto.png", dpi=150)
```

Tips
- Always label each axis with the sense (`maximize` / `minimize`) — it
  is the first thing the reader needs to know.
- Sort the frontier by one objective before drawing a connecting line,
  otherwise the "curve" zig-zags.
