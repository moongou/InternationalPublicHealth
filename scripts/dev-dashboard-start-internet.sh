#!/usr/bin/env bash
# 启动互联网端平台（前端 + 后端）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/.dev-dashboard"
API_PORT="${APP_API_PORT:-8000}"
WEB_PORT="${APP_WEB_PORT:-5181}"
mkdir -p "${STATE_DIR}"

# launchd 环境不继承 nvm/node 路径，这里显式补充
export PATH="${HOME}/.nvm/versions/node/v20.20.1/bin:${HOME}/.nvm/versions/node/v22.23.1/bin:${HOME}/.npm-global/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

cleanup() { "${ROOT_DIR}/scripts/dev-dashboard-stop-internet.sh" >/dev/null 2>&1 || true; }
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

# 后端
(
  cd "${ROOT_DIR}/backend"
  exec "${ROOT_DIR}/backend/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT}"
) &
printf '%s\n' "$!" > "${STATE_DIR}/internet-api.pid"
wait_for_port "${API_PORT}" || { echo "互联网端 API 未能在 ${API_PORT} 启动"; exit 1; }

# 前端
(
  cd "${ROOT_DIR}/frontend"
  export API_PORT="${API_PORT}" WEB_PORT="${WEB_PORT}"
  exec npm run dev:internet
) &
printf '%s\n' "$!" > "${STATE_DIR}/internet-web.pid"
wait_for_port "${WEB_PORT}" || { echo "互联网端前端未能在 ${WEB_PORT} 启动"; exit 1; }

while kill -0 "$(cat "${STATE_DIR}/internet-api.pid")" >/dev/null 2>&1 && kill -0 "$(cat "${STATE_DIR}/internet-web.pid")" >/dev/null 2>&1; do
  sleep 2
done
exit 1
