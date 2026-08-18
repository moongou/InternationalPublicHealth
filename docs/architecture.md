# 系统架构

## 边界与数据流

```text
公开数据源 -> 互联网采集/清洗 -> 互联网数据库 -> 风险/规则/地图
                                                |
                                      加密签名单向数据包
                                                v
口岸系统 -> 内网旅客接口/文件 -> 内网数据库 <- 内网接收/验签/解密
                                  |
                         旅客匹配/预警/布控建议
```

两个平台没有共享数据库、Redis、JWT 密钥或字段密钥。生产物理隔离环境应部署在不同主机或安全域；数据经网闸目录、单向消息队列或受控 HTTPS 白名单网关进入内网。默认基线不启用 API 轮询，因此内网没有外网请求。

## 独立运行单元

| 层 | 互联网端 | 内网端 |
|---|---|---|
| API 入口 | `app.main:app` / 8000 | `app.intranet_main:app` / 8001 |
| 专属路由 | 数据源、采集、风险重算、发送任务、outbox | 旅客、口岸建议、接收器 |
| 前端入口 | `main-internet.tsx` | `main-intranet.tsx` |
| 构建产物 | `dist/internet` | `dist/intranet` |
| 数据库 | `global_health_internet` | `global_health_intranet` |
| 缓存 | `internet-redis` | `intranet-redis` |
| 容器网络 | `internet_zone` | `intranet_zone`（internal） |

## 核心能力

- 六源采集：WHO DONS、ECDC CDTR、ProMED-mail、JHU CSSE、OWID、HealthMap。配置存入 `event_sources`，调度热更新，支持退避重试、原始留存和指纹去重。
- 风险引擎：六因子权重、四级阈值、国家历史、趋势突变、预警、旅客实时匹配。
- 地图：MapLibre GL + Deck.gl，本地 world-atlas 边界，无 CDN；风险、气泡、热力、中转、人员流、内网口岸六类图层及真实 14 日时间轴。
- 摆渡：文件、RabbitMQ、API outbox 三通道；gzip、SHA-256、分片续传、幂等版本入库。支持 AES-256-GCM/Ed25519 或 SM4-CBC/SM2-SM3。
- 规则：条件树 `all/any/not`、版本、草稿、发布、在线测试、执行日志和即时热更新。
- 管理：RBAC、锁定、TOTP、LDAP/AD、审计、统计、全量备份、WAL、恢复校验。

## 大语言模型与用户配置边界

两套平台各自拥有 `llm_providers` 表、字段密钥和默认模型，既不共库，也不通过摆渡包同步。统一网关适配 OpenAI、OpenAI 兼容、Anthropic、Google Gemini 和 Ollama 五类协议，模型发现、连接测试、事件研判和信息提取都调用当前平台数据库中的配置。API 只返回 `has_api_key`，不返回密钥明文。

信息采集链路以 `event_sources` 为事实来源：适配器类型、URL、启停、固定间隔/Cron、IANA 时区、内置/大模型/混合解析、供应商、模型和提示词均为用户数据。调度器在保存后热更新任务；某个源失败会形成独立失败记录并继续其他源。预设 JSON 仅负责互联网空库的首次导入，不是运行期硬编码配置。

内网 ASGI 不注册采集和互联网摆渡发送路由。模型研判属于管理员显式配置后的可选调用；默认空配置不会发出模型请求，物理隔离部署应指向内网推理地址。

## 密码算法密钥职责

国密配置使用两套 SM2 密钥，避免把解密私钥放到互联网端：

- 内网加密密钥对：互联网只持 `SM2_RECIPIENT_PUBLIC_KEY`，内网只持 `SM2_RECIPIENT_PRIVATE_KEY`。随机 SM4 包密钥由前者包封、后者解封。
- 互联网签名密钥对：互联网只持 `SM2_SIGNING_PRIVATE_KEY`，内网只持 `SM2_SIGNING_PUBLIC_KEY`。

AES 配置使用 AES-256-GCM 认证加密和 Ed25519 签名；生产密钥从部署密钥注入，不写入代码、日志或备份资源清单。
