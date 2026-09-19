"""包装板材折叠打孔模板展开 API。

启动：uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from .folding import DIRECTIONS, FoldValidationError, unfold

Direction = Literal["up", "down", "left", "right"]

MAX_RESULT_HOLES = int(os.getenv("MAX_RESULT_HOLES", "200000"))
MAX_BOARD_SIDE = int(os.getenv("MAX_BOARD_SIDE", "1000000"))


class PointIn(BaseModel):
    x: int = Field(..., ge=0, description="打孔点在最终折叠面上的 x（0 基，向右递增）")
    y: int = Field(..., ge=0, description="打孔点在最终折叠面上的 y（0 基，向上递增）")


class UnfoldRequest(BaseModel):
    width: int = Field(..., ge=1, le=MAX_BOARD_SIDE, description="板材网格宽度（格数）")
    height: int = Field(..., ge=1, le=MAX_BOARD_SIDE, description="板材网格高度（格数）")
    folds: list[Direction] = Field(
        default_factory=list,
        description="依次执行的对折方向：up/down（上下折）、left/right（左右折）",
    )
    points: list[PointIn] = Field(
        ..., min_length=1, description="最终折叠面上的打孔点（针穿透折叠包全部层）"
    )

    @field_validator("points")
    @classmethod
    def _unique_points_not_required_but_typed(cls, v: list[PointIn]) -> list[PointIn]:
        if len(v) > 100_000:
            raise ValueError("打孔点数量过多（上限 100000）")
        return v


class PathEntry(BaseModel):
    step: int = Field(..., description="正序折叠中的步骤序号（1 基）")
    direction: Direction
    side: Literal["stationary", "mirror"] = Field(
        ..., description="该步中此孔来自保留在原位的半区还是镜像翻折的半区"
    )


class Hole(BaseModel):
    x: int
    y: int
    coverage: int = Field(..., description="覆盖层数：在该坐标重合的独立传播路径条数")
    source_points: list[int] = Field(..., description="贡献该孔的原始打孔点序号（0 基）")
    paths: list[list[PathEntry]] = Field(
        ..., description="各自的传播路径（按正序折叠步骤排列），与 coverage 等长"
    )


class FoldedInfo(BaseModel):
    width: int
    height: int
    layers: int = Field(..., description="最终折叠包层数（每道对折翻倍）")


class BoardInfo(BaseModel):
    width: int
    height: int


class UnfoldResponse(BaseModel):
    board: BoardInfo
    fold_steps: list[Direction]
    folded: FoldedInfo
    input_points: list[list[int]]
    unique_count: int = Field(..., description="展开后唯一孔位数量（重合已合并）")
    total_propagations: int = Field(..., description="镜像传播产生的路径总数（合并前）")
    holes: list[Hole]


app = FastAPI(
    title="包装板材折叠打孔模板展开 API",
    description=(
        "提交整数网格矩形板材、依次执行的 up/down/left/right 对折方向和最终折叠面上的"
        "打孔点；服务端逆序展开并通过镜像传播孔位，返回展开后的唯一孔位、覆盖层数与"
        "来源传播路径。折叠轴长度为奇数的步骤会被拒绝（422）。"
    ),
    version="1.0.0",
)


@app.exception_handler(FoldValidationError)
async def _fold_validation_handler(_request: Request, exc: FoldValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": str(exc), "details": exc.details}},
    )


@app.get("/", tags=["meta"])
async def root() -> dict[str, str]:
    return {
        "service": "board-fold-unfold",
        "docs": "/docs",
        "openapi": "/openapi.json",
        "health": "/health",
        "unfold_endpoint": "POST /unfold",
    }


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/unfold", response_model=UnfoldResponse, tags=["unfold"])
async def do_unfold(req: UnfoldRequest) -> UnfoldResponse:
    result = unfold(
        width=req.width,
        height=req.height,
        folds=list(req.folds),
        points=[(p.x, p.y) for p in req.points],
        max_result_holes=MAX_RESULT_HOLES,
    )
    return UnfoldResponse.model_validate(result)
