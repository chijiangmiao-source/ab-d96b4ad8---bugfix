# 低温探测器时钟树补偿审计

时钟沿经树状布线送往采样端。**共享上游补偿会同时移动整片子树**，逐叶校准
可能把其他叶端推出窗口。本系统接收一批时钟树（2–55 个唯一 ASCII 节点、一棵
根向有向树、非负整数固有延迟、唯一边标识、0–16 的整数可加上限，至少两个叶端
给出整数到达闭区间），求分级最优加量方案，并以树表展示边补偿、叶端到达值与
剩余裕量。

## 目录

```
backend/          FastAPI + scipy/HiGHS MILP 求解后端（独立 Dockerfile）
frontend/         React + Vite + TypeScript 前端（独立 Dockerfile，nginx 反代）
verify/           一次性校验服务（Dockerfile + 编排脚本）
docker-compose.yml
```

## 运行

```bash
cp .env.example .env        # 可选：调整 API_PORT / WEB_PORT
docker compose build
docker compose up -d api web
```

- 页面：http://localhost:${WEB_PORT:-8080}
- API 健康检查：http://localhost:8000/health
- 端口通过 `.env` 的 `API_PORT` / `WEB_PORT` 可配置（compose 默认 8000 / 8080）。

## 求解规则（加量向量按边标识 ASCII 排序）

1. **第一级**：最小化加量为正的边数（优先使用共享上游边，一次移动整片子树）；
2. **第二级**：在第一级最优解中最小化总加量；
3. **第三级**：取字典序最小加量向量；
4. 对每条可调边，报告其在**全部前两级同优解**中的最小/最大加量；
5. 无解时，用删除过滤求一个包含意义下最小的冲突叶端子集，列出这些叶端及其
   各自可达区间（零加量…根路径满加量）。

## 无解情形

返回 `status: "infeasible"` 与 `conflict.leaves`（最小冲突核），给出每个冲突
叶端的要求闭区间和可达闭区间；页面同时展示冲突面板并**保留输入**。

## 页面行为

- 真实调用 `POST /api/v1/solve`（经 nginx 同源自 `/api` 代理到后端）；
- 树表按深度缩进显示：入边标识、固有延迟、可加上限、采用加量、到达值、
  要求窗口、剩余裕量（到最近窗口边界的距离及上下界余量）；
- 校验失败（422）或请求失败后，输入区内容原样保留（并持久化到 localStorage）。

## verify 一次性服务

```bash
docker compose build verify
docker compose up verify          # 退出码 0 = 全部通过
echo $?
```

`verify/run.sh` 依次执行并以退出码报告结论：

1. 后端单元测试（pytest，含目标层级、同优范围、字典序、冲突核、HTTP 用例）；
2. 前端生产构建（vite build；另用 esbuild 把同一份 App 源码打成 jsdom 可执行
   的 IIFE，不改变交付产物）；
3. HTTP 冒烟（API `/health`、Web 首页、nginx 代理的 `/health`、静态资源、meta）；
4. 对**真实 API** 用三类样例核对：共享上游补偿、同优边范围、叶端窗口冲突；
5. 对**真实构建页面**驱动 React UI（加载样例→提交→真实请求→断言渲染的树表/
   边表/叶端表/冲突面板），并核对 422 与 JSON 错误后输入保留。

## API 摘要

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 常驻服务健康检查 |
| GET | `/api/v1/meta` | 批次约束与目标层级说明 |
| POST | `/api/v1/solve` | 提交一个时钟树批次 |

请求体示例：

```json
{
  "nodes": ["R", "A", "L1", "L2"],
  "edges": [
    {"id": "e0", "source": "R", "target": "A", "delay": 10, "cap": 16},
    {"id": "e1", "source": "A", "target": "L1", "delay": 0, "cap": 16},
    {"id": "e2", "source": "A", "target": "L2", "delay": 0, "cap": 16}
  ],
  "windows": [
    {"node": "L1", "lo": 14, "hi": 14},
    {"node": "L2", "lo": 14, "hi": 20}
  ]
}
```
