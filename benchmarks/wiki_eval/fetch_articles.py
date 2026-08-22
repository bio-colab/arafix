"""
يجلب مقالات ويكيبيديا العربية وينظّفها إلى ملفات ذهبية UTF-8.

الذهب = النص المنظف **قبل** تحويله PDF. يُكتب مرةً واحدة ولا يُستبدل
إلا بطلبٍ صريح (--force) — فسلامة المرجع أهم من حداثته.

التنظيف:
  * إزالة إشارات المراجع [1] [2] [note 1]
  * إزالة الروابط والعناوين اللاتينية الزائدة إن اقترنت بأقواس
  * طيّ الفراغات المتعددة والأسطر الفارغة المتتالية
  * قطع عند حدود الفقرة إلى max_chars من manifest

الاستعمال:
    python fetch_articles.py            # يجلب ما لا ملفَّ ذهبيَّ له
    python fetch_articles.py --force    # يعيد الجلب والكتابة
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent
ARTICLES_DIR = ROOT / "articles"
MANIFEST = json.loads((ROOT / "articles.json").read_text(encoding="utf-8"))
API = MANIFEST["source_api"]
MAX_CHARS = int(MANIFEST.get("max_chars", 6000))

session = requests.Session()
session.headers["User-Agent"] = "arafix-wiki-eval/1.0 (benchmark harness)"


def clean_extract(raw: str) -> str:
    """ينظّف نص explaintext: مراجع، روابط، فراغات — ويقطع عند فقرة."""
    t = raw
    # إشارات المراجع [1] [23] [note 3]
    t = re.sub(r"\[(?:\d+|note\s*\d+|[a-z])\]", "", t)
    # عناوين الأقسام تصل كسطور قصيرة مستقلة في explaintext — نحتفظ بها.
    # روابط الويب المجرّدة
    t = re.sub(r"https?://\S+", "", t)
    # طيّ الفراغات داخل السطر
    t = re.sub(r"[ \t\u00a0]+", " ", t)
    # أسطر فارغة متتالية → فاصل فقرة واحد
    lines = [ln.rstrip() for ln in t.splitlines()]
    out: list[str] = []
    blank = False
    for ln in lines:
        if not ln.strip():
            if blank:
                continue
            blank = True
            out.append("")
        else:
            blank = False
            out.append(ln)
    t = "\n".join(out).strip()

    # قطعٌ عند حدود الفقرة دون شطرج الكلمة
    if len(t) > MAX_CHARS:
        cut = t.rfind("\n", 0, MAX_CHARS)
        if cut < MAX_CHARS // 2:
            cut = t.rfind(" ", 0, MAX_CHARS)
        if cut > 0:
            t = t[:cut].rstrip()
    return t


def fetch(title: str) -> str:
    last_exc: Exception | None = None
    for attempt in range(5):
        try:
            resp = session.get(API.format(title=title), timeout=30)
            if resp.status_code in (429, 502, 503):
                wait = min(60.0, 3.0 * (2**attempt))
                print(f"    {resp.status_code} — انتظار {wait:.0f}s…", flush=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            payload = resp.json()
            pages = payload["query"]["pages"]
            # formatversion=2 يجعلها قائمة؛ الإصدار ١ قاموس — نقبل الاثنين.
            page = pages[0] if isinstance(pages, list) else next(iter(pages.values()))
            if "extract" not in page or not page["extract"].strip():
                raise RuntimeError(f"لا نصّا للمقالة: {title}")
            return page["extract"]
        except requests.HTTPError as exc:
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
        except RuntimeError as exc:
            raise exc from None
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"فشل بعد المحاولات: {title} ({last_exc})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="أعد الجلب حتى لو وُجد الذهب")
    ap.add_argument("--only", help="slug مقالةٍ واحدة")
    args = ap.parse_args()

    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    for art in MANIFEST["articles"]:
        slug, title = art["slug"], art["title"]
        if args.only and slug != args.only:
            continue
        gold_path = ARTICLES_DIR / f"{slug}.gold.txt"
        if gold_path.exists() and not args.force:
            print(f"  SKIP {slug} (ذهب موجود — استعمل --force لإعادة الجلب)")
            continue
        try:
            raw = fetch(title)
            cleaned = clean_extract(raw)
            gold_path.write_text(cleaned + "\n", encoding="utf-8")
            print(f"  OK   {slug:14s} {art['domain']:10s} {len(cleaned):5d} حرفاً")
            time.sleep(2.0)  # أدبٌ مع الخادم: ويكيبيديا تقيّد الوتيرة
        except Exception as exc:  # noqa: BLE001 - التقرير لا الانهيار
            failures.append(f"{slug}: {exc}")
            print(f"  FAIL {slug}: {exc}")

    if failures:
        print(f"\n{len(failures)} فشل:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"\nكل المقالات جاهزة في {ARTICLES_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
