# B：语义规划与共用布局

`llm/planner.py` 使用 OpenAI Responses 的严格 JSON schema。LLM 输入原文、Sudachi 分词与参考家族统计，输出分词修正、semantic_role、importance、visual_role、家族建议与强调关系。没有绝对坐标，没有模型生成 PNG。

LLM 输出的 token 必须逐字符重建输入，role/importance/family 必须在允许范围；新增坐标字段、遗漏标点、改写原文、非法强调子串都拒绝。规划失败明确返回错误，不默默把 A 输出冒充 B。B 与 A 使用同一 `LayoutEngine`、`Renderer`、`FontProvider`、字体字节与约束。家族建议改变搜索优先顺序，并不免除硬约束。短语强调关系转换为短语内部的首个内容字符锚点。

## 已执行与未执行

20 条标题的冻结语义 JSON 是本次会话助手产生的模型辅助研究产物，保存为 `session_plans.json`。它们在对照前冻结，记录 provenance，所有计划经原文重建校验。B 使用这些计划生成了完整候选，与 A 具有相同字体、seed 和配置。

当前环境没有 `OPENAI_API_KEY`，因此没有执行在线 Responses 调用。不能把冻结计划的读取时间计为 LLM 延迟，也不能计算未知调用成本。`--live-llm` 可以在配置 Key 后用完全相同 Benchmark 重跑，记录实际模型、response ID、usage 与 API latency。默认模型名是可改的实验配置，不是“最新”或“最佳”结论。

## Vision Critic

`llm/critic.py` 是可选实验适配器，接受 1–4 张参考图与 4–50 张有效候选，返回严格候选 ID 排名和理由。ID 不得遗漏、重复，Critic 只能排名，不能绕过共用约束。默认关闭，未在线运行，未纳入“B 更好”的结论。无证据时不加入 CLIP/DINO 依赖，也不训练神经网络。

## 部署与秘密

Key 只放服务端环境变量，不进入 JavaScript、仓库、模型输入日志或可下载参数。模型仅收到文本/参考统计；规划器不上传字体本体。Vision Critic 若显式启用会发送渲染图与选择的参考图，应在私有研究范围使用。

在线浏览器版可以演示 20 条固定文本的冻结 B 计划；任意新文本的在线 B 需要 Python 后端实际配置 API Key。两者在 UI 中分别标明，不能作为生产实时推理的等价证据。

官方技术来源：OpenAI Structured Outputs / Responses 文档、HarfBuzz shaping 文档。接口结构经文档检索后实现；当前无在线调用凭据，仍需真实 provider 集成验证。
