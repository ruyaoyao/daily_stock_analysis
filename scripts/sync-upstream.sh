#!/usr/bin/env bash
#
# 手动同步 upstream（本仓库为 ZhuLinsen/daily_stock_analysis 的 fork）。
#
# 由于是 fork，GitHub 不会自动跑 schedule 工作流，upstream 的更新也不会自动并入；
# 本脚本让你「手动、可控」地把 upstream 的预设分支并入你 fork 的对应分支。
#
# 预设行为（安全优先）：
#   1) 确保 upstream remote 存在（默认指向 ZhuLinsen，只读 https，无需金钥）
#   2) fetch upstream
#   3) 要求工作区干净，否则中止
#   4) 切到目标本地分支（默认 main），以 fast-forward 方式并入 upstream/<分支>
#   5) 默认「不 push」；加 --push 才推回你的 origin
#   6) 结束后切回原分支
#
# 用法：
#   scripts/sync-upstream.sh [--push] [--branch <本地分支>] \
#       [--strategy ff|merge|rebase] [--upstream <git-url>] [--dry-run]
#
# 例：
#   scripts/sync-upstream.sh                 # 把 main fast-forward 到 upstream/main（不 push）
#   scripts/sync-upstream.sh --push          # 同上并推回 origin/main
#   scripts/sync-upstream.sh --strategy merge --push
#   scripts/sync-upstream.sh --branch main --dry-run
#
set -euo pipefail

UPSTREAM_URL_DEFAULT="https://github.com/ZhuLinsen/daily_stock_analysis.git"
UPSTREAM_REMOTE="upstream"

BRANCH=""              # 留空则用 upstream 的预设分支
STRATEGY="ff"          # ff | merge | rebase
DO_PUSH=0
DRY_RUN=0
UPSTREAM_URL="$UPSTREAM_URL_DEFAULT"

log()  { printf '\033[36m[sync-upstream]\033[0m %s\n' "$*"; }
warn() { printf '\033[33m[sync-upstream]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m[sync-upstream] 错误：\033[0m %s\n' "$*" >&2; exit 1; }
run()  { if [ "$DRY_RUN" = "1" ]; then printf '  (dry-run) %s\n' "$*"; else eval "$*"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --push) DO_PUSH=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --strategy) STRATEGY="${2:-}"; shift 2 ;;
    --upstream) UPSTREAM_URL="${2:-}"; shift 2 ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    *) die "未知参数：$1（用 --help 查看用法）" ;;
  esac
done

case "$STRATEGY" in ff|merge|rebase) ;; *) die "--strategy 只能是 ff / merge / rebase" ;; esac

# 必须在仓库内
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || die "不在 git 仓库内"
cd "$(git rev-parse --show-toplevel)"

# 1) 确保 upstream remote
if git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
  existing="$(git remote get-url "$UPSTREAM_REMOTE")"
  log "已存在 upstream remote：$existing"
else
  log "新增 upstream remote -> $UPSTREAM_URL"
  run "git remote add '$UPSTREAM_REMOTE' '$UPSTREAM_URL'"
fi

# 2) fetch upstream
log "fetch upstream..."
run "git fetch --prune '$UPSTREAM_REMOTE'"

# 解析 upstream 预设分支
if [ -z "$BRANCH" ]; then
  BRANCH="$(git remote show "$UPSTREAM_REMOTE" 2>/dev/null | sed -n 's/.*HEAD branch: //p' | head -1)"
  BRANCH="${BRANCH:-main}"
fi
log "目标分支：$BRANCH（upstream/$BRANCH）"

# 干净工作区检查（dry-run 时放宽）
if [ "$DRY_RUN" != "1" ] && [ -n "$(git status --porcelain)" ]; then
  die "工作区有未提交变更，请先提交或 stash 后再同步（避免合并冲突污染）。"
fi

ORIG_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
RESTORE=0
if [ "$ORIG_BRANCH" != "$BRANCH" ]; then RESTORE=1; fi

cleanup() {
  if [ "$RESTORE" = "1" ] && [ "$DRY_RUN" != "1" ]; then
    git checkout -q "$ORIG_BRANCH" 2>/dev/null || true
    log "已切回原分支：$ORIG_BRANCH"
  fi
}
trap cleanup EXIT

# 3) 切到目标分支（不存在则基于 upstream/<branch> 建立）
if git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  run "git checkout -q '$BRANCH'"
else
  log "本地无 $BRANCH 分支，基于 upstream/$BRANCH 建立"
  run "git checkout -q -b '$BRANCH' '$UPSTREAM_REMOTE/$BRANCH'"
fi

# 领先/落后统计
if [ "$DRY_RUN" != "1" ]; then
  read -r behind ahead < <(git rev-list --left-right --count "$UPSTREAM_REMOTE/$BRANCH...$BRANCH" 2>/dev/null || echo "0 0")
  log "相对 upstream/$BRANCH：落后 $behind 个提交、领先 $ahead 个提交"
  if [ "$behind" = "0" ]; then log "已是最新，无需同步。"; fi
  if [ "$ahead" != "0" ] && [ "$STRATEGY" = "ff" ]; then
    warn "本地 $BRANCH 领先 $ahead 个提交，无法 fast-forward。"
    warn "请改用 --strategy merge 或 --strategy rebase（注意可能有冲突需手动解决）。"
    exit 2
  fi
fi

# 4) 并入
case "$STRATEGY" in
  ff)     log "fast-forward 并入 upstream/$BRANCH"; run "git merge --ff-only '$UPSTREAM_REMOTE/$BRANCH'" ;;
  merge)  log "merge 并入 upstream/$BRANCH"; run "git merge --no-edit '$UPSTREAM_REMOTE/$BRANCH'" ;;
  rebase) log "rebase 到 upstream/$BRANCH"; run "git rebase '$UPSTREAM_REMOTE/$BRANCH'" ;;
esac

# 5) 可选 push
if [ "$DO_PUSH" = "1" ]; then
  log "push 到 origin/$BRANCH"
  run "git push origin '$BRANCH'"
else
  log "未推送（如需同步到你的 GitHub fork，请加 --push 或自行 git push origin $BRANCH）。"
fi

log "完成。后续若要把更新带进功能分支：git checkout <feature> && git merge $BRANCH"
