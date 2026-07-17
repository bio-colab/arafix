"""
الأنبوب — القائد الذي ينظّم الدرجات ولا يفعل شيئاً بنفسه.

قاعدتان تحكمان هذا الملف:

  ١. **الترتيب ليس اعتباطياً.** التطبيع قبل الاتجاه إلزاماً، لأن كاشف
     الاتجاه يستعمل التاء المربوطة شاهداً، والتاء المربوطة مخبوءةٌ
     خلف شكلها الرسومي (U+FE93) ما لم تُطبَّع أوّلاً. فالدرجة ١ تفتح
     عين الدرجة ٢.

  ٢. **لا درجةَ تُطبَّق بلا شاهد.** كل مرحلة تُسأل: أشخّصت علّتك؟ فإن
     لم تُشخَّص، تُتخطّى وتُسجَّل في التقرير. المكتبة لا تعالج «احتياطاً».
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace

from .diagnose import DEFAULT_THRESHOLDS, detect_mojibake, detect_visual_order, diagnose
from .extractors import get_extractor
from .lamalef import repair_lam_alef_transposition
from .normalize import NormalizeConfig, expand_deferred_forms, normalize_text
from .order import ReorderConfig, fix_order
from .types import (
    Defect,
    Diagnosis,
    DocumentResult,
    PageResult,
    RepairResult,
    Stage,
)

__all__ = ["PipelineConfig", "repair_text", "extract_pdf"]


@dataclass
class PipelineConfig:
    """إعدادات الأنبوب كاملاً — كائن واحد يُمرَّر ولا يُنسخ."""

    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    reorder: ReorderConfig = field(default_factory=ReorderConfig)

    enable_mojibake_fix: bool = True
    enable_normalize: bool = True
    enable_reorder: bool = True

    #: ترقيع انقلاب لام-ألف الوارد من أدواتٍ أخرى («المجالت» ← «المجلات»).
    #: لا يلزم لِما تعالجه هذه المكتبة من أوّله — إنما لِما وَرِثته معطوباً.
    enable_lam_alef_repair: bool = True

    #: معجمُ كلماتٍ عربية صحيحة. بدونه يُصلَح القاطعُ وحده ويُبلَّغ عن
    #: المُبهَم. ومعه تُحسَم المواضع الوسطية كـ«المجالت» أيضاً.
    lexicon: Iterable[str] | None = None

    #: اعكس النص ولو لم يُشخَّص معكوساً. للحالات التي تعرفها يقيناً.
    force_reorder: bool = False

    #: عتبات مخصّصة تُدمج فوق `DEFAULT_THRESHOLDS`.
    thresholds: dict = field(default_factory=dict)

    extractor: str = "auto"


def repair_text(text: str, config: PipelineConfig | None = None) -> RepairResult:
    """
    يشخّص نصاً ويصلحه بالدرجات ٠–٢، ويُرجع النتيجة كاملةً بتقريرها.

    هذه هي الدالة الأمّ. كل ما عداها غلافٌ حولها.

    >>> r = repair_text("\ufee3\ufeae\ufea3\ufe92\ufe8e")
    >>> r.text
    'مرحبا'
    >>> Stage.NORMALIZE in r.stages_applied
    True
    """
    cfg = config or PipelineConfig()
    th = {**DEFAULT_THRESHOLDS, **cfg.thresholds}

    original = text
    current = text
    stages: list[Stage] = []
    notes: list[str] = []

    # --- الدرجة ٠ -------------------------------------------------------
    dg: Diagnosis = diagnose(current, th)
    stages.append(Stage.DIAGNOSE)

    # --- الموجيبيك: يسبق كل شيء، فهو عطبٌ في الترميز لا في النص --------
    if cfg.enable_mojibake_fix:
        is_moji, recovered, _ = detect_mojibake(current)
        if is_moji and recovered:
            current = recovered
            notes.append("أُصلح موجيبيك (UTF-8 كان مفكوكاً بـ Latin-1)")
            dg = diagnose(current, th)  # كل تشخيصٍ سابق كان على نصٍّ مشوّه
    elif dg.has(Defect.MOJIBAKE):
        notes.append("كُشف موجيبيك ولم يُصلَح (المفتاح مطفأ)")

    # --- الدرجة ١أ: الأشكال المفردة وحدها -----------------------------
    #
    # التطبيع قبل الاتجاه شرطٌ (كاشف الاتجاه يحتاج التاء المربوطة مكشوفة)،
    # لكنّ التطبيع **الكامل** قبل الاتجاه عطبٌ: يفكّ «ﻻ» إلى حرفين فيعكسهما
    # العكسُ إلى «ال». فنقسم الدرجة ١ تمريرتين، والدرجة ٢ بينهما:
    #
    #     ١أ مفردات  →  ٢ اتجاه  →  ١ب رباطات
    #
    # فتُفتَح عينُ الدرجة ٢ ولا تُسلَّم سكيناً.
    shaped_source = current  # الطبقة الرسومية — شاهدةُ الدرجة ٢، تُحفظ قبل محوها
    needs_norm = dg.has(Defect.PRESENTATION_FORMS) or dg.has(Defect.TATWEEL_NOISE)
    if cfg.enable_normalize and needs_norm:
        current = normalize_text(current, replace(cfg.normalize, expand_ligatures=False))
        stages.append(Stage.NORMALIZE)
        notes.append("طُبِّعت الأشكال المفردة؛ أُبقيت الرباطات ذرّاتٍ حتى يستقرّ الترتيب")

    # --- الدرجة ٢: يُعاد التشخيص لأن الدرجة ١ غيّرت المعطيات ----------
    order_conf = 1.0
    if cfg.enable_reorder:
        score, _ = detect_visual_order(current, shaped_source=shaped_source)
        if cfg.force_reorder or score > th["visual_order"]:
            current = fix_order(current, cfg.reorder)
            stages.append(Stage.REORDER)
            order_conf = min(1.0, abs(score)) if not cfg.force_reorder else 0.5
            notes.append(
                f"أُصلح الاتجاه (درجة {score:+.2f})"
                if not cfg.force_reorder
                else "أُصلح الاتجاه قسراً بأمر المستعمل — بلا شاهد"
            )
        else:
            notes.append(f"لم يُمسّ الاتجاه (درجة {score:+.2f} دون العتبة)")

    # --- الدرجة ١ب: الآن استقرّ الترتيب، فليُفكَّ الرباط بأمان ----------
    if cfg.enable_normalize and cfg.normalize.expand_ligatures:
        expanded = expand_deferred_forms(current)
        if expanded != current:
            current = expanded
            stages.append(Stage.EXPAND_LIGATURES)
            notes.append("طُبِّع المؤجَّل (الرباطات والتشكيل الفاصل) بعد استقرار الترتيب")

    # --- ترقيع ما وَرِثناه معطوباً من أداةٍ أخرى ------------------------
    lam_conf = 1.0
    if cfg.enable_lam_alef_repair and dg.has(Defect.LAM_ALEF_TRANSPOSED):
        rep = repair_lam_alef_transposition(current, cfg.lexicon)
        current = rep.text
        stages.append(Stage.REPAIR_LAM_ALEF)
        lam_conf = rep.confidence
        notes.append(
            f"رُدَّ {rep.fixed_decisive} انقلابَ لام-ألف بشاهدٍ قاطع (ألفان متجاورتان)"
        )
        if rep.fixed_by_lexicon:
            notes.append(f"وحُسم {rep.fixed_by_lexicon} موضعاً مُبهَماً بالمعجم")
        if rep.suspects_left:
            notes.append(
                f"بقي {rep.suspects_left} موضعاً مُبهَماً لم يُمسّ: "
                + "، ".join(rep.suspect_words[:5])
                + " — مرِّر lexicon= لحسمها"
            )
        if rep.article_like:
            notes.append(
                f"و{rep.article_like} موضعاً في موقع «ال» التعريف — غالباً سليمة، لم تُسرَد"
            )

    # --- الدرجة ٣: نُصرّح بالحاجة ولا ندّعي القدرة في هذا المسار -------
    if dg.has(Defect.BROKEN_CMAP):
        notes.append(
            "كُشفت محارف PUA: الخريطة تالفة. النص وحده لا يُنجيك هنا — "
            "استعمل extract_pdf() لتُبنى الخريطة من الخط المضمَّن (الدرجة ٣)."
        )

    if dg.has(Defect.NO_TEXT_LAYER):
        notes.append("لا طبقة نصية — هذه حالة الدرجة ٤ (OCR) الوحيدة المشروعة.")

    confidence = min(_final_confidence(dg, order_conf, stages), lam_conf)

    return RepairResult(
        text=current,
        original=original,
        diagnosis=dg,
        stages_applied=stages,
        confidence=confidence,
        notes=notes,
    )


def _final_confidence(dg: Diagnosis, order_conf: float, stages: list[Stage]) -> float:
    """
    ثقة الأنبوب = أضعف حلقةٍ فيه.

    التطبيع حتميّ (١٫٠)، والاتجاه احتماليّ (بدرجته)، والخريطة التالفة
    تسقف الثقة عند ٠٫٣ مهما فعلنا — لأن ما استخرجناه أصلاً بلا معنى.
    """
    conf = 1.0
    if Stage.REORDER in stages:
        conf = min(conf, order_conf)
    if dg.has(Defect.BROKEN_CMAP):
        conf = min(conf, 0.3)
    if dg.has(Defect.NO_TEXT_LAYER):
        conf = 0.0
    return round(conf, 3)


def extract_pdf(path: str, config: PipelineConfig | None = None) -> DocumentResult:
    """
    يستخرج ملف PDF كاملاً ويصلحه صفحةً صفحة.

    كل صفحة تُشخَّص وتُعالَج مستقلةً — عمداً. الملف الواحد قد يخلط
    صفحاتٍ سليمةً بأخرى معطوبة (فصلٌ لُصق من مصدر آخر، جدولٌ صُدِّر
    بمحرّك مختلف). التشخيص الجَمعيّ يخفي هذا.
    """
    cfg = config or PipelineConfig()
    extractor = get_extractor(cfg.extractor)

    doc = DocumentResult(path=path)
    doc.metadata["extractor"] = extractor.name

    for raw in extractor.pages(path):
        result = repair_text(raw.text, cfg)
        if raw.is_empty and raw.has_images:
            result.notes.append("صفحة بلا نصّ وفيها صور — ممسوحة ضوئياً على الأرجح")
        doc.pages.append(
            PageResult(page_number=raw.number, repair=result, fonts=raw.fonts)
        )

    return doc
