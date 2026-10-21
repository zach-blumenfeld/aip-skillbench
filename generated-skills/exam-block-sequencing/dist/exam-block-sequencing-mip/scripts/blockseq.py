#!/usr/bin/env python3
"""Exam block sequencing: inspect, solve (heuristic warm start + PySCIPOpt MIP), audit, report.

Requires: Python >= 3.10, numpy, pandas, pyscipopt (SCIP). No other packages.
  python3 scripts/blockseq.py inspect --data /root/data
  python3 scripts/blockseq.py solve   --data /root/data --out /root/output [--heur-seconds 120] [--time-limit 180]
  python3 scripts/blockseq.py audit   --data /root/data --out /root/output
  python3 scripts/blockseq.py report  --data /root/data --out /root/output

Objective semantics (from the task's data README; override with flags if the README differs):
  - slots are taken in the order given by the instance; next(s) is the following slot in that list
  - pair/triplet tables are ORDERED; keys follow schedule order; missing rows count as 0
  - eve_morn_b2b_count   = sum over s in eve_morn_start  of P[blk(s), blk(next s)]
  - other_b2b_count      = sum over s in other_b2b_start of P[blk(s), blk(next s)]
  - same_day_triple_count  = sum over s in triple_day_start of T[a,b,c]   (a,b,c at s, s+1, s+2)
  - cross_day_triple_count = sum over s in triple_24_start  of T[a,b,c]
  - z_three_in_four_count  = sum over s with s and next(s) both triple starts (day or 24h)
                             of T[a,b,c] + T[a,c,d]   (a,b,c,d at s..s+3; --overlap-offsets)
  - objective = weighted sum of the five counts (--w-* flags)
"""
import argparse
import json
import math
import os
import sys
import time

import numpy as np
import pandas as pd

COMPONENTS = ["eve_morn_b2b_count", "other_b2b_count", "same_day_triple_count",
              "cross_day_triple_count", "z_three_in_four_count"]


# ----------------------------------------------------------------------------- loading
def _label_key(v):
    """Normalise a block/slot label so 3, 3.0 and '3' match."""
    s = str(v).strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
    except ValueError:
        pass
    return s


def _find_cols(df, n_keys):
    cols = list(df.columns)
    count_col = next((c for c in cols if str(c).strip().lower() in ("count", "counts", "weight", "value", "n")), cols[-1])
    key_cols = [c for c in cols if c != count_col][:n_keys]
    if len(key_cols) != n_keys:
        raise SystemExit(f"expected {n_keys} key columns + a count column, got columns {cols}")
    return key_cols, count_col


def load_instance(data_dir):
    path = os.path.join(data_dir, "instance.json")
    if not os.path.exists(path):
        raise SystemExit(f"missing {path}")
    with open(path) as f:
        inst = json.load(f)
    blocks = list(inst.get("all_blocks", []))
    for vb in inst.get("virtual_blocks", []) or []:          # virtual blocks are scheduled like normal ones
        if _label_key(vb) not in {_label_key(b) for b in blocks}:
            blocks.append(vb)
    if not blocks:
        raise SystemExit("instance.json has no all_blocks")
    slots = inst.get("all_slots") or inst.get("slots")
    if slots is None:
        slots = list(range(1, len(blocks) + 1))               # slot labels 1..N in order
    start_keys = ["triple_day_start", "triple_24_start", "eve_morn_start", "other_b2b_start"]
    for k in start_keys + ["large_blocks", "early_slots"]:
        if k not in inst:
            print(f"WARNING: instance.json has no '{k}'; treating it as empty", file=sys.stderr)
    blabel = {_label_key(b): b for b in blocks}
    slabel = {_label_key(s): s for s in slots}
    bidx = {_label_key(b): i for i, b in enumerate(blocks)}
    sidx = {_label_key(s): i for i, s in enumerate(slots)}
    if len(blocks) != len(slots):
        raise SystemExit(f"{len(blocks)} blocks vs {len(slots)} slots: a one-to-one schedule is impossible")

    def slot_list(k):
        out = []
        for s in inst.get(k, []) or []:
            if _label_key(s) not in sidx:
                raise SystemExit(f"{k} references slot {s} not in the slot list")
            out.append(sidx[_label_key(s)])
        return out

    large = []
    for b in inst.get("large_blocks", []) or []:
        if _label_key(b) not in bidx:
            raise SystemExit(f"large_blocks references unknown block {b}")
        large.append(bidx[_label_key(b)])
    early = slot_list("early_slots")
    if large and len(early) < len(large):
        raise SystemExit(f"{len(large)} large blocks but only {len(early)} early slots: infeasible")
    return dict(raw=inst, blocks=blocks, slots=slots, bidx=bidx, sidx=sidx, blabel=blabel, slabel=slabel,
                n=len(blocks), large=sorted(set(large)), early=sorted(set(early)),
                starts={k: sorted(set(slot_list(k))) for k in start_keys},
                virtual=[_label_key(v) for v in inst.get("virtual_blocks", []) or []])


def load_tables(data_dir, inst):
    n = inst["n"]
    P = np.zeros((n, n))
    T = np.zeros((n, n, n))
    unknown = 0
    for fname, arr, k in (("pair_counts.csv", P, 2), ("triplet_counts.csv", T, 3)):
        path = os.path.join(data_dir, fname)
        if not os.path.exists(path):
            raise SystemExit(f"missing {path}")
        df = pd.read_csv(path)
        kc, cc = _find_cols(df, k)
        dups = df.duplicated(kc).sum()
        if dups:
            print(f"WARNING: {fname} has {dups} duplicate ordered keys; summing them", file=sys.stderr)
        for row in df[kc + [cc]].itertuples(index=False):
            keys = [_label_key(v) for v in row[:k]]
            if any(key not in inst["bidx"] for key in keys):
                unknown += 1
                continue
            val = float(row[k]) if pd.notna(row[k]) else 0.0
            arr[tuple(inst["bidx"][key] for key in keys)] += val   # ordered key, no sorting
    if unknown:
        print(f"WARNING: {unknown} count rows reference blocks not in the instance; ignored", file=sys.stderr)
    return P, T


def parse_offsets(text):
    out = []
    for part in text.split(";"):
        offs = tuple(int(x) for x in part.split(","))
        if len(offs) != 3 or offs[0] != 0 or not (offs[0] < offs[1] < offs[2]):
            raise SystemExit(f"bad overlap offsets '{part}': need '0,i,j' with 0<i<j")
        out.append(offs)
    return out


def build_terms(inst, P, T, args):
    """Return list of (start_pos, offsets, table, weight, component). Positions are 0-based indices."""
    n = inst["n"]
    st = inst["starts"]
    terms, skipped = [], []

    def add(pos, offs, table, w, comp):
        if pos + offs[-1] >= n:
            skipped.append((comp, inst["slots"][pos]))
            return
        terms.append((pos, offs, table, w, comp))

    for s in st["eve_morn_start"]:
        add(s, (0, 1), P, args.w_eve_morn, "eve_morn_b2b_count")
    for s in st["other_b2b_start"]:
        add(s, (0, 1), P, args.w_other_b2b, "other_b2b_count")
    for s in st["triple_day_start"]:
        add(s, (0, 1, 2), T, args.w_same_day, "same_day_triple_count")
    for s in st["triple_24_start"]:
        add(s, (0, 1, 2), T, args.w_cross_day, "cross_day_triple_count")
    q = set(st["triple_day_start"]) | set(st["triple_24_start"])
    for s in sorted(q):
        if s + 1 in q:                       # two qualifying triple windows start in consecutive slots
            for offs in parse_offsets(args.overlap_offsets):
                add(s, offs, T, args.w_overlap, "z_three_in_four_count")
    if skipped:
        print(f"WARNING: {len(skipped)} windows run past the last slot and are not scored: {skipped[:5]}",
              file=sys.stderr)
    return terms


# ----------------------------------------------------------------------------- evaluation
def evaluate(seq, terms, weights):
    """Pure evaluator. seq[pos] = block index. Returns raw counts per component + weighted objective."""
    counts = {c: 0.0 for c in COMPONENTS}
    for pos, offs, table, w, comp in terms:
        counts[comp] += table[tuple(seq[pos + o] for o in offs)]
    out = {c: (int(round(v)) if abs(v - round(v)) < 1e-9 else v) for c, v in counts.items()}
    obj = sum(weights[c] * counts[c] for c in COMPONENTS)
    out["objective"] = int(round(obj)) if abs(obj - round(obj)) < 1e-9 else obj
    return out


def check_feasible(seq, inst):
    errs = []
    n = inst["n"]
    if len(seq) != n:
        errs.append(f"schedule has {len(seq)} slots, expected {n}")
    if sorted(seq) != list(range(n)):
        missing = set(range(n)) - set(seq)
        dup = [inst["blocks"][b] for b in set(seq) if seq.count(b) > 1]
        errs.append(f"not a permutation: missing={[inst['blocks'][b] for b in missing]} duplicated={dup}")
    early = set(inst["early"])
    for pos, b in enumerate(seq):
        if b in inst["large"] and pos not in early:
            errs.append(f"large block {inst['blocks'][b]} in non-early slot {inst['slots'][pos]}")
    return errs


def weights_from(args):
    return {"eve_morn_b2b_count": args.w_eve_morn, "other_b2b_count": args.w_other_b2b,
            "same_day_triple_count": args.w_same_day, "cross_day_triple_count": args.w_cross_day,
            "z_three_in_four_count": args.w_overlap}


# ----------------------------------------------------------------------------- heuristic
def _move_matrix(n):
    """Index permutations for all swap, reversal and segment-move (length 1-3) neighbours."""
    idx = list(range(n))
    moves = []
    for i in range(n):
        for j in range(i + 1, n):
            m = idx[:]
            m[i], m[j] = m[j], m[i]
            moves.append(m)
            if j - i > 1:
                moves.append(idx[:i] + idx[i:j + 1][::-1] + idx[j + 1:])
    for L in (1, 2, 3):
        for i in range(n - L + 1):
            seg, rest = idx[i:i + L], idx[:i] + idx[i + L:]
            for k in range(len(rest) + 1):
                if k != i:
                    moves.append(rest[:k] + seg + rest[k:])
    return np.unique(np.array(moves, dtype=np.int64), axis=0)


def local_search(inst, terms, seconds, seed, stall_kicks=3000):
    """Iterated local search with numpy batch evaluation of the full neighbourhood.

    Steepest descent over swaps/reversals/segment moves; kicks = 2-4 random swaps or a
    double-bridge segment exchange; restarts
    from a random feasible permutation after `stall_kicks` kicks without a new best."""
    n = inst["n"]
    rng = np.random.default_rng(seed)
    groups = {}
    for pos, offs, table, w, comp in terms:
        g = groups.setdefault((offs, id(table)), [offs, table, np.zeros(n)])
        g[2][pos] += w
    groups = [(o, t, np.nonzero(wv)[0], wv[np.nonzero(wv)[0]]) for o, t, wv in groups.values()]

    def cost(S):
        S = np.atleast_2d(S)
        tot = np.zeros(S.shape[0])
        for offs, table, pos, wv in groups:
            tot += (table[tuple(S[:, pos + o] for o in offs)] * wv).sum(1)
        return tot

    is_large = np.zeros(n, bool)
    is_large[inst["large"]] = True
    late = np.array([p for p in range(n) if p not in set(inst["early"])], dtype=np.int64)

    def feas(S):
        S = np.atleast_2d(S)
        return ~is_large[S[:, late]].any(1) if len(late) else np.ones(S.shape[0], bool)

    M = _move_matrix(n)

    def descend(seq):
        c = cost(seq)[0]
        while True:
            C = seq[M]
            cc = cost(C)
            cc[~feas(C)] = np.inf
            k = int(cc.argmin())
            if cc[k] < c - 1e-9:
                seq, c = C[k], cc[k]
            else:
                return seq, c

    def random_feasible():
        small = [b for b in range(n) if not is_large[b]]
        lg = [b for b in range(n) if is_large[b]]
        rng.shuffle(small)
        seq = np.empty(n, dtype=np.int64)
        seq[late] = small[:len(late)]
        rest = np.array(small[len(late):] + lg, dtype=np.int64)
        rng.shuffle(rest)
        seq[[p for p in range(n) if p not in set(late.tolist())]] = rest
        return seq

    deadline = time.time() + seconds
    best, best_cost = None, math.inf
    restarts = kicks = 0
    while True:
        restarts += 1
        cur, c = descend(random_feasible())
        run_best, run_cost, stall = cur, c, 0
        while stall < stall_kicks and time.time() < deadline:
            kicks += 1
            stall += 1
            x = (run_best if rng.random() < 0.7 else cur).copy()
            if rng.random() < 0.5 or n < 4:
                for _ in range(int(rng.integers(2, 5))):
                    i, j = rng.choice(n, 2, replace=False)
                    x[i], x[j] = x[j], x[i]
            else:  # double-bridge kick: A B C D -> A C B D
                i, j, k = sorted(rng.choice(np.arange(1, n), 3, replace=False))
                x = np.concatenate([x[:i], x[j:k], x[i:j], x[k:]])
            if not feas(x)[0]:
                continue
            x, cx = descend(x)
            if cx <= c or rng.random() < 0.05:
                cur, c = x, cx
            if cx < run_cost - 1e-9:
                run_best, run_cost, stall = x, cx, 0
        if run_cost < best_cost:
            best, best_cost = run_best, run_cost
        if time.time() >= deadline:
            break
    return [int(b) for b in best], float(best_cost), restarts, kicks


# ----------------------------------------------------------------------------- MIP
def solve_mip(inst, terms, warm, time_limit, threads_note=""):
    from pyscipopt import Model, quicksum
    n = inst["n"]
    N = range(n)
    large, early = set(inst["large"]), set(inst["early"])
    # aggregate weighted tables per (start, offsets)
    agg = {}
    for pos, offs, table, w, comp in terms:
        key = (pos, offs)
        agg[key] = agg.get(key, 0) + w * table
    for (pos, offs) in agg:
        if len(offs) == 3 and offs[1] != 1 and offs[2] != offs[1] + 1:
            raise RuntimeError(f"MIP linearization supports triple offsets (0,1,k) or (0,k,k+1); got {offs}")

    m = Model("exam_block_sequencing")
    m.hideOutput()
    m.setParam("limits/time", float(time_limit))
    x = {(b, s): m.addVar(vtype="B", name=f"x_{b}_{s}") for b in N for s in N}
    for b in N:
        m.addCons(quicksum(x[b, s] for s in N) == 1, name=f"block_once_{b}")
    for s in N:
        m.addCons(quicksum(x[b, s] for b in N) == 1, name=f"slot_once_{s}")
    for b in large:                               # front-loading: large blocks only in early slots
        for s in N:
            if s not in early:
                m.addCons(x[b, s] == 0, name=f"frontload_{b}_{s}")
    # adjacent-pair flow variables y[a,b,s] (a at s, b at s+1), integral given integral x
    y = {}
    for s in range(n - 1):
        for a in N:
            for b in N:
                if a != b:
                    y[a, b, s] = m.addVar(vtype="C", lb=0, ub=1, name=f"y_{a}_{b}_{s}")
        for a in N:
            m.addCons(quicksum(y[a, b, s] for b in N if b != a) == x[a, s], name=f"yout_{a}_{s}")
        for b in N:
            m.addCons(quicksum(y[a, b, s] for a in N if a != b) == x[b, s + 1], name=f"yin_{b}_{s}")
    obj = []
    aux = []   # (var, kind, data) for warm-start values
    for (pos, offs), W in agg.items():
        if offs == (0, 1):
            obj.extend(W[a, b] * y[a, b, pos] for a in N for b in N if a != b and W[a, b] != 0)
        elif offs[1] == 1:       # (0,1,k): u[a,b] >= sum_c W[a,b,c] x[c,pos+k] - M(1 - y[a,b,pos])
            k = offs[2]
            for a in N:
                for b in N:
                    if a == b:
                        continue
                    coef = {c: W[a, b, c] for c in N if c not in (a, b) and W[a, b, c] != 0}
                    if not coef:
                        continue
                    M = max(coef.values())
                    u = m.addVar(vtype="C", lb=0, name=f"u_{a}_{b}_{pos}_{k}")
                    m.addCons(u >= quicksum(v * x[c, pos + k] for c, v in coef.items()) - M * (1 - y[a, b, pos]))
                    obj.append(u)
                    aux.append((u, "u", (a, b, pos, k, coef)))
        else:                    # (0,k,k+1): v[a] >= sum_{c,d} W[a,c,d] y[c,d,pos+k] - M(1 - x[a,pos])
            k = offs[1]
            for a in N:
                coef = {(c, d): W[a, c, d] for c in N for d in N
                        if len({a, c, d}) == 3 and W[a, c, d] != 0}
                if not coef:
                    continue
                M = max(coef.values())
                v = m.addVar(vtype="C", lb=0, name=f"v_{a}_{pos}_{k}")
                m.addCons(v >= quicksum(val * y[c, d, pos + k] for (c, d), val in coef.items()) - M * (1 - x[a, pos]))
                obj.append(v)
                aux.append((v, "v", (a, pos, k, coef)))
    m.setObjective(quicksum(obj), "minimize")

    warm_accepted = None
    if warm is not None:
        sol = m.createSol()
        for b in N:
            for s in N:
                m.setSolVal(sol, x[b, s], 1.0 if warm[s] == b else 0.0)
        for (a, b, s), var in y.items():
            m.setSolVal(sol, var, 1.0 if (warm[s] == a and warm[s + 1] == b) else 0.0)
        for var, kind, data in aux:
            if kind == "u":
                a, b, pos, k, coef = data
                val = coef.get(warm[pos + k], 0.0) if (warm[pos] == a and warm[pos + 1] == b) else 0.0
            else:
                a, pos, k, coef = data
                val = coef.get((warm[pos + k], warm[pos + k + 1]), 0.0) if warm[pos] == a else 0.0
            m.setSolVal(sol, var, val)
        warm_accepted = bool(m.addSol(sol, free=True))

    t0 = time.time()
    m.optimize()
    wall = time.time() - t0
    status = str(m.getStatus()).lower()
    if m.getNSols() == 0:
        raise RuntimeError(f"No feasible solution found; solver status={status}")
    best = m.getBestSol()
    inc = float(m.getSolObjVal(best))
    try:
        bound = float(m.getDualbound())
    except Exception:
        bound = None
    try:
        gap = float(m.getGap())
    except Exception:
        gap = None
    seq = [None] * n
    for s in N:
        hits = [b for b in N if m.getSolVal(best, x[b, s]) > 0.5]
        if len(hits) != 1:
            raise RuntimeError(f"extraction failed at slot index {s}: {hits}")
        seq[s] = hits[0]
    info = dict(solver="SCIP via PySCIPOpt", scip_version=str(m.version()) if hasattr(m, "version") else None,
                status=status, time_limit_s=time_limit, wall_time_s=round(wall, 2),
                incumbent_objective=inc, best_bound=bound, gap=gap, n_solutions=m.getNSols(),
                warm_start_accepted=warm_accepted, n_vars=m.getNVars(), n_conss=m.getNConss(),
                proven_optimal=(status == "optimal"))
    return seq, info


# ----------------------------------------------------------------------------- I/O helpers
def write_schedule(path, seq, inst):
    pd.DataFrame({"slot": inst["slots"], "block": [inst["blocks"][b] for b in seq]}).to_csv(path, index=False)


def read_schedule(path, inst):
    df = pd.read_csv(path)
    cols = {c.strip().lower(): c for c in df.columns}
    if "slot" not in cols or "block" not in cols:
        raise SystemExit(f"{path} must have columns slot,block; has {list(df.columns)}")
    by_slot = {}
    for s, b in zip(df[cols["slot"]], df[cols["block"]]):
        sk, bk = _label_key(s), _label_key(b)
        if sk not in inst["sidx"]:
            raise SystemExit(f"unknown slot {s} in {path}")
        if bk not in inst["bidx"]:
            raise SystemExit(f"unknown block {b} in {path}")
        if sk in by_slot:
            raise SystemExit(f"slot {s} appears twice in {path}")
        by_slot[sk] = inst["bidx"][bk]
    missing = [s for s in inst["slots"] if _label_key(s) not in by_slot]
    if missing:
        raise SystemExit(f"slots missing from {path}: {missing}")
    return [by_slot[_label_key(s)] for s in inst["slots"]], len(df)


def add_common(p):
    p.add_argument("--data", default="/root/data")
    p.add_argument("--out", default="/root/output")
    p.add_argument("--w-eve-morn", type=float, default=1.0)
    p.add_argument("--w-other-b2b", type=float, default=1.0)
    p.add_argument("--w-same-day", type=float, default=10.0)
    p.add_argument("--w-cross-day", type=float, default=10.0)
    p.add_argument("--w-overlap", type=float, default=5.0)
    p.add_argument("--overlap-offsets", default="0,1,2;0,2,3",
                   help="triplet position offsets scored per overlap start; '0,1,2;0,2,3' = (a,b,c)+(a,c,d)")


# ----------------------------------------------------------------------------- commands
def cmd_inspect(args):
    inst = load_instance(args.data)
    P, T = load_tables(args.data, inst)
    terms = build_terms(inst, P, T, args)
    st = inst["starts"]
    q = set(st["triple_day_start"]) | set(st["triple_24_start"])
    sym_p = bool(np.allclose(P, P.T))
    sym_t = bool(np.allclose(T, T.transpose(2, 1, 0)))
    summ = {
        "n_blocks": inst["n"], "n_slots": len(inst["slots"]),
        "slot_order": inst["slots"],
        "slot_source": "instance all_slots" if (inst["raw"].get("all_slots") or inst["raw"].get("slots")) else "1..N (no slot list in instance)",
        "virtual_blocks": inst["virtual"],
        "n_large_blocks": len(inst["large"]), "n_early_slots": len(inst["early"]),
        "frontload_active": bool(inst["large"]) and len(inst["early"]) < inst["n"],
        "starts": {k: [inst["slots"][s] for s in v] for k, v in st.items()},
        "overlap_starts": [inst["slots"][s] for s in sorted(q) if s + 1 in q],
        "pair_rows_nonzero": int((P > 0).sum()), "triplet_rows_nonzero": int((T > 0).sum()),
        "pair_table_symmetric": sym_p, "triplet_table_reverse_symmetric": sym_t,
        "n_scored_terms": len(terms),
        "weights": weights_from(args), "overlap_offsets": args.overlap_offsets,
    }
    print("{\n" + ",\n".join(f'  "{k}": {json.dumps(v, default=str)}' for k, v in summ.items()) + "\n}")


def cmd_solve(args):
    inst = load_instance(args.data)
    P, T = load_tables(args.data, inst)
    terms = build_terms(inst, P, T, args)
    weights = weights_from(args)
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    warm, warm_cost, restarts, kicks = local_search(inst, terms, args.heur_seconds, args.seed)
    errs = check_feasible(warm, inst)
    if errs:
        raise SystemExit(f"heuristic produced infeasible schedule: {errs}")
    print(f"[heuristic] iterated local search {args.heur_seconds}s, {restarts} restarts, {kicks} kicks, "
          f"objective {warm_cost:g}",
          file=sys.stderr)
    mip_info = None
    final, method = warm, "heuristic"
    if args.time_limit > 0:
        try:
            seq, mip_info = solve_mip(inst, terms, warm, args.time_limit)
            print(f"[mip] status={mip_info['status']} incumbent={mip_info['incumbent_objective']:g} "
                  f"bound={mip_info['best_bound']} gap={mip_info['gap']}", file=sys.stderr)
            final, method = seq, "mip"
        except ImportError as exc:
            print(f"WARNING: pyscipopt unavailable ({exc}); keeping heuristic solution", file=sys.stderr)
        except RuntimeError as exc:
            print(f"WARNING: MIP step failed ({exc}); keeping heuristic solution", file=sys.stderr)
    errs = check_feasible(final, inst)
    if errs:
        raise SystemExit(f"final schedule infeasible: {errs}")
    metrics = evaluate(final, terms, weights)
    if mip_info is not None and abs(metrics["objective"] - mip_info["incumbent_objective"]) > 1e-4 * max(1, abs(metrics["objective"])):
        raise SystemExit(f"solver objective {mip_info['incumbent_objective']} != recomputed {metrics['objective']}: "
                         "check linearization/extraction")
    write_schedule(os.path.join(args.out, "schedule.csv"), final, inst)
    info = dict(method=method, final_objective=metrics["objective"], final_metrics=metrics,
                heuristic=dict(name="iterated local search (steepest descent over swap/reversal/segment moves, "
                                    "random-swap kicks, restarts), feasibility-preserving",
                               seconds=args.heur_seconds, restarts=restarts, kicks=kicks, seed=args.seed,
                               objective=warm_cost),
                mip=mip_info, weights=weights, overlap_offsets=args.overlap_offsets,
                total_wall_time_s=round(time.time() - t0, 2),
                n_blocks=inst["n"], n_large_blocks=len(inst["large"]), n_early_slots=len(inst["early"]),
                virtual_blocks=inst["virtual"])
    with open(os.path.join(args.out, "solve_info.json"), "w") as f:
        json.dump(info, f, indent=2, default=str)
    print(json.dumps({"method": method, "objective": metrics["objective"],
                      "status": mip_info["status"] if mip_info else "heuristic-only",
                      "bound": mip_info["best_bound"] if mip_info else None,
                      "gap": mip_info["gap"] if mip_info else None}, indent=2))


def cmd_audit(args):
    inst = load_instance(args.data)
    P, T = load_tables(args.data, inst)
    terms = build_terms(inst, P, T, args)
    weights = weights_from(args)
    sched_path = os.path.join(args.out, "schedule.csv")
    seq, nrows = read_schedule(sched_path, inst)
    errs = check_feasible(seq, inst)
    if nrows != inst["n"]:
        errs.append(f"schedule.csv has {nrows} rows, expected {inst['n']}")
    if errs:
        print(json.dumps({"feasible": False, "errors": errs}, indent=2))
        raise SystemExit(1)
    metrics = evaluate(seq, terms, weights)
    mpath = os.path.join(args.out, "metrics.json")
    with open(mpath, "w") as f:
        json.dump(metrics, f, indent=2)
    seq2, _ = read_schedule(sched_path, inst)
    with open(mpath) as f:
        disk = json.load(f)
    assert evaluate(seq2, terms, weights) == disk == metrics, "round-trip metrics mismatch"
    note = None
    ipath = os.path.join(args.out, "solve_info.json")
    if os.path.exists(ipath):
        with open(ipath) as f:
            info = json.load(f)
        if abs(info.get("final_objective", metrics["objective"]) - metrics["objective"]) > 1e-6:
            print(json.dumps({"feasible": True, "error": "solve_info final_objective differs from schedule.csv",
                              "solve_info": info.get("final_objective"), "recomputed": metrics["objective"]}))
            raise SystemExit(1)
        note = "matches solve_info.json"
    print(json.dumps({"feasible": True, "checks": ["each block exactly once", "each slot exactly one block",
                                                   "large blocks in early slots"],
                      "metrics": metrics, "solve_info": note}, indent=2))


def _fmt(v, nd=4):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if math.isinf(v):
            return "inf"
        if v.is_integer():
            return str(int(v))
        return f"{v:.{nd}g}" if abs(v) < 1 else f"{v:.2f}"
    return str(v)


def _pct(v):
    if v is None:
        return "n/a"
    if math.isinf(v) or v >= 1e19:          # SCIP reports 1e+20 when no useful dual bound exists
        return "infinite (no useful dual bound within the time limit)"
    return f"{v:.4f} ({100 * v:.2f}%)"


def cmd_report(args):
    ipath, mpath = os.path.join(args.out, "solve_info.json"), os.path.join(args.out, "metrics.json")
    for p in (ipath, mpath):
        if not os.path.exists(p):
            raise SystemExit(f"missing {p}; run solve and audit first")
    with open(ipath) as f:
        info = json.load(f)
    with open(mpath) as f:
        met = json.load(f)
    inst = load_instance(args.data)
    seq, _ = read_schedule(os.path.join(args.out, "schedule.csv"), inst)
    w = info["weights"]
    mip = info.get("mip")
    here = os.path.dirname(os.path.abspath(__file__))
    tdir = os.path.join(os.path.dirname(here), "assets")
    if mip:
        cert = ("proven optimal (solver status optimal)" if mip.get("proven_optimal") else
                f"best feasible incumbent within the time limit, NOT proven optimal (relative gap {_pct(mip.get('gap'))})")
        status_block = "\n".join([
            f"- Solver: {mip.get('solver')} (SCIP {mip.get('scip_version')})",
            f"- Time limit: {mip.get('time_limit_s')} s (wall time used {mip.get('wall_time_s')} s)",
            f"- Solver status: {mip.get('status')}",
            f"- Incumbent objective: {_fmt(mip.get('incumbent_objective'))}",
            f"- Best bound: {_fmt(mip.get('best_bound'))}",
            f"- Relative gap (SCIP, |primal-dual|/|dual|): {_pct(mip.get('gap'))}",
            f"- Warm start accepted: {mip.get('warm_start_accepted')}; model size: {mip.get('n_vars')} variables, {mip.get('n_conss')} constraints",
            f"- Certification: {cert}"])
    else:
        cert = "heuristic only (no solver certificate; quality unproven)"
        status_block = "- No MIP solve was completed; the final schedule is the iterated-local-search incumbent (no bound, no gap).\n- Certification: " + cert
    if mip:
        extraction = ("The schedule is extracted from the solver's best solution (x[b,s] > 0.5, exactly one block "
                      "per slot), validated (each block exactly once, each slot exactly one block, large blocks only "
                      "in early slots), and every metric is recomputed by a pure evaluator from `schedule.csv` on disk "
                      "and the input tables only. The recomputed objective equals the solver incumbent objective "
                      f"({_fmt(mip.get('incumbent_objective'))}). No post-processing was applied after the solver.")
    else:
        extraction = ("The MIP above was formulated but not solved in this run, so the schedule is the best permutation "
                      "found by the iterated local search; it carries no bound or optimality certificate. It was "
                      "validated (each block exactly once, each slot exactly one block, large blocks only in early "
                      "slots), and every metric is recomputed by a pure evaluator from `schedule.csv` on disk and "
                      "the input tables only.")
    h = info["heuristic"]
    fill = dict(
        weights_eve=_fmt(w["eve_morn_b2b_count"]), weights_other=_fmt(w["other_b2b_count"]),
        weights_day=_fmt(w["same_day_triple_count"]), weights_24=_fmt(w["cross_day_triple_count"]),
        weights_z=_fmt(w["z_three_in_four_count"]), overlap_offsets=info["overlap_offsets"],
        overlap_terms=" + ".join("triplet[" + ",".join("abcd"[o] if o < 4 else f"s+{o}" for o in offs) + "]"
                                 for offs in parse_offsets(info["overlap_offsets"])),
        n_blocks=info["n_blocks"], n_large=info["n_large_blocks"], n_early=info["n_early_slots"],
        virtual=", ".join(map(str, info["virtual_blocks"])) or "none",
        heur_seconds=h["seconds"], heur_restarts=h["restarts"], heur_obj=_fmt(h["objective"]), seed=h["seed"],
        status_block=status_block, method=info["method"], certification=cert, extraction=extraction,
        objective=met["objective"], eve=met["eve_morn_b2b_count"], other=met["other_b2b_count"],
        day=met["same_day_triple_count"], cross=met["cross_day_triple_count"], z=met["z_three_in_four_count"],
        c_eve=_fmt(w["eve_morn_b2b_count"] * met["eve_morn_b2b_count"]),
        c_other=_fmt(w["other_b2b_count"] * met["other_b2b_count"]),
        c_day=_fmt(w["same_day_triple_count"] * met["same_day_triple_count"]),
        c_cross=_fmt(w["cross_day_triple_count"] * met["cross_day_triple_count"]),
        c_z=_fmt(w["z_three_in_four_count"] * met["z_three_in_four_count"]),
        schedule_table="\n".join(f"| {s} | {inst['blocks'][b]} |" for s, b in zip(inst["slots"], seq)),
        large_ok=all(b not in inst["large"] or p in inst["early"] for p, b in enumerate(seq)),
    )
    for name in ("formulation.md", "report.md"):
        with open(os.path.join(tdir, name + ".tmpl")) as f:
            text = f.read()
        with open(os.path.join(args.out, name), "w") as f:
            f.write(text.format(**fill))
    print(f"wrote {os.path.join(args.out, 'formulation.md')} and {os.path.join(args.out, 'report.md')}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("inspect", "solve", "audit", "report"):
        p = sub.add_parser(name)
        add_common(p)
        if name == "solve":
            p.add_argument("--heur-seconds", type=float, default=120.0)
            p.add_argument("--time-limit", type=float, default=180.0, help="SCIP time limit in s; 0 = skip MIP")
            p.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    {"inspect": cmd_inspect, "solve": cmd_solve, "audit": cmd_audit, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
