#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

# Allow running the script from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from democrai.core.runtime.foundation.paths import get_base_dir


def _configure_project_cache(cache_root: Path) -> None:
    docling_cache = cache_root / "docling"
    docling_models = docling_cache / "models"
    hf_cache = cache_root / "hf"
    onnx_cache = cache_root / "onnx"
    surya_cache = cache_root / "surya" / "models"
    for path in (cache_root, docling_cache, docling_models, hf_cache, onnx_cache, surya_cache):
        path.mkdir(parents=True, exist_ok=True)

    os.environ["XDG_CACHE_HOME"] = str(cache_root)
    os.environ["HF_HOME"] = str(hf_cache)
    os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_cache)
    os.environ["TRANSFORMERS_CACHE"] = str(hf_cache)
    os.environ["DOCLING_CACHE_DIR"] = str(docling_cache)
    os.environ["DOCLING_ARTIFACTS_PATH"] = str(docling_models)
    os.environ["ORT_CACHE_DIR"] = str(onnx_cache)
    os.environ["MODEL_CACHE_DIR"] = str(surya_cache)


def _preload_docling_models(cache_root: Path) -> None:
    artifacts_dir = cache_root / "docling" / "models"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docling-tools",
        "models",
        "download",
        "-o",
        str(artifacts_dir),
        "layout",
        "tableformer",
        "code_formula",
        "picture_classifier",
        "rapidocr",
    ]
    print(f"[preload] docling models: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _preload_hf_repos(repos: list[str]) -> None:
    if not repos:
        return
    from huggingface_hub import snapshot_download

    for repo in repos:
        repo_id = str(repo or "").strip()
        if not repo_id:
            continue
        print(f"[preload] huggingface snapshot: {repo_id}")
        snapshot_download(repo_id=repo_id, revision="main")


def _preload_spacy_model(model_name: str) -> None:
    target = str(model_name or "").strip()
    if not target:
        return
    cmd = [sys.executable, "-m", "spacy", "download", target]
    print(f"[preload] spacy model: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def _build_sample_pdf(path: Path) -> None:
    image = Image.new("RGB", (1400, 900), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    draw.text((50, 80), "Docling preload check", fill=(0, 0, 0))
    draw.text((50, 140), "This page is used to warm model cache.", fill=(0, 0, 0))
    image.save(path, "PDF")


def _warm_docling_pipeline(sample_pdf: Path) -> None:
    del sample_pdf
    raise RuntimeError(
        "knowledge_docling_preload_placeholder "
        "reason=legacy_knowledge_extractors_reference_removed"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Preload Docling artifacts into project cache.")
    parser.add_argument(
        "--cache-root",
        default="",
        help="Cache root directory. Default: <project>/.cache",
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=[],
        help="Extra HuggingFace repo to preload (repeatable).",
    )
    args = parser.parse_args()

    base_dir = Path(get_base_dir())
    cache_root = Path(args.cache_root).expanduser().resolve() if str(args.cache_root).strip() else (base_dir / ".cache")
    _configure_project_cache(cache_root)
    print(f"[preload] cache_root={cache_root}")

    repos = list(args.repo or [])
    if not repos:
        repos = [
            "docling-project/docling-layout-heron",
            "sentence-transformers/all-MiniLM-L6-v2",
        ]
    try:
        _preload_docling_models(cache_root)
    except Exception as exc:
        print(f"[preload] warning docling model preload failed: {exc}", file=sys.stderr)

    try:
        _preload_hf_repos(repos)
    except Exception as exc:
        print(f"[preload] warning huggingface preload failed: {exc}", file=sys.stderr)

    try:
        _preload_spacy_model("it_core_news_lg")
    except Exception as exc:
        print(f"[preload] warning spacy preload failed: {exc}", file=sys.stderr)

    with tempfile.TemporaryDirectory(prefix="docling-preload-", dir=str(cache_root)) as tmpdir:
        sample_pdf = Path(tmpdir) / "sample.pdf"
        _build_sample_pdf(sample_pdf)
        _warm_docling_pipeline(sample_pdf)

    print("[preload] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
