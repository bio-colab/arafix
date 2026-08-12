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

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace

from .diagnose import DEFAULT_THRESHOLDS, detect_mojibake, detect_visual_order, diagnose
from .extractors import get_extractor
from .hygiene import (
    collapse_midword_spaces,
    count_artifacts,
    insert_particle_spaces,
    normalize_arabic_punctuation_spacing,
    sanitize_extraction,
)
from .lamalef import repair_lam_alef_transposition
from .layout import LayoutConfig, LayoutMode
from .noise import GeometricNoiseConfig
from .normalize import (
    NormalizeConfig,
    expand_deferred_forms,
    fold_pdf_homoglyphs,
    normalize_text,
)
from .order import ReorderConfig, fix_order
from .pdf_confusions import repair_pdf_confusions
from .types import (
    BlockResult,
    BlocksResult,
    Defect,
    Diagnosis,
    DocumentResult,
    PageResult,
    RepairResult,
    Stage,
    TextBlock,
)

__all__ = [
    "PipelineConfig",
    "repair_text",
    "repair_blocks",
    "extract_pdf",
    "harvest_document_lexicon",
]


_ARABIC_WORD = re.compile(r"[\u0621-\u064A\u0671-\u06D3]{3,}")


def _effective_lexicon(cfg: PipelineConfig) -> set[str] | None:
    """
    يبني معجم الإصلاح الفعّال: نواة مضمَّنة ∪ lexicon المستعمل.

    يُرجع ``None`` إن لم يتوفّر أي مصدر — عندها يُصلَح القاطع فقط
    داخل ``repair_lam_alef_transposition``.
    """
    vocab: set[str] = set()
    if cfg.use_core_lexicon:
        from .lexicon.core import get_core_lexicon

        vocab |= set(get_core_lexicon())
    if cfg.lexicon is not None:
        vocab |= set(cfg.lexicon)
    return vocab or None


def _is_lam_alef_suspect_word(word: str) -> bool:
    """
    أكلمةٌ مرشّحة لانقلاب لام-ألف مُبهَم؟ لا تُدخَل في معجم الوثيقة.

    وإلا حصدْنا «المجالت» من الصفحة المعطوبة فحمتْ نفسها من الإصلاح
    بقاعدة «إن كانت في المعجم اتركها» — وهي قاعدة صحيحة للمعجم الخارجيّ
    (أفعالهم) وخاطئة للحصاد الداخليّ.
    """
    from .lamalef import _AMBIGUOUS, _looks_like_article

    return any(
        not _looks_like_article(word, hit.start())
        for hit in _AMBIGUOUS.finditer(word)
    )


@dataclass
class PipelineConfig:
    """إعدادات الأنبوب كاملاً — كائن واحد يُمرَّر ولا يُنسخ."""

    normalize: NormalizeConfig = field(default_factory=NormalizeConfig)
    reorder: ReorderConfig = field(default_factory=ReorderConfig)

    enable_mojibake_fix: bool = True
    enable_normalize: bool = True
    enable_reorder: bool = True

    #: بوابة النظافة (NBSP / soft-hyphen / مسافات يونيكود). مطفأة فقط
    #: إن كنت تقيس آثار المحرّك نفسه لا تريد إخفاءها.
    enable_hygiene: bool = True

    #: ترقيع انقلاب لام-ألف الوارد من أدواتٍ أخرى («المجالت» ← «المجلات»).
    #: لا يلزم لِما تعالجه هذه المكتبة من أوّله — إنما لِما وَرِثته معطوباً.
    enable_lam_alef_repair: bool = True

    #: معجمُ كلماتٍ عربية صحيحة (من المستعمل). بدونه يُصلَح القاطعُ وحده
    #: ما لم يُفعَّل ``use_core_lexicon``. ومع معجمٍ تُحسَم «المجالت» وأمثالها.
    lexicon: Iterable[str] | None = None

    #: ادمج المعجم المضمَّن الخفيف (``arafix.lexicon.core``) لحسم المُبهَم
    #: الشائع بلا ملف خارجي. يُحمَّل كسولاً عند أول حاجة.
    use_core_lexicon: bool = True

    #: بعد إصلاح كل الصفحات: ابنِ معجماً من كلمات الملف نفسه وأعِد
    #: ترقيع لام-ألف المُبهَم. بلا نموذج خارجيّ — الوثيقة تشهد لنفسها.
    harvest_document_lexicon: bool = True

    #: اعكس النص ولو لم يُشخَّص معكوساً. للحالات التي تعرفها يقيناً.
    force_reorder: bool = False

    #: عتبات مخصّصة تُدمج فوق `DEFAULT_THRESHOLDS`.
    thresholds: dict = field(default_factory=dict)

    extractor: str = "auto"

    #: التحليل البنيويّ: ``auto`` | ``linear`` | ``columns`` | ``full``.
    #: ``auto`` يفعّل الأعمدة عند اكتشاف ميزاب؛ الصفحة ذات العمود الواحد
    #: تبقى مطابقةً للسلوك الخطّيّ السابق.
    layout: LayoutMode = "auto"

    #: إعدادات التفصيل للأعمدة/الترويسة/الجداول.
    layout_config: LayoutConfig = field(default_factory=LayoutConfig)

    #: أصلح كل سطر/خلية كتلةً مستقلة ثم أعد التجميع (أقوى للجداول).
    repair_per_block: bool = True

    #: إصلاح حدود كلمات مستخرج PDF (فراغات هندسية داخل الكلمة أو أدوات
    #: ملتصقة). مرحلة مستقلة محافظة؛ أطفئها لقياس نص المستخرج كما هو.
    enable_spacing_repair: bool = True

    #: Closed-list confusions from **published Arabic book PDFs** (Safahat
    #: independent-eval books: امل→الم، كثري→كثير، …). Not AI-generated.
    #: See ``arafix.pdf_confusions``. Off = leave raw after PF/order only.
    enable_pdf_confusion_repair: bool = True

    #: فلترة spans PDF ذات دليل هندسي قوي (watermark رمادي مائل/تكرار موضعي).
    #: None يعطلها؛ الافتراضي المحافظ مفعّل في مسار PyMuPDF الهندسي فقط.
    geometric_noise: GeometricNoiseConfig | None = field(
        default_factory=GeometricNoiseConfig
    )


def harvest_document_lexicon(texts: Iterable[str]) -> set[str]:
    """
    يجمع كلماتٍ عربية ≥ ٣ أحرف من نصوصٍ **بعد** الإصلاح الأوليّ.

    الفكرة: إن ظهرت «المجلات» صحيحةً في صفحة، و«المجالت» في أخرى،
    فالمعجم الداخليّ يحسم الثانية بلا ملفٍ خارجيّ.

    **لا تُحصد** الكلمات المشتبهة بانقلاب لام-ألف — وإلا حمتِ المعطوبةُ
    نفسها من الإصلاح.
    """
    vocab: set[str] = set()
    for t in texts:
        for w in _ARABIC_WORD.findall(t):
            if not _is_lam_alef_suspect_word(w):
                vocab.add(w)
    return vocab


def repair_text(text: str, config: PipelineConfig | None = None) -> RepairResult:
    """
    يشخّص نصاً ويصلحه بالدرجات ٠–٢، ويُرجع النتيجة كاملةً بتقريرها.

    هذه هي الدالة الأمّ. كل ما عداها غلافٌ حولها.

    >>> r = repair_text("\ufee3\ufeae\ufea3\ufe92\ufe8e")
    >>> r.text
    'مرحبا'
    >>> Stage.NORMALIZE in r.stages_applied
    True
    >>> repair_text("دراسة\u00a0مقارنة").text
    'دراسة مقارنة'
    """
    cfg = config or PipelineConfig()
    th = {**DEFAULT_THRESHOLDS, **cfg.thresholds}

    original = text
    current = text
    stages: list[Stage] = []
    notes: list[str] = []

    # --- بوابة النظافة: قبل التشخيص، كي لا تشوّش الشواهد ---------------
    if cfg.enable_hygiene:
        arts = count_artifacts(current)
        cleaned = sanitize_extraction(
            current,
            strip_zero_width=cfg.normalize.strip_zero_width,
        )
        if cleaned != current:
            current = cleaned
            stages.append(Stage.HYGIENE)
            bits = []
            if arts["nbsp_like"]:
                bits.append(f"{arts['nbsp_like']} مسافة يونيكود")
            if arts["soft_hyphen"]:
                bits.append(f"{arts['soft_hyphen']} soft-hyphen→-")
            if arts.get("thousands_as_comma"):
                bits.append(f"{arts['thousands_as_comma']} ٬→،")
            if arts.get("replacement"):
                bits.append(f"{arts['replacement']} U+FFFD")
            if arts.get("zero_width"):
                bits.append(f"{arts['zero_width']} محرف صفريّ العرض")
            notes.append(
                "نُظِّفت آثار الاستخراج: " + ("، ".join(bits) if bits else "ترقيم/مسافات")
            )

    # --- الدرجة ٠ -------------------------------------------------------
    dg: Diagnosis = diagnose(current, th)
    stages.append(Stage.DIAGNOSE)

    # --- الموجيبيك: يسبق كل شيء، فهو عطبٌ في الترميز لا في النص --------
    if cfg.enable_mojibake_fix and dg.has(Defect.MOJIBAKE):
        # diagnose() has already run the exact mojibake detector. For healthy
        # input, running it again is an expensive duplicate scan; only decode
        # a second time when the diagnosis established this defect.
        _is_moji, recovered, _ = detect_mojibake(current)
        if recovered:
            current = recovered
            notes.append("أُصلح موجيبيك (UTF-8 كان مفكوكاً بـ Latin-1)")
            dg = diagnose(current, th)  # كل تشخيصٍ سابق كان على نصٍّ مشوّه
    elif not cfg.enable_mojibake_fix and dg.has(Defect.MOJIBAKE):
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
    # القاطع (ألفان متجاورتان) يُصلَح بلا معجم. المُبهَم يحتاج معجماً
    # (مضمَّناً و/أو lexicon=). نوحّد البوابة مع repair_blocks: لا نشترط
    # Defect.LAM_ALEF_TRANSPOSED وحده — فالمُبهَم لا يُسجَّل قاطعاً.
    lam_conf = 1.0
    if cfg.enable_lam_alef_repair:
        vocab = _effective_lexicon(cfg)
        has_decisive = dg.has(Defect.LAM_ALEF_TRANSPOSED)
        has_ambiguous = int(dg.metrics.get("lam_alef_ambiguous", 0) or 0) > 0
        if has_decisive or has_ambiguous or vocab is not None:
            rep = repair_lam_alef_transposition(current, vocab)
            if rep.fixed_decisive or rep.fixed_by_lexicon:
                current = rep.text
                stages.append(Stage.REPAIR_LAM_ALEF)
                lam_conf = rep.confidence
                if rep.fixed_decisive:
                    notes.append(
                        f"رُدَّ {rep.fixed_decisive} انقلابَ لام-ألف بشاهدٍ قاطع "
                        "(ألفان متجاورتان)"
                    )
                if rep.fixed_by_lexicon:
                    notes.append(
                        f"وحُسم {rep.fixed_by_lexicon} موضعاً مُبهَماً بالمعجم"
                    )
            elif rep.suspects_left:
                notes.append(
                    f"بقي {rep.suspects_left} موضعاً مُبهَماً لم يُمسّ: "
                    + "، ".join(rep.suspect_words[:5])
                    + " — مرِّر lexicon= أو فعِّل use_core_lexicon"
                )
            if rep.article_like and (rep.fixed_decisive or rep.fixed_by_lexicon):
                notes.append(
                    f"و{rep.article_like} موضعاً في موقع «ال» التعريف — "
                    "غالباً سليمة، لم تُسرَد"
                )

    # --- الدرجة ٣: نُصرّح بالحاجة ولا ندّعي القدرة في هذا المسار -------
    if dg.has(Defect.BROKEN_CMAP):
        notes.append(
            "كُشفت محارف PUA: الخريطة تالفة. النص وحده لا يُنجيك هنا — "
            "استعمل extract_pdf() لتُبنى الخريطة من الخط المضمَّن (الدرجة ٣)."
        )

    if dg.has(Defect.NO_TEXT_LAYER):
        notes.append("لا طبقة نصية — هذه حالة الدرجة ٤ (OCR) الوحيدة المشروعة.")

    # --- P1: PDF homoglyph fold (always, even when PF normalize was skipped) -
    if cfg.normalize.fold_pdf_homoglyphs:
        folded = fold_pdf_homoglyphs(current)
        if folded != current:
            current = folded
            notes.append("طُوِيَت محارف PDF الهجينة (ی/ھ → ي/ه)")

    # --- مرحلة الفراغات ثم التباسات PDF (حلقات Safahat 2–3) -------------
    # 1) طيّ انقسامات داخل الكلمة كي ترى قائمة الالتباسات token متصلاً.
    # 2) التباسات PDF المغلقة.
    # 3) إدراج حدود أدوات/ترقيم ملتصقة بعد انتهاء تصحيح الحروف.
    # المرحلة قابلة للإيقاف كوحدة واحدة، مثل بقية درجات الأنبوب.
    spacing_changed = False
    if cfg.enable_spacing_repair:
        collapsed = collapse_midword_spaces(current)
        if collapsed != current:
            current = collapsed
            spacing_changed = True
            notes.append("طُويت مسافات هندسية داخل الكلمات (مو ضع → موضع، …)")

    if cfg.enable_pdf_confusion_repair:
        conf = repair_pdf_confusions(current)
        if conf.total:
            current = conf.text
            stages.append(Stage.REPAIR_PDF_CONFUSIONS)
            bits = []
            if conf.al_meem_fixes:
                bits.append(f"امل→الم ×{conf.al_meem_fixes}")
            if conf.ye_reh_fixes:
                bits.append(f"ري/ير وأشباهها ×{conf.ye_reh_fixes}")
            notes.append(
                "ترقيع التباسات كتب PDF منشورة (Safahat/عيّنة مستقلة): "
                + "، ".join(bits)
            )

    if cfg.enable_spacing_repair:
        spaced = insert_particle_spaces(current)
        spaced = normalize_arabic_punctuation_spacing(spaced)
        if spaced != current:
            current = spaced
            spacing_changed = True
            notes.append("أُصلحت حدود الترقيم العربية سياقياً (المادة(١٧) → المادة (١٧)، …)")
        if spacing_changed:
            stages.append(Stage.REPAIR_SPACING)

    confidence = min(_final_confidence(dg, order_conf, stages), lam_conf)

    return RepairResult(
        text=current,
        original=original,
        diagnosis=dg,
        stages_applied=stages,
        confidence=confidence,
        notes=notes,
    )


def repair_blocks(
    blocks: Sequence[TextBlock | str | tuple[str, str] | dict],
    config: PipelineConfig | None = None,
) -> BlocksResult:
    """
    يصلح كتلاً **مستقلة** — كلٌّ تُشخَّص وحدها فلا تُلوَّث جارتها.

    هذا مدخل الجداول والأعمدة وmarkitdown: الخلية المعكوسة تُصلَح،
    والسليمة لا تُمسّ، حتى لو جاورتْها في الصفحة نفسها.

    يقبل أشكالاً مرنة::

        repair_blocks(["نص", "آخر"])
        repair_blocks([TextBlock("…", id="r0c1", role="cell")])
        repair_blocks([("r0c1", "…"), ("r0c2", "…")])
        repair_blocks([{"text": "…", "id": "a", "role": "cell"}])

    >>> out = repair_blocks(["\ufee3\ufeae\ufea3\ufe92\ufe8e", "مرحبا"])
    >>> out.texts[0]
    'مرحبا'
    """
    cfg = config or PipelineConfig()
    results: list[BlockResult] = []

    for raw in blocks:
        block = _coerce_block(raw)
        rep = repair_text(block.text, cfg)
        results.append(BlockResult(block=block, repair=rep))

    # معجمٌ داخليّ عبر الكتل — نفس فكرة الصفحات
    if cfg.harvest_document_lexicon and cfg.enable_lam_alef_repair:
        _apply_harvested_lexicon_to_blocks(results, cfg)

    return BlocksResult(blocks=results)


def _coerce_block(raw: TextBlock | str | tuple | dict) -> TextBlock:
    if isinstance(raw, TextBlock):
        return raw
    if isinstance(raw, str):
        return TextBlock(text=raw)
    if isinstance(raw, tuple) and len(raw) == 2:
        a, b = raw
        # ("id", "text") أو ("text",) — إن كان الثاني أطول فهو النص غالباً
        if isinstance(a, str) and isinstance(b, str):
            return TextBlock(text=b, id=a)
    if isinstance(raw, dict):
        return TextBlock(
            text=str(raw.get("text", "")),
            id=raw.get("id"),
            role=raw.get("role"),
            bbox=raw.get("bbox"),
            meta=dict(raw.get("meta") or {}),
        )
    raise TypeError(
        f"كتلة غير مفهومة: {type(raw)!r}. "
        "مرِّر str أو TextBlock أو (id, text) أو dict."
    )


def _apply_harvested_lexicon_to_blocks(
    results: list[BlockResult], cfg: PipelineConfig
) -> None:
    vocab = harvest_document_lexicon(b.repair.text for b in results)
    extra = _effective_lexicon(cfg)
    if extra:
        vocab |= extra
    if not vocab:
        return
    for br in results:
        rep = repair_lam_alef_transposition(br.repair.text, vocab)
        if rep.fixed_by_lexicon or rep.fixed_decisive:
            br.repair.text = rep.text
            if rep.fixed_by_lexicon:
                br.repair.notes.append(
                    f"حُسم {rep.fixed_by_lexicon} موضعاً مُبهَماً بمعجم الوثيقة/النواة"
                )
            if Stage.REPAIR_LAM_ALEF not in br.repair.stages_applied:
                br.repair.stages_applied.append(Stage.REPAIR_LAM_ALEF)


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


def _canonical_font_name(name: str) -> str:
    """مقارنة متسامحة لأسماء الخط بين texttrace وموارد PDF."""
    return re.sub(r"[^0-9a-z]", "", name.lower()).removeprefix("subset")


def _recover_broken_cmap_page(raw, glyph_maps) -> tuple[object, int]:
    """استبدل PUA/FFFD فقط حين يثبت glyph ID معناه في الخط المضمّن.

    لا توجد هنا محاولة لغوية أو تخمين اسم glyph: إن غاب المعرّف أو الخريطة
    الموثوقة يبقى النص كما هو وتستمر بوابة التشخيص في إظهار BROKEN_CMAP.
    """
    if not raw.glyphs or not glyph_maps:
        return raw, 0

    normalized = {_canonical_font_name(name): glyph_map for name, glyph_map in glyph_maps.items()}

    def find_map(font: str):
        key = _canonical_font_name(font)
        if key in normalized:
            return normalized[key]
        matches = [
            value
            for name, value in normalized.items()
            if name.startswith(key) or key.startswith(name)
        ]
        return matches[0] if len(matches) == 1 else None

    recovered = 0
    glyphs = []
    replacement_candidates: dict[str, set[str]] = {}
    for glyph in raw.glyphs:
        text = glyph[2]
        is_unmapped = any("\ue000" <= char <= "\uf8ff" or char == "\ufffd" for char in text)
        glyph_id = int(glyph[5]) if len(glyph) > 5 else None
        font = str(glyph[6]) if len(glyph) > 6 else ""
        glyph_map = find_map(font) if glyph_id is not None and font else None
        replacement = glyph_map.lookup_id(glyph_id) if glyph_map else None
        if is_unmapped and replacement:
            glyph = (*glyph[:2], replacement, *glyph[3:])
            replacement_candidates.setdefault(text, set()).add(replacement)
            recovered += 1
        glyphs.append(glyph)

    if not recovered:
        return raw, 0
    # A PUA codepoint is not globally meaningful across fonts. Only rewrite
    # the page text when every occurrence observed for that codepoint agrees;
    # structural consumers still receive the per-glyph replacements above.
    replacements = {
        old: next(iter(values))
        for old, values in replacement_candidates.items()
        if len(values) == 1
    }
    text = raw.text
    for old, new in replacements.items():
        text = text.replace(old, new)
    return replace(raw, glyphs=glyphs, text=text, layout=None), recovered


def extract_pdf(path: str, config: PipelineConfig | None = None) -> DocumentResult:
    """
    يستخرج ملف PDF كاملاً ويصلحه صفحةً صفحة.

    كل صفحة تُشخَّص وتُعالَج مستقلةً — عمداً. الملف الواحد قد يخلط
    صفحاتٍ سليمةً بأخرى معطوبة (فصلٌ لُصق من مصدر آخر، جدولٌ صُدِّر
    بمحرّك مختلف). التشخيص الجَمعيّ يخفي هذا.

    إن كان ``harvest_document_lexicon`` مفعّلاً (الافتراضيّ)، تُجمع كلمات
    الصفحات بعد الإصلاح وتُمرَّر معجماً لترقيع «المجالت» وأمثالها.

    مع ``layout="auto"`` (افتراضيّ منذ 0.8.0): تُكتشف الأعمدة والترويسة
    والجداول من هندسة الجليفات، ويُصلَح كل سطر/خلية على حدة.
    """
    cfg = config or PipelineConfig()

    # مرِّر وضع البنية للمستخرج إن دعمه
    if cfg.extractor == "auto":
        from .extractors import PyMuPDFExtractor

        extractor = (
            PyMuPDFExtractor(
                layout_mode=cfg.layout,
                geometric_noise=cfg.geometric_noise,
            )
            if PyMuPDFExtractor.available()
            else get_extractor("auto")
        )
    else:
        from .extractors import REGISTRY

        cls = REGISTRY.get(cfg.extractor)
        if cls is not None and cfg.extractor == "pymupdf":
            extractor = cls(layout_mode=cfg.layout)  # type: ignore[call-arg]
        else:
            extractor = get_extractor(cfg.extractor)

    page_cfg = replace(cfg, harvest_document_lexicon=False)

    doc = DocumentResult(path=path)
    doc.metadata["extractor"] = extractor.name
    doc.metadata["layout"] = cfg.layout

    glyph_maps = None
    cmap_recovered = 0
    noise_removed = 0
    noise_reasons: dict[str, int] = {}
    for raw in extractor.pages(path):
        noise_removed += int(getattr(raw, "noise_spans_removed", 0) or 0)
        for reason, count in (getattr(raw, "noise_reasons", {}) or {}).items():
            noise_reasons[reason] = noise_reasons.get(reason, 0) + int(count)
        has_unmapped = any(
            any("\ue000" <= char <= "\uf8ff" or char == "\ufffd" for char in glyph[2])
            for glyph in raw.glyphs
        )
        if has_unmapped:
            if glyph_maps is None:
                try:
                    from .cmap import build_glyph_map

                    glyph_maps = {
                        name: build_glyph_map(data, name)
                        for name, data in extractor.font_bytes(path).items()
                    }
                except Exception:
                    glyph_maps = {}
            raw, count = _recover_broken_cmap_page(raw, glyph_maps)
            cmap_recovered += count
        page = _extract_one_page(raw, page_cfg)
        doc.pages.append(page)

    if cmap_recovered:
        doc.metadata["cmap_glyphs_recovered"] = cmap_recovered
    if noise_removed:
        doc.metadata["geometric_noise_spans_removed"] = noise_removed
        doc.metadata["geometric_noise_reasons"] = noise_reasons
    if cfg.harvest_document_lexicon and cfg.enable_lam_alef_repair and doc.pages:
        vocab = harvest_document_lexicon(p.text for p in doc.pages)
        extra = _effective_lexicon(cfg)
        if extra:
            vocab |= extra
        fixed_pages = 0
        for page in doc.pages:
            rep = repair_lam_alef_transposition(page.repair.text, vocab)
            if rep.text != page.repair.text:
                page.repair.text = rep.text
                fixed_pages += 1
                page.repair.notes.append(
                    f"معجم الوثيقة/النواة: حُسم {rep.fixed_by_lexicon} مُبهَم "
                    f"+ {rep.fixed_decisive} قاطع عبر الصفحات"
                )
                if Stage.REPAIR_LAM_ALEF not in page.repair.stages_applied:
                    page.repair.stages_applied.append(Stage.REPAIR_LAM_ALEF)
        doc.metadata["document_lexicon_size"] = len(vocab)
        doc.metadata["document_lexicon_pages_touched"] = fixed_pages

    doc.metadata["max_columns"] = max((p.n_columns for p in doc.pages), default=1)
    doc.metadata["table_count"] = sum(len(p.tables) for p in doc.pages)
    return doc


def _extract_one_page(raw, cfg: PipelineConfig) -> PageResult:
    """صفحة واحدة: بنيويّ إن لزم، وإلا خطّيّ كلاسيكي."""
    from .layout import Glyph, analyze_layout

    layout = raw.layout
    if raw.glyphs:
        gs = []
        for g in raw.glyphs:
            y, x, t, s = g[0], g[1], g[2], g[3]
            sq = int(g[4]) if len(g) > 4 else 0
            gs.append(Glyph(y=y, x=x, text=t, size=s, seq=sq))
        layout = analyze_layout(
            gs,
            page_width=raw.width or 595.0,
            page_height=raw.height or 842.0,
            config=cfg.layout_config,
            mode=cfg.layout,
        )

    structural = (
        layout is not None
        and cfg.repair_per_block
        and cfg.layout != "linear"
        and (
            layout.n_columns > 1
            or layout.tables
            or layout.headers
            or layout.footers
        )
    )

    if structural:
        blocks_in = layout.to_blocks(page_number=raw.number)
        if blocks_in:
            repaired = repair_blocks(blocks_in, cfg)
            by_id = {b.id: b.text for b in repaired.blocks if b.id}
            text = layout.reassemble_from_blocks(by_id, page_number=raw.number)
            # تشخيص نهائي على المُجمَّع — السطور أُصلحت؛ لا عكس جماعيّ قسري
            final = repair_text(text, cfg)
            notes = list(dict.fromkeys([*final.notes, *layout.notes]))  # فريد مع حفظ الترتيب
            notes.append(
                f"بنيويّ: {layout.n_columns} عمود، "
                f"{len(layout.tables)} جدول، "
                f"{len(layout.headers)} ترويسة، {len(layout.footers)} تذييل"
            )
            result = RepairResult(
                text=final.text,
                original=raw.text,
                diagnosis=final.diagnosis,
                stages_applied=final.stages_applied,
                confidence=min(repaired.confidence, final.confidence),
                notes=notes,
            )
            if raw.is_empty and raw.has_images:
                result.notes.append(
                    "صفحة بلا نصّ وفيها صور — ممسوحة ضوئياً على الأرجح"
                )
            return PageResult(
                page_number=raw.number,
                repair=result,
                fonts=raw.fonts,
                layout=layout,
                blocks=repaired,
                n_columns=layout.n_columns,
                tables=_repaired_tables(layout, by_id, raw.number),
            )

    # مسار خطّيّ — صفحة عمود واحد بلا ترويسة/جدول مميّزين
    source = layout.plain_text if layout is not None else raw.text
    result = repair_text(source, cfg)
    if raw.is_empty and raw.has_images:
        result.notes.append("صفحة بلا نصّ وفيها صور — ممسوحة ضوئياً على الأرجح")
    if layout is not None and layout.notes:
        result.notes.extend(layout.notes)
    return PageResult(
        page_number=raw.number,
        repair=result,
        fonts=raw.fonts,
        layout=layout,
        n_columns=layout.n_columns if layout else 1,
        tables=_raw_tables(layout) if layout else [],
    )


def _repaired_tables(layout, by_id: dict[str, str], page_number: int) -> list[list[list[str]]]:
    out: list[list[list[str]]] = []
    for ti, table in enumerate(layout.tables):
        grid = [
            [
                by_id.get(f"p{page_number}t{ti}r{i}c{j}", cell)
                for j, cell in enumerate(row)
            ]
            for i, row in enumerate(table.rows)
        ]
        out.append(grid)
    return out


def _raw_tables(layout) -> list[list[list[str]]]:
    return [t.rows for t in layout.tables]

