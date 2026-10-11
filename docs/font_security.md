# 字体与任务生命周期

没有商业字体，也没有在 Git 或 Docker 中内置任何研究字体。OFL 研究字体也只在 `.research-fonts`；交付的样例是标题轮廓或光栅图片，不能据此下载整个字体。

`FontProvider` 是可替换协议，当前有 `UploadFontProvider`、`PrivateFontProvider` 和浏览器 `BrowserFontProvider`。服务端：24 MiB 单文件、8 文件/64 MiB 单会话、扩展名/MIME/sfnt 文件头/必要表检查。大请求含 chunked body 在 multipart 解析前限制。文件名不作为路径；随机 ID + 扩展名存储，目录按会话秘密的 SHA256 隔离，权限 0700/0600。

上传的 fontTools 检查运行在内存与时间受限子进程。渲染运行在独立子进程，每任务独立目录，CPU/内存/文件大小限制和 50 秒父进程超时。任务只复制指定会话的字体，完成或失败都删除字体副本与任务输入。原上传文件有一小时 TTL；清理线程每 60 秒运行，重启时也清理。任务输出同一 TTL、同一会话验证。只允许下载 `candidate-[1-8].png/svg`，没有字体下载路由。

cookie 是随机 256 bit bearer session，HttpOnly、SameSite Strict。生产 HTTPS 时设 `SECURE_COOKIES=1`。没有跨源上传/写入许可。`DELETE /fonts` 清理该会话字体与结果。任务结果不可跨会话读取，已通过两个 TestClient 验证。

管理员字体只有 `PRIVATE_MODE=1` 且设置 `ADMIN_TOKEN` 才通过 Bearer 授权可用。`PRIVATE_FONT_DIR` 只读挂载，管理员字体不会被 Web 返回本体。普通模式不能列出或使用它们。

浏览器部署版的字体只放 Web Worker 内存；不调用字体上传 API，不写 localStorage/IndexedDB，没有网络字体 URL。清理按钮释放 HarfBuzz 对象，关闭页面终止 Worker。静态资产不含 ttf/otf/woff。字体缺字会报具体字符，不默默用系统字体替补。

本地内存 rate limit 与两并发槽属于单进程保护；生产保持一个 uvicorn worker。扩展到多实例应使用共享队列/限流/会话存储，不能把当前本地目录当跨节点存储。解析器隔离不是完整 OS 沙箱；高流量公网部署还应使用容器资源和反向代理限制。
