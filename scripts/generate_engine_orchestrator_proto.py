from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "democrai/core/application/ai/engine/orchestrator/proto"
PROTO_FILE = PROTO_DIR / "engine_orchestrator.proto"
GRPC_FILE = PROTO_DIR / "engine_orchestrator_pb2_grpc.py"


def main() -> int:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            "-I",
            str(PROTO_DIR),
            f"--python_out={PROTO_DIR}",
            f"--grpc_python_out={PROTO_DIR}",
            str(PROTO_FILE),
        ],
        check=True,
        cwd=str(ROOT),
    )
    text = GRPC_FILE.read_text(encoding="utf-8")
    text = text.replace(
        "import engine_orchestrator_pb2 as engine__orchestrator__pb2",
        "from democrai.core.application.ai.engine.orchestrator.proto import "
        "engine_orchestrator_pb2 as engine__orchestrator__pb2",
    )
    GRPC_FILE.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
