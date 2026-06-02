from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTO_DIR = ROOT / "democrai/core/application/runtime_prompt/grpc/proto"
PROTO_FILE = PROTO_DIR / "runtime_prompt.proto"
GRPC_FILE = PROTO_DIR / "runtime_prompt_pb2_grpc.py"


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
        "import runtime_prompt_pb2 as runtime__prompt__pb2",
        "from democrai.core.application.runtime_prompt.grpc.proto import "
        "runtime_prompt_pb2 as runtime__prompt__pb2",
    )
    GRPC_FILE.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
