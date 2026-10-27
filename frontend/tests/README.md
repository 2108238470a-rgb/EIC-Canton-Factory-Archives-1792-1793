# 文献分析端到端验收

所有 AI 内容使用明确命名的隔离测试文献。测试后端仅使用内存 SQLite 和模拟模型，不连接生产数据库，不调用已配置远程模型。不要将该后端作为生产服务器启动。

1. 在 backend 目录运行：`PYTHONPATH=. python tests/fixtures/insights_server.py`（默认 127.0.0.1:8009）。
2. 在 frontend 目录启动正常 Next 应用，例如 `NEXT_DIST_DIR=.next-v2-final npm run start -- --port 3103`。
3. 使用已经安装 Playwright 的环境运行 `node tests/insights-e2e.cjs`。若 Playwright 不在模块路径，可设置 `PLAYWRIGHT_MODULE` 为已有安装目录；`CHROME_PATH` 可指定本机 Chrome。
4. `TEST_FRONTEND_URL`、`TEST_API_URL` 可覆盖两个测试地址。

浏览器将所有 /api/ 请求路由到隔离后端。流程覆盖分析创建→全文概览→原图与引句→事件日期→AI主题目录→重命名新修订→JSON manifest 导出。测试文献 #90001 不写入生产数据库。

后端其余接口/失效/并发保护/失败重试/跨页/Unicode/分层摘要测试：在 backend 目录运行 `python -m unittest discover -s tests -q`。
