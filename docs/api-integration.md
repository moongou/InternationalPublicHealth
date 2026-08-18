# 内网接口与摆渡对接

所有业务接口位于 `/api/v1`，交互式 OpenAPI 位于 `/docs`。普通接口使用 `Authorization: Bearer <JWT>`；互联网摆渡 outbox 使用独立 `X-API-Key`。生产入口必须使用 HTTPS/TLS。

## 旅客 REST

`POST /api/v1/passengers` 接受单个对象或数组；`POST /api/v1/passengers/risk-batch` 接受数组。示例：

```json
{
  "passenger_id": "PAX-20260818-001",
  "document_type": "护照",
  "document_number": "G12345678",
  "name": "张三",
  "gender": "男",
  "birth_date": "1990-01-01",
  "nationality": "中国",
  "travel_history": [{"country":"泰国","entry_date":"2026-08-01","exit_date":"2026-08-10"}],
  "transit_countries": ["新加坡"],
  "entry_port": "北京首都国际机场",
  "entry_time": "2026-08-18T10:30:00Z",
  "flight_no": "CA970",
  "seat_no": "32A",
  "health_declaration": true,
  "contact_info": {"phone":"13800138000","email":"zhangsan@example.com"}
}
```

响应只返回脱敏证件、姓名、风险分级、原因、建议和规则版本。相同 `passenger_id` 返回 409。

查询：`GET /passengers/{id}`、`GET /passengers?page=&page_size=&level=&port=`。预警：`GET /health-alerts`。口岸建议：`POST /port-advice`，参数 `port_name`、`port_type=airport|seaport|land`、`alert_level`。

## CSV / JSONL

上传接口：`POST /passengers/import`，multipart 字段名 `file`，最大 20 MB。JSONL 每行一个标准对象。CSV 必需列：

```text
passenger_id,document_type,document_number,name,nationality,entry_port,entry_time
```

可选列：`gender,birth_date,travel_country,travel_entry_date,travel_exit_date,transit_countries,flight_no,seat_no,health_declaration`；多个中转国用分号分隔。自动目录文件名：`PASSENGER_YYYYMMDD_NNN.jsonl|csv`。

## 数据摆渡

互联网任务：

- `POST /transfer/tasks`：`{"channel":"file|message_queue|api_polling","data_type":"full|incremental"}`。
- `GET /transfer/tasks`、`GET /transfer/tasks/{id}`、`POST /transfer/tasks/{id}/retry`。
- `GET /transfer/outbox`、`GET /transfer/outbox/{package_id}`：仅机器 API Key。

内网接收：

- `GET /transfer/receiver/status`
- `POST /transfer/receiver/scan`
- `POST /transfer/receiver/consume-queue`
- `POST /transfer/receiver/poll-api`（只读配置地址）
- `POST /transfer/receiver/upload`（最大 500 MB）

包包含 metadata、gzip 后密文、签名、SHA-256、schema version、源/目标和 package ID。内网依次验签、解密、校验、解压、Schema 验证和幂等入库。文件通道通过分片清单支持断点重组。

## 大语言模型与信息源 API

管理员在两侧分别使用：

- `GET/POST /admin/llm/providers`：查询或新建本平台供应商。
- `PATCH/DELETE /admin/llm/providers/{id}`：修改或删除；被信息源引用时删除返回 409。
- `POST /admin/llm/providers/{id}/models`：连接供应商并获取模型列表。
- `POST /admin/llm/providers/{id}/test`：用已选模型执行真实最小对话测试。
- `POST /ai/analyze-event`：使用指定或本平台默认模型研判事件；未配置可用模型时返回 409。

互联网端信息源使用 `GET /sources/status`、`POST /sources`、`PATCH/DELETE /sources/{id}` 和 `POST /sources/run`。配置字段包含 `schedule_type=interval|cron`、`frequency_seconds`、`cron_expression`、`schedule_timezone`、`parser_mode=builtin|llm|hybrid`、`llm_provider_id`、`llm_model` 与 `prompt_template`。密钥只允许写入供应商创建/修改请求，任何响应都不会包含密钥明文。

## 常见状态码

- 400/422：字段或文件格式错误。
- 401：JWT/API Key 无效。
- 403：角色不足或管理员未完成 MFA。
- 409：重复旅客、重复配置或通道未启用。
- 413：文件超限。
- 423：账号锁定。
