"""折叠 / 展开核心算法。

约定（整数网格，格点即单元格中心，0 基索引）
-------------------------------------------

* 板材为 ``width x height`` 的矩形网格，坐标 ``(x, y)``：
  原点在左下角，x 向右递增，y 向上递增；
  合法范围 ``0 <= x < width``、``0 <= y < height``。
* 一次"对折"把当前板材沿中线折成两半，折叠后其中一半保留在原位（stationary），
  另一半（folded）叠到它上面，板材在该方向上的长度减半。

    - ``up``    ：下半部分向上折，上半部分保留 -> height 必须为偶数
    - ``down``  ：上半部分向下折，下半部分保留 -> height 必须为偶数
    - ``right`` ：左半部分向右折，右半部分保留 -> width  必须为偶数
    - ``left``  ：左半部分保留，右半部分向左折 -> width  必须为偶数

* 打孔作用于最终折叠面，针穿透折叠包内的所有层；展开时每经过一道对折，
  孔位都会跨过折缝"镜像"传播出另一个孔。若某次折叠时沿折叠轴的当前长度
  （左右折叠看 width、上下折叠看 height）为奇数，不存在整数中线，该步骤被拒绝。
* 不同来源传播到同一坐标时合并为一个唯一孔位，并保留各自的传播路径：
  路径条数即覆盖层数 ``coverage``。
"""

from __future__ import annotations

from typing import Any

DIRECTIONS = ("up", "down", "left", "right")

# 每个方向的元数据：
#   axis       折叠作用的坐标轴（沿该轴的长度必须为偶数）
#   stationary 保留在原位的半区（"low" = 低坐标半区，"high" = 高坐标半区）
#   side_low   逆展开时，原低坐标半区的格在折叠包中属于哪一面
#   side_high  逆展开时，原高坐标半区的格在折叠包中属于哪一面
# side 取值：stationary = 折后保留在原位的一面，mirror = 镜像翻折过来的一面
_FOLD_SPEC: dict[str, dict[str, str]] = {
    "up":    {"axis": "y", "stationary": "high", "side_low": "mirror",     "side_high": "stationary"},
    "down":  {"axis": "y", "stationary": "low",  "side_low": "stationary", "side_high": "mirror"},
    "right": {"axis": "x", "stationary": "high", "side_low": "mirror",     "side_high": "stationary"},
    "left":  {"axis": "x", "stationary": "low",  "side_low": "stationary", "side_high": "mirror"},
}


class FoldValidationError(ValueError):
    """输入非法（奇数折叠轴、孔点越界、未知方向等）。"""

    def __init__(self, message: str, *, code: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or {}


def folded_dimensions(width: int, height: int, folds: list[str]) -> tuple[int, int, int]:
    """按给定顺序正序折叠，返回最终折叠包的 ``(width, height, layers)``。

    layers 为折叠包的层数（每折一次翻倍），同时校验奇数折叠轴。
    """
    w, h, layers = width, height, 1
    for step, direction in enumerate(folds, start=1):
        spec = _FOLD_SPEC[direction]
        if spec["axis"] == "y":
            if h % 2 == 1:
                raise FoldValidationError(
                    f"第 {step} 步 '{direction}' 折叠时，折叠轴长度 height={h} 为奇数，"
                    "不存在整数折缝，无法对折",
                    code="odd_fold_axis",
                    details={
                        "step": step,
                        "direction": direction,
                        "axis": "y",
                        "current_length": h,
                    },
                )
            h //= 2
        else:
            if w % 2 == 1:
                raise FoldValidationError(
                    f"第 {step} 步 '{direction}' 折叠时，折叠轴长度 width={w} 为奇数，"
                    "不存在整数折缝，无法对折",
                    code="odd_fold_axis",
                    details={
                        "step": step,
                        "direction": direction,
                        "axis": "x",
                        "current_length": w,
                    },
                )
            w //= 2
        layers *= 2
    return w, h, layers


def _reverse_split(coord: int, half: int, stationary: str) -> tuple[int, int]:
    """单坐标的逆展开：折后坐标 -> (原低半区坐标, 原高半区坐标)。"""
    if stationary == "high":
        # 保留高半区：原低半区是翻折过来的镜像
        return half - 1 - coord, half + coord
    # 保留低半区：原高半区是翻折过来的镜像
    return coord, 2 * half - 1 - coord


def unfold(
    width: int,
    height: int,
    folds: list[str],
    points: list[tuple[int, int]],
    *,
    max_result_holes: int = 200_000,
) -> dict[str, Any]:
    """逆序展开，镜像传播孔位，合并重合坐标并保留各自的传播路径。

    返回结构见 API 层（``holes`` / ``unique_count`` / ``folded`` / ...）。
    """
    fw, fh, layers = folded_dimensions(width, height, folds)
    # 当前工作尺寸（逆展开时会逐步还原回原板尺寸）
    cur_w, cur_h = fw, fh

    # 在最终折叠面上校验打孔点
    for idx, (x, y) in enumerate(points):
        if not (0 <= x < fw and 0 <= y < fh):
            raise FoldValidationError(
                f"打孔点 #{idx + 1} ({x}, {y}) 超出最终折叠面 "
                f"[0, {fw - 1}] x [0, {fh - 1}]（折叠后 {fw}x{fh}）",
                code="point_out_of_bounds",
                details={"index": idx, "point": [x, y], "folded_width": fw, "folded_height": fh},
            )

    # 每个活动孔位携带：当前坐标 + 来源种子序号 + 已展开出的传播路径。
    # 路径按正序折叠时间记录：逆序处理时把每一步前插到最前面。
    active: list[dict[str, Any]] = [
        {"x": x, "y": y, "seed": idx, "path": []} for idx, (x, y) in enumerate(points)
    ]

    for reverse_idx, direction in enumerate(reversed(folds), start=1):
        step = len(folds) - reverse_idx + 1  # 该步在正序折叠中的序号（1 基）
        spec = _FOLD_SPEC[direction]
        axis = spec["axis"]
        half = cur_h if axis == "y" else cur_w

        nxt: list[dict[str, Any]] = []
        for item in active:
            coord = item["y"] if axis == "y" else item["x"]
            low_coord, high_coord = _reverse_split(coord, half, spec["stationary"])

            low_entry = {"step": step, "direction": direction, "side": spec["side_low"]}
            high_entry = {"step": step, "direction": direction, "side": spec["side_high"]}

            if axis == "y":
                nxt.append({**item, "y": low_coord, "path": [low_entry, *item["path"]]})
                nxt.append({**item, "y": high_coord, "path": [high_entry, *item["path"]]})
            else:
                nxt.append({**item, "x": low_coord, "path": [low_entry, *item["path"]]})
                nxt.append({**item, "x": high_coord, "path": [high_entry, *item["path"]]})

        active = nxt
        if axis == "y":
            cur_h = 2 * half
        else:
            cur_w = 2 * half

        if len(active) > max_result_holes:
            raise FoldValidationError(
                f"展开后的孔位数量将超过上限 {max_result_holes}，请减小板材或折叠次数",
                code="too_many_holes",
                details={"limit": max_result_holes},
            )

    # 合并重合坐标，保留各自的传播路径
    merged: dict[tuple[int, int], dict[str, Any]] = {}
    for item in active:
        key = (item["x"], item["y"])
        slot = merged.get(key)
        if slot is None:
            merged[key] = {"sources": [item["seed"]], "paths": [item["path"]]}
        else:
            slot["sources"].append(item["seed"])
            slot["paths"].append(item["path"])

    holes = [
        {
            "x": x,
            "y": y,
            "coverage": len(data["paths"]),
            "source_points": data["sources"],
            "paths": data["paths"],
        }
        for (x, y), data in merged.items()
    ]
    # 稳定排序：先下后上、先左后右（与网格坐标系一致）
    holes.sort(key=lambda h: (h["y"], h["x"]))

    return {
        "board": {"width": width, "height": height},
        "fold_steps": list(folds),
        "folded": {
            "width": fw,
            "height": fh,
            "layers": layers,
        },
        "input_points": [[x, y] for x, y in points],
        "unique_count": len(holes),
        "total_propagations": len(active),
        "holes": holes,
    }
