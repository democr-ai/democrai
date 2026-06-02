from __future__ import annotations

import json
import subprocess
from pathlib import Path


def on_post_build(*, config) -> None:
    root_dir = Path(__file__).resolve().parents[2]
    script_path = root_dir / "docs" / "tools" / "render_shiki_codeblocks.mjs"
    site_dir = Path(config.site_dir).resolve()

    subprocess.run(
        ["node", str(script_path), str(site_dir)],
        cwd=root_dir,
        check=True,
    )

    search_index_path = site_dir / "search" / "search_index.json"
    if search_index_path.exists():
        search_index = json.loads(search_index_path.read_text(encoding="utf-8"))
        search_index_js = site_dir / "search" / "search_index.js"
        payload = json.dumps(search_index, ensure_ascii=False, separators=(",", ":"))
        search_index_js.write_text(
            f"window.__MKDOCS_SEARCH_DATA__ = {payload};\n",
            encoding="utf-8",
        )
