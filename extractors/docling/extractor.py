from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import urlretrieve

from democrai.sdk.extractors import BaseExtractor, ExtractorResult, ExtractorSource
from democrai.sdk.dependencies import (
    fs_exists,
    fs_path,
    get_extractor_local_cache_path,
    install_python_packages,
    install_torch_runtime,
    write_installed_torch_constraint,
)


_DOCLING_VERSION = "2.97.0"
_DOCLING_TESSEROCR_PACKAGE = f"docling[tesserocr]=={_DOCLING_VERSION}"
_DOCLING_RAPIDOCR_PACKAGE = f"docling[rapidocr]=={_DOCLING_VERSION}"
_DOCLING_OCR_ENGINES = {"tesserocr", "rapidocr"}
_TORCH_PACKAGES = ("torch==2.10.0", "torchvision==0.25.0", "torchaudio==2.10.0")
_TORCH_MODULES = ("torch", "torchvision", "torchaudio")


class DoclingExtractor(BaseExtractor):
    extractor_id = "docling"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        install_config: dict[str, Any] | None = None,
    ) -> None:
        ocr_engine = str(
            (install_config or {}).get("ocr_engine") or "tesserocr"
        ).strip()
        if ocr_engine not in _DOCLING_OCR_ENGINES:
            raise ValueError(f"docling_ocr_engine_unsupported:{ocr_engine}")
        torch_plan = install_torch_runtime(
            packages=_TORCH_PACKAGES,
            modules=_TORCH_MODULES,
            force=force,
            clean_target=force,
        )
        torch_constraint = write_installed_torch_constraint(
            distributions=_TORCH_MODULES,
        )
        if ocr_engine == "tesserocr":
            install_python_packages(
                [
                    _DOCLING_TESSEROCR_PACKAGE,
                ],
                modules=["docling", "tesserocr"],
                force=force,
                allow_source=True,
                extra_index_url=torch_plan.index_url,
                extra_pip_args=["--constraint", torch_constraint],
            )
            cls._materialize_tesserocr_tessdata(
                install_config=dict(install_config or {})
            )
            cls._download_docling_artifacts(ocr_engine=ocr_engine)
            cls._warmup_docling_models(ocr_engine=ocr_engine)
            return
       
        install_python_packages(
            [
                _DOCLING_RAPIDOCR_PACKAGE,
            ],
            modules=["docling", "rapidocr", "onnxruntime"],
            force=force,
            allow_source=True,
            extra_index_url=torch_plan.index_url,
            extra_pip_args=["--constraint", torch_constraint],
        )
        cls._download_docling_artifacts(ocr_engine=ocr_engine)
        cls._warmup_docling_models(ocr_engine=ocr_engine)

    @classmethod
    def _materialize_tesserocr_tessdata(
        cls,
        *,
        install_config: dict[str, Any],
    ) -> None:
        target = cls._tessdata_path()
        os.makedirs(fs_path(target), exist_ok=True)
        print(f"Preparing Tesseract language data cache: {target}", flush=True)
        languages = cls._tesserocr_languages(install_config)
        for language in languages:
            destination = target / f"{language}.traineddata"
            if fs_exists(destination):
                continue
            source = (
                "https://raw.githubusercontent.com/tesseract-ocr/"
                f"tessdata_fast/main/{language}.traineddata"
            )
            urlretrieve(source, fs_path(destination))

    @staticmethod
    def _tesserocr_languages(install_config: dict[str, Any]) -> tuple[str, ...]:
        raw_languages = install_config.get("ocr_languages")
        if isinstance(raw_languages, str):
            items = [raw_languages]
        elif isinstance(raw_languages, list):
            items = raw_languages
        else:
            items = ["eng", "ita", "osd"]
        languages = tuple(
            str(item or "").strip().lower() for item in items if str(item or "").strip()
        )
        return languages or ("eng", "ita", "osd")

    @classmethod
    def _warmup_docling_models(cls, *, ocr_engine: str) -> None:
        print("Preparing Docling model cache", flush=True)
        pdf_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".pdf",
                prefix="docling-warmup-",
                delete=False,
            ) as handle:
                handle.write(cls._warmup_pdf_bytes())
                pdf_path = handle.name
            extractor = cls({"ocr_engine": ocr_engine, "ocr_enabled": True})
            extractor._convert_document(pdf_path)
        except Exception as exc:
            raise RuntimeError("docling_model_warmup_failed") from exc
        finally:
            if pdf_path:
                try:
                    Path(pdf_path).unlink(missing_ok=True)
                except Exception:
                    pass

    @staticmethod
    def _warmup_pdf_bytes() -> bytes:
        return (
            b"%PDF-1.4\n"
            b"1 0 obj\n"
            b"<< /Type /Catalog /Pages 2 0 R >>\n"
            b"endobj\n"
            b"2 0 obj\n"
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>\n"
            b"endobj\n"
            b"3 0 obj\n"
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
            b"endobj\n"
            b"4 0 obj\n"
            b"<< /Length 44 >>\n"
            b"stream\n"
            b"BT /F1 12 Tf 20 120 Td (Docling warmup) Tj ET\n"
            b"endstream\n"
            b"endobj\n"
            b"5 0 obj\n"
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\n"
            b"endobj\n"
            b"xref\n"
            b"0 6\n"
            b"0000000000 65535 f \n"
            b"0000000009 00000 n \n"
            b"0000000058 00000 n \n"
            b"0000000115 00000 n \n"
            b"0000000241 00000 n \n"
            b"0000000335 00000 n \n"
            b"trailer\n"
            b"<< /Size 6 /Root 1 0 R >>\n"
            b"startxref\n"
            b"405\n"
            b"%%EOF\n"
        )

    @classmethod
    def _download_docling_artifacts(cls, *, ocr_engine: str) -> None:
        artifacts_path = cls._docling_artifacts_path()
        os.makedirs(fs_path(artifacts_path), exist_ok=True)
        print(f"Preparing Docling artifacts cache: {artifacts_path}", flush=True)
        try:
            from docling.utils import model_downloader
        except Exception as exc:
            raise RuntimeError("docling_model_downloader_unavailable") from exc
        try:
            model_downloader.download_models(
                output_dir=Path(fs_path(artifacts_path)),
                with_layout=True,
                with_tableformer=True,
                with_easyocr=False,
                with_rapidocr=ocr_engine == "rapidocr",
                with_code_formula=True,
                with_picture_classifier=False,
            )
        except Exception as exc:
            raise RuntimeError("docling_artifacts_download_failed") from exc

    @classmethod
    def _cache_root(cls) -> Path:
        return get_extractor_local_cache_path(cls.extractor_id)

    @classmethod
    def _docling_artifacts_path(cls) -> Path:
        return cls._cache_root() / "docling" / "models"

    @classmethod
    def _tessdata_path(cls) -> Path:
        return cls._cache_root() / "tessdata"

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        missing_local = cls._missing_modules(("docling", "docling"))
        if not cls._docling_version_matches():
            missing_local.append(f"docling=={_DOCLING_VERSION}")
        has_tesserocr = not cls._missing_modules(("tesserocr", "tesserocr"))
        has_rapidocr = not cls._missing_modules(
            ("rapidocr", "rapidocr"),
            ("onnxruntime", "onnxruntime"),
        )
        if not has_tesserocr and not has_rapidocr:
            missing_local.append("tesserocr or rapidocr")
        missing_local.extend(cls._missing_modules(("torch", "PyTorch runtime")))
        return cls._build_ready_payload(
            missing_local=missing_local,
            ok_message="Docling extractor ready",
            error_message="Docling extractor requires local dependencies",
        )

    @staticmethod
    def _docling_version_matches() -> bool:
        try:
            spec = importlib.util.find_spec("docling")
            origin = str(getattr(spec, "origin", "") or "").strip() if spec else ""
            if not origin:
                return False
            target = Path(origin).resolve().parent.parent
            versions = {
                str(distribution.version or "").strip()
                for distribution in importlib.metadata.distributions(path=[str(target)])
                if str(distribution.metadata.get("Name") or "")
                .strip()
                .lower()
                .replace("_", "-")
                == "docling"
            }
            return versions == {_DOCLING_VERSION}
        except Exception:
            return False

    def _extract_source(self, source: ExtractorSource) -> ExtractorResult:
        file_path = self._materialize_source_to_path(source)
        document = self._convert_document(file_path)
        markdown = self._export_markdown(document)
        chunks = self._extract_chunks(document, source=source)
        index = self._extract_index(chunks=chunks, source=source)
        tables = self._extract_tables(document, source=source)
        formulas = self._extract_formulas(document, source=source)
        return ExtractorResult(
            source=source,
            structure={
                "type": "document",
                "name": source.name,
                "source": source.source,
                "mime_type": source.mime_type,
                "chunk_count": len(chunks),
                "index_count": len(index),
                "table_count": len(tables),
                "formula_count": len(formulas),
            },
            markdown_content=markdown,
            chunks=chunks,
            index=index,
            formulas=formulas,
            tables=tables,
            images=[],
        )

    def _convert_document(self, file_path) -> Any:
        try:
            from docling.document_converter import DocumentConverter
        except Exception as exc:
            raise RuntimeError(
                "Docling is required to use the docling extractor."
            ) from exc

        converter = DocumentConverter(
            format_options=self._build_format_options(),
        )
        conversion = converter.convert(str(file_path))
        document = getattr(conversion, "document", None)
        if document is None:
            raise RuntimeError(f"docling_document_missing:{file_path}")
        return document

    def _build_format_options(self) -> dict[Any, Any] | None:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import PdfFormatOption
        except Exception:
            return None

        options = PdfPipelineOptions()
        if hasattr(options, "artifacts_path"):
            options.artifacts_path = self._docling_artifacts_path()
        if hasattr(options, "do_ocr"):
            options.do_ocr = bool(self._config.get("ocr_enabled", True))
        if hasattr(options, "ocr_options"):
            options.ocr_options = self._build_ocr_options()
        for attr_name in (
            "do_formula_enrichment",
            "do_formula_extraction",
            "do_code_enrichment",
            "do_code_extraction",
        ):
            if hasattr(options, attr_name):
                setattr(options, attr_name, True)
        try:
            return {
                InputFormat.PDF: PdfFormatOption(pipeline_options=options),
            }
        except Exception:
            return None

    def _build_ocr_options(self) -> Any:
        ocr_engine = str(self._config.get("ocr_engine") or "tesserocr").strip()
        if ocr_engine == "tesserocr":
            from docling.datamodel.pipeline_options import TesseractOcrOptions

            return TesseractOcrOptions(path=str(self._tessdata_path()))
        if ocr_engine == "rapidocr":
            from docling.datamodel.pipeline_options import RapidOcrOptions

            return RapidOcrOptions()
        raise ValueError(f"docling_ocr_engine_unsupported:{ocr_engine}")

    @staticmethod
    def _export_markdown(document: Any) -> str:
        exporter = getattr(document, "export_to_markdown", None)
        if callable(exporter):
            return str(exporter() or "").strip()
        return ""

    def _extract_chunks(
        self, document: Any, *, source: ExtractorSource
    ) -> list[dict[str, Any]]:
        try:
            from docling.chunking import HierarchicalChunker
        except Exception:
            return self._chunk_text(
                self._export_markdown(document),
                chunk_size=int(self._config.get("chunk_size", 1200)),
                overlap=int(self._config.get("chunk_overlap", 150)),
                source_name=source.name,
            )

        chunker = HierarchicalChunker(merge_list_items=True)
        items: list[dict[str, Any]] = []
        try:
            iterator = chunker.chunk(dl_doc=document)
        except Exception:
            iterator = []
        for index, chunk in enumerate(iterator):
            payload = self._chunk_payload(chunk)
            text = str(payload.get("text") or "").strip()
            if not text:
                continue
            meta = dict(payload.get("meta") or {})
            headings = [
                str(item).strip()
                for item in list(meta.get("headings") or [])
                if str(item).strip()
            ]
            items.append(
                {
                    "id": f"{source.name}:{index}",
                    "chunk_index": index,
                    "text": text,
                    "headings": headings,
                    "heading": headings[0] if headings else "",
                    "source": source.source,
                    "meta": meta,
                }
            )
        return items

    def _extract_index(
        self, *, chunks: list[dict[str, Any]], source: ExtractorSource
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for chunk in chunks:
            heading = str(chunk.get("heading") or "").strip()
            if not heading or heading in seen:
                continue
            seen.add(heading)
            items.append(
                {
                    "id": f"{source.source}:heading:{len(items)}",
                    "title": heading,
                    "level": 1,
                    "source": source.source,
                }
            )
        if items:
            return items
        return self._build_simple_index(
            source.name, chunks=chunks, source=source.source
        )

    def _extract_tables(
        self, document: Any, *, source: ExtractorSource
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for doc_item in self._iterate_doc_items(document):
            rendered = self._render_doc_item(doc_item)
            if not rendered or "|" not in rendered:
                continue
            items.append(
                {
                    "id": f"{source.source}:table:{len(items)}",
                    "text": rendered,
                    "source": source.source,
                }
            )
        return items

    def _extract_formulas(
        self, document: Any, *, source: ExtractorSource
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for doc_item in self._iterate_doc_items(document):
            if not self._is_formula_item(doc_item):
                continue
            rendered = self._render_doc_item(doc_item)
            if not rendered:
                continue
            items.append(
                {
                    "id": f"{source.source}:formula:{len(items)}",
                    "text": rendered,
                    "source": source.source,
                }
            )
        return items

    @staticmethod
    def _chunk_payload(chunk: Any) -> dict[str, Any]:
        exporter = getattr(chunk, "export_json_dict", None)
        if callable(exporter):
            try:
                payload = exporter()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        dumper = getattr(chunk, "model_dump", None)
        if callable(dumper):
            try:
                payload = dumper()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        return {}

    @staticmethod
    def _iterate_doc_items(document: Any) -> list[Any]:
        iterator = getattr(document, "iterate_items", None)
        if not callable(iterator):
            return []
        try:
            entries = list(iterator())
        except Exception:
            return []
        # docling's iterate_items() yields (item, level) tuples, not bare items;
        # unpack so table/formula detection sees the real NodeItem.
        return [
            entry[0] if isinstance(entry, tuple) and entry else entry
            for entry in entries
        ]

    @staticmethod
    def _render_doc_item(doc_item: Any) -> str:
        exporter = getattr(doc_item, "export_to_markdown", None)
        if callable(exporter):
            try:
                return str(exporter() or "").strip()
            except Exception:
                return ""
        text = getattr(doc_item, "text", None)
        return str(text or "").strip()

    @staticmethod
    def _is_formula_item(doc_item: Any) -> bool:
        candidates = [
            getattr(doc_item, "label", None),
            getattr(doc_item, "type", None),
            getattr(doc_item, "kind", None),
            doc_item.__class__.__name__,
        ]
        normalized = " ".join(
            str(candidate).strip().lower() for candidate in candidates if candidate
        )
        return "formula" in normalized or "equation" in normalized
