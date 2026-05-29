import datetime as dt
import importlib.util
from pathlib import Path

SCRIPT = Path('/home/peter/.hermes/scripts/daily_reading_supplement_scaffold.py')


def load_module():
    spec = importlib.util.spec_from_file_location('daily_reading_supplement_scaffold', SCRIPT)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_note_adds_stable_commentary_anchors():
    drs = load_module()
    day = dt.date(2026, 5, 23)
    note = drs.build_note(day, [('John 14:10-21', 'In the beginning was text.')])

    assert '<!-- drs:passage-start john-14-10-21 -->' in note
    assert '<!-- drs:commentary-start john-14-10-21 -->' in note
    assert drs.SCAFFOLD_PLACEHOLDER in note
    assert '<!-- drs:commentary-end john-14-10-21 -->' in note


def test_manifest_tracks_pending_lanes_and_fragment_ready(tmp_path, monkeypatch):
    drs = load_module()
    monkeypatch.setattr(drs, 'STATUS_DIR', tmp_path / 'state')
    day = dt.date(2026, 5, 23)
    readings = [('Acts 20:7-12', 'Upon the first day of the week.')]
    note = tmp_path / 'note.md'
    note.write_text(drs.build_note(day, readings), encoding='utf-8')

    manifest = drs.build_manifest(day, readings, note, 'note.md')
    passage = manifest['passages'][0]
    assert passage['slug'] == 'acts-20-7-12'
    assert passage['status'] == 'pending'
    assert set(passage['lanes']) == set(drs.LANE_NAMES)
    assert all(status == 'pending' for status in passage['lanes'].values())

    fragment = drs.fragment_path(day, 'acts-20-7-12')
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text('- **Source** (`direct verse commentary`):\n\n  > Quote', encoding='utf-8')
    manifest = drs.build_manifest(day, readings, note, 'note.md')
    assert manifest['passages'][0]['status'] == 'fragment-ready'


def test_assemble_fragments_patches_only_anchored_commentary(tmp_path, monkeypatch):
    drs = load_module()
    monkeypatch.setattr(drs, 'STATUS_DIR', tmp_path / 'state')
    day = dt.date(2026, 5, 23)
    readings = [('John 14:10-21', 'Liturgical text here.')]
    note = tmp_path / 'note.md'
    note.write_text(drs.build_note(day, readings), encoding='utf-8')
    slug = 'john-14-10-21'
    fragment = drs.fragment_path(day, slug)
    fragment.parent.mkdir(parents=True, exist_ok=True)
    fragment.write_text('- **Augustine** (`direct verse commentary`):\n\n  > Actual source text.', encoding='utf-8')

    results = drs.assemble_fragments(day, note, readings)
    saved = note.read_text(encoding='utf-8')

    assert results == [f'{slug}:patched']
    assert drs.SCAFFOLD_PLACEHOLDER not in saved
    assert '> Actual source text.' in saved
    assert '### Liturgical Text' in saved
