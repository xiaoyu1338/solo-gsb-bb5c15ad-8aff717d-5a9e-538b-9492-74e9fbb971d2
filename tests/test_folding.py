"""算法与 API 的验证用例。

直接运行：python -m tests.test_folding （不依赖 pytest）
或：       pytest -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.folding import DIRECTIONS, FoldValidationError, folded_dimensions, unfold  # noqa: E402


def _hole_map(result):
    return {(h["x"], h["y"]): h for h in result["holes"]}


def test_two_by_two_up_then_left():
    # 4x4 板材：up（下半折上去，保留高半区）后 left（右半折到左边，保留低半区）
    # 最终折叠面 2x2，在 (0,0) 打孔
    r = unfold(4, 4, ["up", "left"], [(0, 0)])
    assert r["folded"] == {"width": 2, "height": 2, "layers": 4}
    assert r["unique_count"] == 4
    assert r["total_propagations"] == 4
    # up 逆展开 y: 0 -> {1(镜像), 2(保留)}；left 逆展开 x: 0 -> {0(保留), 3(镜像)}
    assert set(_hole_map(r)) == {(0, 1), (3, 1), (0, 2), (3, 2)}
    h = _hole_map(r)[(0, 1)]
    assert h["coverage"] == 1
    # 路径按正序折叠步骤排列
    assert [(e["step"], e["direction"], e["side"]) for e in h["paths"][0]] == [
        (1, "up", "mirror"),       # up 时来自原下半区（翻折）
        (2, "left", "stationary"), # left 时来自原左半区（保留）
    ]
    # y=1 来自 up 的镜像（原下半区），x=3 来自 left 的镜像（原右半区）
    assert [(e["step"], e["side"]) for e in _hole_map(r)[(3, 1)]["paths"][0]] == [
        (1, "mirror"),
        (2, "mirror"),
    ]
    assert [(e["step"], e["side"]) for e in _hole_map(r)[(3, 2)]["paths"][0]] == [
        (1, "stationary"),
        (2, "mirror"),
    ]


def test_down_and_right_directions():
    # down 保留下半区；right 保留右半区
    r = unfold(2, 2, ["down", "right"], [(0, 0)])
    assert set(_hole_map(r)) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    h11 = _hole_map(r)[(1, 1)]
    assert [(e["direction"], e["side"]) for e in h11["paths"][0]] == [
        ("down", "mirror"),    # y=1 是 down 时镜像翻折的上半区
        ("right", "stationary"),  # x=1 是 right 时保留在原位的右半区
    ]


def test_odd_axis_rejected():
    # 4x3：第一次 up 时 height=3 为奇数 -> 拒绝
    try:
        unfold(4, 3, ["up"], [(0, 0)])
    except FoldValidationError as e:
        assert e.code == "odd_fold_axis"
        assert e.details["step"] == 1
        assert e.details["axis"] == "y"
        assert e.details["current_length"] == 3
    else:
        raise AssertionError("expected odd_fold_axis")

    # 先 left 合法（width=4 -> 2），再 left 时 width=2 合法；构造 width 先偶后奇：
    # width=6 -> 3（第一次 left 合法），第二次 left 时 width=3 奇数 -> 拒绝
    try:
        unfold(6, 2, ["left", "left"], [(0, 0)])
    except FoldValidationError as e:
        assert e.code == "odd_fold_axis"
        assert e.details["step"] == 2
        assert e.details["axis"] == "x"
        assert e.details["current_length"] == 3
    else:
        raise AssertionError("expected odd_fold_axis at step 2")


def test_point_out_of_bounds():
    try:
        unfold(4, 4, ["up", "left"], [(2, 0)])  # 折叠面只有 2x2
    except FoldValidationError as e:
        assert e.code == "point_out_of_bounds"
    else:
        raise AssertionError("expected point_out_of_bounds")


def test_coverage_full_board_uniform_layers():
    # 每折一次覆盖翻倍；4 道折叠后单个孔覆盖 16 个唯一位置，coverage 全为 1
    r = unfold(4, 4, ["up", "down", "left", "right"], [(0, 0)])
    assert r["folded"]["layers"] == 16
    assert r["unique_count"] == 16
    assert all(h["coverage"] == 1 for h in r["holes"])
    # 覆盖满整板（路径集合构成原板材的一个划分）
    assert set(_hole_map(r)) == {(x, y) for x in range(4) for y in range(4)}


def test_coincident_points_merge_and_keep_paths():
    # 相同打孔点提交两次：坐标合并，coverage=2，保留两条来源路径
    r = unfold(2, 2, ["up"], [(0, 0), (0, 0)])
    assert r["unique_count"] == 2
    assert r["total_propagations"] == 4
    for h in r["holes"]:
        assert h["coverage"] == 2
        assert h["source_points"] == [0, 1]
        assert len(h["paths"]) == 2


def test_no_folds():
    r = unfold(3, 2, [], [(1, 1)])
    assert r["folded"] == {"width": 3, "height": 2, "layers": 1}
    assert set(_hole_map(r)) == {(1, 1)}
    assert _hole_map(r)[(1, 1)]["paths"] == [[]]


def test_dimensions_helper():
    # (8,6) -> up(8,3) -> left(4,3) -> left(2,3)，层数翻倍三次
    assert folded_dimensions(8, 6, ["up", "left", "left"]) == (2, 3, 8)


def test_directions_constant():
    assert DIRECTIONS == ("up", "down", "left", "right")


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
