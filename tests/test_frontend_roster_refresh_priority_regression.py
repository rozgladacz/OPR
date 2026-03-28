from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
APP_JS_PATH = ROOT_DIR / "app/static/js/app.js"


def test_roster_refresh_priority_prefers_newer_authoritative_updates() -> None:
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');
        const code = fs.readFileSync({json.dumps(str(APP_JS_PATH))}, 'utf8');
        const sandbox = {{
          console,
          Map,
          Set,
          JSON,
          window: {{ setTimeout, clearTimeout }},
          document: {{ addEventListener: () => {{}} }},
        }};
        sandbox.window.window = sandbox.window;
        vm.createContext(sandbox);
        vm.runInContext(code, sandbox);

        const unitCosts = [12.5, 8.5, 20.0];
        const expectedTotal = unitCosts.reduce((sum, value) => sum + value, 0);

        const events = [
          {{
            token: {{ dedupeKey: 'local:edit-1', version: 1, authoritative: false }},
            total: 39.0,
          }},
          {{
            token: {{ dedupeKey: 'server:req-2', version: 2, authoritative: true }},
            total: expectedTotal,
          }},
          {{
            token: {{ dedupeKey: 'local:edit-1-replay', version: 1, authoritative: false }},
            total: 39.0,
          }},
        ];

        let state = {{ latestAppliedVersion: 0, latestAuthoritativeVersion: 0 }};
        let total = 0;
        const history = [];
        for (const event of events) {{
          const decision = sandbox.resolveRosterRefreshPriority(state, event.token);
          state = decision.state;
          if (decision.apply) {{
            total = event.total;
          }}
          history.push({{ apply: decision.apply, total }});
        }}

        console.log(JSON.stringify({{ total, expectedTotal, history }}));
        """
    )
    completed = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)

    assert payload["expectedTotal"] == 41.0
    assert payload["total"] == payload["expectedTotal"]
    assert payload["history"] == [
        {"apply": True, "total": 39.0},
        {"apply": True, "total": 41.0},
        {"apply": False, "total": 41.0},
    ]
