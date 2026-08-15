#!/bin/bash
# 推送到 GitHub 的完整流程(合并远程内容版本)

cd "$(dirname "$0")"

echo "=== Step 1: 切换回SSH远程仓库(密钥已验证) ==="
git remote remove origin 2>/dev/null
git remote add origin git@github.com:yumingjie0405/-1792-1793-.git

echo ""
echo "=== Step 2: 拉取远程内容并允许不相关历史合并 ==="
git pull origin main --allow-unrelated-histories --no-edit

echo ""
echo "=== Step 3: 推送到 GitHub ==="
git push -u origin master:main

echo ""
echo "=== 完成! 查看远程仓库 ==="
git remote -v
echo ""
echo "GitHub 仓库地址: https://github.com/yumingjie0405/-1792-1793-"
