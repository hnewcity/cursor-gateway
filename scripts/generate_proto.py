#!/usr/bin/env python3.14
"""Regenerate checked-in Python protobuf classes with protoc 36.1 or later."""

import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
subprocess.run(
    [
        "protoc",
        f"--proto_path={root / 'src'}",
        f"--python_out={root / 'src'}",
        str(root / "src/cursor_gateway/proto/agent.proto"),
    ],
    check=True,
)
