# 全球公共卫生监测与口岸预警系统

> InternationalPublicHealth — 国际公共卫生研究平台（数据采集、分析与可视化）

本项目依据 `001-需求.docx` 建设两个独立平台：

- 互联网端：全球公开疫情采集、清洗、风险评分、地图研判、规则和单向摆渡发送。
- 内网端：离线镜像展示、摆渡接收、旅客风险匹配、口岸布控建议、LDAP/AD 与本地认证。

互联网与内网使用不同 ASGI 入口、数据库、Redis、前端入口、构建产物和 Docker 镜像。互联网 API 不注册旅客接口，内网 API 不注册采集与摆渡发送接口；JWT 还通过平台 audience 阻止跨平台复用。

## 目录

- `backend/app/main.py`：互联网 API 入口。
- `backend/app/intranet_main.py`：内网 API 入口。
- `frontend/internet.html`、`frontend/intranet.html`：独立前端入口。
- `docker-compose.yml`：双平台逻辑隔离参考部署。
- `docs/`：架构、部署、运维、用户、接口、安全与验收文档。
- `scripts/prepare_offline_bundle.ps1`：生成内网离线镜像交付包。

## 本地开发

```powershell
cd backend
py -3.13 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

另开终端启动内网 API：

```powershell
cd backend
$env:DEPLOYMENT_MODE='intranet'
.venv\Scripts\python.exe -m uvicorn app.intranet_main:app --port 8001
```

前端：

```powershell
cd frontend
npm ci
npm run dev:internet
npm run dev:intranet
```

开发环境会写入隔离的 SQLite 数据库并创建演示种子数据，默认管理员为 `admin / LocalAdmin@2026`。生产环境禁止默认密码、默认密钥和演示数据。

## 用户可配置的信息采集与大模型

- 互联网端和内网端都在“系统管理 → 大语言模型”独立维护供应商、服务地址、API 密钥和默认模型；支持 OpenAI、OpenAI 兼容、Anthropic、Google Gemini 与 Ollama 协议，可获取模型列表并执行真实最小对话连接测试。
- 两侧配置分别存放在各自数据库中，API 密钥用各平台自己的 `FIELD_ENCRYPTION_KEY` 加密，接口不回传明文，模型配置和密钥不经摆渡通道传输。
- 互联网端的信息源、URL、启停状态、固定间隔或 Cron 周期、计划时区、解析方式、供应商、模型和提取提示词都是数据库中的用户配置，可在运行中新增、编辑、停用和删除，无需修改代码或重启。
- `backend/config/source_presets.json` 只在互联网端首次空库初始化时导入广泛预设源；导入后与用户新增源一样由数据库管理，不会在后续启动时覆盖用户配置。
- 内网默认不主动访问外部模型服务；只有管理员显式配置并启用供应商后，用户发起研判才会调用该地址。物理隔离环境应优先配置内网 Ollama 或内网兼容推理服务。

## 验证

```powershell
cd backend
.venv\Scripts\python.exe -m pytest -q --cov=app --cov-fail-under=70

cd ..\frontend
npm run build

cd ..
docker compose --env-file .env.example config --quiet
```

当前自动化结果见 [验收矩阵](docs/acceptance-matrix.md)。生产部署步骤见 [部署手册](docs/deployment.md)。
