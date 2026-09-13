"""Prune-stale tests: Step 1 keeps data/ equal to the current universe so old
delisted/renamed/out-of-scope stock files do not accumulate on disk.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import store as storemod


def test_prune_removes_only_out_of_universe(tmp_path):
    d = tmp_path / "daily"
    d.mkdir()
    for s in ["BSE", "RELIANCE", "OLDCO", "DELISTED"]:
        (d / f"{s}.parquet").write_bytes(b"x")  # placeholder files
    removed = storemod.prune_stale_parquets(d, {"BSE", "RELIANCE"})
    assert sorted(removed) == ["DELISTED", "OLDCO"]
    assert sorted(p.stem for p in d.glob("*.parquet")) == ["BSE", "RELIANCE"]


def test_prune_is_case_insensitive_and_noop_when_all_kept(tmp_path):
    d = tmp_path / "daily"
    d.mkdir()
    (d / "BSE.parquet").write_bytes(b"x")
    removed = storemod.prune_stale_parquets(d, {"bse"})  # keep set differs in case
    assert removed == []
    assert (d / "BSE.parquet").exists()


def test_prune_ignores_non_parquet_files(tmp_path):
    d = tmp_path / "daily"
    d.mkdir()
    (d / "BSE.parquet").write_bytes(b"x")
    (d / "manifest_note.txt").write_bytes(b"x")
    storemod.prune_stale_parquets(d, set())  # keep nothing
    assert not (d / "BSE.parquet").exists()
    assert (d / "manifest_note.txt").exists()  # only *.parquet is touched


def test_prune_missing_dir_is_safe(tmp_path):
    assert storemod.prune_stale_parquets(tmp_path / "nope", {"BSE"}) == []
