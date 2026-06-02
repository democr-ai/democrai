from __future__ import annotations

from types import SimpleNamespace

from extractors.docling.extractor import DoclingExtractor


def test_docling_rapidocr_install_warms_docling_with_fake_pdf(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "extractors.docling.extractor.install_torch_runtime",
        lambda force: calls.append(("torch", force))
        or SimpleNamespace(index_url="https://download.pytorch.org/whl/cpu"),
    )
    monkeypatch.setattr(
        "extractors.docling.extractor.write_installed_torch_constraint",
        lambda: calls.append(("constraint",)) or "/tmp/constraint.txt",
    )
    monkeypatch.setattr(
        "extractors.docling.extractor.install_python_packages",
        lambda packages, **kwargs: calls.append(("packages", packages, kwargs)),
    )
    monkeypatch.setattr(
        DoclingExtractor,
        "_download_docling_artifacts",
        classmethod(lambda cls, *, ocr_engine: calls.append(("artifacts", ocr_engine))),
    )
    monkeypatch.setattr(
        DoclingExtractor,
        "_warmup_docling_models",
        classmethod(lambda cls, *, ocr_engine: calls.append(("warmup", ocr_engine))),
    )

    DoclingExtractor._install(force=True, install_config={"ocr_engine": "rapidocr"})

    assert calls == [
        ("torch", True),
        ("constraint",),
        (
            "packages",
            ["docling[rapidocr]"],
            {
                "modules": ["docling", "rapidocr", "onnxruntime"],
                "force": True,
                "extra_index_url": "https://download.pytorch.org/whl/cpu",
                "extra_pip_args": ["--constraint", "/tmp/constraint.txt"],
            },
        ),
        ("artifacts", "rapidocr"),
        ("warmup", "rapidocr"),
    ]
