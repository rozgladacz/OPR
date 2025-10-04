from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"


def _build_sandbox_script(body: str) -> str:
    return textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const path = {json.dumps(str(APP_JS_PATH))};
        const code = fs.readFileSync(path, 'utf8');
        const sandbox = {{
          console,
          Map,
          Set,
          JSON,
          window: {{
            setTimeout: setTimeout,
            clearTimeout: clearTimeout,
          }},
          document: {{
            addEventListener: () => {{}},
          }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);
        {body}
        """
    )


def _run_node(script: str) -> dict[str, object]:
    result = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    stdout = result.stdout.strip()
    assert stdout, "Node script produced no output"
    return json.loads(stdout)


def test_loadout_state_preserves_aura_variant_counts() -> None:
    banner_key = "aura::banner"
    medic_key = "aura::medic"
    aura_items = [
        {
            "ability_id": 50,
            "loadout_key": banner_key,
            "default_count": 2,
            "label": "Sztandar",
        },
        {
            "ability_id": 50,
            "loadout_key": medic_key,
            "default_count": 1,
            "label": "Medyk",
        },
    ]

    script_body = f"""
        const bannerKey = {json.dumps(banner_key)};
        const medicKey = {json.dumps(medic_key)};
        const auraItems = {json.dumps(aura_items)};
        const state = sandbox.createLoadoutState({{}});
        sandbox.ensureStateEntries(state.aura, auraItems, 'ability_id', 'default_count', {{ fallbackIdKeys: ['id'] }});
        state.aura.set(bannerKey, 3);
        state.aura.set(medicKey, 1);
        state.auraLabels.set(bannerKey, 'Sztandar');
        state.auraLabels.set(medicKey, 'Medyk');
        const serialized = JSON.parse(sandbox.serializeLoadoutState(state));
        const reloaded = sandbox.createLoadoutState(serialized);
        console.log(JSON.stringify({{
          initialKeys: Array.from(state.aura.keys()),
          serializedAura: serialized.aura.sort((a, b) => a.id.localeCompare(b.id)),
          serializedLabels: serialized.aura_labels.sort((a, b) => a.id.localeCompare(b.id)),
          reloadedCounts: [reloaded.aura.get(bannerKey), reloaded.aura.get(medicKey)],
        }}));
    """

    script = _build_sandbox_script(script_body)

    result = _run_node(script)

    assert result["initialKeys"] == [banner_key, medic_key]

    serialized_aura = result["serializedAura"]
    assert serialized_aura == [
        {"id": banner_key, "count": 3},
        {"id": medic_key, "count": 1},
    ]

    serialized_labels = result["serializedLabels"]
    assert serialized_labels == [
        {"id": banner_key, "name": "Sztandar"},
        {"id": medic_key, "name": "Medyk"},
    ]

    assert result["reloadedCounts"] == [3, 1]
