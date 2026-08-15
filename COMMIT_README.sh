#!/bin/bash
# 提交 README 更新并推送

cd "$(dirname "$0")"

echo "=== Step 1: 提交 README 和配置更新 ==="
git add README.md .gitignore assets/ PUSH_TO_GITHUB.sh
git commit -m "Add professional README with project overview

- English title: East India Company Canton Factory Archives Platform (1792–1793)
- Comprehensive documentation with architecture diagram
- Usage guide and configuration reference
- Recent bug fixes summary (bbox alignment, LLM retry)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"

echo ""
echo "=== Step 2: 推送到 GitHub ==="
git remote set-url origin git@github.com:yumingjie0405/-1792-1793-.git
git push origin master:main

echo ""
echo "=== 完成! ==="
echo ""
echo "📝 下一步: 修改 GitHub 仓库名称"
echo ""
echo "方法1: 通过 GitHub Web 界面"
echo "  1. 打开 https://github.com/yumingjie0405/-1792-1793-/settings"
echo "  2. 在 Repository name 输入框填入:"
echo "     EIC-Canton-Factory-Archives-1792-1793"
echo "  3. 点击 'Rename' 按钮"
echo ""
echo "方法2: 使用 GitHub CLI (需要先安装 gh)"
echo "  gh repo rename EIC-Canton-Factory-Archives-1792-1793"
echo ""
echo "重命名后,更新本地远程地址:"
echo "  git remote set-url origin git@github.com:yumingjie0405/EIC-Canton-Factory-Archives-1792-1793.git"
echo ""
echo "📌 别忘了将截图保存到 assets/platform-preview.png 然后再次提交!"
