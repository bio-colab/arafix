"""
سجلّ المحرّكات.

إضافة محرّك جديد: اكتب صنفاً يحقّق `Extractor`، وسجّله بسطر واحد
هنا. لا يلزم تعديل شيء آخر في المكتبة — وهذا هو المقصود بـ«قابل
للتوسّع» عملياً لا شعاراً.
"""

from __future__ import annotations

from .base import Extractor, RawPage
from .pymupdf_extractor import PyMuPDFExtractor

__all__ = ["Extractor", "RawPage", "PyMuPDFExtractor", "REGISTRY", "get_extractor", "register"]


REGISTRY: dict[str, type[Extractor]] = {
    PyMuPDFExtractor.name: PyMuPDFExtractor,
}


def register(cls: type[Extractor]) -> type[Extractor]:
    """مزخرِف تسجيل — استعمله على صنف محرّكك الجديد."""
    REGISTRY[cls.name] = cls
    return cls


def get_extractor(name: str = "auto") -> Extractor:
    """
    يُرجع نسخةً من المحرّك المطلوب، أو أوّل متاحٍ إن كان `auto`.

    :raises RuntimeError: إن لم يتوفّر أيّ محرّك (لا تبعيّات مثبَّتة).
    """
    if name == "auto":
        for cls in REGISTRY.values():
            if cls.available():
                return cls()
        raise RuntimeError("لا محرّك متاح. ثبّت أحدها: pip install arafix[pdf]")

    if name not in REGISTRY:
        raise KeyError(f"محرّك مجهول: {name}. المتاح: {', '.join(REGISTRY)}")
    cls = REGISTRY[name]
    if not cls.available():
        raise RuntimeError(f"المحرّك {name} مسجَّل لكن تبعيّاته غير مثبَّتة")
    return cls()
