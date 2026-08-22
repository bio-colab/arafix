"""
حلقة التقييم المستقلة: يستخرج كل PDF بثلاثته، يقارن بالذهب، يصنّف
كل خطأ CER إلى سببه الجذري، ويراقب المكتبة من الداخل عبر audit trail.

المنهجية لكل مقالة×نمط:
  1. الخام: fitz.get_text() بلا إصلاح — يقيس شدة الإتلاف (خط الأساس).
  2. arafix.extract_pdf بالإعدادات الكاملة + audit_mode="full".
  3. القياس ضد الذهب: CER/WER كامل + letters-only للخام والمُصلَح.
  4. تصنيف فروق المحارف (difflib) إلى أصناف سببية.
  5. مراقبة داخلية: المراحل المطبقة، قواعد الـaudit، الثقة، الزمن.

الأدلة الفعلية لأنماط التخزين (مُثبتة بالفحص لا بالافتراض):
  clean      ← استخراجٌ معكوساً بالكامل بحروفٍ أساسية (اختبار الدرجة ٢ وحدها)
  pf         ← أشكال رسومية معكوسة (اختبار تطبيع + عكس معاً — السلّم الكامل)
  pf_visual  ← أشكال رسومية بترتيبها المنطقي (اختبار التطبيع دون عكس)
"""
from __future__ import annotations

import difflib
import json
import re
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

import fitz

from arafix import PipelineConfig, extract_pdf
from arafix.evaluate import evaluate_text

ROOT = Path(__file__).resolve().parent
REPORTS_DIR = ROOT / "reports"
MANIFEST = json.loads((ROOT / "articles.json").read_text(encoding="utf-8"))

MODES = ("clean", "pf", "pf_visual")
MODE_MEANING = {
    "clean": "حروف أساسية معكوسة (الدرجة ٢)",
    "pf": "أشكال رسومية معكوسة (السلّم الكامل)",
    "pf_visual": "أشكال رسومية منطقية (تطبيع فقط)",
}


def is_pf(ch: str) -> bool:
    return "\ufb50" <= ch <= "\ufeff"


def is_mn(ch: str) -> bool:
    return unicodedata.category(ch) == "Mn"


def letters_only(t: str) -> str:
    return "".join(
        c for c in t if not (c.isspace() or c in ".,؛:!؟()[]{}«»\"'-—–/\\|*+=<>٪٪@#$&_~^`")
    )


def normalize_layout(t: str) -> str:
    """يفصل أثر تخطيط المولّد عن الإتلاف: فواصل الأسطر فنُّ لفٍّ لا محتوى."""
    return re.sub(r"\s+", " ", t.replace("\u00ad", "")).strip()


def cer(ref: str, hyp: str) -> float:
    """CER حرفيّ بمسافة ليفنشتاين على النص الكامل."""
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(ref)


def classify_errors(gold: str, out: str) -> dict[str, int]:
    """يصنّف فروق المحارف بين الذهب والمخرَج إلى أصنافٍ سببية."""
    sm = difflib.SequenceMatcher(None, gold, out, autojunk=False)
    buckets: Counter[str] = Counter()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        g_seg, o_seg = gold[i1:i2], out[j1:j2]
        g_letters = [c for c in g_seg if not c.isspace()]
        o_letters = [c for c in o_seg if not c.isspace()]

        if not g_letters and not o_letters:
            buckets["spacing"] += max(len(g_seg), len(o_seg), 1)
        elif not o_letters:
            if all(is_mn(c) for c in g_letters):
                buckets["diacritic-loss"] += len(g_letters)
            elif any(c.isspace() for c in g_seg):
                buckets["spacing-loss"] += len(g_seg)
            else:
                buckets["letter-deletion"] += len(g_letters)
        elif not g_letters:
            if any(is_pf(c) for c in o_letters):
                buckets["residual-pf"] += len(o_letters)
            else:
                buckets["letter-insertion"] += len(o_letters)
        else:
            if any(is_pf(c) for c in o_letters):
                buckets["residual-pf"] += len(o_letters)
            elif (
                "".join(c for c in g_seg if is_mn(c)) != ""
                or any(is_mn(c) for c in o_letters)
            ) and "".join(c for c in g_seg if not is_mn(c)) == "".join(
                c for c in o_seg if not is_mn(c)
            ):
                buckets["diacritic-mismatch"] += max(len(g_seg), len(o_seg))
            else:
                buckets["letter-substitution"] += max(len(g_letters), len(o_letters))
    return dict(buckets)


def full_power_config() -> PipelineConfig:
    return PipelineConfig(audit_mode="summary")


def evaluate_one(slug: str, mode: str) -> dict | None:
    pdf_path = ROOT / "pdfs" / f"{slug}.{mode}.pdf"
    gold_path = ROOT / "articles" / f"{slug}.gold.txt"
    if not pdf_path.exists() or not gold_path.exists():
        return None
    gold = gold_path.read_text(encoding="utf-8")

    # --- ١) الخام بلا إصلاح ------------------------------------------
    doc_raw = fitz.open(str(pdf_path))
    raw = "\n".join(p.get_text() for p in doc_raw)
    doc_raw.close()

    # --- ٢) الأنبوب الكامل مع التتبع الداخلي --------------------------
    t0 = time.perf_counter()
    result = extract_pdf(str(pdf_path), full_power_config())
    dt_ms = (time.perf_counter() - t0) * 1000

    repaired = "\n\n".join(p.text for p in result.pages)

    # --- ٣) القياس (بعد فصل أثر التخطيط عن المحتوى) -------------------
    gold_cmp = normalize_layout(gold)
    raw_cmp = normalize_layout(raw)
    rep_cmp = normalize_layout(repaired)

    raw_cer = evaluate_text(raw_cmp, gold_cmp).cer.rate
    rep_eval = evaluate_text(rep_cmp, gold_cmp)
    rep_cer_lo = evaluate_text(letters_only(rep_cmp), letters_only(gold_cmp)).cer.rate
    raw_cer_lo = evaluate_text(letters_only(raw_cmp), letters_only(gold_cmp)).cer.rate

    # --- ٤) تصنيف الأخطاء السببية -------------------------------------
    taxonomy = classify_errors(gold_cmp, rep_cmp)

    # --- ٥) المراقبة الداخلية -----------------------------------------
    stages_pages: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    confidences: list[float] = []
    for p in result.pages:
        for s in set(p.repair.stages_applied):
            stages_pages[s.value] += 1
        confidences.append(p.repair.confidence)
        if p.repair.audit is not None:
            for event in p.repair.audit.events:
                rule_counts[f"{event.stage}:{event.rule}"] += 1

    profile = result.metadata.get("document_corruption_profile", {})

    return {
        "article": slug,
        "mode": mode,
        "mode_meaning": MODE_MEANING[mode],
        "pages": len(result.pages),
        "gold_chars": len(gold),
        "raw": {
            "chars": len(raw),
            "pf_chars": sum(1 for c in raw if is_pf(c)),
            "cer": round(raw_cer, 4),
            "cer_letters": round(raw_cer_lo, 4),
        },
        "repaired": {
            "chars": len(repaired),
            "pf_chars": sum(1 for c in repaired if is_pf(c)),
            "cer": round(rep_eval.cer.rate, 4),
            "wer": round(rep_eval.wer.rate, 4),
            "cer_letters": round(rep_cer_lo, 4),
        },
        "improvement_pct": round(
            100.0 * (raw_cer - rep_eval.cer.rate) / max(raw_cer, 1e-9), 2
        ),
        "confidence_min": min(confidences) if confidences else None,
        "confidence_max": max(confidences) if confidences else None,
        "stages_pages": dict(stages_pages),
        "audit_rules": dict(rule_counts.most_common()),
        "corruption_profile": profile,
        "error_taxonomy": dict(sorted(taxonomy.items(), key=lambda kv: -kv[1])),
        "total_errors": sum(taxonomy.values()),
        "time_ms": round(dt_ms, 1),
    }


def main() -> int:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    slugs = [a["slug"] for a in MANIFEST["articles"]]

    results = []
    for slug in slugs:
        for mode in MODES:
            row = evaluate_one(slug, mode)
            if row is None:
                print(f"  SKIP {slug}.{mode}", file=sys.stderr)
                continue
            results.append(row)
            r = row["repaired"]
            print(
                f"  {slug:14s} {mode:10s} "
                f"raw_cer={row['raw']['cer']:.3f} → cer={r['cer']:.3f} "
                f"(letters={r['cer_letters']:.3f}) "
                f"تحسين={row['improvement_pct']:6.1f}%  [{row['time_ms']:.0f}ms]"
            )

    (REPORTS_DIR / "eval_report.json").write_text(
        json.dumps({"schema": "arafix.wiki-eval.v1", "results": results},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"\nJSON: {REPORTS_DIR / 'eval_report.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
