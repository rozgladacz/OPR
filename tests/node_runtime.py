from __future__ import annotations

import os
import shutil
from pathlib import Path


def resolve_node_binary() -> str:
    configured = os.getenv("NODE_BINARY", "").strip()
    if configured:
        configured_path = Path(configured)
        if configured_path.is_file():
            return str(configured_path)
        discovered = shutil.which(configured)
        if discovered:
            return discovered
        raise FileNotFoundError(
            f"NODE_BINARY is set but not executable: {configured!r}"
        )

    discovered = shutil.which("node")
    if discovered:
        return discovered

    raise FileNotFoundError(
        "Node.js executable not found. Install Node.js or set NODE_BINARY to node.exe path."
    )
