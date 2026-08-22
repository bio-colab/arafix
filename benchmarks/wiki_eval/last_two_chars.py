# -*- coding: utf-8 -*-
"""تحديد المحرفين المتسببين في فرق يس العثمانية بين النسختين."""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, "../..")

from arafix import PipelineConfig, extract_pdf  # noqa: E402


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", t).strip()


gold = norm(open("quran/yaseen.uthmani.gold.txt", encoding="utf-8").read())
new_out = norm(
    "\n".join(
        p.text.strip()
        for p in extract_pdf("quran/pdfs/uthmani.pf_visual.pdf", PipelineConfig()).pages
    )
)

code = (
    "import sys, re, json\n"
    "sys.path.insert(0, r'C:\\Users\\Eylias\\AppData\\Local\\Temp\\opencode\\old_tree\\src')\n"
    "from arafix import PipelineConfig, extract_pdf\n"
    "r = extract_pdf(r'quran/pdfs/uthmani.pf_visual.pdf', PipelineConfig())\n"
    "t = re.sub(r'\\s+', ' ', chr(10).join(p.text.strip() for p in r.pages)).strip()\n"
    "open(sys.argv[1], 'w', encoding='utf-8').write(t)\n"
)
subprocess.run(
    [sys.executable, "-c", code, str(Path("_old_uthmani.txt"))],
    capture_output=True, text=True, encoding="utf-8", cwd=".",
)
old_out = norm(open("_old_uthmani.txt", encoding="utf-8").read())

diffs = [(i, a, b) for i, (a, b) in enumerate(zip(gold, new_out)) if a != b]
print(f"ذهب={len(gold)} جديد={len(new_out)} فروق موضعية={len(diffs)}")
for i, a, b in diffs[:12]:
    print(f"  @{i}: ذهب {a!r}({hex(ord(a))}) | خرج {b!r}({hex(ord(b))})")
    print(f"     …{gold[max(0, i - 18):i + 18]!r}…")

# وكم موضعاً في القديم؟
diffs_old = [(i, a, b) for i, (a, b) in enumerate(zip(gold, old_out)) if a != b]
print(f"\nفروق القديم مقابل الذهب: {len(diffs_old)}")
