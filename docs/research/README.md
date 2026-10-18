# 研究记录

这里保存参考分析、评估和独立实验。正式使用请看[使用说明](../user-guide.md)。

## 正式引擎的证据与限制

| 文档 | 内容 |
| --- | --- |
| [参考分析](../reference_analysis.md) | 82 张截图的观察、测量可靠性与字体假设 |
| [排版规律](../typography_rules.md) | 字号、假名、断行、字距与布局家族 |
| [A 算法说明](../algorithm_baseline.md) | 分词、规则、束搜索、评分与退火 |
| [A/B 对照](../comparison.md) | 同文本、同字体、同配置的 240 张输出；真实调用与计划重放的区别 |
| [全部参考对照](../full_reference_comparison.md) | 82 条、492 张 A 候选，断行与色位偏差 |
| [颜色规则修订](../color_rules_revision.md) | 出现位置、自定义色、助词保护与验证 |
| [着色位置与叙事](../color_position_narrative.md) | 原作中的词内色点、角色语境与推测边界 |
| [中文、Seed 和颜色检查](../input_seed_color.md) | 行为审计和可复现条件 |
| [需求核对](../requirements_audit.md) | 已完成、部分完成与暂缓内容 |

当前没有独立人工评审证明 B 整体优于 A，也没有证明任意输入都能达到原作设计水平。内部评分、断行匹配和色位重合各有用途，不能当作审美胜率。

## 独立实验

| 实验 | 当前结论 |
| --- | --- |
| [16 张参考的最小闭环](../minimal_reference_loop.md) | 结构迁移、排序器、优化和 Top-6 已跑通；未稳定超过原有引擎，未接替正式生成 |
| [视觉语法修订](../visual_grammar_revision.md) | 已保存完整对照；该轮色位指标退步，未采用为默认 |
| Vision Critic | 三条尝试中两条完成、一条超时，缺少收益证据，默认关闭；记录在 `experiments/vision_probe.json` |

最小闭环采用 Title / Visual Groups / Glyphs，标注 16 张、76 组、110 个字位置，其中 19 个假名内部字框未知。排序器虽能区分多数人工扰动，却在 15/16 条上把生成候选排到原作几何之上，并存在色位盲点。先解决这些已知失效，再决定是否扩大实验；不以训练正确率替代可见改善。

B 尚未接入这个新排序闭环。TextLogoLayout 独立评估与新闭环的浏览器同步也未完成。没有把这些事项写成正式功能。

## 复现入口

以下命令用于研究，不是应用启动步骤。完整参数在各实验文档中。

```bash
# 原作测量、标注和字体对照
.venv/bin/python analysis/measure_references.py
.venv/bin/python analysis/annotate.py
.venv/bin/python analysis/run_font_experiments.py
.venv/bin/python analysis/fit_layout_statistics.py

# 使用冻结计划的 A/B 对照，不调用在线模型
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/benchmark.py
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/ablations.py

# 使用此前真实调用得到的计划重放
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/benchmark.py \
  --replay-plans experiments/live-benchmark/results.json --out /tmp/title-ab-replay

# 全部参考对照
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m experiments.reference_comparison

# 独立的 16 张最小闭环
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m experiments.minimal_reference_loop \
  --ranker --benchmark --diagnose
```

测量、重建参考裁剪及包含原图的 Benchmark 需要 `references/originals/` 中的原始截图。截图不随仓库提交；已有测量、裁剪和结果可以直接查看。字体实验可下载开放字体到被 Git 忽略的 `.research-fonts/`，不会下载商业字体。

要重新请求在线 B，在服务进程中配置 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 和接口类型，再运行：

```bash
PYTHONPATH=. OPENBLAS_NUM_THREADS=1 .venv/bin/python experiments/benchmark.py \
  --live-llm --out /tmp/title-ab-live
```

可加 `--kanji /path/a.ttf --kana /path/b.otf --seed 42`。`create_session_plans.py` 只重建早期固定计划，不发起在线请求；不应据此统计模型调用延迟。不要覆盖已有证据后继续引用旧数字。

参数分别保存在 `config/layout_weights.yaml`、`template_rules.yaml`、`color_palettes.yaml`、`reference_evaluation.yaml` 与 `minimal_reference_loop.yaml`。产物记录 Seed、字体、配置与计划来源；上游模型生成本身不受排版 Seed 控制。
