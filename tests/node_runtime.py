from __future__ import annotations

import os
import shutil
from pathlib import Path


def _discover_local_node() -> str | None:
    project_root = Path(__file__).resolve().parents[1]
    node_root = project_root / ".tools" / "node"
    if not node_root.exists():
        return None

    candidates = sorted(
        node_root.rglob("node.exe"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return str(candidates[0])
    return None


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

    local_node = _discover_local_node()
    if local_node:
        return local_node

    raise FileNotFoundError(
        "Node.js executable not found. Install Node.js or set NODE_BINARY to node.exe path."
    )
