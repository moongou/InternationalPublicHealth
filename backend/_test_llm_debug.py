"""临时调试脚本：验证内网端大模型配置端点。"""
import os
os.environ.setdefault("DEPLOYMENT_MODE", "intranet")
os.environ.setdefault("APP_ENV", "development")

from fastapi.testclient import TestClient
from app.app_factory import create_intranet_app

app = create_intranet_app()
client = TestClient(app)

# 用 rfg 免密登录（非生产环境）
resp = client.post("/api/v1/auth/login", json={"username": "rfg", "password": "dev"})
print("LOGIN:", resp.status_code, resp.json())
if resp.status_code != 200:
    raise SystemExit(1)
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 获取 providers
resp = client.get("/api/v1/admin/llm/providers", headers=headers)
print("GET providers:", resp.status_code, resp.json())

# 创建 provider
resp = client.post("/api/v1/admin/llm/providers", headers=headers, json={
    "name": "debug-provider", "provider_type": "openai_compatible",
    "base_url": "https://api.deepseek.com", "api_key": "sk-test",
    "selected_model": "deepseek-chat", "enabled": True, "is_default": False,
})
print("POST provider:", resp.status_code, resp.json())
