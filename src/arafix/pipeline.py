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

from dataclasses import dataclass, field

from .diagnose import DEFAULT_THRESHOLDS, detect_mojibake, detect_visual_order, diagnose
from .extractors import get_extractor
from .normalize import NormalizeConfig, normalize_text
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

    # --- الدرجة ١: التطبيع قبل الاتجاه، وهذا شرطٌ لا ترتيب ذوق --------
    if cfg.enable_normalize and dg.has(Defect.PRESENTATION_FORMS):
        current = normalize_text(current, cfg.normalize)
        stages.append(Stage.NORMALIZE)
        notes.append("طُبِّعت الأشكال الرسومية إلى حروفها الأصلية")
    elif cfg.enable_normalize and dg.has(Defect.TATWEEL_NOISE):
        current = normalize_text(current, cfg.normalize)
        stages.append(Stage.NORMALIZE)
        notes.append("حُذفت الكشيدة الزخرفية")

    # --- الدرجة ٢: يُعاد التشخيص لأن الدرجة ١ غيّرت المعطيات ----------
    order_conf = 1.0
    if cfg.enable_reorder:
        score, _ = detect_visual_order(current)
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

    # --- الدرجة ٣: نُصرّح بالحاجة ولا ندّعي القدرة في هذا المسار -------
    if dg.has(Defect.BROKEN_CMAP):
        notes.append(
            "كُشفت محارف PUA: الخريطة تالفة. النص وحده لا يُنجيك هنا — "
            "استعمل extract_pdf() لتُبنى الخريطة من الخط المضمَّن (الدرجة ٣)."
        )

    if dg.has(Defect.NO_TEXT_LAYER):
        notes.append("لا طبقة نصية — هذه حالة الدرجة ٤ (OCR) الوحيدة المشروعة.")

    confidence = _final_confidence(dg, order_conf, stages)

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
