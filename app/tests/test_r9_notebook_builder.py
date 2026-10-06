"""Selftest cho _notebook_builder helper."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

NB_BUILDER = Path(__file__).resolve().parents[2] / "scripts" / "training" / "_notebook_builder.py"


def _import():
    import importlib.util
    spec = importlib.util.spec_from_file_location("nb_builder", NB_BUILDER)
    if spec is None or spec.loader is None:
        pytest.fail(f"không load được {NB_BUILDER}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nb_builder"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_module_imports():
    _import()


def test_make_cell_keeps_newlines():
    mod = _import()
    cell = mod.make_cell("a = 1\nb = 2\n", cell_type="code")
    assert cell["cell_type"] == "code"
    assert cell["source"] == ["a = 1\n", "b = 2\n"]
    assert cell["execution_count"] is None
    assert cell["outputs"] == []
    # Markdown cell không có execution_count
    md_cell = mod.make_cell("# Title\n", cell_type="markdown")
    assert "execution_count" not in md_cell


def test_make_cell_rejects_non_string():
    mod = _import()
    with pytest.raises(TypeError):
        mod.make_cell(123)


def test_make_notebook_has_required_keys():
    mod = _import()
    nb = mod.make_notebook([mod.make_cell("x = 1", "code")])
    assert {"cells", "metadata", "nbformat", "nbformat_minor"}.issubset(nb.keys())
    assert nb["nbformat"] == 4
    assert nb["nbformat_minor"] == 5
    assert nb["metadata"]["kernelspec"]["language"] == "python"


def test_save_notebook_writes_valid_json(tmp_path):
    mod = _import()
    nb = mod.make_notebook([
        mod.make_cell("# title", "markdown"),
        mod.make_cell("x = 1", "code"),
    ])
    out = tmp_path / "test.ipynb"
    mod.save_notebook(nb, out)
    assert out.is_file()
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["nbformat"] == 4
    assert len(loaded["cells"]) == 2


def test_save_notebook_creates_parent(tmp_path):
    mod = _import()
    out = tmp_path / "nested" / "dir" / "test.ipynb"
    nb = mod.make_notebook([mod.make_cell("x = 1", "code")])
    mod.save_notebook(nb, out)
    assert out.is_file()


def test_format_version_constant():
    mod = _import()
    assert mod.NOTEBOOK_FORMAT_VERSION == (4, 5)
    assert "cells" in mod.REQUIRED_KEYS
    assert "metadata" in mod.REQUIRED_KEYS