#!/usr/bin/env bash
# One-shot verification entrypoint. Runs, in order:
#   1. backend unit tests
#   2. frontend production build
#   3. HTTP smoke (api health, web index, proxied health)
#   4. scenario checks against the REAL api
#   5. scenario checks against the REAL built page
# Exits non-zero (with a summary) if any stage fails.
set -u

cd "$(dirname "$0")/.."
ROOT="$(pwd)"

API_URL="${API_URL:-http://api:8000}"
WEB_URL="${WEB_URL:-http://web:80}"

# Container uses /opt/venv; elsewhere rely on the activated environment.
[ -d /opt/venv ] && export PATH="/opt/venv/bin:$PATH"

fail=0
run_stage() {
  local name="$1"; shift
  echo
  echo "=============================================================="
  echo "▶ $name"
  echo "=============================================================="
  if "$@"; then
    echo "✔ $name"
  else
    echo "✘ $name 失败"
    fail=1
  fi
}

wait_for() {
  local url="$1" tries=60
  echo "等待 $url ..."
  for _ in $(seq 1 "$tries"); do
    python -c "import httpx,sys; sys.exit(0 if httpx.get('$url', timeout=3).status_code==200 else 1)" 2>/dev/null \
      && return 0
    sleep 2
  done
  echo "超时: $url 不可用"
  return 1
}

# 1. unit tests
run_stage "后端单元测试 (pytest)" \
  bash -c "cd '$ROOT/backend' && python -m pytest tests -q"

# 2. frontend build (production bundle + jsdom-executable copy of same App)
frontend_build() {
  cd "$ROOT/frontend" && npm run build || return 1
  node_modules/.bin/esbuild verify-entry.tsx \
    --bundle --format=iife --platform=browser --jsx=automatic \
    --define:import.meta.env.VITE_API_BASE='""' \
    --outfile=dist/verify-bundle.js
}
run_stage "前端生产构建 (vite build + 验证包)" frontend_build

# Services must be up before smoke/scenario stages.
wait_for "$API_URL/health" || exit 1
wait_for "$WEB_URL/" || exit 1

# 3. HTTP smoke
http_smoke() {
  python - "$API_URL" "$WEB_URL" <<'PY'
import sys, httpx
api, web = sys.argv[1], sys.argv[2]
ok = True
for name, url in [("API 健康检查", f"{api}/health"),
                  ("Web 首页", f"{web}/"),
                  ("Web 经 nginx 代理的 /health", f"{web}/health"),
                  ("Web 静态资源入口", None)]:
    if url is None:
        idx = httpx.get(f"{web}/", timeout=5).text
        url = f"{web}/" + (idx.split('src="/')[1].split('"')[0])
    r = httpx.get(url, timeout=5)
    good = r.status_code == 200
    print(f"  [{'PASS' if good else 'FAIL'}] {name}: {r.status_code}")
    ok &= good
r = httpx.get(f"{api}/api/v1/meta", timeout=5)
print(f"  [{'PASS' if r.status_code==200 else 'FAIL'}] API meta: {r.status_code}")
ok &= r.status_code == 200
sys.exit(0 if ok else 1)
PY
}
run_stage "HTTP 冒烟" http_smoke

# 4. real API scenarios
run_stage "真实 API 样例核对" python "$ROOT/verify/verify_api.py"

# 5. real page scenarios (built bundle served by web, calling API via nginx)
run_stage "真实页面展示核对" node "$ROOT/verify/verify_page.mjs"

echo
echo "=============================================================="
if [ "$fail" -eq 0 ]; then
  echo "全部验证通过 (unit tests / build / smoke / API / page)"
else
  echo "存在验证失败，详见上方日志"
fi
exit "$fail"
