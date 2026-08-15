#!/bin/bash
# 推送到 GitHub 的完整流程

cd "$(dirname "$0")"

echo "=== Step 1: 切换到HTTPS远程仓库(SSH密钥问题) ==="
git remote remove origin 2>/dev/null
git remote add origin https://github.com/yumingjie0405/-1792-1793-.git

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
