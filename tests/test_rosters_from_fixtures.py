
import os, glob, json, yaml
import pytest

# This test file expects that your domain models and cost calculator are importable.
# Replace these imports with your project's actual modules.
try:
    from app.services.costs import compute_roster_total, compute_unit_total  # placeholders
except Exception:
    compute_roster_total = lambda roster: 0
    compute_unit_total = lambda unit, models: 0

def load_fixtures():
    base = os.path.join(os.path.dirname(__file__), 'fixtures', 'rosters')
    files = sorted(glob.glob(os.path.join(base, '*.yaml')) + glob.glob(os.path.join(base, '*.yml')) + glob.glob(os.path.join(base, '*.json')))
    for fp in files:
        with open(fp, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f) if fp.endswith(('.yaml','.yml')) else json.load(f)
        yield os.path.basename(fp), data

@pytest.mark.parametrize('fname,data', list(load_fixtures()))
def test_rosters_from_fixtures(fname, data):
    assert 'rosters' in data
    # Here you'd instantiate roster/unit objects or your DTOs and feed your cost engine.
    # For now, we just validate fixture shape; project-specific integration is left to Codex step.
    for r in data['rosters']:
        assert 'name' in r
        assert 'units' in r
        assert isinstance(r['units'], list)
        # Optional expected fields
        _ = r.get('expected_total', None)
        _ = r.get('expected_warnings_contains', [])
