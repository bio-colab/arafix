#!/usr/bin/env bash
# إعادة تسمية الحزمة. مثال:  ./rename.sh warraq
#
# التسمية أهونُ ما تكون قبل أوّل نشر، وأصعبُ ما تكون بعده: بعد النشر
# يبقى الاسم القديم على PyPI أبداً (لا تُحذف الأسماء)، وتنكسر روابطُ
# كلِّ من ثبّت. فافعلها الآن أو لا تفعلها.
set -euo pipefail
NEW="${1:?الاستعمال: ./rename.sh <الاسم_الجديد>}"
OLD="arafix"
[ "$NEW" = "$OLD" ] && { echo "الاسم نفسه — لا شيء يُفعل"; exit 0; }

echo "→ $OLD ← $NEW"
git mv "src/$OLD" "src/$NEW" 2>/dev/null || mv "src/$OLD" "src/$NEW"
grep -rl "$OLD" --include='*.py' --include='*.toml' --include='*.md' --include='*.yml' \
     --include='*.sh' . 2>/dev/null | grep -v '\.git/' | xargs sed -i "s/\b$OLD\b/$NEW/g"

echo "→ تحقّق"
ruff check src tests examples
PYTHONPATH=src python3 -m pytest tests --doctest-modules "src/$NEW" -q
python3 -m build --wheel -o /tmp/rn >/dev/null 2>&1 && echo "  البناء ✅"

cat <<MSG

تمّ. وبقي عليك يدوياً:
  · أعِد تسمية مستودع GitHub إلى $NEW
  · حدّث "Repository name" و"PyPI Project Name" في إعدادات الناشر على PyPI
  · راجع RELEASING.md — الحقول تغيّرت

MSG
