"""FastAPI service for the cryogenic clock-tree compensation audit."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from .solver import CAP_MAX, Edge, SolverError, Window, build_model, solve

logger = logging.getLogger("clocktree")

app = FastAPI(
    title="低温探测器时钟树补偿审计 API",
    version="1.0.0",
    description="提交时钟树批次，返回分级最优边加量、叶端到达值、剩余裕量与冲突分析。",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class EdgeIn(BaseModel):
    id: str = Field(..., description="边唯一标识 (ASCII)")
    source: str
    target: str
    delay: int = Field(..., ge=0, description="非负整数固有延迟")
    cap: int = Field(..., ge=0, le=CAP_MAX, description="0..16 整数可加上限")


class WindowIn(BaseModel):
    node: str
    lo: int
    hi: int

    @field_validator("lo", "hi")
    @classmethod
    def _ints(cls, v):
        if not isinstance(v, int):
            raise ValueError("区间端点须为整数")
        return v


class BatchIn(BaseModel):
    nodes: list[str]
    edges: list[EdgeIn]
    windows: list[WindowIn]


@app.get("/health")
def health():
    return {"status": "ok", "service": "clocktree-audit", "cap_max": CAP_MAX}


@app.get("/api/v1/meta")
def meta():
    return {
        "node_count": {"min": 2, "max": 55},
        "cap_max": CAP_MAX,
        "min_windows": 2,
        "objectives": [
            "minimize_positive_edges",
            "minimize_total_compensation",
            "lexicographically_smallest_vector",
        ],
    }


@app.post("/api/v1/solve")
def solve_batch(batch: BatchIn):
    edges = [
        Edge(
            id=e.id,
            source=e.source,
            target=e.target,
            delay=e.delay,
            cap=e.cap,
        )
        for e in batch.edges
    ]
    windows = [Window(node=w.node, lo=w.lo, hi=w.hi) for w in batch.windows]
    model = build_model(batch.nodes, edges, windows)
    return solve(model)


@app.exception_handler(SolverError)
def solver_error_handler(_request, exc: SolverError):
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=422,
        content={"detail": str(exc), "type": "validation_error"},
    )
