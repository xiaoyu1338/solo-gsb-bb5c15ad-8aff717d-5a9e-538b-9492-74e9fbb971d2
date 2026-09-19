# 包装板材折叠打孔模板展开 API

用 Python + FastAPI 实现：客户端提交整数网格矩形板材、**依次执行**的上下 / 左右对折方向，
以及最终折叠面上的打孔点；服务端**逆序展开**折叠，通过**镜像传播**孔位，
拒绝折叠轴当前长度为奇数的步骤，合并重合坐标但保留各自的传播路径，
返回展开后的唯一孔位、覆盖层数和来源路径。

## 一条命令启动

需要 Docker（含 Compose 插件）：

```bash
docker compose up --build -d
```

容器启动时依赖已随镜像安装完毕，服务直接运行在 **http://localhost:8000** ：

| 地址 | 说明 |
| --- | --- |
| http://localhost:8000 | 服务信息 |
| http://localhost:8000/health | 健康检查 |
| http://localhost:8000/docs | Swagger 交互文档（可直接发请求） |
| http://localhost:8000/openapi.json | OpenAPI 描述 |

停止 / 查看日志：

```bash
docker compose down
docker compose logs -f
```

## 配置

通过 `docker-compose.yml` 的 `environment`（或容器环境变量）配置，均有默认值，无需配置即可运行：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MAX_RESULT_HOLES` | `200000` | 展开后孔位（镜像传播路径）总数上限，超过返回 `422` |
| `MAX_BOARD_SIDE` | `1000000` | 板材单边最大格数 |

宿主机端口在 `docker-compose.yml` 的 `ports` 修改，例如 `"18000:8000"`。

## 折叠与坐标约定

- 板材为 `width × height` 的**整数网格**，坐标 `(x, y)` 为 0 基格点索引：
  原点在**左下角**，x 向右递增，y 向上递增。
- `folds` 按数组顺序正序执行，每次对折使对应方向长度减半：

  | 方向 | 含义 | 保留在原位的半区 | 要求 |
  | --- | --- | --- | --- |
  | `up` | 下半部分向上折 | 上半区（高 y） | 当前 `height` 为偶数 |
  | `down` | 上半部分向下折 | 下半区（低 y） | 当前 `height` 为偶数 |
  | `left` | 右半部分向左折 | 左半区（低 x） | 当前 `width` 为偶数 |
  | `right` | 左半部分向右折 | 右半区（高 x） | 当前 `width` 为偶数 |

- 某一步折叠轴长度（左右折叠看当前 `width`，上下折叠看当前 `height`）为**奇数**时
  不存在整数折缝，该请求被拒绝，返回 `422` 与出错步骤。
- `points` 是**最终折叠面**上的打孔点（针穿透折叠包全部层）。
- 逆序展开时，每个孔在每道对折处跨过折缝镜像出另一个孔；传播到同一坐标的孔合并为
  一个唯一孔位，但保留各自的传播路径，路径条数即**覆盖层数** `coverage`。

## 请求 / 返回示例

请求：

```bash
curl -s http://localhost:8000/unfold \
  -H 'Content-Type: application/json' \
  -d '{
        "width": 4,
        "height": 4,
        "folds": ["up", "left"],
        "points": [{"x": 0, "y": 0}]
      }'
```

4×4 板材先 `up`（4×4 → 4×2）再 `left`（4×2 → 2×2），最终折叠面为 2×2，
在 `(0,0)` 打孔。逆展开时：`up` 的折后 y=0 镜像回原板 y∈{1,2}（分别属于镜像/保留半区），
`left` 的折后 x=0 镜像回原板 x∈{0,3}，共 4 个孔：

```json
{
  "board": { "width": 4, "height": 4 },
  "fold_steps": ["up", "left"],
  "folded": { "width": 2, "height": 2, "layers": 4 },
  "input_points": [[0, 0]],
  "unique_count": 4,
  "total_propagations": 4,
  "holes": [
    {
      "x": 0, "y": 1,
      "coverage": 1,
      "source_points": [0],
      "paths": [[
        { "step": 1, "direction": "up",   "side": "mirror" },
        { "step": 2, "direction": "left", "side": "stationary" }
      ]]
    },
    {
      "x": 3, "y": 1,
      "coverage": 1,
      "source_points": [0],
      "paths": [[
        { "step": 1, "direction": "up",   "side": "mirror" },
        { "step": 2, "direction": "left", "side": "mirror" }
      ]]
    },
    {
      "x": 0, "y": 2,
      "coverage": 1,
      "source_points": [0],
      "paths": [[
        { "step": 1, "direction": "up",   "side": "stationary" },
        { "step": 2, "direction": "left", "side": "stationary" }
      ]]
    },
    {
      "x": 3, "y": 2,
      "coverage": 1,
      "source_points": [0],
      "paths": [[
        { "step": 1, "direction": "up",   "side": "stationary" },
        { "step": 2, "direction": "left", "side": "mirror" }
      ]]
    }
  ]
}
```

若多个来源（包括重复提交的打孔点）传播到同一坐标，该孔只出现一次，
但 `coverage` 与 `paths` 条数等于重合的路径数，例如对 2×2 板材 `up` 折后
在 `(0,0)` 提交两个相同打孔点：每个孔 `"coverage": 2, "source_points": [0, 1]`，
`paths` 含两条独立路径。

字段说明：

- `folded`：最终折叠面尺寸 `width × height` 与层数 `layers`（每道对折翻倍）。
- `holes[].x / y`：展开后在原板材网格上的唯一孔位坐标。
- `holes[].coverage`：覆盖层数 = 在该坐标重合的独立传播路径条数。
- `holes[].source_points`：贡献该孔的原始打孔点序号（0 基，对应 `points`）。
- `holes[].paths`：各自的传播路径，按**正序折叠步骤**排列；
  每项标注该步 `step`、`direction`，以及此孔在该步来自保留在原位的半区
  （`stationary`）还是镜像翻折的半区（`mirror`）。

奇数折叠轴被拒绝的示例（4×3 直接 `up`，height=3）：

```json
{
  "error": {
    "code": "odd_fold_axis",
    "message": "第 1 步 'up' 折叠时，折叠轴长度 height=3 为奇数，不存在整数折缝，无法对折",
    "details": { "step": 1, "direction": "up", "axis": "y", "current_length": 3 }
  }
}
```

## 本地开发（不用 Docker）

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

运行测试（纯标准库，无需安装 pytest）：

```bash
python -m tests.test_folding
```

## 项目结构

```
.
├── app/
│   ├── __init__.py
│   ├── folding.py      # 折叠/逆展开核心算法（无框架依赖）
│   └── main.py         # FastAPI 路由、模型与错误处理
├── tests/
│   └── test_folding.py # 算法用例（可直接 python 运行）
├── Dockerfile          # 构建镜像，构建时装依赖、启动即服务
├── docker-compose.yml  # 一条命令：docker compose up --build -d
└── requirements.txt
```
