#!/usr/bin/env bash
#
# 一键启动：后端 (FastAPI + Stockfish) 和前端 (Next.js) 一起跑，Ctrl-C 同时结束两个。
#
# 端口可以改：
#     BACKEND_PORT=8010 FRONTEND_PORT=3010 ./scripts/dev.sh
# 脚本会自动把前端指向新的后端地址，并把新的前端地址加入后端 CORS 白名单。
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

info() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }

# ------------------------------------------------------------------ 前置检查
if [[ ! -x "$PYTHON" ]]; then
  bad "找不到 Python 虚拟环境：$PYTHON"
  echo "    请先运行：./scripts/setup.sh"
  exit 1
fi

if [[ ! -f "$ROOT/backend/engine/bin/stockfish" && -z "${STOCKFISH_PATH:-}" ]] \
   && ! command -v stockfish >/dev/null 2>&1; then
  bad "找不到 Stockfish 引擎"
  echo "    请先运行：$PYTHON backend/scripts/install_stockfish.py"
  echo "    或者在 .env 里设置 STOCKFISH_PATH 指向引擎可执行文件"
  exit 1
fi

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  bad "前端依赖还没安装"
  echo "    请先运行：./scripts/setup.sh   或者：cd frontend && npm install"
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  bad "找不到 node，请先安装 Node.js 20.9 或更高版本"
  exit 1
fi

# ---------------------------------------------------------- 端口占用 / 残留锁
port_pid() {
  # 打印占用指定端口的进程 PID（没有则输出空）
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1
  fi
}

NEXT_LOCK="$ROOT/frontend/.next/dev/lock"
if [[ -f "$NEXT_LOCK" ]]; then
  LOCK_PID="$("$PYTHON" -c "import json,sys;print(json.load(open(sys.argv[1])).get('pid',''))" "$NEXT_LOCK" 2>/dev/null || true)"
  if [[ -n "$LOCK_PID" ]] && ! kill -0 "$LOCK_PID" 2>/dev/null; then
    rm -f "$NEXT_LOCK"
    ok "已清理上次异常退出留下的 Next 锁文件（旧 PID $LOCK_PID）"
  fi
fi

BACKEND_PID="$(port_pid "$BACKEND_PORT")"
FRONTEND_PID="$(port_pid "$FRONTEND_PORT")"
if [[ -n "$BACKEND_PID" || -n "$FRONTEND_PID" ]]; then
  bad "端口已被占用，无法启动："
  [[ -n "$BACKEND_PID" ]] && echo "    端口 $BACKEND_PORT 被 PID $BACKEND_PID 占用（后端端口）"
  [[ -n "$FRONTEND_PID" ]] && echo "    端口 $FRONTEND_PORT 被 PID $FRONTEND_PID 占用（前端端口）"
  echo
  echo "    如果那就是你自己已经启动的服务，直接打开 http://localhost:$FRONTEND_PORT 使用即可。"
  echo "    想结束它：kill ${BACKEND_PID:-} ${FRONTEND_PID:-}"
  echo "    或者换端口启动：BACKEND_PORT=8010 FRONTEND_PORT=3010 ./scripts/dev.sh"
  exit 1
fi

# ---------------------------------------------------------------------- 启动
cleanup() {
  trap - EXIT INT TERM
  echo
  info "正在停止服务…"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

export CORS_ORIGINS="http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT"
export NEXT_PUBLIC_API_BASE="http://127.0.0.1:$BACKEND_PORT"

info "启动后端 http://127.0.0.1:$BACKEND_PORT （Stockfish 分析接口）"
(cd "$ROOT/backend" && "$PYTHON" -m uvicorn api.main:app --host 127.0.0.1 --port "$BACKEND_PORT") &

info "启动前端 http://localhost:$FRONTEND_PORT （界面）"
(cd "$ROOT/frontend" && PORT="$FRONTEND_PORT" npm run dev) &

sleep 3
cat <<EOF

================================================================
  界面地址：   http://localhost:$FRONTEND_PORT
  接口地址：   http://127.0.0.1:$BACKEND_PORT/api/health
  停止服务：   在这个终端按 Ctrl-C
================================================================

EOF

wait
