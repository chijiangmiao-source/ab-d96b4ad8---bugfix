#!/usr/bin/env python3
"""Verify the REAL api with the three canonical scenarios:

  A. shared upstream compensation (one edge moves a whole subtree)
  B. per-edge ranges across stage 1&2 co-optimal solutions + lexicographic tie
  C. leaf window conflict caused by shared-upstream coupling
"""

from __future__ import annotations

import os
import sys

import httpx

API = os.environ.get("API_URL", "http://api:8000").rstrip("/")
FAILURES: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail and not cond else ''}")
    if not cond:
        FAILURES.append(f"{name}: {detail}")


def post(batch: dict) -> dict:
    r = httpx.post(f"{API}/api/v1/solve", json=batch, timeout=30)
    r.raise_for_status()
    return r.json()


def vec_by_id(result: dict) -> dict[str, int]:
    return dict(zip(result["objectives"]["vector_order"], result["objectives"]["vector"]))


def scenario_shared() -> None:
    print("A. 共享上游补偿")
    r = post({
        "nodes": ["R", "A", "L1", "L2"],
        "edges": [
            {"id": "e0", "source": "R", "target": "A", "delay": 10, "cap": 16},
            {"id": "e1", "source": "A", "target": "L1", "delay": 0, "cap": 16},
            {"id": "e2", "source": "A", "target": "L2", "delay": 0, "cap": 16},
        ],
        "windows": [
            {"node": "L1", "lo": 14, "hi": 14},
            {"node": "L2", "lo": 14, "hi": 20},
        ],
    })
    check("status=feasible", r["status"] == "feasible",
          (r.get("conflict") or {}).get("message", ""))
    if r["status"] != "feasible":
        return
    v = vec_by_id(r)
    check("仅一条正边 e0=4（整片子树一起移动）", v == {"e0": 4, "e1": 0, "e2": 0}, str(v))
    check("正向边数=1", r["objectives"]["positive_edges"] == 1)
    check("总加量=4", r["objectives"]["total_compensation"] == 4)
    check("向量按边标识 ASCII 排序", r["objectives"]["vector_order"] == ["e0", "e1", "e2"])
    arrivals = {x["node"]: x["arrival"] for x in r["leaves"]}
    check("两叶端到达值均为 14", arrivals == {"L1": 14, "L2": 14}, str(arrivals))
    by_leaf = {x["node"]: x for x in r["leaves"]}
    # L1 is a closed point [14,14]: margin 0 on both sides.
    check("L1 闭点窗口剩余裕量 0（下界/上界均为 0）",
          (by_leaf["L1"]["margin"], by_leaf["L1"]["margin_low"],
           by_leaf["L1"]["margin_high"]) == (0, 0, 0))
    # L2 window [14,20]: sits on the lower bound, upper-side slack 6.
    check("L2 剩余裕量 0（贴下界），上界侧余量 6",
          (by_leaf["L2"]["margin"], by_leaf["L2"]["margin_low"],
           by_leaf["L2"]["margin_high"]) == (0, 0, 6),
          str(by_leaf["L2"]))
    tree = {x["node"]: x for x in r["tree"]["rows"]}
    check("树表含边补偿/到达/裕量",
          tree["A"]["compensation"] == 4 and tree["L1"]["arrival"] == 14
          and tree["L1"]["margin"] == 0)


def scenario_ranges() -> None:
    print("B. 前两级同优解中的边范围与字典序")
    r = post({
        "nodes": ["R", "A", "B", "L1", "L2"],
        "edges": [
            {"id": "s", "source": "R", "target": "A", "delay": 0, "cap": 16},
            {"id": "t", "source": "A", "target": "B", "delay": 0, "cap": 16},
            {"id": "u", "source": "B", "target": "L1", "delay": 0, "cap": 16},
            {"id": "v", "source": "A", "target": "L2", "delay": 0, "cap": 16},
        ],
        "windows": [
            {"node": "L1", "lo": 4, "hi": 4},
            {"node": "L2", "lo": 2, "hi": 2},
        ],
    })
    check("status=feasible", r["status"] == "feasible")
    if r["status"] != "feasible":
        return
    v = vec_by_id(r)
    check("正向边数=2", r["objectives"]["positive_edges"] == 2)
    check("总加量=4", r["objectives"]["total_compensation"] == 4)
    check("字典序最小向量 s=2,t=0,u=2,v=0", v == {"s": 2, "t": 0, "u": 2, "v": 0}, str(v))
    e = {x["id"]: x for x in r["edges"]}
    check("共享边 s 在同优解中固定为 2", (e["s"]["min"], e["s"]["max"]) == (2, 2))
    check("t 在同优解中可取 0..2（同优边范围）", (e["t"]["min"], e["t"]["max"]) == (0, 2),
          f"({e['t']['min']},{e['t']['max']})")
    check("u 在同优解中可取 0..2", (e["u"]["min"], e["u"]["max"]) == (0, 2))
    check("v 在同优解中固定为 0", (e["v"]["min"], e["v"]["max"]) == (0, 0))
    check("采用列与字典序向量一致 t=0,u=2", e["t"]["chosen"] == 0 and e["u"]["chosen"] == 2)


def scenario_conflict() -> None:
    print("C. 叶端窗口冲突（共享上游边强制同步）")
    r = post({
        "nodes": ["R", "A", "L1", "L2"],
        "edges": [
            {"id": "e0", "source": "R", "target": "A", "delay": 0, "cap": 16},
            {"id": "e1", "source": "A", "target": "L1", "delay": 0, "cap": 0},
            {"id": "e2", "source": "A", "target": "L2", "delay": 0, "cap": 0},
        ],
        "windows": [
            {"node": "L1", "lo": 2, "hi": 2},
            {"node": "L2", "lo": 8, "hi": 8},
        ],
    })
    check("status=infeasible", r["status"] == "infeasible")
    if r["status"] != "infeasible":
        return
    c = r["conflict"]
    names = {x["node"] for x in c["leaves"]}
    check("最小冲突核恰为 {L1,L2}", names == {"L1", "L2"}, str(names))
    by = {x["node"]: x for x in c["leaves"]}
    check("L1 报告要求区间 [2,2] 与可达区间 [0,16]",
          (by["L1"]["lo"], by["L1"]["hi"], by["L1"]["reachable_low"],
           by["L1"]["reachable_high"]) == (2, 2, 0, 16))
    check("L2 报告要求区间 [8,8] 与可达区间 [0,16]",
          (by["L2"]["lo"], by["L2"]["hi"], by["L2"]["reachable_low"],
           by["L2"]["reachable_high"]) == (8, 8, 0, 16))
    check("附带人类可读冲突说明", bool(c["message"]))


def scenario_validation() -> None:
    print("D. 校验失败路径 (422)")
    bad = {
        "nodes": ["R", "A"],
        "edges": [{"id": "e1", "source": "R", "target": "A", "delay": -1, "cap": 16}],
        "windows": [],
    }
    r = httpx.post(f"{API}/api/v1/solve", json=bad, timeout=30)
    check("负延迟/缺窗口返回 422", r.status_code == 422, f"got {r.status_code}")


def main() -> int:
    print(f"核对真实 API: {API}")
    h = httpx.get(f"{API}/health", timeout=10)
    h.raise_for_status()
    check("健康检查 200 ok", h.json().get("status") == "ok", h.text)
    scenario_shared()
    scenario_ranges()
    scenario_conflict()
    scenario_validation()
    print(f"\nAPI 核对: {len(FAILURES)} 项失败")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
