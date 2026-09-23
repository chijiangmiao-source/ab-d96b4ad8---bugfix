"""Unit tests for the solver hierarchy and the HTTP API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.solver import (
    Edge,
    SolverError,
    Window,
    build_model,
    solve,
)

client = TestClient(app)


def E(eid, source, target, delay, cap):
    return Edge(id=eid, source=source, target=target, delay=delay, cap=cap)


def W(node, lo, hi):
    return Window(node=node, lo=lo, hi=hi)


def ids(result):
    return result["objectives"]["vector_order"]


def vec(result):
    return result["objectives"]["vector"]


# --------------------------------------------------------------------------- #
# basic feasible hierarchy
# --------------------------------------------------------------------------- #

def test_simple_tree_objective_hierarchy():
    # root R --e1--> A --e2--> L1
    #          \--e3--> L2
    # intrinsic arrivals: L1 = 3+2 = 5, L2 = 4
    nodes = ["R", "A", "L1", "L2"]
    edges = [
        E("e1", "R", "A", 3, 16),
        E("e2", "A", "L1", 2, 16),
        E("e3", "R", "L2", 4, 16),
    ]
    windows = [W("L1", 7, 10), W("L2", 7, 10)]
    m = build_model(nodes, edges, windows)
    r = solve(m)
    assert r["status"] == "feasible"
    # e1 (R->A) only serves L1; L2's sole edge e3 must take +3, and L1 needs
    # +2..+5 via e1/e2 -> minimum 2 positive edges, cheapest total 5.
    assert r["objectives"]["positive_edges"] == 2
    assert r["objectives"]["total_compensation"] == 5
    assert dict(zip(ids(r), vec(r))) == {"e1": 0, "e2": 2, "e3": 3}
    by_id = {row["id"]: row for row in r["edges"]}
    # stage 1&2 optima: e3 pinned 3; (e1,e2) splits L1's +2 -> ranges [0,2]
    assert (by_id["e1"]["min"], by_id["e1"]["max"]) == (0, 2)
    assert (by_id["e2"]["min"], by_id["e2"]["max"]) == (0, 2)
    assert by_id["e3"]["min"] == 3 and by_id["e3"]["max"] == 3
    leaf = {x["node"]: x for x in r["leaves"]}
    assert leaf["L1"]["arrival"] == 7 and leaf["L2"]["arrival"] == 7
    assert leaf["L1"]["margin"] == 0
    assert leaf["L2"]["margin"] == 0


def test_shared_upstream_preferred_over_per_leaf():
    # shared edge e0 with cap 16; two leaf edges each cap 16.
    # windows require +4 on both leaves -> e0=4 uses ONE positive edge
    nodes = ["R", "A", "L1", "L2"]
    edges = [
        E("e0", "R", "A", 10, 16),
        E("e1", "A", "L1", 0, 16),
        E("e2", "A", "L2", 0, 16),
    ]
    windows = [W("L1", 14, 20), W("L2", 14, 20)]
    r = solve(build_model(nodes, edges, windows))
    assert r["objectives"]["positive_edges"] == 1
    assert vec(r) == [4, 0, 0]


def test_zero_cap_edge_is_fixed():
    nodes = ["R", "L1", "L2"]
    edges = [
        E("a", "R", "L1", 5, 0),
        E("b", "R", "L2", 7, 16),
    ]
    windows = [W("L1", 5, 9), W("L2", 7, 9)]
    r = solve(build_model(nodes, edges, windows))
    by_id = {x["id"]: x for x in r["edges"]}
    assert by_id["a"]["chosen"] == 0
    assert by_id["a"]["min"] == 0 and by_id["a"]["max"] == 0
    assert not by_id["a"]["adjustable"]


def test_lexicographic_tie_break_uses_id_order():
    # two symmetric leaf edges, both must receive >=2; min positive = 2,
    # total = 4, vector already zero-padded -> lex tie irrelevant.
    # Build a case with genuine slack: require sums, redistribution allowed.
    nodes = ["R", "A", "L1", "L2"]
    edges = [
        E("e0", "R", "A", 0, 16),
        E("e1", "A", "L1", 0, 16),
        E("e2", "A", "L2", 0, 16),
    ]
    # L1 window [2,2], L2 window [2,2]: total >=4, positive edges min:
    # e0=2 covers 2 on each, leaves need 0 more -> 1 positive edge total 2?
    # e0=2 => L1=2,L2=2 yes! single edge.
    r = solve(build_model(nodes, edges, [W("L1", 2, 2), W("L2", 2, 2)]))
    assert vec(r) == [2, 0, 0]
    # now windows [2,3]: e0=2 => both 2, single positive edge, total 2.
    r = solve(build_model(nodes, edges, [W("L1", 2, 3), W("L2", 2, 3)]))
    assert r["objectives"]["positive_edges"] == 1
    assert r["objectives"]["total_compensation"] == 2
    assert vec(r) == [2, 0, 0]
    # ranges across stage 1&2 optima: e0 pinned 2
    by_id = {x["id"]: x for x in r["edges"]}
    assert (by_id["e0"]["min"], by_id["e0"]["max"]) == (2, 2)


def test_range_across_tied_optima():
    # L1 window [0,4], L2 window [4,4], caps: e0 shared 16, e1/e2 leaf 16
    # e0=4 => L1=4 (in window), L2=4 => 1 positive edge, total 4. unique.
    # Build redistribution tie instead: both leaves [4,4]:
    # e0=4 unique as well. Use wide windows with exact total:
    nodes = ["R", "A", "L1", "L2"]
    edges = [
        E("e0", "R", "A", 0, 16),
        E("e1", "A", "L1", 0, 16),
        E("e2", "A", "L2", 0, 16),
    ]
    windows = [W("L1", 4, 8), W("L2", 4, 8)]
    r = solve(build_model(nodes, edges, windows))
    # 1 positive edge possible: e0=4 => both 4, total 4
    assert r["objectives"]["positive_edges"] == 1
    assert r["objectives"]["total_compensation"] == 4
    # stage1/2 optima: e0=4 only (e1/e2 alone cannot reach both leaves)
    by_id = {x["id"]: x for x in r["edges"]}
    assert (by_id["e0"]["min"], by_id["e0"]["max"]) == (4, 4)

    # genuine tie: L1 in [2,6], L2 in [2,6], must use exactly...
    # e0=2 => both 2: unique minimum. Use a 3-edge-chain sharing case:
    nodes2 = ["R", "A", "B", "L1", "L2"]
    edges2 = [
        E("s", "R", "A", 0, 16),    # shared by both leaves
        E("t", "A", "B", 0, 16),    # L1 only
        E("u", "B", "L1", 0, 16),   # L1 only
        E("v", "A", "L2", 0, 16),   # L2 only
    ]
    wins2 = [W("L1", 4, 4), W("L2", 2, 2)]
    r2 = solve(build_model(nodes2, edges2, wins2))
    # min positive edges: s=2, v=0, L2=2; L1 needs 4: t+u=2 -> 3 positive
    # edges minimum (s, one of {t,u}, v=0) -> s=2,t=2,u=0 OR s=2,t=0,u=2:
    # t and u both on L1 path; either single edge =2 => 2 positive edges
    assert r2["objectives"]["positive_edges"] == 2
    assert r2["objectives"]["total_compensation"] == 4
    d = {x["id"]: x for x in r2["edges"]}
    assert (d["s"]["min"], d["s"]["max"]) == (2, 2)
    assert d["t"]["min"] == 0 and d["t"]["max"] == 2
    assert d["u"]["min"] == 0 and d["u"]["max"] == 2
    # chosen vector lexicographically smallest: t before u -> t=0, u=2
    assert dict(zip(ids(r2), vec(r2))) == {"s": 2, "t": 0, "u": 2, "v": 0}


def test_high_fanout_leaf_edges_beat_cap_limited_shared_edge():
    # Root R --a-shared(cap 8)--> A --b00..b09(cap 16)--> ten leaves, every
    # leaf a closed point at 16. Using the shared edge covers at most 8 of the
    # required 16 and forces ALL ten leaf edges positive on top: 11 positive
    # edges / total 88. Keeping the shared edge at 0 and putting 16 on each
    # leaf edge costs more total (160) but only 10 positive edges, so the
    # primary objective must reject the shared edge despite its fan-out.
    leaves = [f"L{i:02d}" for i in range(10)]
    nodes = ["R", "A"] + leaves
    edges = [E("a-shared", "R", "A", 0, 8)]
    edges += [E(f"b{i:02d}", "A", f"L{i:02d}", 0, 16) for i in range(10)]
    windows = [W(n, 16, 16) for n in leaves]
    r = solve(build_model(nodes, edges, windows))
    assert r["status"] == "feasible"
    assert r["objectives"]["positive_edges"] == 10
    assert r["objectives"]["total_compensation"] == 160
    v = dict(zip(ids(r), vec(r)))
    assert v["a-shared"] == 0
    for i in range(10):
        assert v[f"b{i:02d}"] == 16
    # Every edge is pinned across all stage 1&2 optima.
    by_id = {x["id"]: x for x in r["edges"]}
    assert (by_id["a-shared"]["min"], by_id["a-shared"]["max"]) == (0, 0)
    for i in range(10):
        eid = f"b{i:02d}"
        assert (by_id[eid]["min"], by_id[eid]["max"]) == (16, 16)
    # Every leaf really arrives at the closed point 16.
    assert {x["node"]: x["arrival"] for x in r["leaves"]} == {n: 16 for n in leaves}
    tree = {x["node"]: x for x in r["tree"]["rows"]}
    assert tree["A"]["compensation"] == 0
    assert tree["L00"]["arrival"] == 16 and tree["L09"]["arrival"] == 16


def test_lexicographic_tie_break_on_chain_prefix():
    # Zero-delay tree R --a(cap4)--> A --b(cap3)--> B --d(cap2)--> L1, plus
    # R --c(cap1)--> L0. L0 requires the closed point 0 (c pinned 0), L1
    # requires [6,7]. Stage 1/2 optima need exactly 2 positive edges and total
    # 6: (a,b) = (3,3) or (4,2) with d=0, or a=4,d=2 with b=0, etc. The
    # lexicographically smallest vector in id order (a,b,c,d) is (3,3,0,0).
    nodes = ["R", "A", "B", "L0", "L1"]
    edges = [
        E("a", "R", "A", 0, 4),
        E("b", "A", "B", 0, 3),
        E("d", "B", "L1", 0, 2),
        E("c", "R", "L0", 0, 1),
    ]
    windows = [W("L0", 0, 0), W("L1", 6, 7)]
    r = solve(build_model(nodes, edges, windows))
    assert r["status"] == "feasible"
    assert r["objectives"]["positive_edges"] == 2
    assert r["objectives"]["total_compensation"] == 6
    assert ids(r) == ["a", "b", "c", "d"]
    assert vec(r) == [3, 3, 0, 0]
    by_id = {x["id"]: x for x in r["edges"]}
    # Co-optimal ranges across all stage 1&2 solutions:
    assert (by_id["a"]["min"], by_id["a"]["max"]) == (3, 4)
    assert (by_id["b"]["min"], by_id["b"]["max"]) == (0, 3)
    assert (by_id["c"]["min"], by_id["c"]["max"]) == (0, 0)
    assert (by_id["d"]["min"], by_id["d"]["max"]) == (0, 2)
    arrivals = {x["node"]: x["arrival"] for x in r["leaves"]}
    assert arrivals == {"L0": 0, "L1": 6}


# --------------------------------------------------------------------------- #
# infeasibility / conflicts
# --------------------------------------------------------------------------- #

def test_infeasible_independent_windows_minimal_core():
    # Each window individually unreachable: minimal unsat cores are singletons;
    # reachable intervals must still be reported for the chosen core.
    nodes = ["R", "L1", "L2"]
    edges = [
        E("a", "R", "L1", 10, 2),
        E("b", "R", "L2", 10, 2),
    ]
    # L1 reachable [10,12] wants [20,20]; L2 reachable [10,12] wants [0,5]
    windows = [W("L1", 20, 20), W("L2", 0, 5)]
    r = solve(build_model(nodes, edges, windows))
    assert r["status"] == "infeasible"
    assert 1 <= len(r["conflict"]["leaves"]) <= 2
    for c in r["conflict"]["leaves"]:
        assert (c["reachable_low"], c["reachable_high"]) == (10, 12)


def test_infeasible_shared_upstream_coupling_conflict():
    # The core scenario: a shared edge forces a whole subtree to move together.
    # R --e0--> A --e1(cap0)--> L1
    #             \--e2(cap0)--> L2
    # L1 wants arrival 2, L2 wants arrival 8, only e0 adjustable -> impossible,
    # and each window alone IS feasible, so the minimal core is exactly the
    # pair {L1, L2}.
    nodes = ["R", "A", "L1", "L2"]
    edges = [
        E("e0", "R", "A", 0, 16),
        E("e1", "A", "L1", 0, 0),
        E("e2", "A", "L2", 0, 0),
    ]
    windows = [W("L1", 2, 2), W("L2", 8, 8)]
    r = solve(build_model(nodes, edges, windows))
    assert r["status"] == "infeasible"
    assert {c["node"] for c in r["conflict"]["leaves"]} == {"L1", "L2"}
    by = {c["node"]: c for c in r["conflict"]["leaves"]}
    assert (by["L1"]["reachable_low"], by["L1"]["reachable_high"]) == (0, 16)
    assert (by["L2"]["reachable_low"], by["L2"]["reachable_high"]) == (0, 16)
    assert r["conflict"]["message"]


def test_minimal_conflict_subset_with_bystander():
    # L1,L2 conflict; L3 is satisfiable alongside anything -> must be dropped
    # from the reported minimal conflict set.
    nodes = ["R", "L1", "L2", "L3"]
    edges = [
        E("a", "R", "L1", 0, 16),
        E("b", "R", "L2", 0, 16),
        E("c", "R", "L3", 5, 16),
    ]
    windows = [
        W("L1", 100, 100),   # unreachable (max 16)
        W("L2", 100, 100),   # also unreachable, but each alone still infeasible
        W("L3", 5, 21),
    ]
    r = solve(build_model(nodes, edges, windows))
    assert r["status"] == "infeasible"
    names = {c["node"] for c in r["conflict"]["leaves"]}
    # L1 alone is infeasible, L2 alone infeasible -> singleton minimal sets
    # (deletion filter keeps whichever singletons remain infeasible)
    assert "L3" not in names
    assert names <= {"L1", "L2"}


# --------------------------------------------------------------------------- #
# input validation
# --------------------------------------------------------------------------- #

def test_validation_errors():
    with pytest.raises(SolverError):
        build_model(["R"], [], [])  # too few nodes
    with pytest.raises(SolverError):
        build_model(["R", "R"], [E("a", "R", "R", 0, 0)], [])
    nodes = ["R", "L1", "L2"]
    with pytest.raises(SolverError):
        build_model(nodes, [E("a", "R", "L1", 0, 16)], [W("L1", 0, 1), W("L2", 0, 1)])
    with pytest.raises(SolverError):
        build_model(nodes,
                    [E("a", "R", "L1", 0, 16), E("a", "R", "L2", 0, 16)],
                    [W("L1", 0, 1), W("L2", 0, 1)])
    with pytest.raises(SolverError):
        build_model(nodes,
                    [E("a", "R", "L1", -1, 16), E("b", "R", "L2", 0, 16)],
                    [W("L1", 0, 1), W("L2", 0, 1)])
    with pytest.raises(SolverError):
        build_model(nodes,
                    [E("a", "R", "L1", 0, 17), E("b", "R", "L2", 0, 16)],
                    [W("L1", 0, 1), W("L2", 0, 1)])
    with pytest.raises(SolverError):
        # window on internal node
        build_model(["R", "A", "L1", "L2"],
                    [E("a", "R", "A", 0, 16), E("b", "A", "L1", 0, 16),
                     E("c", "A", "L2", 0, 16)],
                    [W("A", 0, 1), W("L1", 0, 1)])


def test_rootward_orientation_accepted():
    # child -> parent edges (root-directed tree)
    nodes = ["R", "L1", "L2"]
    edges = [E("a", "L1", "R", 3, 16), E("b", "L2", "R", 5, 16)]
    r = solve(build_model(nodes, edges, [W("L1", 3, 9), W("L2", 5, 9)]))
    assert r["status"] == "feasible"
    assert {x["node"] for x in r["tree"]["rows"]} == set(nodes)


# --------------------------------------------------------------------------- #
# HTTP API
# --------------------------------------------------------------------------- #

def payload(**over):
    p = {
        "nodes": ["R", "A", "L1", "L2"],
        "edges": [
            {"id": "e1", "source": "R", "target": "A", "delay": 3, "cap": 16},
            {"id": "e2", "source": "A", "target": "L1", "delay": 2, "cap": 16},
            {"id": "e3", "source": "R", "target": "L2", "delay": 4, "cap": 16},
        ],
        "windows": [
            {"node": "L1", "lo": 7, "hi": 10},
            {"node": "L2", "lo": 7, "hi": 10},
        ],
    }
    p.update(over)
    return p


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_api_solve_feasible():
    r = client.post("/api/v1/solve", json=payload())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "feasible"
    assert body["tree"]["root"] == "R"
    assert len(body["edges"]) == 3
    assert {x["node"] for x in body["leaves"]} == {"L1", "L2"}


def test_api_solve_infeasible():
    # shared upstream coupling: e1 moves both leaves together, leaf edges fixed
    p = payload()
    p["edges"] = [
        {"id": "e1", "source": "R", "target": "A", "delay": 0, "cap": 16},
        {"id": "e2", "source": "A", "target": "L1", "delay": 0, "cap": 0},
        {"id": "e3", "source": "A", "target": "L2", "delay": 0, "cap": 0},
    ]
    p["windows"] = [
        {"node": "L1", "lo": 2, "hi": 2},
        {"node": "L2", "lo": 8, "hi": 8},
    ]
    r = client.post("/api/v1/solve", json=p)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "infeasible"
    assert {c["node"] for c in body["conflict"]["leaves"]} == {"L1", "L2"}


def test_api_validation_422():
    p = payload(nodes=["R", "A"])
    r = client.post("/api/v1/solve", json=p)
    assert r.status_code == 422
    assert "detail" in r.json()


def test_api_bad_type_422():
    p = payload()
    p["edges"][0]["cap"] = 99
    r = client.post("/api/v1/solve", json=p)
    assert r.status_code == 422


def test_api_high_fanout_prefers_leaf_edges():
    leaves = [f"L{i:02d}" for i in range(10)]
    p = {
        "nodes": ["R", "A"] + leaves,
        "edges": (
            [{"id": "a-shared", "source": "R", "target": "A", "delay": 0, "cap": 8}]
            + [
                {"id": f"b{i:02d}", "source": "A", "target": f"L{i:02d}",
                 "delay": 0, "cap": 16}
                for i in range(10)
            ]
        ),
        "windows": [{"node": n, "lo": 16, "hi": 16} for n in leaves],
    }
    r = client.post("/api/v1/solve", json=p)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["objectives"]["positive_edges"] == 10
    assert body["objectives"]["total_compensation"] == 160
    v = dict(zip(body["objectives"]["vector_order"], body["objectives"]["vector"]))
    assert v["a-shared"] == 0
    assert all(v[f"b{i:02d}"] == 16 for i in range(10))
    edges = {x["id"]: x for x in body["edges"]}
    assert (edges["a-shared"]["min"], edges["a-shared"]["max"]) == (0, 0)
    assert all(
        (edges[f"b{i:02d}"]["min"], edges[f"b{i:02d}"]["max"]) == (16, 16)
        for i in range(10)
    )
    assert all(x["arrival"] == 16 for x in body["leaves"])


def test_api_lexicographic_tie_break_chain():
    p = {
        "nodes": ["R", "A", "B", "L0", "L1"],
        "edges": [
            {"id": "a", "source": "R", "target": "A", "delay": 0, "cap": 4},
            {"id": "b", "source": "A", "target": "B", "delay": 0, "cap": 3},
            {"id": "d", "source": "B", "target": "L1", "delay": 0, "cap": 2},
            {"id": "c", "source": "R", "target": "L0", "delay": 0, "cap": 1},
        ],
        "windows": [
            {"node": "L0", "lo": 0, "hi": 0},
            {"node": "L1", "lo": 6, "hi": 7},
        ],
    }
    r = client.post("/api/v1/solve", json=p)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["objectives"]["positive_edges"] == 2
    assert body["objectives"]["total_compensation"] == 6
    assert body["objectives"]["vector_order"] == ["a", "b", "c", "d"]
    assert body["objectives"]["vector"] == [3, 3, 0, 0]
    edges = {x["id"]: x for x in body["edges"]}
    assert (edges["a"]["min"], edges["a"]["max"]) == (3, 4)
    assert (edges["b"]["min"], edges["b"]["max"]) == (0, 3)
    assert (edges["c"]["min"], edges["c"]["max"]) == (0, 0)
    assert (edges["d"]["min"], edges["d"]["max"]) == (0, 2)
    arrivals = {x["node"]: x["arrival"] for x in body["leaves"]}
    assert arrivals == {"L0": 0, "L1": 6}
