#!/bin/bash
# setup_remotes.sh - 为新项目一键配置双推送远程源 (GitHub + QNAP)

set -e

# 固定配置
GITHUB_USER="sunchen0213"
QNAP_USER="sunchen"
QNAP_HOST="http://fxy-qnap.mycloudnas.com:9300"

# 检查当前目录是否为 git 仓库
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "[提示] 当前目录未初始化 Git，正在执行 git init..."
    git init
fi

# 获取项目名称（优先级：命令行参数 > 用户输入 > 当前文件夹名）
CURRENT_DIR=$(basename "$PWD")
if [ -n "$1" ]; then
    REPO_NAME="$1"
else
    read -p "请输入项目名称 [默认: $CURRENT_DIR]: " INPUT_NAME
    REPO_NAME="${INPUT_NAME:-$CURRENT_DIR}"
fi

# 去除可能误输入的 .git 后缀
REPO_NAME="${REPO_NAME%.git}"

GITHUB_URL="https://github.com/${GITHUB_USER}/${REPO_NAME}.git"
QNAP_URL="${QNAP_HOST}/${QNAP_USER}/${REPO_NAME}.git"

echo ""
echo "正在为项目 [${REPO_NAME}] 配置远程源..."
echo "  - GitHub: ${GITHUB_URL}"
echo "  - QNAP:   ${QNAP_URL}"
echo ""

# 判断 origin 是否已存在
if git remote | grep -q "^origin$"; then
    echo "[!] 检测到已存在 origin，正在更新配置（保留分支跟踪）..."
    # 1. 确保 fetch 地址是 GitHub
    git remote set-url origin "$GITHUB_URL"
    # 2. 设置/覆盖第一个 push 地址 (GitHub)
    git remote set-url --push origin "$GITHUB_URL"
    # 3. 追加第二个 push 地址 (QNAP)
    git remote set-url --add --push origin "$QNAP_URL"
else
    echo "[1/3] 添加 origin fetch 源 (GitHub)..."
    git remote add origin "$GITHUB_URL"

    echo "[2/3] 添加 origin push 源 1 (GitHub)..."
    git remote set-url --add --push origin "$GITHUB_URL"

    echo "[3/3] 添加 origin push 源 2 (QNAP)..."
    git remote set-url --add --push origin "$QNAP_URL"
fi

echo ""
echo "=== 配置完成！当前远程源列表： ==="
git remote -v
