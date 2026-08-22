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
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .cmap import GlyphMap
    from .extractors.base import RawPage

from .audit import (
    AuditMode,
    AuditTrail,
    EvidenceItem,
    Patch,
    RepairAudit,
    RepairDecision,
    sha256_text,
)
from .context import DocumentContext
from .diagnose import DEFAULT_THRESHOLDS, detect_mojibake, detect_visual_order, diagnose
from .evidence import (
    CandidateGenerator,
    EvidenceFusion,
    NegativeEvidenceModel,
)
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
    fold_simple_forms,
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
from .unicode_tables import is_arabic, is_presentation_form

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

    #: إنقاذ الانعكاس الجزئي: صفحةٌ سليمة إجمالاً قد تخفي سطراً معكوساً
    #: (ترويسة، عنوان، اقتباس) يغرقَه التصويتُ الصفحيّ فيمرّ بلا علاج.
    #: عند التفعيل تُفحص كل سطرٍ بالشواهد والعتبة نفسيهما، ولا يُعكس
    #: إلا ما اجتازها وحده. مطفأ افتراضياً حتى يُقاس أثره على مدوناتك.
    rescue_mixed_lines: bool = False

    #: نمط ثقة لام-ألف: ``classic`` يعاقب كل مشتبهٍ متبقٍّ ‎0.1 مطلقاً —
    #: ولا يُفعَّل العقاب إلا إن وقع إصلاح في النداء نفسه. ``density``
    #: ينسّب العقوبة لكثافة المشتبهات لكل مئة كلمة (‎0.02 لكل ١٪) بحدٍّ
    #: أدنى 0.35، ويطبّقها ولو بلا إصلاح — الصفحات الطويلة لا تُعاقَب
    #: زوراً على مشتبهاتها القليلة، والقصيرة لا تفلت بعشراتها.
    confidence_mode: str = "classic"

    #: ربطُ الحركات العالقة بين قاعدتين بالقاعدة **التالية** عند العكس —
    #: لِمَ تُفعِّله؟ لأن مولِّدَ استخراجك ينتج انعكاساً خاماً للمحارف
    #: على النص المُشكَّل (MuPDF مثلاً: «ةَّيم» حيث كانت «ميَّة»). ولِمَ
    #: لا يُستنتَج تلقائياً؟ لأن ثبوت الانعكاس لا يثبت الاتفاقية: الملفات
    #: الحديثة تحافظ على العناقيد ويُفسدها الربط الأمامي. جرِّبهما على
    #: عينة من ملفاتك وثبّت الأفضل (قياساً: ‎11.6% ← ‎2% على ملفٍ رقمي،
    #: و‎12.5% ← ‎<3% على ملفٍّ مُشكَّل معكوس).
    forward_flank_marks: bool = False

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

    #: احتفظ بـbbox الرسم الأصلي للـRAG المكاني. مطفأ افتراضياً لتجنب كلفة إضافية.
    preserve_spatial_bboxes: bool = False

    #: Provenance اختياري: off (افتراضي)، summary، أو full مع رقعة قابلة للعكس.
    audit_mode: AuditMode | str = AuditMode.OFF

    #: نموذج سياق وثيقة اختياري؛ لا يعمل إلا عند تفعيل العلم صراحةً.
    context_model: DocumentContext | None = None
    enable_context_scoring: bool = False

    #: مكوّنات evidence اختيارية تُستخدم عند بناء DocumentContext تلقائياً.
    candidate_generator: CandidateGenerator | None = None
    evidence_fusion: EvidenceFusion | None = None
    negative_evidence: NegativeEvidenceModel | None = None


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


def _line_reversal_score(line: str) -> tuple[float, list]:
    """درجة الاتجاه لسطرٍ واحد بطبقتَي الفحص نفسِهما (مطابقٌ لعقلية diagnose)."""
    return detect_visual_order(fold_simple_forms(line), shaped_source=line)


#: علامات نهاية الجملة — في النص المنطقي تختم السطر لا تبدأه.
_LINE_TERMINATORS = ".؟!؛"


def _punctuation_position_hint(text: str) -> dict[str, int] | None:
    """
    ملاحظة تشخيصية (لا تدخل التصويت): نقاطُ الجملة في رؤوس الأسطر.

    في التخزين المعكوس بصرياً تقع نقطةُ نهاية الجملة العربية عند **بداية**
    السطر بدل خاتمته. تُستعمل كسجل امتناعٍ إضافي في التقرير فقط —
    شاهدٌ رابع محتمل لم يُوزَن بعد، ونعرضه بدل إخفائه.
    """
    starts = ends = 0
    for ln in text.splitlines():
        s = ln.strip()
        if len(s) < 12:
            continue  # الأسطر القصيرة (عناوين، أرقام) بلا شهادة
        if s[0] in _LINE_TERMINATORS:
            starts += 1
        if s[-1] in _LINE_TERMINATORS:
            ends += 1
    if starts + ends == 0:
        return None
    return {
        "lines_starting_with_terminator": starts,
        "lines_ending_with_terminator": ends,
    }


def _lam_alef_confidence(
    rep, text: str, cfg: PipelineConfig
) -> float:
    """
    ثقة مرحلة لام-ألف بحسب ``cfg.confidence_mode``.

    * ``classic``: سلوك ١.٠ التاريخي حرفياً — العقاب (‎0.1 لكل مشتبه،
      حد أدنى 0.35) لا يُفعَّل إلا إن وقع إصلاحٌ في النداء نفسه.
    * ``density``: العقوبة كثافية (‎0.02 لكل ١٪ مشتبهات من الكلمات،
      حد أدنى 0.35) وتطبَّق ولو بلا إصلاح.
    """
    if cfg.confidence_mode == "classic":
        return rep.confidence
    if cfg.confidence_mode != "density":
        raise ValueError(
            f"confidence_mode غير معروف: {cfg.confidence_mode!r} — classic|density"
        )
    n_words = max(1, len(_ARABIC_WORD.findall(text)))
    density_pct = 100.0 * rep.suspects_left / n_words
    return round(max(0.35, 1.0 - 0.02 * density_pct), 3)


def _rescue_mixed_direction_lines(
    text: str,
    shaped_source: str,
    th: dict[str, float],
) -> tuple[str, int, float, list[EvidenceItem]] | None:
    """
    إنقاذ الانعكاس الجزئي — يعالج ما يغارقه التصويت الصفحي.

    صفحةٌ سليمة إجمالاً قد تخفي سطراً معكوساً واحداً (ترويسة، عنوان،
    اقتباساً لاتينياً مُعكَس عربيُّه). الشواهد تُجمَع على مستوى النص كله،
    فتُغرق الأقلية المعكوسة تحت العتبة فيمرّ السطرُ بلا علاج. هنا يُفحص
    كل سطرٍ وحده بالشواهد والعتبة نفسيهما، ولا يُعكس إلا من اجتازها.

    البوابات الثلاث:
      * الصفحة كلها لم تجتز العتبة (وإلا لانعكست كاملةً قبل الوصول هنا).
      * السطر ذاته يجتاز العتبة نفسها فوقها.
      * كفاية العيّنة: بلا برهانِ وصلٍ لا يُحكم على سطرٍ أقلّ من
        ``min_arabic_chars`` — البرهانُ وحده يستغني عن العيّنة.

    :returns: (النص الجديد، عدد الأسطر المُنقَذة، أدنى درجةٍ بينها، شواهد)
              أو None إن لم يوجد ما يُنقذ.
    """
    lines = text.split("\n")
    if len(lines) < 2:
        return None  # سطرٌ واحد: قرار الصفحة هو قراره بديهياً

    src_lines = shaped_source.split("\n")
    aligned = len(src_lines) == len(lines)

    out = list(lines)
    fixed_count = 0
    weakest_score = 1.0
    evidence_items: list[EvidenceItem] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        shaped_line = src_lines[i] if aligned else line
        score, evs = _line_reversal_score(shaped_line)
        if score <= th["visual_order"]:
            continue
        proof = any(e.name == "joining_forms" and e.value > 0 for e in evs)
        arabic_chars = sum(1 for c in line if is_arabic(c) or is_presentation_form(c))
        if not proof and arabic_chars < th["min_arabic_chars"]:
            continue
        before_line = line
        out[i] = fix_order(line)
        if out[i] == before_line:
            continue  # لا شيء تغيّر فعلاً — لا نشاهد إنقاذاً وهمياً
        fixed_count += 1
        weakest_score = min(weakest_score, abs(score))
        evidence_items.append(
            EvidenceItem(f"line-{i + 1}-order-score", score, detail=evs[0].detail if evs else "")
        )

    if not fixed_count:
        return None
    return "\n".join(out), fixed_count, round(min(1.0, weakest_score), 3), evidence_items


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
    audit = AuditTrail(text, cfg.audit_mode)

    original = text
    current = text
    stages: list[Stage] = []
    notes: list[str] = []

    # --- بوابة النظافة: قبل التشخيص، كي لا تشوّش الشواهد ---------------
    # Latin-1 mojibake may contain U+00AD (byte 0xAD). Preserve it until the
    # exact UTF-8 recovery path consumes the original byte sequence.
    protect_mojibake = (
        cfg.enable_mojibake_fix
        and "\u00ad" in current
        and detect_mojibake(current)[0]
    )
    if cfg.enable_hygiene:
        arts = count_artifacts(current)
        cleaned = sanitize_extraction(
            current,
            soft_hyphen_to=None if protect_mojibake else "-",
            strip_zero_width=cfg.normalize.strip_zero_width,
        )
        if cleaned != current:
            before = current
            current = cleaned
            stages.append(Stage.HYGIENE)
            audit.record(
                before,
                current,
                stage=Stage.HYGIENE.value,
                rule="SANITIZE_EXTRACTION",
                evidence=(
                    EvidenceItem(
                        "extraction-artifacts",
                        sum(arts.values()),
                        detail=(
                            "Unicode spaces, soft-hyphen, punctuation, replacement, "
                            "or zero-width artifacts"
                        ),
                    ),
                ),
            )
            bits = []
            if arts["nbsp_like"]:
                bits.append(f"{arts['nbsp_like']} مسافة يونيكود")
            if arts["soft_hyphen"] and not protect_mojibake:
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

    presentation_count = sum(0xFE70 <= ord(char) <= 0xFE7F for char in current)
    if audit.enabled and presentation_count and not dg.has(Defect.PRESENTATION_FORMS):
        audit.abstain(
            stage=Stage.NORMALIZE.value,
            rule="PRESENTATION_FORM_BELOW_THRESHOLD",
            decision=RepairDecision.UNCERTAIN,
            evidence=(
                EvidenceItem("presentation-form-count", presentation_count),
                EvidenceItem(
                    "arabic-sample-threshold",
                    th["min_arabic_chars"],
                    detail="Insufficient density for automatic normalization",
                ),
            ),
            metadata={"threshold": th["presentation_forms"]},
        )

    # --- الموجيبيك: يسبق كل شيء، فهو عطبٌ في الترميز لا في النص --------
    if cfg.enable_mojibake_fix and dg.has(Defect.MOJIBAKE):
        # diagnose() has already run the exact mojibake detector. For healthy
        # input, running it again is an expensive duplicate scan; only decode
        # a second time when the diagnosis established this defect.
        _is_moji, recovered, _ = detect_mojibake(current)
        if recovered:
            before = current
            current = recovered
            audit.record(
                before,
                current,
                stage=Stage.HYGIENE.value,
                rule="MOJIBAKE_UTF8_LATIN1_RECOVERY",
                evidence=(EvidenceItem("exact-mojibake-detector", True),),
            )
            notes.append("أُصلح موجيبيك (UTF-8 كان مفكوكاً بـ Latin-1)")
            dg = diagnose(current, th)  # كل تشخيصٍ سابق كان على نصٍّ مشوّه
    elif not cfg.enable_mojibake_fix and dg.has(Defect.MOJIBAKE):
        audit.abstain(
            stage=Stage.DIAGNOSE.value,
            rule="MOJIBAKE_FIX_DISABLED",
            decision=RepairDecision.UNCERTAIN,
            evidence=(EvidenceItem("mojibake-detected", True),),
        )
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
        before = current
        current = normalize_text(current, replace(cfg.normalize, expand_ligatures=False))
        stages.append(Stage.NORMALIZE)
        audit.record(
            before,
            current,
            stage=Stage.NORMALIZE.value,
            rule="FOLD_PRESENTATION_FORMS",
            evidence=(EvidenceItem("presentation-form-defect", True),),
        )
        notes.append("طُبِّعت الأشكال المفردة؛ أُبقيت الرباطات ذرّاتٍ حتى يستقرّ الترتيب")

    # --- الدرجة ٢: يُعاد التشخيص لأن الدرجة ١ غيّرت المعطيات ----------
    order_conf = 1.0
    if cfg.enable_reorder:
        score, order_evidence = detect_visual_order(current, shaped_source=shaped_source)
        order_audit_evidence = tuple(
            EvidenceItem(item.name, item.value, item.detail) for item in order_evidence
        )
        if cfg.force_reorder or score > th["visual_order"]:
            before = current
            # اتفاقية العلامات تمرَّر كما ضبطها المستعمل (انظر أعلاه).
            rcfg = replace(cfg.reorder, forward_flank_marks=cfg.forward_flank_marks)
            current = fix_order(current, rcfg)
            stages.append(Stage.REORDER)
            audit.record(
                before,
                current,
                stage=Stage.REORDER.value,
                rule="VISUAL_ORDER_REVERSAL",
                confidence=min(1.0, abs(score)) if not cfg.force_reorder else 0.5,
                evidence=(
                    EvidenceItem(
                        "visual-order-score",
                        score,
                        detail="Composite order detector score",
                    ),
                    *order_audit_evidence,
                ),
                metadata={"forced": cfg.force_reorder},
            )
            order_conf = min(1.0, abs(score)) if not cfg.force_reorder else 0.5
            notes.append(
                f"أُصلح الاتجاه (درجة {score:+.2f})"
                if not cfg.force_reorder
                else "أُصلح الاتجاه قسراً بأمر المستعمل — بلا شاهد"
            )
        else:
            # إنقاذ الانعكاس الجزئي: الصفحة لم تجتز العتبة إجمالاً، لكن
            # قد تخفي سطراً معكوساً يغارقه التصويت الصفحي.
            rescued: tuple[str, int, float, list[EvidenceItem]] | None = None
            if cfg.rescue_mixed_lines and "\n" in current:
                rescued = _rescue_mixed_direction_lines(current, shaped_source, th)
            if rescued is not None:
                before = current
                current, n_rescued, rescue_conf, rescue_evidence = rescued
                stages.append(Stage.REORDER)
                order_conf = rescue_conf
                audit.record(
                    before,
                    current,
                    stage=Stage.REORDER.value,
                    rule="MIXED_LINE_RESCUE",
                    confidence=order_conf,
                    evidence=(
                        EvidenceItem("rescued-lines", n_rescued),
                        EvidenceItem("page-score-below-threshold", round(score, 3)),
                        *rescue_evidence,
                    ),
                    metadata={"threshold": th["visual_order"]},
                )
                notes.append(
                    f"أُصلح الاتجاه في {n_rescued} سطرٍ معكوس داخل صفحةٍ "
                    "سالمة إجمالاً (إنقاذ مختلط)"
                )
            if audit.enabled and 0.20 <= abs(score) < th["visual_order"] and rescued is None:
                hint = _punctuation_position_hint(current)
                abstain_metadata: dict = {"threshold": th["visual_order"]}
                if hint is not None and hint["lines_starting_with_terminator"] > hint[
                    "lines_ending_with_terminator"
                ]:
                    abstain_metadata["punctuation_position_hint"] = hint
                audit.abstain(
                    stage=Stage.REORDER.value,
                    rule="VISUAL_ORDER_BELOW_THRESHOLD",
                    decision=RepairDecision.UNCERTAIN,
                    confidence=abs(score),
                    evidence=(
                        EvidenceItem(
                            "visual-order-score",
                            score,
                            detail=f"Below configured threshold {th['visual_order']:.2f}",
                        ),
                        *order_audit_evidence,
                    ),
                    metadata=abstain_metadata,
                )
            if rescued is None:
                notes.append(f"لم يُمسّ الاتجاه (درجة {score:+.2f} دون العتبة)")

    # --- الدرجة ١ب: الآن استقرّ الترتيب، فليُفكَّ الرباط بأمان ----------
    if cfg.enable_normalize and cfg.normalize.expand_ligatures:
        expanded = expand_deferred_forms(current)
        if expanded != current:
            before = current
            current = expanded
            stages.append(Stage.EXPAND_LIGATURES)
            audit.record(
                before,
                current,
                stage=Stage.EXPAND_LIGATURES.value,
                rule="EXPAND_DEFERRED_FORMS",
                evidence=(EvidenceItem("deferred-presentation-forms", True),),
            )
            notes.append("طُبِّع المؤجَّل (الرباطات والتشكيل الفاصل) بعد استقرار الترتيب")

    # --- ترقيع ما وَرِثناه معطوباً من أداةٍ أخرى ------------------------
    # القاطع (ألفان متجاورتان) يُصلَح بلا معجم. المُبهَم يحتاج معجماً
    # (مضمَّناً و/أو lexicon=). نوحّد البوابة مع repair_blocks: لا نشترط
    # Defect.LAM_ALEF_TRANSPOSED وحده — فالمُبهَم لا يُسجَّل قاطعاً.
    lam_conf = 1.0
    if cfg.confidence_mode not in ("classic", "density"):
        raise ValueError(
            f"confidence_mode غير معروف: {cfg.confidence_mode!r} — classic|density"
        )
    if cfg.enable_lam_alef_repair:
        vocab = _effective_lexicon(cfg)
        has_decisive = dg.has(Defect.LAM_ALEF_TRANSPOSED)
        has_ambiguous = int(dg.metrics.get("lam_alef_ambiguous", 0) or 0) > 0
        if has_decisive or has_ambiguous or vocab is not None:
            rep = repair_lam_alef_transposition(current, vocab)
            if rep.fixed_decisive or rep.fixed_by_lexicon:
                before = current
                current = rep.text
                stages.append(Stage.REPAIR_LAM_ALEF)
                lam_conf = _lam_alef_confidence(rep, current, cfg)
                audit.record(
                    before,
                    current,
                    stage=Stage.REPAIR_LAM_ALEF.value,
                    rule="LAM_ALEF_TRANSPOSITION",
                    confidence=lam_conf,
                    evidence=(
                        EvidenceItem("decisive-fixes", rep.fixed_decisive),
                        EvidenceItem("lexicon-fixes", rep.fixed_by_lexicon),
                    ),
                )
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
                if cfg.confidence_mode == "density":
                    # الكثافة تعاقب المشتبهات حتى بلا إصلاح: بقاءُ عشرات
                    # المُبهَمات في صفحةٍ شهادةٌ على فسادها لا على سلامتنا.
                    lam_conf = _lam_alef_confidence(rep, current, cfg)
                audit.abstain(
                    stage=Stage.REPAIR_LAM_ALEF.value,
                    rule="LAM_ALEF_AMBIGUOUS",
                    decision=RepairDecision.UNCERTAIN,
                    evidence=(EvidenceItem("suspect-count", rep.suspects_left),),
                    metadata={"suspect_words": rep.suspect_words[:5]},
                )
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
        audit.abstain(
            stage=Stage.REBUILD_CMAP.value,
            rule="BROKEN_CMAP_NOT_RESOLVED_IN_TEXT_MODE",
            decision=RepairDecision.UNSAFE,
            evidence=(EvidenceItem("broken-cmap-defect", True),),
        )
        notes.append(
            "كُشفت محارف PUA: الخريطة تالفة. النص وحده لا يُنجيك هنا — "
            "استعمل extract_pdf() لتُبنى الخريطة من الخط المضمَّن (الدرجة ٣)."
        )

    if dg.has(Defect.NO_TEXT_LAYER):
        audit.abstain(
            stage=Stage.OCR.value,
            rule="NO_TEXT_LAYER_OCR_NOT_SHIPPED",
            decision=RepairDecision.UNSAFE,
            evidence=(EvidenceItem("no-text-layer", True),),
        )
        notes.append("لا طبقة نصية — هذه حالة الدرجة ٤ (OCR) الوحيدة المشروعة.")

    # --- P1: PDF homoglyph fold (always, even when PF normalize was skipped) -
    if cfg.normalize.fold_pdf_homoglyphs:
        folded = fold_pdf_homoglyphs(current)
        if folded != current:
            before = current
            current = folded
            audit.record(
                before,
                current,
                stage=Stage.NORMALIZE.value,
                rule="FOLD_PDF_HOMOGLYPHS",
                evidence=(EvidenceItem("closed-pdf-homoglyph-map", True),),
            )
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
            before = current
            current = collapsed
            audit.record(
                before,
                current,
                stage=Stage.REPAIR_SPACING.value,
                rule="COLLAPSE_MIDWORD_SPACES",
                evidence=(EvidenceItem("arabic-neighbour-geometry", True),),
            )
            spacing_changed = True
            notes.append("طُويت مسافات هندسية داخل الكلمات (مو ضع → موضع، …)")

    if cfg.enable_pdf_confusion_repair:
        conf = repair_pdf_confusions(current)
        if conf.total:
            before = current
            current = conf.text
            stages.append(Stage.REPAIR_PDF_CONFUSIONS)
            audit.record(
                before,
                current,
                stage=Stage.REPAIR_PDF_CONFUSIONS.value,
                rule="CLOSED_PDF_CONFUSIONS",
                evidence=(
                    EvidenceItem("closed-list-total", conf.total),
                    EvidenceItem("al-meem-fixes", conf.al_meem_fixes),
                    EvidenceItem("ye-reh-fixes", conf.ye_reh_fixes),
                ),
            )
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
            before = current
            current = spaced
            audit.record(
                before,
                current,
                stage=Stage.REPAIR_SPACING.value,
                rule="CONTEXTUAL_ARABIC_SPACING",
                evidence=(EvidenceItem("arabic-punctuation-context", True),),
            )
            spacing_changed = True
            notes.append("أُصلحت حدود الترقيم العربية سياقياً (المادة(١٧) → المادة (١٧)، …)")
        if spacing_changed:
            stages.append(Stage.REPAIR_SPACING)

    if cfg.enable_context_scoring and cfg.context_model is not None:
        context_result = cfg.context_model.repair(current)
        if context_result.changed:
            before = current
            current = context_result.text
            stages.append(Stage.CONTEXT)
            audit.record(
                before,
                current,
                stage=Stage.CONTEXT.value,
                rule="DOCUMENT_CONTEXT_SCORING",
                confidence=context_result.confidence,
                evidence=(
                    EvidenceItem("accepted-context-decisions", context_result.accepted_count),
                    EvidenceItem("document-vocabulary", len(cfg.context_model.vocabulary)),
                    EvidenceItem("phrase-support", cfg.context_model.min_phrase_support),
                ),
                metadata={
                    "decisions": [
                        decision.to_dict() for decision in context_result.decisions
                    ],
                    "fusion_decisions": [
                        decision.to_dict()
                        for decision in context_result.fusion_decisions
                    ],
                },
            )
            notes.append(
                f"أُصلحت {context_result.accepted_count} كلمة بدليل معجم/عبارات الوثيقة"
            )
        elif cfg.enable_context_scoring and context_result.fusion_decisions:
            has_unsafe = any(
                decision.decision is RepairDecision.UNSAFE
                for decision in context_result.fusion_decisions
            )
            audit.abstain(
                stage=Stage.CONTEXT.value,
                rule="DOCUMENT_CONTEXT_EVIDENCE_ABSTENTION",
                decision=(
                    RepairDecision.UNSAFE if has_unsafe else RepairDecision.UNCERTAIN
                ),
                evidence=(
                    EvidenceItem(
                        "fusion-decisions",
                        len(context_result.fusion_decisions),
                        detail="Candidates were generated but no SAFE decision was authorized",
                        source="evidence-fusion",
                    ),
                ),
                metadata={
                    "fusion_decisions": [
                        decision.to_dict()
                        for decision in context_result.fusion_decisions
                    ]
                },
            )

    confidence = min(_final_confidence(dg, order_conf, stages), lam_conf)

    return RepairResult(
        text=current,
        original=original,
        diagnosis=dg,
        stages_applied=stages,
        confidence=confidence,
        notes=notes,
        audit=audit.finalize(current),
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
            before = br.repair.text
            br.repair.audit = _append_audit_after_text_change(
                br.repair.audit,
                original=br.repair.original,
                before=before,
                after=rep.text,
                rule="DOCUMENT_LEXICON_LAM_ALEF",
                evidence=(
                    EvidenceItem("lexicon-fixes", rep.fixed_by_lexicon),
                    EvidenceItem("decisive-fixes", rep.fixed_decisive),
                ),
            )
            br.repair.text = rep.text
            _refresh_diagnosis_after_text_change(br.repair, cfg)
            if rep.fixed_by_lexicon:
                br.repair.notes.append(
                    f"حُسم {rep.fixed_by_lexicon} موضعاً مُبهَماً بمعجم الوثيقة/النواة"
                )
            if Stage.REPAIR_LAM_ALEF not in br.repair.stages_applied:
                br.repair.stages_applied.append(Stage.REPAIR_LAM_ALEF)


def _refresh_diagnosis_after_text_change(repair: RepairResult, cfg: PipelineConfig) -> None:
    """Refresh derived diagnosis after a document-level text post-pass.

    The post-pass is already audited and must not rerun the full repair ladder;
    only derived diagnostics are refreshed here. Existing confidence remains a
    conservative lower bound for the earlier, evidence-bearing stages.
    """
    repair.diagnosis = diagnose(repair.text, {**DEFAULT_THRESHOLDS, **cfg.thresholds})
    repair.confidence = min(
        repair.confidence,
        _final_confidence(repair.diagnosis, repair.confidence, repair.stages_applied),
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


def _canonical_font_name(name: str) -> str:
    """مقارنة متسامحة لأسماء الخط بين texttrace وموارد PDF."""
    lowered = name.lower()
    lowered = re.sub(r"^[a-z]{6}\+", "", lowered)
    return re.sub(r"[^0-9a-z]", "", lowered).removeprefix("subset")


def _append_audit_abstention_after_text(
    audit: RepairAudit | None,
    *,
    original: str,
    after: str,
    decision: RepairDecision,
    evidence: Iterable[EvidenceItem],
    metadata: Mapping[str, object] | None = None,
) -> RepairAudit | None:
    """Append a no-op evidence decision while preserving page hashes and patch."""
    if audit is None:
        return None
    trail = AuditTrail(original, audit.mode)
    trail.abstain(
        stage=Stage.CONTEXT.value,
        rule="DOCUMENT_CONTEXT_EVIDENCE_ABSTENTION",
        decision=decision,
        evidence=evidence,
        metadata=metadata,
    )
    delta = trail.finalize(after)
    if delta is None:
        return audit
    offset = len(audit.events) + len(audit.abstentions)
    abstentions = tuple(
        replace(event, event_id=offset + event.event_id)
        for event in delta.abstentions
    )
    return replace(
        audit,
        repaired_sha256=sha256_text(after),
        abstentions=(*audit.abstentions, *abstentions),
    )


def _append_audit_after_text_change(
    audit: RepairAudit | None,
    *,
    original: str,
    before: str,
    after: str,
    rule: str,
    evidence: Iterable[EvidenceItem],
    stage: Stage = Stage.REPAIR_LAM_ALEF,
    metadata: Mapping[str, object] | None = None,
) -> RepairAudit | None:
    """Keep a page audit consistent after a later document-level repair."""
    if audit is None or before == after:
        return audit

    delta_trail = AuditTrail(before, audit.mode)
    delta_trail.record(
        before,
        after,
        stage=stage.value,
        rule=rule,
        evidence=evidence,
        metadata=metadata,
    )
    delta = delta_trail.finalize(after)
    if delta is None:
        return audit

    offset = len(audit.events) + len(audit.abstentions)
    events = tuple(replace(event, event_id=offset + event.event_id) for event in delta.events)
    abstentions = tuple(
        replace(event, event_id=offset + event.event_id) for event in delta.abstentions
    )
    return replace(
        audit,
        repaired_sha256=sha256_text(after),
        events=(*audit.events, *events),
        abstentions=(*audit.abstentions, *abstentions),
        patch=Patch.from_texts(original, after) if audit.mode is AuditMode.FULL else None,
    )


def _recover_broken_cmap_page(
    raw: RawPage, glyph_maps: Mapping[str, GlyphMap]
) -> tuple[RawPage, int]:
    """استبدل PUA/FFFD فقط حين يثبت glyph ID معناه في الخط المضمّن.

    لا توجد هنا محاولة لغوية أو تخمين اسم glyph: إن غاب المعرّف أو الخريطة
    الموثوقة يبقى النص كما هو وتستمر بوابة التشخيص في إظهار BROKEN_CMAP.
    """
    if not raw.glyphs or not glyph_maps:
        return raw, 0

    normalized = {_canonical_font_name(name): glyph_map for name, glyph_map in glyph_maps.items()}

    def find_map(font: str) -> GlyphMap | None:
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
        replacement = (
            glyph_map.lookup_id(glyph_id)
            if glyph_map is not None and glyph_id is not None
            else None
        )
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
                preserve_spatial_bboxes=cfg.preserve_spatial_bboxes,
                layout_config=cfg.layout_config,
            )
            if PyMuPDFExtractor.available()
            else get_extractor("auto")
        )
    else:
        from .extractors import REGISTRY

        cls = REGISTRY.get(cfg.extractor)
        if cls is not None and cfg.extractor == "pymupdf":
            extractor = cls(
                layout_mode=cfg.layout,
                preserve_spatial_bboxes=cfg.preserve_spatial_bboxes,
                layout_config=cfg.layout_config,
            )  # type: ignore[call-arg]
        else:
            extractor = get_extractor(cfg.extractor)

    page_cfg = replace(
        cfg,
        harvest_document_lexicon=False,
        enable_context_scoring=False,
    )

    doc = DocumentResult(path=path)
    doc.metadata["extractor"] = extractor.name
    doc.metadata["layout"] = cfg.layout

    glyph_maps: dict[str, GlyphMap] | None = None
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
                except Exception as exc:
                    glyph_maps = {}
                    # الفشل الصامت يُخفي سبب ضياع استرجاع الدرجة ٣؛ نسجّله
                    # كي يفحصه المستخدم في diagnose بدل التخمين.
                    doc.metadata["cmap_build_failed"] = str(exc)
            raw, count = _recover_broken_cmap_page(raw, glyph_maps)
            cmap_recovered += count
        page = _extract_one_page(raw, page_cfg)
        doc.pages.append(page)

    context_model = cfg.context_model
    if cfg.enable_context_scoring and context_model is None and doc.pages:
        context_model = DocumentContext.from_texts(
            (page.text for page in doc.pages),
            candidate_generator=cfg.candidate_generator,
            evidence_fusion=cfg.evidence_fusion,
            negative_evidence=cfg.negative_evidence,
        )
    if cfg.enable_context_scoring and context_model is not None and doc.pages:
        context_pages_touched = 0
        for page in doc.pages:
            before = page.repair.text
            context_result = context_model.repair(before)
            if not context_result.changed:
                if context_result.fusion_decisions:
                    has_unsafe = any(
                        decision.decision is RepairDecision.UNSAFE
                        for decision in context_result.fusion_decisions
                    )
                    page.repair.audit = _append_audit_abstention_after_text(
                        page.repair.audit,
                        original=page.repair.original,
                        after=before,
                        decision=(
                            RepairDecision.UNSAFE
                            if has_unsafe
                            else RepairDecision.UNCERTAIN
                        ),
                        evidence=(
                            EvidenceItem(
                                "fusion-decisions",
                                len(context_result.fusion_decisions),
                                detail=(
                                    "Candidates were generated but no SAFE decision "
                                    "was authorized"
                                ),
                                source="evidence-fusion",
                            ),
                        ),
                        metadata={
                            "fusion_decisions": [
                                decision.to_dict()
                                for decision in context_result.fusion_decisions
                            ]
                        },
                    )
                continue
            page.repair.audit = _append_audit_after_text_change(
                page.repair.audit,
                original=page.repair.original,
                before=before,
                after=context_result.text,
                stage=Stage.CONTEXT,
                rule="DOCUMENT_CONTEXT_SCORING",
                evidence=(
                    EvidenceItem("accepted-context-decisions", context_result.accepted_count),
                    EvidenceItem("document-vocabulary", len(context_model.vocabulary)),
                    EvidenceItem("phrase-support", context_model.min_phrase_support),
                ),
                metadata={
                    "decisions": [
                        decision.to_dict() for decision in context_result.decisions
                    ],
                    "fusion_decisions": [
                        decision.to_dict()
                        for decision in context_result.fusion_decisions
                    ],
                },
            )
            page.repair.text = context_result.text
            _refresh_diagnosis_after_text_change(page.repair, cfg)
            page.repair.stages_applied.append(Stage.CONTEXT)
            page.repair.notes.append(
                f"أُصلحت {context_result.accepted_count} كلمة بدليل معجم/عبارات الوثيقة"
            )
            context_pages_touched += 1
        doc.metadata["document_context_vocabulary_size"] = len(context_model.vocabulary)
        doc.metadata["document_context_pages_touched"] = context_pages_touched

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
            before = page.repair.text
            rep = repair_lam_alef_transposition(before, vocab)
            if rep.text != before:
                page.repair.audit = _append_audit_after_text_change(
                    page.repair.audit,
                    original=page.repair.original,
                    before=before,
                    after=rep.text,
                    rule="DOCUMENT_LEXICON_LAM_ALEF",
                    evidence=(
                        EvidenceItem("lexicon-fixes", rep.fixed_by_lexicon),
                        EvidenceItem("decisive-fixes", rep.fixed_decisive),
                    ),
                )
                page.repair.text = rep.text
                _refresh_diagnosis_after_text_change(page.repair, cfg)
                fixed_pages += 1
                page.repair.notes.append(
                    f"معجم الوثيقة/النواة: حُسم {rep.fixed_by_lexicon} مُبهَم "
                    f"+ {rep.fixed_decisive} قاطع عبر الصفحات"
                )
                if Stage.REPAIR_LAM_ALEF not in page.repair.stages_applied:
                    page.repair.stages_applied.append(Stage.REPAIR_LAM_ALEF)
        doc.metadata["document_lexicon_size"] = len(vocab)
        doc.metadata["document_lexicon_pages_touched"] = fixed_pages

    # --- بطاقة فساد المستند: أرقامٌ خام لمن يريد بوّابَه في أنبوبه ------
    # لا قرار هنا — قراءة فقط. RAG والمهام الدفعية يستفيدون من معرفة
    # «كم صفحةً لامسها أي سلك إصلاح» قبل أن يثقوا بالنص.
    _CONTENT_STAGES = {
        Stage.NORMALIZE,
        Stage.REORDER,
        Stage.EXPAND_LIGATURES,
        Stage.REPAIR_LAM_ALEF,
        Stage.REPAIR_SPACING,
        Stage.REPAIR_PDF_CONFUSIONS,
        Stage.CONTEXT,
    }
    stage_page_counts: dict[str, int] = {}
    pages_content_repaired = 0
    for page in doc.pages:
        page_stages = set(page.repair.stages_applied)
        for s in page_stages:
            stage_page_counts[s.value] = stage_page_counts.get(s.value, 0) + 1
        if page_stages & _CONTENT_STAGES:
            pages_content_repaired += 1
    doc.metadata["document_corruption_profile"] = {
        "pages_total": len(doc.pages),
        "pages_content_repaired": pages_content_repaired,
        "stage_page_counts": stage_page_counts,
    }

    doc.metadata["max_columns"] = max((p.n_columns for p in doc.pages), default=1)
    doc.metadata["table_count"] = sum(len(p.tables) for p in doc.pages)
    return doc


def _extract_one_page(raw, cfg: PipelineConfig) -> PageResult:
    """صفحة واحدة: بنيويّ إن لزم، وإلا خطّيّ كلاسيكي."""
    from .layout import Glyph, analyze_layout

    layout = raw.layout
    if raw.glyphs and layout is None:
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
            # Blocks already ran the content stages. Reassembly only needs
            # boundary hygiene; do not reverse/normalize the whole page again.
            final = repair_text(
                text,
                replace(
                    cfg,
                    enable_mojibake_fix=False,
                    enable_normalize=False,
                    enable_reorder=False,
                    enable_lam_alef_repair=False,
                    enable_pdf_confusion_repair=False,
                    enable_context_scoring=False,
                    harvest_document_lexicon=False,
                ),
            )
            page_audit = AuditTrail(raw.text, cfg.audit_mode)
            page_audit.record(
                raw.text,
                final.text,
                stage="layout",
                rule="STRUCTURAL_REASSEMBLY",
                evidence=(
                    EvidenceItem("columns", layout.n_columns),
                    EvidenceItem("tables", len(layout.tables)),
                    EvidenceItem("repaired-blocks", len(repaired.blocks)),
                ),
                metadata={
                    "inner_events": final.audit.changed_events if final.audit else 0,
                    "inner_abstentions": final.audit.abstention_count
                    if final.audit
                    else 0,
                },
            )
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
                audit=page_audit.finalize(final.text),
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
                width=raw.width,
                height=raw.height,
                tables=_repaired_tables(layout, by_id, raw.number),
            )

    # مسار خطّيّ — صفحة عمود واحد بلا ترويسة/جدول مميّزين
    source = layout.plain_text if layout is not None else raw.text
    result = repair_text(source, cfg)
    if raw.is_empty and raw.has_images:
        result.notes.append("صفحة بلا نصّ وفيها صور — ممسوحة ضوئياً على الأرجح")
    if layout is not None and layout.notes:
        result.notes.extend(layout.notes)
    page_audit = AuditTrail(raw.text, cfg.audit_mode)
    page_audit.record(
        raw.text,
        result.text,
        stage="linear",
        rule="LINEAR_PAGE_REPAIR",
        evidence=(EvidenceItem("layout-source", layout is not None),),
        metadata={
            "inner_events": result.audit.changed_events if result.audit else 0,
            "inner_abstentions": result.audit.abstention_count if result.audit else 0,
        },
    )
    result.audit = page_audit.finalize(result.text)
    return PageResult(
        page_number=raw.number,
        repair=result,
        fonts=raw.fonts,
        layout=layout,
        n_columns=layout.n_columns if layout else 1,
        width=raw.width,
        height=raw.height,
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

