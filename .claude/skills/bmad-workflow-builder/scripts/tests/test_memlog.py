# /// script
# requires-python = ">=3.10"
# dependencies = ["pytest>=8.0"]
# ///
"""Tests for memlog.py. Run: uv run --with pytest pytest scripts/tests/test_memlog.py

The spine under test is the flat, append-only, chronological invariant: every entry is
one typed line recorded at the end in the order it happened -- no sections, no grouping,
no edit, no removal.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import memlog  # noqa: E402

MEMLOG = ".memlog.md"


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / MEMLOG)


def read(path):
    return Path(path).read_text(encoding="utf-8")


def body_of(path):
    return memlog.split(read(path))[1]


def entries(path):
    return [ln for ln in body_of(path).splitlines() if ln.startswith("- ")]


def init(path, **fields):
    fields = fields or {"subject": "Reinvent the lunchbox"}
    argv = ["init", "--path", path]
    for k, v in fields.items():
        argv += ["--field", f"{k}={v}"]
    assert memlog.main(argv) == 0


def append(path, entry_type, text):
    assert memlog.main(["append", "--path", path, "--type", entry_type, "--text", text]) == 0


# --- init ---------------------------------------------------------------

def test_init_writes_frontmatter_fields(path):
    init(path)
    meta, body = memlog.split(read(path))
    assert meta["subject"] == "Reinvent the lunchbox"
    assert meta["status"] == "active"
    assert "updated" in meta
    assert body.strip() == ""


def test_init_arbitrary_fields(path):
    init(path, subject="T", owner="BMad")
    meta, _ = memlog.split(read(path))
    assert meta["owner"] == "BMad"


def test_init_refuses_overwrite(path):
    init(path)
    assert memlog.main(["init", "--path", path, "--field", "subject=other"]) == 2


def test_init_creates_missing_parent_dir(tmp_path):
    nested = str(tmp_path / "a" / "b" / MEMLOG)
    assert memlog.main(["init", "--path", nested, "--field", "subject=T"]) == 0
    assert Path(nested).is_file()


def test_init_rejects_malformed_field(path):
    assert memlog.main(["init", "--path", path, "--field", "noequals"]) == 2


# --- append: flat chronological order, typed -----------------------------

def test_append_lands_at_end_in_order(path):
    init(path)
    append(path, "note", "first")
    append(path, "note", "second")
    append(path, "note", "third")
    assert entries(path) == ["- (note) first", "- (note) second", "- (note) third"]


def test_no_sections_or_headings_ever(path):
    init(path)
    append(path, "event", "started foo")
    append(path, "note", "an idea")
    append(path, "event", "started bar")
    assert "## " not in body_of(path)


def test_type_renders_as_inline_tag(path):
    init(path)
    append(path, "decision", "lead with one account")
    append(path, "gap", "no retention baseline yet")
    body = body_of(path)
    assert "- (decision) lead with one account" in body
    assert "- (gap) no retention baseline yet" in body


def test_all_six_entry_types_accepted(path):
    init(path)
    for t in ("decision", "direction", "assumption", "gap", "note", "event"):
        append(path, t, f"a {t}")
    body = body_of(path)
    for t in ("decision", "direction", "assumption", "gap", "note", "event"):
        assert f"({t})" in body


def test_unknown_type_is_rejected(path):
    init(path)
    # argparse choices rejects it before our handler (exit code 2 via SystemExit)
    with pytest.raises(SystemExit):
        memlog.main(["append", "--path", path, "--type", "idea", "--text", "x"])


def test_append_collapses_newlines_into_one_line(path):
    init(path)
    append(path, "note", "line one\nline two\n  spaced   out")
    assert entries(path) == ["- (note) line one line two spaced out"]


# --- set-complete -------------------------------------------------------

def test_set_complete_flips_status(path):
    init(path)
    assert memlog.main(["set-complete", "--path", path]) == 0
    assert memlog.split(read(path))[0]["status"] == "complete"


def test_set_complete_preserves_body(path):
    init(path)
    append(path, "decision", "keep me")
    memlog.main(["set-complete", "--path", path])
    meta, body = memlog.split(read(path))
    assert meta["status"] == "complete"
    assert "- (decision) keep me" in body


def test_updated_stays_last(path):
    init(path)
    append(path, "note", "x")
    meta = memlog.split(read(path))[0]
    assert list(meta)[-1] == "updated"


# --- robustness ---------------------------------------------------------

def test_roundtrip_render_is_stable(path):
    init(path)
    append(path, "note", "one")
    first = read(path)
    meta, body = memlog.split(first)
    assert memlog.render(meta, body) == first


def test_commas_in_field_survive(path):
    init(path, subject="cars, trains, and planes")
    append(path, "note", "z")
    meta, _ = memlog.split(read(path))
    assert meta["subject"] == "cars, trains, and planes"


def test_triple_dash_in_field_does_not_corrupt_frontmatter(path):
    # A `---` inside a value must NOT be read as the closing fence.
    init(path, subject="Pricing --- tiers --- and add-ons")
    append(path, "note", "an idea")
    meta, body = memlog.split(read(path))
    assert meta["subject"] == "Pricing --- tiers --- and add-ons"
    assert meta["status"] == "active"
    assert entries(path) == ["- (note) an idea"]
    assert "status:" not in body


def test_newline_in_field_is_neutralized(path):
    memlog.main(["init", "--path", path, "--field", "subject=line one\nline two"])
    append(path, "note", "x")
    meta, _ = memlog.split(read(path))
    assert "\n" not in meta["subject"]
    assert meta["status"] == "active"


# --- atomic write: no temp file lingers, no half-write ------------------

def test_atomic_write_leaves_no_temp_file(tmp_path):
    p = str(tmp_path / MEMLOG)
    init(p)
    append(p, "note", "x")
    assert not (tmp_path / (MEMLOG + ".tmp")).exists()
    # the real file is the only memlog artifact present
    leftovers = [f.name for f in tmp_path.iterdir() if f.name.endswith(".tmp")]
    assert leftovers == []


def test_append_survives_after_many_writes(path):
    init(path)
    for i in range(50):
        append(path, "event", f"step {i}")
    assert len(entries(path)) == 50
    assert entries(path)[0] == "- (event) step 0"
    assert entries(path)[-1] == "- (event) step 49"


# --- JSON ack -----------------------------------------------------------

def test_append_emits_json_ack(path, capsys):
    init(path)
    append(path, "decision", "x")
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["status"] == "active"
    assert out["n"] == 1
    assert out["type"] == "decision"
    assert out["memlog"].endswith(MEMLOG)


def test_ack_n_climbs(path, capsys):
    init(path)
    append(path, "note", "a")
    append(path, "note", "b")
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["n"] == 2


def test_set_complete_ack(path, capsys):
    init(path)
    memlog.main(["set-complete", "--path", path])
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["status"] == "complete"


def test_no_edit_or_remove_subcommand_exists(path):
    init(path)
    for bad in ("edit", "remove", "delete", "set"):
        with pytest.raises(SystemExit):
            memlog.main([bad, "--path", path])
