import time

from app.solver import Edge, Window, build_model, solve


def _binary_tree_55():
    nodes = [f"n{i}" for i in range(55)]
    edges = []
    for i in range(1, 55):
        parent = (i - 1) // 2
        edges.append(Edge(
            id=f"e{i:02d}",
            source=f"n{parent}",
            target=f"n{i}",
            delay=1 + (i % 3),
            cap=4 + (i % 4) * 4,  # 4,8,12,16 mix
        ))
    children = {n: [] for n in nodes}
    for e in edges:
        children[e.source].append(e.target)
    leaves = [n for n in nodes if not children[n]]
    return nodes, edges, leaves


def test_full_size_55_tight_windows():
    nodes, edges, leaves = _binary_tree_55()
    # tight, leaf-specific windows force real multi-stage optimization
    windows = []
    for k, n in enumerate(leaves):
        target = 12 + (k % 7)
        windows.append(Window(n, target, target + 2))
    t0 = time.time()
    r = solve(build_model(nodes, edges, windows))
    dt = time.time() - t0
    assert r["status"] == "feasible", r.get("conflict")
    assert len(r["tree"]["rows"]) == 55
    for leaf in r["leaves"]:
        assert leaf["lo"] <= leaf["arrival"] <= leaf["hi"]
    p = r["objectives"]["positive_edges"]
    t = r["objectives"]["total_compensation"]
    assert p >= 1 and t >= p  # genuine compensation needed
    print(f"\n55-node tight: {dt:.2f}s pos={p} total={t}")
    assert dt < 90


def test_full_size_55_infeasible_conflict():
    # Several leaves demand closed points beyond any reachable arrival
    # (depth ~5, max path compensation < 90); stress the deletion filter on
    # a 54-edge model (one MILP per removal).
    nodes, edges, leaves = _binary_tree_55()
    windows = [Window(n, 400 + 50 * k, 400 + 50 * k) for k, n in enumerate(leaves[:3])]
    windows += [Window(n, 0, 60) for n in leaves[3:]]
    t0 = time.time()
    r = solve(build_model(nodes, edges, windows))
    dt = time.time() - t0
    assert r["status"] == "infeasible"
    assert 1 <= len(r["conflict"]["leaves"]) <= 3
    for c in r["conflict"]["leaves"]:
        assert c["reachable_high"] >= 0
    print(f"\n55-node infeasible: {dt:.2f}s core={[c['node'] for c in r['conflict']['leaves']]}")
    assert dt < 90
