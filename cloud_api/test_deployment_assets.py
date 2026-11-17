"""Catch source-complete builds whose deployment archive drops browser modules."""

import ast
import io
import tarfile
from pathlib import Path

from scripts.deploy_cloud_update import source_archive


def test_cloud_archive_contains_every_public_pilot_asset():
    root = Path(__file__).resolve().parents[1]
    source = ast.parse((root / "cloud_api/app.py").read_text(encoding="utf-8"))
    route = next(n for n in ast.walk(source)
                 if isinstance(n, ast.FunctionDef) and n.name == "pilot_asset")
    allowed = next(n.comparators[0] for n in ast.walk(route)
                   if isinstance(n, ast.Compare) and isinstance(n.left, ast.Name)
                   and n.left.id == "asset" and isinstance(n.comparators[0], ast.Set))
    assets = {f"cloud_api/web/{n.value}" for n in allowed.elts}
    payload, _ = source_archive()
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        packaged = set(archive.getnames())
    assert assets <= packaged, f"Public assets missing from cloud build: {sorted(assets - packaged)}"
