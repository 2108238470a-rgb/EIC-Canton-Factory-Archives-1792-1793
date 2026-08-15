#!/bin/bash
# 推送到 GitHub 的完整流程

cd "$(dirname "$0")"

echo "=== Step 1: 添加远程仓库 ==="
git remote add origin git@github.com:yumingjie0405/-1792-1793-.git 2>/dev/null || echo "远程仓库已存在,跳过"

echo ""
echo "=== Step 2: 首次提交 ==="
git add -A
git commit -F .git-commit-msg.txt

echo ""
echo "=== Step 3: 推送到 GitHub (master → main) ==="
git push -u origin master:main

echo ""
echo "=== 完成! 查看远程仓库 ==="
git remote -v
echo ""
echo "GitHub 仓库地址: https://github.com/yumingjie0405/-1792-1793-"
