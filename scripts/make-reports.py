from pathlib import Path
import json,html
ROOT=Path(__file__).resolve().parents[1]

def main():
    summary=json.loads((ROOT/'experiments/benchmark/summary.json').read_text());a=summary['modes']['A'];b=summary['modes']['B']
    comparison=f'''# A/B 初版对照

20 条固定标题，包括 13 条参考标题和 7 条未见输入；A/B 各六候选，共 {summary['candidate_count']} 个。相同 Noto Sans JP Black + Shippori Mincho SemiBold 字体字节、seed=42、dataset、配置、SVG/PNG Renderer 与硬约束。所有候选保存，未挑选“最佳 demo”替代测试集。

| 项 | A 规则 | B 冻结语义计划 |
|---|---|---|
| 成功标题 | 20/20 | 20/20 |
| 引擎中位延迟 | {a['engine_latency_median_ms']:.0f} ms | {b['engine_latency_median_ms']:.0f} ms |
| LLM API 延迟 | 无调用 | 未测，不能计为 0 |
| API 成本 | 无大模型调用费用；服务计算仍有成本 | 未测；冻结产物不等价于生产成本 |
| 最大溢出罚项 | {a['overflow_max']} | {b['overflow_max']} |
| 最大禁则违规数 | {a['kinsoku_max']} | {b['kinsoku_max']} |
| 最大低分辨率 ink 重叠率 | {a['collision_max']:.6f} | {b['collision_max']:.6f} |
| 内部分数均值 | {a['score_mean']:.3f} | {b['score_mean']:.3f} |
| 稳定性 | 固定字体/版本/seed，重跑 SVG 相同 | 固定计划时相同；在线模型稳定性未测 |
| 可解释性 | 规则、全部坐标与分数项可查 | 语义 JSON 可查；最终位置仍来自相同算法 |

上述引擎时间不含字体首次加载、PNG 转换、浏览器网络与在线 LLM。CPU、样本长度与缓存影响结果；B 较低时间可能来自 token 数量/边界不同，不能声称 B 在线更快。

## 质量判断

两组内部分数接近。分数本身使用各方案的 importance，评分目标随 planner 变化，因此不能当独立审美评价，也不能据均值差宣布 B 优于 A。禁则、原文完整与溢出是可比较的客观检查；风格、视觉主次和节奏需要独立人类评价。

B 的可见贡献在「待ちかねた再会」的单字锚点、「氷/炎」对照、重复结构和某些假名/助词强调。A 已能产生明显大小层级、混排与错位组合，但对上下文含义、隐喻、只用假名的短语仍依赖代理规则。这是观察，不是盲评结论。

`experiments/benchmark/index.html` 展示原图标题裁剪、A/B 的全部六张，可隐藏方案标签并导出偏好记录。尚未收集外部评审，标签隐藏也不是随机双盲实验。不得虚构 preference 胜率。

## 泛化与复杂度

7 条未见输入均成功生成；不代表任意标题都符合参考风格。参考来自同一系列、82 张不是独立设计分布。占用面积拟合排除 benchmark 参考 ID，但家族归纳用过全部样本，属于探索性对照而非严格未知域测试。

默认保留 A。B 作为可配置语义插件；没有在线质量与成本证据时不把它设为必需依赖。Vision Critic 适配器关闭，未把 embedding similarity 当审美答案。

## 下一次可验证实验

接入实际 API 后，以相同字体/seed/文本重跑 `--live-llm`，固定模型版本并记录 usage；再做多次调用稳定性、外部评审的随机化配对与语义强调消融。与初版冻结计划的结果区分存放，不覆盖本轮 provenance。
'''
    (ROOT/'docs/comparison.md').write_text(comparison)
    docs=['reference_analysis','typography_rules','algorithm_baseline','llm_pipeline','comparison','font_security','deployment']
    page=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Title Lab · 研究与实现</title><style>body{max-width:1000px;margin:40px auto;background:#09090b;color:#fafafa;font:14px system-ui;line-height:1.9;padding:0 24px}a{color:#d4d4d8}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px system-ui;border-top:1px solid #27272a;padding-top:28px;margin-top:50px}h1{font-weight:500}nav{display:flex;flex-wrap:wrap;gap:15px}img{width:100%;border:1px solid #27272a;border-radius:8px}</style><a href="/">← 返回生成器</a><h1>研究与实现</h1><p>82 个参考样本 · 7 个字体方向 · 20 条测试文本 · 240 个候选。几何规律与字体身份假设分别记录。</p><nav>']
    for name in docs:page.append(f'<a href="#{name}">{name}</a>')
    page.append('</nav>')
    for name in docs:page.append(f'<pre id="{name}">{html.escape((ROOT/"docs"/(name+".md")).read_text())}</pre>')
    page.append('</html>');(ROOT/'web/client/research.html').write_text(''.join(page))

if __name__=='__main__':main()
