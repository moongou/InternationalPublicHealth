# 部署手册

## 1. 前置条件

- Docker Engine 25+ 与 Compose v2；生产建议 Linux/信创服务器。
- 至少 4 CPU、8 GB 内存、100 GB 数据盘；高数据量环境单独规划 PostgreSQL 与原始数据盘。
- 互联网和内网分别配置 DNS、TLS 证书、主机防火墙及时间同步。内网不得配置公网默认路由。

## 2. 生成密钥

```powershell
python scripts\generate_secrets.py > .env
backend\.venv\Scripts\python.exe scripts\generate_sm2_keys.py >> .env
```

检查并修改 `.env` 中管理员密码。互联网和内网的 `SECRET_KEY`、`FIELD_KEY` 必须不同。若使用 AES，保持 `TRANSFER_ENCRYPTION=AES-256-GCM`；若使用国密，改为 `SM4-CBC` 并保留四个 SM2 变量。

内网 LDAP/AD 可选：设置 `AUTH_MODE=local+ldap`、LDAPS 地址、搜索基准和只读服务账号。系统始终保留本地管理员作为故障恢复账号。

## 3. 启动与健康检查

```powershell
docker compose config --quiet
docker compose build
docker compose up -d
curl http://localhost:5173/health
curl http://localhost:5174/health
```

首次启动自动执行 Alembic 迁移。生产 `SEED_DEMO_DATA=false`，不会写入演示业务数据。首次登录内网管理员后，进入“系统管理 → 双因素认证”绑定 TOTP；绑定完成会强制重新登录。

### 大模型与采集初始化

两个 API 容器都包含 `backend/config/source_presets.json` 和完整 Alembic 迁移。互联网空库首次启动会导入预设信息源，之后配置只由数据库和管理页面维护；内网不会导入互联网采集源。`tzdata` 已固定为运行依赖，Cron 可使用 `Asia/Shanghai` 或其他有效 IANA 时区。

两侧分别登录“系统管理 → 大语言模型”配置本域服务。互联网区可配置获准访问的云端供应商；内网区默认保持空配置，确需研判时只配置安全域内可达的 Ollama/兼容推理集群。不要复制两侧数据库或 `FIELD_ENCRYPTION_KEY`，也不要把模型密钥放入摆渡包、镜像层或源代码。

## 4. 物理隔离部署

同机 Compose 用于验收或逻辑强隔离。正式物理隔离时：

1. 互联网区只启动 `internet-db internet-redis internet-api internet-web`。
2. 内网区只启动 `intranet-db intranet-redis intranet-api intranet-web`。
3. 文件通道把互联网 `/app/runtime/transfer/outbound` 经网闸投递到内网 `/app/runtime/inbound`。
4. 消息队列通道连接厂商提供的单向代理；两侧不得共享可双向路由的普通网络。
5. API 轮询默认关闭。确需使用时，只给内网主机到指定 HTTPS 网关的单一白名单路由，启用 mTLS，并设置 `ENABLE_API_POLLING=true`、`API_POLL_BASE_URL` 和机器密钥。

外部负载均衡器必须终止 TLS 1.2+，启用 HSTS；摆渡 outbox 建议独立端口强制客户端证书，并限制来源 IP。前端容器只在安全域内部提供 8080 服务。

## 5. 离线交付

联网构建机执行：

```powershell
.\scripts\prepare_offline_bundle.ps1 -OutputDirectory runtime\offline-bundle-20260818
```

脚本拉取基础镜像、构建四个应用镜像、导出 `images.tar`、复制部署源码并生成 SHA-256 清单。将整个目录经审批介质带入内网后：

```powershell
.\release\scripts\load_offline_bundle.ps1 -BundleDirectory <离线包目录>
# 修改 release\.env 后：
.\release\scripts\load_offline_bundle.ps1 -BundleDirectory <离线包目录> -Start
```

启动使用 `--no-build --pull never`，不会访问镜像仓库。内网前端构建还会执行外部 URL 静态扫描。

## 6. 信创适配

代码只依赖 Python、PostgreSQL、Redis、Nginx 和标准浏览器，可在统信 UOS、银河麒麟及兼容 OCI 的容器环境运行。ARM64 环境用 `docker buildx build --platform linux/arm64` 重新制作离线镜像；国密模式使用 gmssl。数据库可在完成兼容性回归后替换为支持 PostgreSQL 协议的国产数据库。
