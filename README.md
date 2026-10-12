# 日文标题自动排版生成器 · Title Lab

根据 82 张参考截图研究并实现的第一版：字形级字号与混排、光学字距、禁则断行、多家族搜索、可解释评分和 4–8 候选。输入日文或中文，选择预置字体或用户自己的 TTF/OTF，输出可下载 PNG、轮廓 SVG 和可复现参数 JSON。

新增独立的 [16 张参考最小闭环](docs/minimal_reference_loop.md)：Title → Visual Groups → Glyphs 标注、结构迁移、留一 pairwise ranker、退火搜索与 Top-6。已实际生成四阶段共 480 张对照，难例留一正确率 91.4%，但生成候选排序与着色位置仍有明确失败，未替换默认引擎。运行 `.venv/bin/python -m experiments.minimal_reference_loop --ranker --benchmark --diagnose`；查看 `experiments/minimal-reference-loop/index.html`。

A 不依赖任何大模型。B 用语义 JSON 调用完全相同的布局/字体/渲染引擎。完整 Benchmark 有 20 条标题 × 2 方案 × 6 候选。B 已接入兼容服务并完成 20 条真实调用；仍不能声称比 A 好。

“参考标题 · 82”提供全部参考原文；“参考对照”逐条展示原图与 A 的六张生成图，可搜索、筛选偏差、切换原截图并下载。全参考共 492 张，默认断行匹配 56/81，六候选覆盖 74/81，默认色位平均重合 31.5%。这些是开发样本诊断，不是审美胜率；详细偏差见 [full_reference_comparison.md](docs/full_reference_comparison.md)。

## 本机启动

需要 Python 3.12、Node 24、系统 Cairo/FreeType。Ubuntu 可安装 `libcairo2 libfreetype6`。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
npm run build:browser
OPENBLAS_NUM_THREADS=1 .venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
```

打开 `http://localhost:8000` 即会使用预置字体生成 6 张。可在 8 组开放字体中分别选择汉字/假名字体，也可上传自己的 TTF/OTF。

```bash
docker compose up --build
```

生产 HTTPS 请设 `SECURE_COOKIES=1`。复制 `.env.example` 为不入库的 `.env` 后配置服务端 `LLM_API_KEY`、`LLM_BASE_URL` 和 `LLM_MODEL` 可启用兼容服务的 live B；本机 uvicorn 使用环境变量或 `--env-file`（需安装 python-dotenv）。不把 Key 放入网页。

## 目录

| 路径 | 内容 |
|---|---|
| references | 82 条结构化 dataset；原始截图仅留本地 |
| analysis | 像素测量、颜色位置、布局统计、字体对照、细标 |
| engine | Sudachi、FontProvider、HarfBuzz/FreeType、约束、SVG |
| baseline | 无模型生成入口、三种启发式 |
| llm | 严格语义规划、可选 Vision Critic 实验适配器 |
| experiments | A/B 240 张、全参考 A 492 张、计划、对照与消融脚本 |
| web | FastAPI、隔离任务进程与浏览器端 |
| config | 家族/字号/颜色/权重/搜索参数 |
| docs | 研究、规则、算法、B、对比、字体安全与部署 |

## 研究复现

研究版按追加授权预置 8 组 OFL 字体，完整来源/许可证见 `assets/open-fonts/catalog.json`。商业字体绝不下载、提交或打包。原始研究脚本仍可将实验字体下载到不入库的 `.research-fonts`。

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

全部参考与 A 的对照已保存标题裁剪、完整画布截图裁剪和六个 PNG/SVG，无需本地原图即可查看。重新生成裁剪与全参考诊断需原 JPG：

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python -m experiments.reference_comparison
```

参数在 `config/reference_evaluation.yaml`；结果保存字体 hash、配置 hash、默认顺序及逐指标比较。“按参考筛选候选”是事后读取标注的诊断工具，不是默认排名。Python 对照用 Sudachi，在线重生成用 Kuromoji，两端不承诺逐像素一致。

在线 B 实测：

```bash
LLM_API_KEY=... LLM_BASE_URL=https://your-provider/v1 LLM_MODEL=your-model LLM_API_STYLE=chat_completions PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/benchmark.py --live-llm --out experiments/live-benchmark
```

可用 `--kanji /path/a.ttf --kana /path/b.otf --seed 42` 使用自己的字体。不要将商业字体文件放入仓库或 image。

## 验证

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q
npm test
```

渲染集成测试使用仓库内的 OFL 基准字体；文本/严格计划测试不依赖商业字体。实际浏览器 QA 包含字体上传、实时候选、PNG/SVG 下载、离线 B、移动布局与错误输入。配置、字体 hash 与随机 seed 写入每个结果。

## 交付边界

构图研究增加了 [视觉语法修订](docs/visual_grammar_revision.md) 与 `/composition-study.html` 对照页：82 张参考和 4 条新文本，两版共 1,032 个候选。实验无需剧情或角色输入；本轮色位重合退步，未替换正式默认引擎。运行 `.venv/bin/python -m experiments.composition_study --all` 可复现。

已部署浏览器版，完整 Python 服务可直接部署。实时 LLM 已验证调用、usage 与 API 延迟，但尚无独立审美结论；VLM 三条实验有一次超时，默认关闭，API 金额因缺少单价未测；未完成全部 82 张逐字字号拟合；不支持自动复刻发光、倒影与破损纹理。细字 annotation 用 ink bbox 而不是字体身份或字号真值。规则能捕捉粗粒度设计体系，尚不能证明任意标题与参考等价。

详见 `docs/reference_analysis.md`、`typography_rules.md`、`algorithm_baseline.md`、`llm_pipeline.md`、`comparison.md`。

完整要求与未完成项见 [requirements_audit.md](docs/requirements_audit.md)。

私有 Sites 版通过 `hosting/` 的服务端语义网关启用兼容 LLM；模型看不到用户字体，语义计划由浏览器共用引擎布局。构建前在 `hosting` 运行 `npm ci`，根目录 `npm run build`。密钥仅配置到服务端。

## 中文输入、明暗和换一组

默认“自动转为日文汉字”使用本地 OpenCC 衍生词典，保留句子语法；“中文标题 → 日语”需要服务端模型，原文与译文分别保留且译文可编辑。A 的排版核心仍无模型依赖；选择整句翻译会明确标记为“中文翻译 + A”。

右上 Day/Night 控制界面并保存偏好；“画布与复现”中的黑底/白底控制导出。Seed 控制可复现的字号比例、基线、错位和留白；常用“换一组”，无需手填数字。改变颜色、字体、画布和 Seed 复用同一译文与语义计划。

颜色提供自动、单色、双色、统一前景色；“着色依据”显示颜色角色、重要度与对比度。详细实测与限制见 [input_seed_color.md](docs/input_seed_color.md)。

## 自定义颜色与透明图片

“自定义配色”可设置前景色并添加最多八种强调色。预览下方“局部颜色”按字符指定颜色，Shift 连选、Ctrl/Command 多选；同一个字的不同出现位置分别编辑，所有候选同步，可恢复自动色。

下载区勾选“透明背景”后，PNG 导出 alpha 通道，SVG 不含背景。局部颜色和透明设置立即生效，不重新调用模型或搜索布局。自动强调优先内容字，重复「的／の」不再批量着色；纯色标题可选“统一前景色”。

82 张颜色复查、规则修改与验证见 [color_rules_revision.md](docs/color_rules_revision.md)。

着色位置与原作叙事的专项研究见 [color_position_narrative.md](docs/color_position_narrative.md)，含 82 条具体位置、官方集数映射、词内选字诊断与灰色角色复查。它区分创作语境与设计意图推测，本轮研究没有修改生成规则。
