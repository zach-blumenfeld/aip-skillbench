"""Shared core for exam block sequencing: loading, pure evaluator, annealing search, SCIP MIP.

Pure standard library except `pyscipopt` (imported lazily in build_and_solve_mip).
Every step script imports this module; scripts run with cwd = scripts/.
"""
import csv
import itertools
import json
import math
import os
import random
import sys
import time

# Canonical component names -> metrics.json count keys.
COMPONENTS = [
    ("eve_morn_b2b", "eve_morn_b2b_count"),
    ("other_b2b", "other_b2b_count"),
    ("same_day_triple", "same_day_triple_count"),
    ("cross_day_triple", "cross_day_triple_count"),
    ("three_in_four", "z_three_in_four_count"),
]

WEIGHT_ALIASES = {
    "eve_morn_b2b": ["eve_morn_b2b", "eve_morn", "evening_to_morning_b2b", "eve_morn_b2b_count"],
    "other_b2b": ["other_b2b", "other", "other_b2b_count"],
    "same_day_triple": ["same_day_triple", "same_day", "triple_day", "same_day_triple_count"],
    "cross_day_triple": ["cross_day_triple", "cross_day", "triple_24", "cross_day_triple_count"],
    "three_in_four": ["three_in_four", "z_three_in_four", "overlap", "four_slot_pressure",
                      "z_three_in_four_count"],
}

# Offsets (within the four-slot window a,b,c,d starting at s) of the ordered triplets
# the overlap term charges. Chosen by the overlap-semantics decision.
OVERLAP_RULES = {
    "abc_and_acd": [(0, 1, 2), (0, 2, 3)],
    "acd_only": [(0, 2, 3)],
    "abd_and_acd": [(0, 1, 3), (0, 2, 3)],
    "all_ordered_triples_in_four": [(0, 1, 2), (0, 1, 3), (0, 2, 3), (1, 2, 3)],
}


def fail(msg):
    sys.stderr.write(msg.rstrip() + "\n")
    sys.exit(1)


def read_stdin():
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        fail(f"stdin is not JSON: {exc}")
    return payload.get("state", payload)


def emit(obj):
    sys.stdout.write(json.dumps(obj, default=_json_default))
    sys.stdout.write("\n")


def _json_default(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def num(x):
    """Return an int when the value is integral, else float."""
    if isinstance(x, float) and x.is_integer():
        return int(x)
    return x


# --------------------------------------------------------------------------- loading

def _read_counts(path, arity):
    """Ordered count table: first `arity` columns are block labels, last column the count."""
    table, dup, rows = {}, 0, 0
    with open(path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None:
            fail(f"{path} is empty")
        lower = [h.strip().lower() for h in header]
        cidx = lower.index("count") if "count" in lower else len(header) - 1
        kidx = [i for i in range(len(header)) if i != cidx][:arity]
        if len(kidx) < arity:
            fail(f"{path}: expected {arity} key columns plus a count column, header={header}")
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            rows += 1
            key = tuple(_norm_label(row[i]) for i in kidx)  # ORDERED: never sort
            val = float(row[cidx])
            if key in table:
                dup += 1
                table[key] += val
            else:
                table[key] = val
    return table, rows, dup


def _norm_label(v):
    s = str(v).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def load_instance(data_dir):
    """Load instance.json + ordered pair/triplet tables. Returns a dict used by every step."""
    ip = os.path.join(data_dir, "instance.json")
    if not os.path.isfile(ip):
        fail(f"missing {ip}")
    with open(ip) as f:
        inst = json.load(f)
    warnings = []
    for k in ("all_blocks",):
        if k not in inst:
            fail(f"instance.json lacks '{k}'")
    blocks_raw = list(inst["all_blocks"])
    labels = [_norm_label(b) for b in blocks_raw]
    if len(set(labels)) != len(labels):
        fail("instance.json all_blocks has duplicate labels")
    raw_of = dict(zip(labels, blocks_raw))
    n = len(labels)

    slots_raw = inst.get("all_slots") or inst.get("slots") or inst.get("slot_order")
    if slots_raw:
        slots_raw = list(slots_raw)
        slot_source = "instance.json slot list"
    else:
        slots_raw = list(range(1, n + 1))
        slot_source = "1..len(all_blocks) (instance.json has no slot list; one slot per block)"
    slots = [_norm_label(s) for s in slots_raw]
    if len(slots) != n:
        fail(f"{len(slots)} slots but {n} blocks: a feasible schedule needs one block per slot")
    pos_of_slot = {s: i for i, s in enumerate(slots)}

    def slot_list(key):
        out = []
        for s in inst.get(key, []) or []:
            s = _norm_label(s)
            if s not in pos_of_slot:
                warnings.append(f"{key}: slot {s} not in slot order; ignored")
                continue
            out.append(pos_of_slot[s])
        return sorted(set(out))

    starts = {
        "eve_morn_b2b": slot_list("eve_morn_start"),
        "other_b2b": slot_list("other_b2b_start"),
        "same_day_triple": slot_list("triple_day_start"),
        "cross_day_triple": slot_list("triple_24_start"),
    }
    for key, span in (("eve_morn_b2b", 1), ("other_b2b", 1), ("same_day_triple", 2), ("cross_day_triple", 2)):
        keep = [p for p in starts[key] if p + span < n]
        if len(keep) != len(starts[key]):
            warnings.append(f"{key}: dropped starts whose window runs past the last slot")
        starts[key] = keep
    qualifying = set(starts["same_day_triple"]) | set(starts["cross_day_triple"])
    # Overlap: two qualifying three-slot windows start in consecutive slots s, next(s).
    starts["three_in_four"] = sorted(p for p in qualifying if (p + 1) in qualifying and p + 3 < n)

    large = [_norm_label(b) for b in inst.get("large_blocks", []) or []]
    early = slot_list("early_slots")
    virtual = [_norm_label(b) for b in inst.get("virtual_blocks", []) or []]
    for b in large + virtual:
        if b not in raw_of:
            fail(f"block {b} in large/virtual list is not in all_blocks")
    if large and not inst.get("early_slots"):
        warnings.append("large_blocks given but early_slots empty: front-loading treated as inactive")
    frontload_active = bool(large) and bool(early)
    if frontload_active and len(large) > len(early):
        fail(f"infeasible: {len(large)} large blocks but only {len(early)} early slots")

    pair, prow, pdup = _read_counts(os.path.join(data_dir, "pair_counts.csv"), 2)
    trip, trow, tdup = _read_counts(os.path.join(data_dir, "triplet_counts.csv"), 3)
    if pdup or tdup:
        warnings.append(f"duplicate rows summed: pair={pdup}, triplet={tdup}")
    lab = set(labels)
    unknown = sum(1 for k in pair if not set(k) <= lab) + sum(1 for k in trip if not set(k) <= lab)
    if unknown:
        warnings.append(f"{unknown} count rows reference blocks not in all_blocks; ignored")

    idx = {b: i for i, b in enumerate(labels)}
    P = [[0.0] * n for _ in range(n)]
    for (a, b), v in pair.items():
        if a in idx and b in idx:
            P[idx[a]][idx[b]] = v
    T = [[[0.0] * n for _ in range(n)] for _ in range(n)]
    for (a, b, c), v in trip.items():
        if a in idx and b in idx and c in idx:
            T[idx[a]][idx[b]][idx[c]] = v

    allowed = [[True] * n for _ in range(n)]  # allowed[block][pos]
    if frontload_active:
        early_set = set(early)
        for b in large:
            for p in range(n):
                allowed[idx[b]][p] = p in early_set

    return {
        "labels": labels, "raw_of": raw_of, "n": n, "slots": slots, "slot_raw": slots_raw,
        "slot_source": slot_source, "starts": starts, "large": large, "early": early,
        "virtual": virtual, "frontload_active": frontload_active, "P": P, "T": T,
        "allowed": allowed, "warnings": warnings, "pair_rows": prow, "triplet_rows": trow,
        "idx": idx,
    }


def normalize_weights(w):
    if not isinstance(w, dict):
        fail("weights must be an object")
    out, missing = {}, []
    for canon, aliases in WEIGHT_ALIASES.items():
        val = None
        for a in aliases:
            if a in w:
                val = w[a]
                break
        if val is None:
            missing.append(canon)
        else:
            out[canon] = float(val)
    if missing:
        fail(f"weights missing {missing}; expected keys {list(WEIGHT_ALIASES)}")
    return out


# --------------------------------------------------------------------------- objective terms

def build_terms(inst, weights, overlap_rule):
    """Aggregate every weighted objective term by the positions it reads.

    Returns (pair_terms {(q, q+1): w}, triple_terms {(q1, q2, q3): w}).
    """
    if overlap_rule not in OVERLAP_RULES:
        fail(f"unknown overlap_rule {overlap_rule!r}; choose one of {list(OVERLAP_RULES)}")
    pt, tt = {}, {}
    for comp in ("eve_morn_b2b", "other_b2b"):
        for q in inst["starts"][comp]:
            pt[(q, q + 1)] = pt.get((q, q + 1), 0.0) + weights[comp]
    for comp in ("same_day_triple", "cross_day_triple"):
        for q in inst["starts"][comp]:
            k = (q, q + 1, q + 2)
            tt[k] = tt.get(k, 0.0) + weights[comp]
    for q in inst["starts"]["three_in_four"]:
        for off in OVERLAP_RULES[overlap_rule]:
            k = tuple(q + o for o in off)
            tt[k] = tt.get(k, 0.0) + weights["three_in_four"]
    pt = {k: v for k, v in pt.items() if v}
    tt = {k: v for k, v in tt.items() if v}
    return pt, tt


def evaluate(perm, inst, weights, overlap_rule):
    """Pure evaluator: perm[pos] = block index. Uses only input data and the sequence."""
    P, T, st = inst["P"], inst["T"], inst["starts"]
    c = {}
    c["eve_morn_b2b"] = sum(P[perm[q]][perm[q + 1]] for q in st["eve_morn_b2b"])
    c["other_b2b"] = sum(P[perm[q]][perm[q + 1]] for q in st["other_b2b"])
    c["same_day_triple"] = sum(T[perm[q]][perm[q + 1]][perm[q + 2]] for q in st["same_day_triple"])
    c["cross_day_triple"] = sum(T[perm[q]][perm[q + 1]][perm[q + 2]] for q in st["cross_day_triple"])
    z = 0.0
    for q in st["three_in_four"]:
        for (o1, o2, o3) in OVERLAP_RULES[overlap_rule]:
            z += T[perm[q + o1]][perm[q + o2]][perm[q + o3]]
    c["three_in_four"] = z
    metrics = {"objective": num(sum(weights[k] * c[k] for k, _ in COMPONENTS))}
    for k, mk in COMPONENTS:
        metrics[mk] = num(c[k])
    return metrics


def check_feasible(perm, inst):
    n = inst["n"]
    issues = []
    if len(perm) != n:
        issues.append(f"{len(perm)} positions filled, expected {n}")
    if sorted(perm) != list(range(n)):
        issues.append("blocks missing or duplicated")
    for p, b in enumerate(perm):
        if 0 <= b < n and not inst["allowed"][b][p]:
            issues.append(f"large block {inst['labels'][b]} in non-early slot {inst['slots'][p]}")
    return issues


# --------------------------------------------------------------------------- annealing search

class FastCost:
    def __init__(self, inst, pt, tt):
        self.P, self.T, self.n = inst["P"], inst["T"], inst["n"]
        self.pairs = [(a, b, w) for (a, b), w in pt.items()]
        self.trips = [(a, b, c, w) for (a, b, c), w in tt.items()]
        self._range_cache = {}
        self.by_pos = [[] for _ in range(self.n)]
        for i, (a, b, w) in enumerate(self.pairs):
            for q in (a, b):
                self.by_pos[q].append(("p", i))
        for i, (a, b, c, w) in enumerate(self.trips):
            for q in (a, b, c):
                self.by_pos[q].append(("t", i))

    def total(self, perm):
        P, T = self.P, self.T
        s = 0.0
        for a, b, w in self.pairs:
            s += w * P[perm[a]][perm[b]]
        for a, b, c, w in self.trips:
            s += w * T[perm[a]][perm[b]][perm[c]]
        return s

    def local(self, perm, terms):
        P, T = self.P, self.T
        s = 0.0
        for kind, i in terms:
            if kind == "p":
                a, b, w = self.pairs[i]
                s += w * P[perm[a]][perm[b]]
            else:
                a, b, c, w = self.trips[i]
                s += w * T[perm[a]][perm[b]][perm[c]]
        return s

    def terms_range(self, lo, hi):
        key = (lo, hi)
        r = self._range_cache.get(key)
        if r is None:
            r = self._range_cache[key] = self.terms_for(range(lo, hi + 1))
        return r

    def terms_for(self, positions):
        seen = set()
        for q in positions:
            seen.update(self.by_pos[q])
        return list(seen)


def random_feasible(inst, rng):
    n, allowed = inst["n"], inst["allowed"]
    restricted = [b for b in range(n) if not all(allowed[b])]
    free = [b for b in range(n) if all(allowed[b])]
    rng.shuffle(restricted)
    perm = [None] * n
    for b in restricted:
        opts = [p for p in range(n) if perm[p] is None and allowed[b][p]]
        if not opts:
            fail("could not build a feasible start: front-loading too tight")
        perm[rng.choice(opts)] = b
    rng.shuffle(free)
    it = iter(free)
    for p in range(n):
        if perm[p] is None:
            perm[p] = next(it)
    return perm


def _insert(perm, a, b):
    x = perm[:]
    v = x.pop(a)
    x.insert(b, v)
    return x


def _feasible_range(perm, allowed, lo, hi):
    return all(allowed[perm[p]][p] for p in range(lo, hi + 1))


def local_descent(perm, inst, fc):
    """First-improvement descent over all swaps and insertions to a local optimum."""
    n, allowed = inst["n"], inst["allowed"]
    cur = fc.total(perm)
    improved = True
    while improved:
        improved = False
        for a in range(n):
            for b in range(a + 1, n):
                if allowed[perm[a]][b] and allowed[perm[b]][a]:
                    terms = fc.terms_for((a, b))
                    old = fc.local(perm, terms)
                    perm[a], perm[b] = perm[b], perm[a]
                    d = fc.local(perm, terms) - old
                    if d < -1e-9:
                        cur += d
                        improved = True
                    else:
                        perm[a], perm[b] = perm[b], perm[a]
        for a in range(n):
            for b in range(n):
                if a == b:
                    continue
                x = _insert(perm, a, b)
                lo, hi = min(a, b), max(a, b)
                if not _feasible_range(x, allowed, lo, hi):
                    continue
                terms = fc.terms_range(lo, hi)
                d = fc.local(x, terms) - fc.local(perm, terms)
                if d < -1e-9:
                    perm[:] = x
                    cur += d
                    improved = True
    return perm, cur


def _sa_run(perm, fc, allowed, rng, iters, temp_scale, end_ratio, deadline):
    n = fc.n
    cur = fc.total(perm)
    ups = []
    for _ in range(200):  # temperature from sampled uphill swap deltas
        a, b = rng.randrange(n), rng.randrange(n)
        if a == b or not (allowed[perm[a]][b] and allowed[perm[b]][a]):
            continue
        terms = fc.terms_for((a, b))
        old = fc.local(perm, terms)
        perm[a], perm[b] = perm[b], perm[a]
        d = fc.local(perm, terms) - old
        perm[a], perm[b] = perm[b], perm[a]
        if d > 0:
            ups.append(d)
    temp0 = temp_scale * ((sum(ups) / len(ups)) if ups else 1.0)
    temp1 = max(1e-3, temp0 * end_ratio)
    rb_perm, rb_cost = perm[:], cur
    for it in range(iters):
        if it % 2000 == 0 and time.time() >= deadline:
            break
        temp = temp0 * (temp1 / temp0) ** (it / iters)
        a, b = rng.randrange(n), rng.randrange(n)
        if a == b:
            continue
        if rng.random() < 0.7:  # swap
            if not (allowed[perm[a]][b] and allowed[perm[b]][a]):
                continue
            terms = fc.terms_for((a, b))
            old = fc.local(perm, terms)
            perm[a], perm[b] = perm[b], perm[a]
            d = fc.local(perm, terms) - old
            if d <= 0 or rng.random() < math.exp(-d / temp):
                cur += d
            else:
                perm[a], perm[b] = perm[b], perm[a]
                continue
        else:  # insertion
            lo, hi = min(a, b), max(a, b)
            x = _insert(perm, a, b)
            if not _feasible_range(x, allowed, lo, hi):
                continue
            terms = fc.terms_range(lo, hi)
            d = fc.local(x, terms) - fc.local(perm, terms)
            if d <= 0 or rng.random() < math.exp(-d / temp):
                perm, cur = x, cur + d
            else:
                continue
        if cur < rb_cost - 1e-9:
            rb_perm, rb_cost = perm[:], cur
    return rb_perm, rb_cost


def window_polish(perm, inst, fc, width=6):
    """Exact re-permutation of every window of `width` consecutive positions (repeat to a fixpoint)."""
    n, allowed = inst["n"], inst["allowed"]
    width = min(width, n)
    cur = fc.total(perm)
    improved = True
    while improved:
        improved = False
        for lo in range(0, n - width + 1):
            pos = list(range(lo, lo + width))
            terms = fc.terms_for(pos)
            base = perm[lo:lo + width]
            old = fc.local(perm, terms)
            best_d, best_arr = 0.0, None
            for arr in itertools.permutations(base):
                if any(not allowed[arr[k]][lo + k] for k in range(width)):
                    continue
                perm[lo:lo + width] = arr
                d = fc.local(perm, terms) - old
                if d < best_d - 1e-9:
                    best_d, best_arr = d, list(arr)
            perm[lo:lo + width] = best_arr if best_arr else base
            if best_arr:
                cur += best_d
                improved = True
    return perm, cur


def polish(perm, inst, fc, width=6):
    """Alternate swap/insertion descent and exact window re-permutation until neither improves."""
    perm, c = local_descent(perm, inst, fc)
    while True:
        perm, c2 = window_polish(perm, inst, fc, width)
        if c2 >= c - 1e-9:
            return perm, c2
        perm, c = local_descent(perm, inst, fc)


def _perturb(perm, allowed, rng, strength):
    x = perm[:]
    n = len(x)
    for _ in range(strength):
        a, b = rng.randrange(n), rng.randrange(n)
        if a != b and allowed[x[a]][b] and allowed[x[b]][a]:
            x[a], x[b] = x[b], x[a]
    return x


def search(inst, pt, tt, seconds, seed=0, seeds_from=None, sa_fraction=0.5,
           iters_per_restart=100000, temp_scale=1.0, end_ratio=1e-3, pool_size=4):
    """Hybrid heuristic. Phase 1 (sa_fraction of the budget): multi-restart simulated annealing
    with swap + insertion moves that keep front-loading feasible, each restart polished by
    swap/insertion descent and exact 6-window re-permutation. Phase 2: iterated local search on
    the best `pool_size` distinct schedules, alternating random-swap kicks and short reheated
    anneals, each followed by the same polish; equal-cost moves are accepted (plateau walk).
    """
    rng = random.Random(seed)
    fc = FastCost(inst, pt, tt)
    allowed = inst["allowed"]
    t0 = time.time()
    end_all = t0 + seconds
    end_sa = t0 + seconds * sa_fraction
    best_perm, best_cost, best_t = None, float("inf"), 0.0
    restart_bests, pool = [], []
    seeds = [list(x) for x in (seeds_from or [])]

    def consider(pm, c):
        nonlocal best_perm, best_cost, best_t
        if c < best_cost - 1e-9:
            best_perm, best_cost, best_t = pm[:], c, time.time() - t0

    for sp in seeds:  # polished seeds enter the pool directly
        sp, c = polish(sp, inst, fc)
        pool.append((c, sp))
        consider(sp, c)
    while not restart_bests or time.time() < end_sa:
        perm = random_feasible(inst, rng)
        perm, c = _sa_run(perm, fc, allowed, rng, iters_per_restart, temp_scale, end_ratio, end_sa)
        perm, c = polish(perm, inst, fc)
        restart_bests.append(c)
        pool.append((c, perm))
        consider(perm, c)
    uniq = {}
    for c, pm in sorted(pool, key=lambda z: z[0]):
        uniq.setdefault(tuple(pm), c)
    pool = [[c, list(pm)] for pm, c in list(uniq.items())[:pool_size]]
    ils_iters, ils_improvements = 0, 0
    k = 0
    while time.time() < end_all:
        item = pool[k % len(pool)]
        k += 1
        if k % 2:
            cand = _perturb(item[1], allowed, rng, rng.randint(2, 5))
        else:  # short reheated anneal from the pool member
            cand, _ = _sa_run(item[1][:], fc, allowed, rng, 20000, 0.2, 1e-2, end_all)
        cand, c = polish(cand, inst, fc)
        ils_iters += 1
        if c <= item[0] + 1e-9:
            if c < item[0] - 1e-9:
                ils_improvements += 1
            item[0], item[1] = c, cand
            consider(cand, c)
    total_t = time.time() - t0
    finals = sorted(c for c, _ in pool)
    hits = sum(1 for c in finals if abs(c - best_cost) < 1e-6)
    return {
        "perm": best_perm, "cost": best_cost,
        "sa_restarts": len(restart_bests), "sa_restart_costs_best10": sorted(restart_bests)[:10],
        "ils_pool_final_costs": finals, "ils_pool_members_at_best": hits,
        "ils_iterations": ils_iters, "ils_improvements": ils_improvements,
        "seconds": round(total_t, 2), "best_found_at_seconds": round(best_t, 2),
        "last_improvement_fraction": round(best_t / total_t, 3) if total_t > 0 else 0.0,
    }


# --------------------------------------------------------------------------- MIP

def build_and_solve_mip(inst, pt, tt, time_limit, warm_perm=None, tuning=("heur_fast", "pre_fast")):
    """Compact exact MIP solved with SCIP (PySCIPOpt), warm-started from `warm_perm`.

    y[i,q]   binary  block i at position q (front-loading: only allowed (i,q) are created)
    p[i,j,q] binary  i at q and j at q+1 (arc variable for every consecutive position pair)
    c[i,j,K] >= 0    triple-window cost for position triple K whose adjacent pair is (i,j)
    """
    try:
        from pyscipopt import Model, quicksum, SCIP_PARAMSETTING
    except Exception as exc:  # pragma: no cover
        return {"available": False, "error": f"pyscipopt import failed: {exc}"}

    P, T, n, allowed = inst["P"], inst["T"], inst["n"], inst["allowed"]
    tb = time.time()
    m = Model("exam_block_sequencing")
    m.hideOutput()
    m.setParam("limits/time", float(time_limit))
    # The warm start already supplies a strong incumbent; spend root time on the LP bound.
    if "heur_off" in tuning:
        m.setHeuristics(SCIP_PARAMSETTING.OFF)
    elif "heur_fast" in tuning:
        m.setHeuristics(SCIP_PARAMSETTING.FAST)
    if "sep_fast" in tuning:
        m.setSeparating(SCIP_PARAMSETTING.FAST)
    if "pre_fast" in tuning:
        m.setPresolve(SCIP_PARAMSETTING.FAST)
    if "barrier" in tuning:
        m.setParam("lp/initalgorithm", "b")
    y = {(i, q): m.addVar(vtype="B", name=f"y_{i}_{q}") for i in range(n) for q in range(n) if allowed[i][q]}
    for i in range(n):
        m.addCons(quicksum(y[i, q] for q in range(n) if (i, q) in y) == 1, name=f"block_once_{i}")
    for q in range(n):
        m.addCons(quicksum(y[i, q] for i in range(n) if (i, q) in y) == 1, name=f"slot_once_{q}")
    p = {}
    for q in range(n - 1):
        for i in range(n):
            if (i, q) not in y:
                continue
            for j in range(n):
                if i != j and (j, q + 1) in y:
                    p[i, j, q] = m.addVar(vtype="B", name=f"p_{i}_{j}_{q}")
        for i in range(n):
            if (i, q) in y:
                m.addCons(quicksum(p[i, j, q] for j in range(n) if (i, j, q) in p) == y[i, q])
        for j in range(n):
            if (j, q + 1) in y:
                m.addCons(quicksum(p[i, j, q] for i in range(n) if (i, j, q) in p) == y[j, q + 1])

    obj = []
    for (a, b), w in pt.items():
        for i in range(n):
            for j in range(n):
                if (i, j, a) in p and P[i][j]:
                    obj.append(w * P[i][j] * p[i, j, a])
    cvars = {}  # (K, i, j) -> (var, mode)
    for K, w in tt.items():
        q1, q2, q3 = K
        if q2 == q1 + 1:      # pair at (q1,q2), third block at q3
            mode, pq, lone = "pair_first", q1, q3
        elif q3 == q2 + 1:    # pair at (q2,q3), first block at q1
            mode, pq, lone = "pair_last", q2, q1
        else:
            return {"available": True, "error": f"position triple {K} has no adjacent pair; unsupported"}
        for i in range(n):
            for j in range(n):
                if (i, j, pq) not in p:
                    continue
                if mode == "pair_first":
                    coef = [(k, T[i][j][k]) for k in range(n) if (k, lone) in y and k not in (i, j) and T[i][j][k]]
                else:
                    coef = [(k, T[k][i][j]) for k in range(n) if (k, lone) in y and k not in (i, j) and T[k][i][j]]
                if not coef:
                    continue
                M = max(v for _, v in coef)
                c = m.addVar(vtype="C", lb=0.0, name=f"c_{q1}_{q2}_{q3}_{i}_{j}")
                # c >= sum_k T*y[k,lone] - M*(1 - p[i,j,pq]); tight at the true cost when p = 1, 0 otherwise
                m.addCons(c - quicksum(v * y[k, lone] for k, v in coef) - M * p[i, j, pq] >= -M)
                cvars[(K, i, j)] = (c, mode, pq, lone)
                obj.append(w * c)
    m.setObjective(quicksum(obj), "minimize")
    build_s = time.time() - tb

    warm_ok = None
    if warm_perm is not None:
        sol = m.createSol()
        pos = {b: q for q, b in enumerate(warm_perm)}
        for (i, q), v in y.items():
            m.setSolVal(sol, v, 1.0 if warm_perm[q] == i else 0.0)
        for (i, j, q), v in p.items():
            m.setSolVal(sol, v, 1.0 if (warm_perm[q] == i and warm_perm[q + 1] == j) else 0.0)
        for (K, i, j), (c, mode, pq, lone) in cvars.items():
            val = 0.0
            if warm_perm[pq] == i and warm_perm[pq + 1] == j:
                k = warm_perm[lone]
                val = T[i][j][k] if mode == "pair_first" else T[k][i][j]
            m.setSolVal(sol, c, val)
        warm_ok = bool(m.addSol(sol, free=True))

    ts = time.time()
    m.optimize()
    solve_s = time.time() - ts
    status = str(m.getStatus()).lower()
    res = {
        "available": True, "solver": "SCIP via PySCIPOpt", "status": status,
        "time_limit_seconds": float(time_limit), "build_seconds": round(build_s, 2),
        "solve_seconds": round(solve_s, 2), "warm_start_accepted": warm_ok,
        "n_binary": len(y) + len(p), "n_continuous": len(cvars), "n_constraints": m.getNConss(),
        "n_solutions": m.getNSols(), "nodes": m.getNNodes(),
    }
    try:
        db = float(m.getDualbound())
        res["best_bound"] = db if math.isfinite(db) and abs(db) < 1e19 else None
    except Exception:
        res["best_bound"] = None
    if res["best_bound"] is None:
        res["bound_note"] = "SCIP finished no root LP within the time limit, so it has no dual bound"
    nonneg = all(v >= 0 for row in P for v in row) and all(v >= 0 for a in T for r in a for v in r)
    if nonneg and (res["best_bound"] is None or res["best_bound"] < 0):
        res["best_bound"] = 0.0  # all counts are non-negative, so 0 is a valid (trivial) bound
        res["bound_note"] = res.get("bound_note", "") + "; trivial bound 0 used (all counts non-negative)"
    if m.getNSols() == 0:
        res["error"] = f"no feasible solution; status={status}"
        return res
    best = m.getBestSol()
    res["incumbent_objective"] = float(m.getSolObjVal(best))
    try:
        g = float(m.getGap())
        res["solver_gap"] = g if math.isfinite(g) and abs(g) < 1e19 else None
    except Exception:
        res["solver_gap"] = None
    perm = [None] * n
    for (i, q), v in y.items():
        if m.getSolVal(best, v) > 0.5:
            if perm[q] is not None:
                res["error"] = f"two blocks extracted at position {q}"
                return res
            perm[q] = i
    if any(b is None for b in perm):
        res["error"] = "extraction left a position empty"
        return res
    res["perm"] = perm
    return res


def gap_fields(incumbent, bound):
    if bound is None or incumbent is None:
        return {"absolute_gap": None, "relative_gap": None}
    ab = incumbent - bound
    return {"absolute_gap": round(ab, 6), "relative_gap": round(ab / max(1.0, abs(incumbent)), 6)}


def _search_worker(args):
    data_dir, weights, overlap_rule, seconds, seed, seeds_from = args
    inst = load_instance(data_dir)
    pt, tt = build_terms(inst, weights, overlap_rule)
    return search(inst, pt, tt, seconds, seed=seed, seeds_from=seeds_from)


def parallel_search(data_dir, weights, overlap_rule, seconds, workers=None, base_seed=0, seeds_from=None):
    """Run `search` with different seeds in parallel processes and keep the best schedule."""
    if workers is None:
        workers = max(1, min(4, os.cpu_count() or 1))
    # Only worker 0 gets the seed schedules, so the others stay independent and their agreement
    # with the best remains a real convergence signal.
    jobs = [(data_dir, weights, overlap_rule, seconds, base_seed + w, seeds_from if w == 0 else None)
            for w in range(workers)]
    if workers == 1:
        results = [_search_worker(jobs[0])]
    else:
        from concurrent.futures import ProcessPoolExecutor
        try:
            with ProcessPoolExecutor(max_workers=workers) as ex:
                results = list(ex.map(_search_worker, jobs))
        except Exception as exc:  # e.g. no /dev/shm in a sandbox: fall back to one process
            sys.stderr.write(f"parallel search unavailable ({exc}); running one process\n")
            results = [_search_worker(jobs[0])]
    best = min(results, key=lambda r: r["cost"])
    costs = sorted(r["cost"] for r in results)
    return {
        "perm": best["perm"], "cost": best["cost"], "workers": len(results),
        "worker_best_costs": costs,
        "workers_at_best": sum(1 for c in costs if abs(c - best["cost"]) < 1e-6),
        "sa_restarts_total": sum(r["sa_restarts"] for r in results),
        "ils_iterations_total": sum(r["ils_iterations"] for r in results),
        "seconds": max(r["seconds"] for r in results),
        "best_worker_last_improvement_fraction": best["last_improvement_fraction"],
        "max_last_improvement_fraction": max(r["last_improvement_fraction"] for r in results),
    }
