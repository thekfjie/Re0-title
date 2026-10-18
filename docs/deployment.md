# 部署

项目提供 Python 服务和浏览器渲染两种入口。A/B 在同一入口内共用字体和排版引擎；两端的分词与栅格实现不同，输出不保证逐像素一致。

## Python 服务

本机依赖和启动步骤见[仓库首页](../README.md#快速启动)。构建前端后，FastAPI 同源提供页面、字体上传和渲染 API。

```bash
npm run build:browser
OPENBLAS_NUM_THREADS=1 .venv/bin/uvicorn web.app:app --host 0.0.0.0 --port 8000 --workers 1
```

`GET /api/status` 返回服务类型、模型是否配置、字体 TTL 和大小限制，不返回密钥。前端使用浏览器 Worker 渲染，Python 的 `/render` 接口用于服务端渲染。

## Docker

```bash
docker compose up --build
```

打开 <http://localhost:8000>。镜像只打包清单中的 8 款 OFL 字体；用户上传和管理员字体不进入镜像。

Compose 使用非 root 用户、只读根目录和 `/runtime` tmpfs。临时文件随容器停止消失。HTTPS 部署在反向代理后，并设置 `SECURE_COOKIES=1`。

保持一个 uvicorn worker。当前限流、两个渲染槽、会话和文件存储都在单进程内；多实例部署需要共享队列和存储，不能直接增加 worker 数量代替。

## 启用 B

将 [.env.example](../.env.example) 复制为根目录 `.env`，填写：

| 变量 | 配置 |
| --- | --- |
| `LLM_API_KEY` | 模型密钥，只放服务端 |
| `LLM_BASE_URL` | 兼容服务地址 |
| `LLM_MODEL` | 可用模型名 |
| `LLM_API_STYLE` | `chat_completions` 或 `responses` |
| `LLM_JSON_MODE` | `json_schema` 或 `json_object` |

Docker Compose 会读取 `.env`。直接运行 uvicorn 不会自动读取该文件，需要由 shell、进程管理器或部署平台注入变量。配置缺失时 A 仍可用，B 返回明确错误。更多行为见 [B 的配置与流程](llm_pipeline.md)。

## 字体与渲染 API

`GET /fonts/catalog` 列出内置字体，返回对应 `font_id`。`POST /fonts` 接收 multipart 字段 `file`，返回上传字体 ID、family、subfamily、weight、axes、glyph_count、Japanese coverage、SHA256 和有效期。

上传使用会话 cookie。命令行请求用 `-c cookies.txt` 保存 cookie，再用 `-b cookies.txt` 发起渲染和下载。字体校验、隔离和清理见[字体管理](font_security.md)。

`POST /render` 可直接使用内置字体 ID：

```json
{
  "text": "聖域の終わりと、崩壊の始まり",
  "fonts": {
    "kanji": "builtin_noto-sans-jp-black",
    "kana": "builtin_shippori-mincho-semibold"
  },
  "mode": "classic",
  "seed": 42,
  "count": 6,
  "palette": "night",
  "width": 1200,
  "height": 675,
  "transparent": false
}
```

上传字体时，将对应 ID 替换为上传返回的 `font_id`。`mode: "llm"` 使用实时 B，需要服务端模型配置。

可选字段：

| 字段 | 用途 |
| --- | --- |
| `input_mode` | `original`、`kanji` 或 `translate` |
| `canvas_theme` | `night` 或 `day` |
| `color_mode` | `auto`、`single`、`dual` 或 `none` |
| `custom_colors` | `foreground` 和 1 至 8 项 `accents` |
| `color_overrides` | 按原文位置设置 `start`、`end`、`color`，区间左闭右开 |

返回候选配置和 PNG / SVG 地址。结果路由只接受 `/results/<job_id>/candidate-N.png` 或 `.svg`，读取需持同一会话 cookie；没有字体文件下载路由。`DELETE /fonts` 删除当前会话的字体和结果。

浏览器版的字体选择和上传留在本机 Worker 内存，不调用这些服务端字体接口。

## 管理员私有字体

将字体只读挂载至 `PRIVATE_FONT_DIR`，并同时设置 `PRIVATE_MODE=1` 和 `ADMIN_TOKEN`。`GET /fonts/private` 及使用私有字体的请求需要管理员 Bearer Token。普通会话不能列出或使用它们，Web 不返回字体本体。

Compose 文件中有只读挂载示例。商业字体由管理员自行放置，不写入 Dockerfile 或 Git。

## 私有托管入口

`hosting/` 提供浏览器界面和服务端语义网关。字体在浏览器处理；`/api/plan` 只请求、校验并返回语义计划。

在托管平台的服务端变量中配置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_STYLE`、`LLM_JSON_MODE`，将 `LLM_API_KEY` 设为 secret。配置变化需要重新部署，保留已有私有访问范围。

构建依赖分别安装：

```bash
npm ci
npm --prefix hosting ci
npm run build
```

`npm run build` 生成托管入口的 client/server 产物。`npm run build:browser` 生成供 Python / Docker 使用的静态产物。仅更新仓库文档或展示图不需要重新部署应用。
