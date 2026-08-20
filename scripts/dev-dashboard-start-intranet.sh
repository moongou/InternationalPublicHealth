#!/usr/bin/env bash
# 启动内网端平台（前端 + 后端）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/.dev-dashboard"
API_PORT="${APP_API_PORT:-8002}"
WEB_PORT="${APP_WEB_PORT:-5182}"
mkdir -p "${STATE_DIR}"

# launchd 环境不继承 nvm/node 路径，这里显式补充
export PATH="${HOME}/.nvm/versions/node/v20.20.1/bin:${HOME}/.nvm/versions/node/v22.23.1/bin:${HOME}/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

cleanup() { "${ROOT_DIR}/scripts/dev-dashboard-stop-intranet.sh" >/dev/null 2>&1 || true; }
trap cleanup INT TERM EXIT

# 若端口已被监听，先释放（保证重启干净）
for port in "${API_PORT}" "${WEB_PORT}"; do
  while IFS= read -r pid; do [[ -n "${pid}" ]] && kill "${pid}" >/dev/null 2>&1 || true; done < <(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
done
sleep 1

wait_for_port() {
  local port="$1"
  for _ in $(seq 1 80); do
    lsof -nP -iTCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1 && return 0
    sleep 0.25
  done
  return 1
}

# 后端（内网模式）
(
  cd "${ROOT_DIR}/backend"
  exec env DEPLOYMENT_MODE=intranet "${ROOT_DIR}/backend/.venv/bin/python" -m uvicorn app.intranet_main:app --host 0.0.0.0 --port "${API_PORT}"
) &
printf '%s\n' "$!" > "${STATE_DIR}/intranet-api.pid"
wait_for_port "${API_PORT}" || { echo "内网端 API 未能在 ${API_PORT} 启动"; exit 1; }

# 前端（用 --port 覆盖 package.json 中硬编码的 5174）
(
  cd "${ROOT_DIR}/frontend"
  export API_PORT="${API_PORT}" WEB_PORT="${WEB_PORT}"
  exec node node_modules/vite/bin/vite.js --mode intranet --host 0.0.0.0 --port "${WEB_PORT}"
) &
printf '%s\n' "$!" > "${STATE_DIR}/intranet-web.pid"
wait_for_port "${WEB_PORT}" || { echo "内网端前端未能在 ${WEB_PORT} 启动"; exit 1; }

while kill -0 "$(cat "${STATE_DIR}/intranet-api.pid")" >/dev/null 2>&1 && kill -0 "$(cat "${STATE_DIR}/intranet-web.pid")" >/dev/null 2>&1; do
  sleep 2
done
exit 1
