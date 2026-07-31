"""
إضافة MarkItDown: بعد التحويل إلى Markdown، مرِّر النص على arafix.

التسجيل عبر entry point::

    [project.entry-points."markitdown.plugin"]
    arafix = "arafix.integrations.markitdown_plugin"

الاستعمال::

    from markitdown import MarkItDown
    md = MarkItDown(enable_plugins=True)
    result = md.convert("thesis.pdf")
    # result.markdown / text_content مُصلَح عربياً

لا تُحمَّل تبعيّة MarkItDown إلا عند استدعاء ``register_converters``.
النواة تبقى بلا تبعيّات.
"""

from __future__ import annotations

import contextlib
import os
import tempfile
from typing import Any, BinaryIO

__plugin_interface_version__ = 1

__all__ = [
    "__plugin_interface_version__",
    "register_converters",
    "ArafixPostProcessorConverter",
]


def register_converters(markitdown: Any, **kwargs: Any) -> None:
    """يستدعيه MarkItDown عند ``enable_plugins=True``."""
    # أولوية منخفضة نسبياً: نلتفّ على ناتج المحوّلات لا نستبدلها كلها.
    # نسجّل غلافاً يشتغل على PDF أولاً (أعلى أثر عربيّ)، وpost-process عاماً
    # عبر تحويل ثم إصلاح — انظر ArafixPdfRepairConverter.
    markitdown.register_converter(
        ArafixPostProcessorConverter(
            prefer_arafix_pdf=kwargs.get("arafix_prefer_native_pdf", True),
            pipeline_config=kwargs.get("arafix_config"),
        ),
        priority=kwargs.get("arafix_priority", -0.5),
    )


class ArafixPostProcessorConverter:
    """
    محوّل MarkItDown:

    * **PDF** إن توفّر ``arafix[pdf]``: ``extract_pdf`` مباشرة (أفضل للعربية).
    * وإلا: يرفض الملف فيتركه لمحوّل MarkItDown الافتراضي.

    لإصلاح ناتج *أي* محوّل بعد التحويل، استخدم::

        from arafix.integrations import repair_extracted
        repair_extracted(result.text_content)
    """

    def __init__(
        self,
        *,
        prefer_arafix_pdf: bool = True,
        pipeline_config: Any = None,
    ) -> None:
        self.prefer_arafix_pdf = prefer_arafix_pdf
        self.pipeline_config = pipeline_config

    def accepts(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> bool:
        if not self.prefer_arafix_pdf:
            return False
        ext = (getattr(stream_info, "extension", None) or "").lower()
        mime = (getattr(stream_info, "mimetype", None) or "").lower()
        if ext == ".pdf" or mime in ("application/pdf", "application/x-pdf"):
            try:
                from arafix.extractors import PyMuPDFExtractor

                return PyMuPDFExtractor.available()
            except Exception:
                return False
        return False

    def convert(
        self,
        file_stream: BinaryIO,
        stream_info: Any,
        **kwargs: Any,
    ) -> Any:
        from markitdown import DocumentConverterResult

        from arafix.pipeline import PipelineConfig, extract_pdf

        # MarkItDown يمرّر مساراً أحياناً عبر stream_info.local_path
        path = getattr(stream_info, "local_path", None) or kwargs.get("file_path")
        tmp_path = None
        if not path:
            data = file_stream.read()
            with contextlib.suppress(Exception):
                file_stream.seek(0)
            fd, tmp_path = tempfile.mkstemp(suffix=".pdf")
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            path = tmp_path

        try:
            cfg = self.pipeline_config or PipelineConfig()
            doc = extract_pdf(str(path), cfg)
            title = None
            # أوّل سطر غير فارغ كعنوان تقريبيّ — أفضل من لا شيء لـ LLM
            for line in doc.text.splitlines():
                if line.strip():
                    title = line.strip()[:120]
                    break
            md = doc.text
            # تلميح خفيف للنموذج دون إفساد المحتوى
            footer = (
                f"\n\n<!-- arafix confidence={doc.confidence:.3f} "
                f"pages={len(doc.pages)} extractor="
                f"{doc.metadata.get('extractor', '?')} -->\n"
            )
            return DocumentConverterResult(
                title=title,
                markdown=md + footer,
            )
        finally:
            if tmp_path:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_path)
