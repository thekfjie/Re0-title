# 开发说明

本地依赖与启动命令见[仓库首页](../README.md#快速启动)。日常开发使用 `npm run build:browser` 构建前端，由 FastAPI 同源提供页面和 API。

## 代码入口

| 位置 | 职责 |
| --- | --- |
| `engine/text.py` | Python 日文分词、角色与禁则 |
| `engine/fonts.py` | FontProvider、字形指标与字体校验 |
| `engine/layout.py` | 正式引擎的断行、候选搜索与评分 |
| `engine/renderer.py` | 共用字形轮廓 SVG 和 PNG |
| `llm/planner.py` | B 的严格语义计划与翻译 |
| `web/app.py` | 上传、渲染 API、会话与任务生命周期 |
| `web/client/` | 界面、浏览器渲染 Worker |
| `hosting/` | 私有托管入口的服务端语义网关 |
| `config/` | 布局、颜色、搜索与评分配置 |

Python 与浏览器端在各自运行端内共用 A/B 的渲染引擎。跨端不能用图片差异判断 A/B 优劣。

## 验证

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m pytest -q
npm test
npm run build:browser
```

Python 的渲染测试使用仓库中的 OFL 字体，不需要商业字体。涉及交互时，再检查桌面与手机布局、字体选择、候选切换和导出。`experiments/` 中的浏览器记录用于保留各轮证据，不作为当前界面的操作文档。

## 更新展示图

[展示配置](assets/showcase/recipes.json)记录输入、字体、Seed、着色模式和候选编号；[产物清单](assets/showcase/manifest.json)记录字形布局、字体和代码哈希。

```bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m scripts.render_showcase
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m scripts.render_showcase --check
```

第一条重新生成精选 PNG、轮廓 SVG、透明版本和首页拼图。第二条在内存中重新渲染并逐字节比较，不改文件。生成器直接调用正式的 `LayoutEngine` 和 `Renderer`，不调用模型，不读取原作图片，也不覆盖字形位置或局部颜色。

B 示例复用已保存的真实调用计划。重放验证的是给定计划后的排版，不代表重新测试了在线模型。更改算法、配置或依赖后，应重新审查图片并更新清单；不要通过只改哈希来跳过检查。

首页拼图只缩放并排列完整画布。原作裁剪独立保存在 `docs/assets/references/`，与生成图分目录，来源记录见[效果展示](gallery.md)。

## 研究代码

`references/` 保存参考描述，`analysis/` 保存测量，`experiments/` 保存实验脚本和完整对照。它们的结论与限制见[研究记录](research/README.md)。实验入口不自动替换正式 `engine/layout.py`。

仓库首页的组织方式参考 [Excalidraw](https://github.com/excalidraw/excalidraw) 和 [Satori](https://github.com/vercel/satori)：开头用图说明效果，尽早给出使用入口，技术细节单独查阅。
