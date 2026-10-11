# 在线部署

提供两个互相独立的部署入口，A/B 在各入口内共用同一渲染系统。

Sites 上部署浏览器渲染版与服务端语义 Worker：HarfBuzz WASM + Kuromoji/IPADIC + OffscreenCanvas mask + SVG path。用户上传字体留在本机 Worker 内存；7 组允许再分发的 OFL 字体可直接选用。任意日文可以走 A；20 条固定测试文本可以查看冻结 B 语义计划。服务端 `/api/plan` 支持配置兼容模型；已接入用户指定的兼容服务并完成 20 条真实调用。Sites 不是 Python 服务。

完整 Python 在线服务通过 Docker Compose 或 uvicorn 启动，提供服务端 font_id、Sudachi、FreeType mask、任务隔离、API B 和 PNG/SVG 导出。生产反向代理启用 HTTPS，设置 `SECURE_COOKIES=1`。当前容器仅打包明确清单中的 OFL 字体，管理员商业字体须另行只读挂载。

静态版与 Python 版的分词器、随机源、mask 栅格和像素 PNG 实现不同。它们复用同一配置、角色和母式定义，但不能把跨端差异算作 A/B 的差异。正式 A/B Benchmark 全部由 Python 的共用引擎生成。浏览器页中的实时 A/B 使用浏览器共用引擎。

## 字体/API

`POST /fonts` 接收 multipart `file`，返回 font_id、family、subfamily、weight、axes、glyph_count、Japanese coverage、SHA256 与 TTL。文件头与大小在隔离进程校验。字体没有可下载 URL。

`POST /render` 示例：

```json
{"text":"聖域の終わりと、崩壊の始まり","fonts":{"kanji":"YOUR_FONT_ID","kana":"YOUR_KANA_FONT_ID"},"mode":"classic","seed":42,"count":6,"palette":"night","width":1200,"height":675}
```

`mode:"llm"` 需要配置服务端 Key；不能静默降级。字体 cookie 随同源请求自动带上，curl 使用 `-c cookies.txt` / `-b cookies.txt`。返回候选配置与 `/results/<job_id>/candidate-N.png/svg`，必须持相同会话才能读取。

`DELETE /fonts` 删除当前会话字体和结果。`GET /fonts/private` 要求管理员 Bearer Token，普通会话不能访问。

Docker 环境 `/runtime` 用 tmpfs，容器停止后消失。单进程有两个渲染槽；长期高并发扩容需要外部任务队列与共享存储，此初版未实现。Docker 镜像已实际构建，并在非 root、只读根目录、tmpfs 的容器中验证 OTF 上传、四候选渲染和 PNG 下载。字体文件下载路由不存在，镜像内仅保留清单中的开放字体，上传字体下载路由仍不存在。

## Sites 语义服务配置

在 Sites 的服务端环境变量中设置 `LLM_BASE_URL`、`LLM_MODEL`、`LLM_API_STYLE`、`LLM_JSON_MODE`，并以 secret 设置 `LLM_API_KEY`。不要写入 hosting.json、Git 或网页。环境变化需部署后才应用。Worker 保持现有私有访问范围。

构建：根目录 `npm ci`，`cd hosting && npm ci`，回根目录 `npm run build`。`npm run build:browser` 产生单独静态版供 Python / Docker 使用；前者产生 Sites 的 client/server 产物。
