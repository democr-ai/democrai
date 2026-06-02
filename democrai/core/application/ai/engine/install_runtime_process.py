"""One-shot OS process for a single engine installation."""

from __future__ import annotations

import argparse
import json
import os
import traceback
from pathlib import Path

from democrai.core.application.ai.engine.install_worker_process import (
    _bootstrap_context,
)
from democrai.core.application.ai.engine.runtime.environment import application_root
from democrai.core.application.ai.engine.runtime import install_engine_runtime
from democrai.core.runtime.foundation.app import (
    request_context_from_dict,
    reset_req_ctx,
    set_req_ctx,
)
from democrai.core.runtime.foundation.paths import (
    ENGINES_PATH_ENV,
    EXTRACTORS_PATH_ENV,
    MODULES_PATH_ENV,
)


RESULT_PREFIX = "__DEMOCRAI_ENGINE_INSTALL_RESULT__="
ERROR_PREFIX = "__DEMOCRAI_ENGINE_INSTALL_ERROR__="


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-id", required=True)
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--source-node-id", default="")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    root = Path(application_root())
    os.environ.setdefault(MODULES_PATH_ENV, str(root / "modules"))
    os.environ.setdefault(ENGINES_PATH_ENV, str(root / "engines"))
    os.environ.setdefault(EXTRACTORS_PATH_ENV, str(root / "extractors"))

    _bootstrap_context()
    request_context = request_context_from_dict(
        json.loads(str(os.environ.get("DEMOCRAI_REQUEST_CONTEXT") or "{}"))
    )
    req_token = set_req_ctx(request_context) if request_context is not None else None
    try:
        result = install_engine_runtime(
            engine_id=args.engine_id,
            force=args.force,
            node_id=args.node_id,
            event_id=args.event_id,
            source_node_id=args.source_node_id or None,
        )
        print(RESULT_PREFIX + json.dumps(result, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        traceback.print_exc()
        print(
            ERROR_PREFIX
            + json.dumps({"error": str(exc) or exc.__class__.__name__}, sort_keys=True),
            flush=True,
        )
        return 1
    finally:
        if req_token is not None:
            reset_req_ctx(req_token)


if __name__ == "__main__":
    raise SystemExit(main())
