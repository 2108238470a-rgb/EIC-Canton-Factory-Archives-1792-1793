# 公网团队空站部署

入口：<https://archives.mjyblog.top>。独立部署于 `/opt/eic-research`，Compose 项目名 `eic-research`。现有博客和其他容器不属于本项目。

## 访问与数据

- 整站使用 HTTPS + Nginx Basic Auth；页面、API、扫描图和导出均需登录。当前是团队共享账号，不是多用户权限系统。
- 随机账号密码保存在服务器 `deploy/secrets/access.txt`（0600）；不要加入 Git 或通过公开链接分享。
- 首次部署为空数据库，不上传本机 PDF、OCR、研究标注或历史数据库。
- 数据库与 Redis 不映射公网端口；应用网关只绑定 `127.0.0.1:3108`。
- API 密钥、数据库密码通过 Compose secret 文件加载。服务器项目目录和 secrets 目录为 0700；secret 文件需供容器用户读取，宿主机目录权限不得放宽。
- GPU OCR 内网地址目前从公网服务器不可达，因此远程 OCR **尚未接通**。上传与页面可用不代表识别可用。应通过专用 VPN 或经授权的 SSH 隧道接入，再配置 `deploy/.env` 中的 `PADDLE_OCR_URL`；不要把 GPU 服务直接暴露到公网。

## 版本与配置

前端 Next.js 15.5.28 / React 19.2.9；构建、类型检查与隔离历史分析流程通过。Next.js 14 已不适合本次公网部署。PostCSS、nanoid、source-map-js 使用兼容补丁覆盖，后续升级时重新审计。

后端 Python 3.12，直接依赖约束见 `backend/constraints-server.txt`。镜像构建采用清华 PyPI 镜像解决服务器访问官方源失败问题：

```sh
cd /opt/eic-research
docker compose -f deploy/compose.yml build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
docker compose -f deploy/compose.yml up -d
docker compose -f deploy/compose.yml ps
docker compose -f deploy/compose.yml logs --tail 100 backend worker
```

迁移失败必须停止排查，禁止删库或用 `create_all` 绕过。迁移日志现在保留现有应用 logger，避免启动异常被隐藏。

从 macOS 打包源文件时设置 `COPYFILE_DISABLE=1` 并排除 `._*`、`.env*`、`node_modules`、`.next*`、缓存、storage、Git。AppleDouble 元数据文件不是迁移脚本，两个 Docker 上下文也已排除。

## HTTPS

宿主机站点配置为 `/www/server/panel/vhost/nginx/eic-archives.conf`；模板 `nginx-https.conf`。证书目录 `/opt/eic-research/tls`；ACME webroot `/var/www/eic-acme`。

`eic-certificate-renew.timer` 每日检查续期（随机延迟最多 1 小时），成功后先校验再 reload Nginx。只管理本项目证书：

```sh
systemctl status eic-certificate-renew.timer
systemctl start eic-certificate-renew.service
journalctl -u eic-certificate-renew.service --no-pager -n 40
```

不要覆盖已有博客站点或其他证书。不要关闭 TLS 校验来掩盖证书错误。

## 更新、备份与回滚

更新前暂停本项目 worker 与 backend（先等运行任务结束），备份数据库、storage、部署配置以及旧镜像。以下仅操作本项目，备份目录不得公开：

```sh
cd /opt/eic-research
mkdir -p backups
chmod 700 backups
docker compose -f deploy/compose.yml stop worker backend
docker compose -f deploy/compose.yml exec -T postgres pg_dump -U eic -d eic -Fc > backups/database.dump
docker compose -f deploy/compose.yml run --rm --no-deps --entrypoint tar backend -czf - -C /app/storage . > backups/storage.tar.gz
docker image tag eic-research-backend eic-research-backend:rollback
docker image tag eic-research-frontend eic-research-frontend:rollback
```

示例备份名会覆盖同名文件，正式操作请每次使用独立时间戳目录。secret、TLS 和站点配置也需受限离线备份。检查 `pg_restore --list` 和 `tar -tzf`，并定期在隔离环境恢复验证。

无数据库结构变更时可切回保存的旧源代码及镜像后 `up -d --no-build`。有迁移时不得盲目 downgrade，先在隔离数据库验证；必要时恢复对应备份。**不要运行 `docker compose down -v`，它会删除研究数据。**

## 研究流程与超时处理

1. 阅读器选原文，引句建立标注；也可从文献研究工作区的来源面板带入对应引句。
2. 填写这段原文支持的人物、事件或研究判断，保存后进入刚保存记录的审核页。
3. 核对原图、文本版本和判断，逐字段审核；知识库区分待审与已核实结果。

历史分析使用独立 90 秒单次模型请求预算；超时只拆分未完成批次，保留已完成结果和 Unicode 字符定位，最多拆分两层，避免无限重试。不是整份文献 90 秒必然完成；总体耗时仍取决于文献长度与模型服务。正式语料质量需后续人工验收，本次部署与端到端测试没有额外付费模型调用。
