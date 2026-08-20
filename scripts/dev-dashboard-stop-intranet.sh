#!/usr/bin/env bash
# 停止内网端平台（前端 + 后端）
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${ROOT_DIR}/.dev-dashboard"
API_PORT="${APP_API_PORT:-8002}"
WEB_PORT="${APP_WEB_PORT:-5182}"

for file in "${STATE_DIR}/intranet-web.pid" "${STATE_DIR}/intranet-api.pid"; do
  [[ -f "${file}" ]] || continue
  pid="$(tr -dc '0-9' < "${file}")"
  [[ -n "${pid}" ]] && kill "${pid}" >/dev/null 2>&1 || true
  : > "${file}"
done

for port in "${WEB_PORT}" "${API_PORT}"; do
  while IFS= read -r pid; do
    [[ -n "${pid}" ]] && kill "${pid}" >/dev/null 2>&1 || true
  done < <(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true)
done
exit 0
