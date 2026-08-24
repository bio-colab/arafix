"""H15 — الخط الفاصل الرسمي: استرجاع الترميز ≠ تصحيح لغوي.

المبدأ الثالث للمشروع (معلن في توثيق pipeline.py):

    arafix يستعيد ما كان في الترميز (انعكاس، أشكال عرض، موجيبيك، CMap)
    ولا يصحّح ما كتبه المؤلف. «المجالت» قد تكون خطأ استخراجٍ لرباط
    لا-ألف وقد تكون النص الأصلي نفسه.

هذه الحملة تثبّت الحدود من الجهتين — ضد انجراف نحو «مصحح إملائي
عربي»، وضد انجرافٍ معاكس نحو عكسٍ عدواني بلا شواهد:

  الطبقة أ — الاسترجاع يجب أن يحدث افتراضياً (عيوب الترميز المغلقة).
  الطبقة ب — الجدار: نصٌّ سليمُ الترميزِ خاطئٌ لغوياً يمرّ بلا مساس،
              وحتى المنطقة الرمادية الوحيدة (لا-ألف) مقيَّدةٌ بمفتاحَين
              وقاعدةٍ مغلقةٍ وتدقيق.
  الطبقة ج — الشفافية: كل تغييرٍ افتراضيٍّ له قاعدةٌ مسجَّلة ورقعةٌ
              قابلة للعكس، والامتناع يُسجَّل حيث لا شاهد.
  الطبقة د — سطح الواجهة: لا يوجد ولا سيُنشأ مفتاح «تصحيح عام».
"""
from __future__ import annotations

from pathlib import Path

import pytest

from arafix import (
    DocumentContext,
    PipelineConfig,
    repair_text,
    reverse_visual_line,
)

REPO = Path(__file__).resolve().parents[2]
BASE = {"extractor": "pymupdf"}

#: نصوص «خاطئة» لغوياً لكنها **سليمة الترميز** — الجدار ضد المصحح الإملائي.
NO_SPELLING_FIX_CASES = [
    "ذهبت الى المكتبه",
    "فى الطريق",
    "هاذا الكتاب جميل",
    "لاكن الوقت ضيق",
    "قال إنشاء الله تعالى",
    "زار زوران جوفانوفيتش البلد",
    "شو حالك يا صاحبي",
    "قال: «هاذا نص خاطئ عمدا»",
    "شغل الملف عبر sudo apt",
]


# ---------------------------------------------------------------------------
# الطبقة أ — الاسترجاع يجب أن يحدث
# ---------------------------------------------------------------------------

def test_recovery_presentation_forms_default() -> None:
    assert repair_text("ﻣﺮﺣﺒﺎ", PipelineConfig(**BASE)).text == "مرحبا"


def test_recovery_hybrid_mojibake_default() -> None:
    out = repair_text("Ø§Ù„Ù…Customer Report", PipelineConfig(**BASE)).text
    assert out == "المCustomer Report"


def test_recovery_decisive_lam_alef_artifact_default() -> None:
    # فئة العيب المغلقة: انقلاب اا/لا الصادر عن العكس البصري.
    assert repair_text("االنترنيت", PipelineConfig(**BASE)).text == "الانترنيت"


def test_recovery_visual_order_line_roundtrip_default() -> None:
    line = "شهد عام 2024 تطورا كبيرا في المدينة القديمة"
    baseline = repair_text(line, PipelineConfig(**BASE)).text
    recovered = repair_text(reverse_visual_line(line), PipelineConfig(**BASE)).text
    assert recovered == baseline == line


# ---------------------------------------------------------------------------
# الطبقة ب — الجدار: لا تصحيحاً لغوياً افتراضياً
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text", NO_SPELLING_FIX_CASES)
def test_no_spelling_corrections_by_default(text) -> None:
    res = repair_text(text, PipelineConfig(**BASE))
    assert res.text == text, f"انجراف! تغيّر نصٌ سليمُ الترميز: {text!r}"


def test_gray_zone_is_governed_not_magic() -> None:
    """«المجالت»: المنطقة الرمادية الوحيدة — مقيدةٌ بمفتاحين وقاعدة."""
    gray = "المجالت العلمية"

    # (١) الافتراضي يصلحها — لكن عبر قاعدة الفئة المغلقة فقط:
    audited = repair_text(gray, PipelineConfig(audit_mode="summary", **BASE))
    rules = {e.rule for e in audited.audit.events}
    assert rules <= {"LAM_ALEF_TRANSPOSITION"}
    assert "LAM_ALEF_TRANSPOSITION" in rules

    # (٢) المفتاح الأول يوقفها تماماً:
    assert repair_text(
        gray, PipelineConfig(enable_lam_alef_repair=False, **BASE)).text == gray
    # (٣) المفتاح الثاني (المعجم) يوقفها تماماً:
    assert repair_text(
        gray, PipelineConfig(use_core_lexicon=False, **BASE)).text == gray


def test_lexicon_is_not_a_spell_dictionary() -> None:
    """المعجم يفكّ إبهامَ فئة لا-ألف فقط؛ لا يصلح إملاءً خارجها."""
    assert repair_text(
        "هاذا الكتاب", PipelineConfig(lexicon={"هذا"}, **BASE)).text == "هاذا الكتاب"
    assert repair_text(
        "المكتبه", PipelineConfig(lexicon={"المكتبة"}, **BASE)).text == "المكتبه"


def test_context_scoring_inert_without_explicit_flag() -> None:
    ctx = DocumentContext.from_texts(["نناقش الطاقة المتجددة في العراق."] * 4)
    broken = "نناقش الطاقة المتجددة في العراق."  # «المتجدة» خطأ أصلي محتمل
    res = repair_text(broken, PipelineConfig(context_model=ctx, **BASE))
    assert res.text == broken, "سياقٌ حاضرٌ بلا علمٍ صار مصححاً!"


def test_conservative_detection_floor_single_word() -> None:
    """حد التحفظ المعاكس: كلمةٌ مفردةٌ معكوسةٌ بلا شواهد تمرّ بلا عكس.

    تثبيتٌ ضد الانجراف المعاكس: مستقبلاً، توسيعُ كاشف الانعكاس يجب أن
    يكون قراراً موثقاً يحدّث هذا الاختبار — لا تخميناً صامتاً.
    """
    assert repair_text("ابحرم", PipelineConfig(**BASE)).text == "ابحرم"


# ---------------------------------------------------------------------------
# الطبقة ج — الشفافية والعكسية
# ---------------------------------------------------------------------------

def test_every_default_change_has_rule_and_reversible_patch() -> None:
    changed_inputs = [
        "ﻣﺮﺣﺒﺎ",
        "Ø§Ù„Ù…Customer Report",
        "االنترنيت",
        "المجالت العلمية",
    ]
    for text in changed_inputs:
        res = repair_text(text, PipelineConfig(audit_mode="full", **BASE))
        if res.text == text:
            continue  # لم يتغير → لا شرط
        assert res.audit is not None and res.audit.events, \
            f"تغييرٌ بلا تدقيق على {text!r}"
        assert all(e.rule for e in res.audit.events)
        assert res.reversible_patch is not None
        assert res.reversible_patch.revert(res.text) == text, \
            f"الرقعة غير عكسية على {text!r}"


def test_ambiguous_without_lexicon_abstains_and_records() -> None:
    res = repair_text(
        "المجالت العلمية",
        PipelineConfig(audit_mode="summary", use_core_lexicon=False, **BASE))
    assert res.text == "المجالت العلمية"
    abstain_rules = {a.rule for a in res.audit.abstentions}
    assert "LAM_ALEF_AMBIGUOUS" in abstain_rules


def test_clean_valid_arabic_byte_identity_rich_paragraph() -> None:
    paragraph = (
        "شو حالك يا صاحبي؟ سألت زوران جوفانوفيتش وهو يتصفح sudo apt.\n"
        "قال: «هاذا نص خاطئ عمدا» ثم أضاف فى 2024 لاكن بدون تعديل.\n"
        "ذهبت الى المكتبه وأخذت هاذا الكتاب عن الطاقة المتجدة."
    )
    res = repair_text(paragraph, PipelineConfig(**BASE))
    assert res.text == paragraph


# ---------------------------------------------------------------------------
# الطبقة د — سطح الواجهة: لا بوابةَ تصحيحٍ عام
# ---------------------------------------------------------------------------

def test_no_general_correction_flags_on_config_surface() -> None:
    fields = list(PipelineConfig.__dataclass_fields__)
    suspicious = [f for f in fields if any(
        k in f.lower() for k in ("spell", "grammar", "autocorrect", "correct"))]
    assert not suspicious, f"بوابة تصحيح عام تسللت إلى الواجهة: {suspicious}"


def test_mission_principle_declared_in_pipeline_docstring() -> None:
    src = (REPO / "src" / "arafix" / "pipeline.py").read_text(encoding="utf-8")
    flat = " ".join(src.split())  # توحيد البياض: المبدأ قد يُكسَر أسطراً
    assert "استرجاع الترميز ≠ تصحيح لغوي" in flat
    assert "ولا يصحّح ما كتبه المؤلف" in flat
    assert "لا وجود لمسار «تصحيح إملائي عام»" in flat
