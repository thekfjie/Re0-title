# B：语义规划与共用排版

B 让模型分析标题的分词、重点、连接关系和布局家族建议。模型返回严格 JSON，由正式排版引擎决定字号和位置，再导出图片。

在同一运行端，A 和 B 使用相同的字体系统、布局搜索、约束和渲染器。B 失败时会显示错误，不会把 A 的结果标成 B。

## 服务端配置

| 变量 | 用途 |
| --- | --- |
| `LLM_API_KEY` | 模型服务密钥；也兼容 `OPENAI_API_KEY` |
| `LLM_BASE_URL` | 兼容服务的接口前缀，通常以 `/v1` 结尾 |
| `LLM_MODEL` | 服务提供的模型名 |
| `LLM_API_STYLE` | `chat_completions` 或 `responses` |
| `LLM_JSON_MODE` | `json_schema` 或 `json_object` |

从 [.env.example](../.env.example) 复制配置。Docker Compose 读取根目录 `.env`；直接启动 uvicorn 时由运行环境注入变量。浏览器不接收密钥。无需为了使用 A 配置模型。

优先选服务支持的严格 JSON schema；仅支持 JSON object 的服务也必须通过同样的本地校验。`LLM_MODEL` 是可更换的部署配置，没有预设某个模型最适合排版。

Sites 入口由 `hosting/` 的 `/api/plan` 请求模型，浏览器 Worker 随后排版；Python 入口由 `llm/planner.py` 请求并在服务端排版。配置方式见[部署说明](deployment.md)。

## 计划与校验

计划包含 `tokens`、`suggested_layout_family` 和 `emphasis_relation`。每个 token 指定原文、语义角色、重要度和视觉角色。模型不能输出绝对坐标、字体文件、SVG 或 PNG。

校验会拒绝改写、缺字、调换顺序、遗漏标点、未知角色、超范围重要度和额外坐标字段。合法的家族建议只影响候选搜索，不绕过边界、禁则或碰撞约束。

模型只收到文本和参考统计，不收到用户字体。自动着色仍受共用规则影响，语义重点正确也不保证色位和构图合适。

## 计划复用和复现

页面把计划暂存在当前内存。修改字体、画布、配色和 Seed 时复用它；“重新规划”会再次请求模型。整句中文翻译是另一次显式模型处理，与后续选择 A 或 B 排版分开。

参数 JSON 保留计划及其来源。要复现 B 的布局，应同时固定输入、计划、字体、配置、Seed 和运行端。只固定 Seed 不能保证上游模型返回同一内容。

## 已保存的对照

仓库保留 20 条标题的真实兼容服务调用计划，以及按相同配置重放得到的 A/B 图片。首页展示中的 B 图也使用这些已保存计划重放，不发起新模型请求。

这些结果支持检查 B 的行为，不足以证明 B 整体更好。调用延迟、usage、旧冻结计划和可选 Vision Critic 的记录统一见[研究记录](research/README.md)与 [A/B 对照](comparison.md)。Vision Critic 默认关闭，未进入正式生成流程。
