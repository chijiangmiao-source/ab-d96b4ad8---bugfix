"""Clock-tree compensation solver.

Hierarchy of objectives (edge vector is ordered by edge id, ASCII order):

  1. minimize the number of edges whose added compensation is positive
  2. minimize the total added compensation
  3. lexicographically smallest compensation vector

For every adjustable edge we additionally report the minimum/maximum
compensation it may take across *all* solutions that are jointly optimal for
objectives 1 and 2 (moving a shared upstream edge shifts a whole subtree, so
individual values are usually not unique).

When no feasible compensation exists we report an inclusion-minimal set of
leaves whose arrival windows cannot hold simultaneously, together with the
reachable arrival interval of each such leaf.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

CAP_MAX = 16


class SolverError(Exception):
    """Error in the input model discovered before solving."""


@dataclass
class Edge:
    id: str
    source: str
    target: str
    delay: int
    cap: int


@dataclass
class Window:
    node: str
    lo: int
    hi: int


@dataclass
class Model:
    nodes: list[str]
    edges: list[Edge]
    windows: list[Window]
    root: str
    children: dict[str, list[tuple[str, int]]]  # node -> (child node, edge idx)
    depth: dict[str, int]
    order: list[int]  # edge indices sorted by edge id (vector order)
    base: dict[str, int]  # intrinsic arrival at node (x = 0)
    path: dict[str, list[int]]  # edge indices root -> node


def build_model(nodes: list[str], edges: list[Edge], windows: list[Window]) -> Model:
    """Validate the batch and normalize the tree to root-outward orientation."""
    if not (2 <= len(nodes) <= 55):
        raise SolverError("每批须包含 2 至 55 个节点")
    if len(set(nodes)) != len(nodes):
        raise SolverError("节点名必须唯一")
    for n in nodes:
        if not n or not all(ord(c) < 128 for c in n):
            raise SolverError(f"节点名须为非空 ASCII 字符串: {n!r}")

    node_set = set(nodes)
    if len(edges) != len(nodes) - 1:
        raise SolverError(
            f"根向有向树须恰有 n-1 条边: 节点 {len(nodes)} 个, 边 {len(edges)} 条"
        )
    seen_ids: set[str] = set()
    for e in edges:
        if not e.id or not all(ord(c) < 128 for c in e.id):
            raise SolverError("边标识须为非空 ASCII 字符串")
        if e.id in seen_ids:
            raise SolverError(f"边标识重复: {e.id}")
        seen_ids.add(e.id)
        if e.source not in node_set or e.target not in node_set:
            raise SolverError(f"边 {e.id} 的端点不在节点表中")
        if e.source == e.target:
            raise SolverError(f"边 {e.id} 构成自环")
        if e.delay < 0:
            raise SolverError(f"边 {e.id} 的固有延迟须为非负整数")
        if not (0 <= e.cap <= CAP_MAX):
            raise SolverError(f"边 {e.id} 的可加上限须在 0..{CAP_MAX} 之间")

    if len(windows) < 2:
        raise SolverError("至少须为两个叶端给出到达闭区间")
    win_nodes: set[str] = set()
    for w in windows:
        if w.node not in node_set:
            raise SolverError(f"叶端区间引用了不存在的节点: {w.node}")
        if w.node in win_nodes:
            raise SolverError(f"叶端 {w.node} 给出了多个区间")
        win_nodes.add(w.node)
        if w.lo > w.hi:
            raise SolverError(f"叶端 {w.node} 的区间下界大于上界")

    # Underlying undirected graph must be a tree (n-1 edges + connected).
    adj: dict[str, list[tuple[str, int]]] = {n: [] for n in nodes}
    indeg: dict[str, int] = {n: 0 for n in nodes}
    outdeg: dict[str, int] = {n: 0 for n in nodes}
    for i, e in enumerate(edges):
        adj[e.source].append((e.target, i))
        adj[e.target].append((e.source, i))
        outdeg[e.source] += 1
        indeg[e.target] += 1

    seen = {nodes[0]}
    stack = [nodes[0]]
    while stack:
        u = stack.pop()
        for v, _ in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)
    if len(seen) != len(nodes):
        raise SolverError("边集未连通, 不构成一棵树")

    roots_out = [n for n in nodes if indeg[n] == 0]
    roots_in = [n for n in nodes if outdeg[n] == 0]
    reverse = False
    if len(roots_out) == 1 and all(
        indeg[n] == 1 for n in nodes if n != roots_out[0]
    ):
        root = roots_out[0]
    elif len(roots_in) == 1 and all(
        outdeg[n] == 1 for n in nodes if n != roots_in[0]
    ):
        # edges point rootward (child -> parent); normalize outward
        root = roots_in[0]
        reverse = True
    else:
        raise SolverError("有向边须自唯一根一致指向叶端（或全部指向根）")

    children: dict[str, list[tuple[str, int]]] = {n: [] for n in nodes}
    for i, e in enumerate(edges):
        u, v = (e.target, e.source) if reverse else (e.source, e.target)
        children[u].append((v, i))

    depth: dict[str, int] = {root: 0}
    base: dict[str, int] = {root: 0}
    path: dict[str, list[int]] = {root: []}
    stack = [root]
    while stack:
        u = stack.pop()
        for v, ei in children[u]:
            depth[v] = depth[u] + 1
            base[v] = base[u] + edges[ei].delay
            path[v] = path[u] + [ei]
            stack.append(v)

    leaves = {n for n in nodes if not children[n]}
    for w in windows:
        if w.node not in leaves:
            raise SolverError(f"区间只能赋给叶端节点: {w.node} 不是叶端")

    edge_order = sorted(range(len(edges)), key=lambda i: edges[i].id)
    return Model(
        nodes=nodes,
        edges=edges,
        windows=windows,
        root=root,
        children=children,
        depth=depth,
        order=edge_order,
        base=base,
        path=path,
    )


# --------------------------------------------------------------------------- #
# MILP core
# --------------------------------------------------------------------------- #

def _constraint_matrix(model: Model, window_index):
    """Build (A, lb, ub). Variables: x_0..x_{m-1}, y_0..y_{m-1}."""
    m = len(model.edges)
    caps = np.array([e.cap for e in model.edges], dtype=float)
    rows: list[np.ndarray] = []
    lbs: list[float] = []
    ubs: list[float] = []

    # x_e - cap_e * y_e <= 0 (cap = 0 pins x = 0 via bounds)
    for i, cap in enumerate(caps):
        if cap > 0:
            row = np.zeros(2 * m)
            row[i] = 1.0
            row[m + i] = -cap
            rows.append(row)
            lbs.append(-np.inf)
            ubs.append(0.0)

    # leaf arrival windows: sum of x on root path in [w.lo-base, w.hi-base]
    for wi in window_index:
        w = model.windows[wi]
        row = np.zeros(2 * m)
        for ei in model.path[w.node]:
            row[ei] = 1.0
        rows.append(row)
        lbs.append(float(w.lo - model.base[w.node]))
        ubs.append(float(w.hi - model.base[w.node]))

    A = np.vstack(rows) if rows else np.zeros((0, 2 * m))
    return A, np.array(lbs), np.array(ubs), caps


def _solve_milp(
    model: Model,
    window_index=None,
    *,
    cost=None,
    fixed=None,
    positive_count=None,
    total_comp=None,
):
    """Solve one restricted MILP. ``cost`` is a length-2m objective vector."""
    m = len(model.edges)
    if window_index is None:
        window_index = list(range(len(model.windows)))

    A, lbs, ubs, caps = _constraint_matrix(model, window_index)
    extra_rows, extra_lb, extra_ub = [], [], []

    if positive_count is not None:
        row = np.zeros(2 * m)
        row[m:] = 1.0
        extra_rows.append(row)
        extra_lb.append(float(positive_count))
        extra_ub.append(float(positive_count))

    if total_comp is not None:
        row = np.zeros(2 * m)
        row[:m] = 1.0
        extra_rows.append(row)
        extra_lb.append(float(total_comp))
        extra_ub.append(float(total_comp))

    for fi, fv in (fixed or {}).items():
        row = np.zeros(2 * m)
        row[fi] = 1.0
        extra_rows.append(row)
        extra_lb.append(float(fv))
        extra_ub.append(float(fv))

    if extra_rows:
        A = np.vstack([A, np.vstack(extra_rows)])
        lbs = np.concatenate([lbs, np.array(extra_lb)])
        ubs = np.concatenate([ubs, np.array(extra_ub)])

    bounds = Bounds(
        np.concatenate([np.zeros(m), np.zeros(m)]),
        np.concatenate([caps, np.ones(m)]),
    )
    return milp(
        cost if cost is not None else np.zeros(2 * m),
        constraints=LinearConstraint(A, lbs, ubs),
        integrality=np.ones(2 * m),
        bounds=bounds,
        options={"disp": False, "mip_rel_gap": 0.0, "presolve": True},
    )


def _is_feasible(model: Model, window_index=None) -> bool:
    res = _solve_milp(model, window_index)
    return bool(res.success)


def _unit(m: int, i: int) -> np.ndarray:
    v = np.zeros(2 * m)
    v[i] = 1.0
    return v


def _cost_positive_count(m: int) -> np.ndarray:
    cost = np.zeros(2 * m)
    cost[m:] = 1.0
    return cost


def _cost_total_comp(m: int) -> np.ndarray:
    cost = np.zeros(2 * m)
    cost[:m] = 1.0
    return cost


# --------------------------------------------------------------------------- #
# Result assembly
# --------------------------------------------------------------------------- #

def solve(model: Model) -> dict:
    m = len(model.edges)

    if not _is_feasible(model):
        return _infeasible_report(model)

    # Stage 1: minimize the number of positive-compensation edges.
    res1 = _solve_milp(model, cost=_cost_positive_count(m))
    if not res1.success:  # pragma: no cover - guarded by feasibility call
        raise SolverError("第一级目标求解失败")
    p_star = int(round(res1.fun))

    # Stage 2: among stage-1 optima, minimize total compensation.
    res2 = _solve_milp(model, cost=_cost_total_comp(m), positive_count=p_star)
    if not res2.success:  # pragma: no cover
        raise SolverError("第二级目标求解失败")
    t_star = int(round(res2.fun))

    # Stage 3: lexicographically smallest vector ordered by edge id.
    # A weighted sum cannot encode lexicographic order exactly (no finite weight
    # dominates arbitrarily large compensation on later coordinates), so fix
    # coordinates one at a time to their smallest feasible value.
    chosen: dict[int, int] = {}
    for edge_index in model.order:
        res = _solve_milp(
            model,
            cost=_unit(m, edge_index),
            positive_count=p_star,
            total_comp=t_star,
            fixed=chosen,
        )
        if not res.success:  # pragma: no cover - prior stages guarantee a point
            raise SolverError(
                f"第三级字典序求解失败于边 {model.edges[edge_index].id}"
            )
        chosen[edge_index] = int(round(res.x[edge_index]))

    # Ranges across ALL solutions optimal for stages 1 & 2.
    minima: dict[int, int] = {}
    maxima: dict[int, int] = {}
    for i, e in enumerate(model.edges):
        if e.cap == 0:
            minima[i] = maxima[i] = 0
            continue
        rmin = _solve_milp(
            model, cost=_unit(m, i), positive_count=p_star, total_comp=t_star
        )
        rmax = _solve_milp(
            model, cost=-_unit(m, i), positive_count=p_star, total_comp=t_star
        )
        if not (rmin.success and rmax.success):  # pragma: no cover
            raise SolverError(f"边 {e.id} 的同优范围求解失败")
        minima[i] = int(round(rmin.x[i]))
        maxima[i] = int(round(rmax.x[i]))

    return _feasible_report(model, chosen, minima, maxima, p_star, t_star)


def _arrivals(model: Model, x: dict[int, int]) -> dict[str, int]:
    arr: dict[str, int] = {model.root: 0}
    stack = [model.root]
    while stack:
        u = stack.pop()
        for v, ei in model.children[u]:
            arr[v] = arr[u] + model.edges[ei].delay + x[ei]
            stack.append(v)
    return arr


def _feasible_report(model: Model, chosen, minima, maxima, p_star, t_star) -> dict:
    arrivals = _arrivals(model, chosen)
    win_by_node = {w.node: w for w in model.windows}

    tree_rows = []

    def add_row(u: str, pei: int | None):
        w = win_by_node.get(u)
        arrival = arrivals[u]
        margin = margin_lo = margin_hi = None
        if w is not None:
            margin_lo = arrival - w.lo
            margin_hi = w.hi - arrival
            margin = min(margin_lo, margin_hi)
        return {
            "node": u,
            "depth": model.depth[u],
            "is_leaf": not model.children[u],
            "parent_edge": model.edges[pei].id if pei is not None else None,
            "edge_delay": model.edges[pei].delay if pei is not None else None,
            "edge_cap": model.edges[pei].cap if pei is not None else None,
            "compensation": chosen[pei] if pei is not None else None,
            "arrival": arrival,
            "window": {"lo": w.lo, "hi": w.hi} if w else None,
            "margin": margin,
            "margin_low": margin_lo,
            "margin_high": margin_hi,
        }

    def dfs(u: str, pei):
        tree_rows.append(add_row(u, pei))
        for v, ei in sorted(model.children[u], key=lambda kv: model.edges[kv[1]].id):
            dfs(v, ei)

    dfs(model.root, None)

    edge_rows = []
    for i in model.order:
        e = model.edges[i]
        edge_rows.append({
            "id": e.id,
            "source": e.source,
            "target": e.target,
            "delay": e.delay,
            "cap": e.cap,
            "adjustable": e.cap > 0,
            "chosen": chosen[i],
            "min": minima[i],
            "max": maxima[i],
        })

    leaf_rows = []
    for w in model.windows:
        a = arrivals[w.node]
        leaf_rows.append({
            "node": w.node,
            "arrival": a,
            "lo": w.lo,
            "hi": w.hi,
            "margin": min(a - w.lo, w.hi - a),
            "margin_low": a - w.lo,
            "margin_high": w.hi - a,
            "reachable_low": model.base[w.node],
            "reachable_high": model.base[w.node]
            + sum(model.edges[ei].cap for ei in model.path[w.node]),
        })

    return {
        "status": "feasible",
        "objectives": {
            "positive_edges": p_star,
            "total_compensation": t_star,
            "vector_order": [model.edges[i].id for i in model.order],
            "vector": [chosen[i] for i in model.order],
        },
        "tree": {"root": model.root, "rows": tree_rows},
        "edges": edge_rows,
        "leaves": leaf_rows,
        "conflict": None,
    }


def _infeasible_report(model: Model) -> dict:
    # Deletion filter: find an inclusion-minimal infeasible subset of windows.
    remaining = list(range(len(model.windows)))
    for i in list(remaining):
        trial = [j for j in remaining if j != i]
        if not _is_feasible(model, trial):
            remaining = trial

    conflict_leaves = []
    for wi in remaining:
        w = model.windows[wi]
        cap_sum = sum(model.edges[ei].cap for ei in model.path[w.node])
        conflict_leaves.append({
            "node": w.node,
            "lo": w.lo,
            "hi": w.hi,
            "reachable_low": model.base[w.node],
            "reachable_high": model.base[w.node] + cap_sum,
        })

    names = ", ".join(c["node"] for c in conflict_leaves)
    return {
        "status": "infeasible",
        "objectives": None,
        "tree": None,
        "edges": None,
        "leaves": None,
        "conflict": {
            "leaves": conflict_leaves,
            "message": (
                "不存在可同时满足全部叶端窗口的加量方案；"
                f"以下叶端不能同时满足: {names}"
            ),
        },
    }
