import json
from noderadar import events


def test_prunes_old(tmp_path):
    p = tmp_path / "e.jsonl"
    events.append(p, {"m": "old"}, now=1000)
    events.append(p, {"m": "new"}, now=1000 + 31 * 60)
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    assert [r["m"] for r in rows] == ["new"]
