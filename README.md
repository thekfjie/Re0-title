# 日文标题自动排版生成器 · Title Lab

根据 82 张参考截图研究并实现的第一版：字形级字号与混排、光学字距、禁则断行、多家族搜索、可解释评分和 4–8 候选。输入日文与用户自己的 TTF/OTF，输出可下载 PNG、轮廓 SVG 和可复现参数 JSON。

A 不依赖任何大模型。B 用语义 JSON 调用完全相同的布局/字体/渲染引擎。完整 Benchmark 有 20 条标题 × 2 方案 × 6 候选。B 当前为会话模型的冻结计划，在线 API 尚未实测，不能声称比 A 好。

## 本机启动

需要 Python 3.12、Node 24、系统 Cairo/FreeType。Ubuntu 可安装 `libcairo2 libfreetype6`。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
npm run build
OPENBLAS_NUM_THREADS=1 .venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
```

打开 `http://localhost:8000`，上传自己的字体，生成并下载。字体未上传前只显示研究示例；不使用服务器系统字体替代用户字体。

```bash
docker compose up --build
```

生产 HTTPS 请设 `SECURE_COOKIES=1`。复制 `.env.example` 为不入库的 `.env` 后配置服务端 `OPENAI_API_KEY` 可启用 live B；本机 uvicorn 使用环境变量或 `--env-file`（需安装 python-dotenv）。不把 Key 放入网页。

## 目录

| 路径 | 内容 |
|---|---|
| references | 82 条结构化 dataset；原始截图仅留本地 |
| analysis | 像素测量、颜色位置、布局统计、字体对照、细标 |
| engine | Sudachi、FontProvider、HarfBuzz/FreeType、约束、SVG |
| baseline | 无模型生成入口、三种启发式 |
| llm | 严格语义规划、可选 Vision Critic 实验适配器 |
| experiments | 固定测试集、冻结计划、240 张结果、消融脚本 |
| web | FastAPI、隔离任务进程与浏览器端 |
| config | 家族/字号/颜色/权重/搜索参数 |
| docs | 研究、规则、算法、B、对比、字体安全与部署 |

## 研究复现

没有在仓库提供任何字体。字体实验脚本按官方来源下载 OFL 研究字体到不入库的 `.research-fonts`，商业字体绝不下载或提交。

```bash
.venv/bin/python analysis/run_font_experiments.py
.venv/bin/python analysis/measure_references.py
.venv/bin/python analysis/annotate.py
.venv/bin/python experiments/create_session_plans.py
.venv/bin/python analysis/fit_layout_statistics.py
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/benchmark.py
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/ablations.py
```

原截图在 `references/originals`，因上传原图权限不明确未推入远端代码库；用户提供 ZIP 解包至该目录即可。首次启动不需要截图，因为分析与 Benchmark 已保存。计划 JSON 已冻结，`create_session_plans.py` 只复写同一计划，并不调用在线模型。

在线 B 实测：

```bash
OPENAI_API_KEY=... PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/benchmark.py --live-llm --out experiments/live-benchmark
```

可用 `--kanji /path/a.ttf --kana /path/b.otf --seed 42` 使用自己的字体。不要将商业字体文件放入仓库或 image。

## 验证

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q
npm test
```

渲染集成测试需要本地实验字体，缺失时明确 skip；文本/严格计划测试不依赖商业字体。实际浏览器 QA 包含字体上传、实时候选、PNG/SVG 下载、离线 B、移动布局与错误输入。配置、字体 hash 与随机 seed 写入每个结果。

## 交付边界

已部署浏览器版，完整 Python 服务可直接部署。初版未验证实时 LLM/VLM 的质量、成本和 API 延迟；未完成全部 82 张逐字字号拟合；不支持自动复刻发光、倒影与破损纹理。细字 annotation 用 ink bbox 而不是字体身份或字号真值。规则能捕捉粗粒度设计体系，尚不能证明任意标题与参考等价。

详见 `docs/reference_analysis.md`、`typography_rules.md`、`algorithm_baseline.md`、`llm_pipeline.md`、`comparison.md`。
