#!/usr/bin/env bash
#
# 一次性安装脚本：Python 虚拟环境 + 依赖 + Stockfish + 前端依赖。
# 已经安装过的步骤会自动跳过，可以重复运行。
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-$ROOT/.venv/bin/python}"
NPM_CACHE_FLAG=()

cd "$ROOT"

step()  { printf '\n\033[1m==> %s\033[0m\n' "$1"; }
ok()    { printf '    \033[32m✓\033[0m %s\n' "$1"; }
warn()  { printf '    \033[33m!\033[0m %s\n' "$1"; }
fail()  { printf '    \033[31m✗\033[0m %s\n' "$1"; }

# ---------------------------------------------------------------- Python 虚拟环境
step "1/4 准备 Python 环境"
if [[ ! -x "$PYTHON" ]]; then
  BASE_PYTHON="${BASE_PYTHON:-python3}"
  if ! command -v "$BASE_PYTHON" >/dev/null 2>&1; then
    fail "找不到 python3，请先安装 Python 3.9 或更高版本。"
    exit 1
  fi
  "$BASE_PYTHON" -m venv "$ROOT/.venv" || { fail "创建虚拟环境失败。"; exit 1; }
  ok "已创建 $ROOT/.venv（$("$PYTHON" --version)）"
else
  ok "虚拟环境已存在（$("$PYTHON" --version)）"
fi

step "2/4 安装后端依赖"
if "$PYTHON" -m pip install -q --upgrade pip >/dev/null 2>&1; then :; fi
if "$PYTHON" -m pip install -q -r "$ROOT/backend/requirements.txt"; then
  ok "后端依赖就绪"
else
  fail "安装后端依赖失败，请检查网络或代理设置。"
  exit 1
fi

# --------------------------------------------------------------------- Stockfish
step "3/4 安装 Stockfish 引擎"
if "$PYTHON" "$ROOT/backend/scripts/install_stockfish.py"; then
  ok "引擎可用"
else
  warn "自动安装失败。可以手动安装 Stockfish，然后在 .env 里设置 STOCKFISH_PATH=/你的/路径/stockfish"
fi

# ------------------------------------------------------------------------ 前端
step "4/4 安装前端依赖"
if [[ -d "$ROOT/frontend/node_modules" ]]; then
  ok "node_modules 已存在，跳过"
else
  if [[ ! -w "${HOME}/.npm/_cacache" ]] 2>/dev/null; then
    # 某些机器上 ~/.npm 属于 root，npm 会直接报 EPERM；改用项目内的缓存目录。
    NPM_CACHE_FLAG=(--cache "$ROOT/.npm-cache")
    warn "检测到 ~/.npm 不可写，改用项目内缓存目录 .npm-cache"
  fi
  if (cd "$ROOT/frontend" && npm install "${NPM_CACHE_FLAG[@]}" --no-audit --no-fund); then
    ok "前端依赖就绪"
  else
    fail "npm install 失败。可以尝试：cd frontend && npm install --cache ../.npm-cache"
    exit 1
  fi
fi

cat <<'EOF'

安装完成。启动应用：

    ./scripts/dev.sh

然后浏览器打开 http://localhost:3000

EOF
