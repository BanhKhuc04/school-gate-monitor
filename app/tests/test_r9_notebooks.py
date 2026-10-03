"""Selftest cho 3 notebook R9.

Verify:
- File JSON hợp lệ với schema nbformat 4.5
- Mỗi cell code có source compile được (compile() không chạy cell)
- Tất cả markdown cell có source
- Mỗi cell có keys bắt buộc theo nbformat

Không cần nbformat package — test thuần bằng json + ast.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NB_DIR = ROOT / "notebooks"

NOTEBOOK_NAMES = (
    "yolo11_plate.ipynb",
    "yolo11_helmet_electric.ipynb",
    "cct_plate_ocr.ipynb",
)


@pytest.mark.parametrize("name", NOTEBOOK_NAMES)
def test_notebook_json_valid(name):
    path = NB_DIR / name
    assert path.is_file(), f"{path} không tồn tại"
    nb = json.loads(path.read_text(encoding="utf-8"))
    # Required keys
    assert {"cells", "metadata", "nbformat", "nbformat_minor"}.issubset(nb.keys())
    assert nb["nbformat"] == 4
    assert nb["nbformat_minor"] == 5
    # Metadata có kernelspec + language_info
    assert "kernelspec" in nb["metadata"]
    assert nb["metadata"]["kernelspec"]["language"] == "python"
    assert "language_info" in nb["metadata"]
    # Cells: phải có ít nhất markdown + 3 code cells
    cells = nb["cells"]
    md_cells = [c for c in cells if c["cell_type"] == "markdown"]
    code_cells = [c for c in cells if c["cell_type"] == "code"]
    assert len(md_cells) >= 1, "Phải có ít nhất 1 markdown cell (title)"
    assert len(code_cells) >= 5, f"Phải có ≥5 code cells, có {len(code_cells)}"


@pytest.mark.parametrize("name", NOTEBOOK_NAMES)
def test_code_cells_compile(name):
    """Mỗi code cell source phải compile được (không thực thi)."""
    path = NB_DIR / name
    nb = json.loads(path.read_text(encoding="utf-8"))
    errors = []
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        source = "".join(c["source"])
        try:
            ast.parse(source, filename=f"{name}#cell{i}", mode="exec")
        except SyntaxError as exc:
            errors.append(f"cell {i}: {exc.msg} (line {exc.lineno})")
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("name", NOTEBOOK_NAMES)
def test_markdown_cells_have_source(name):
    """Mỗi markdown cell phải có source không rỗng."""
    path = NB_DIR / name
    nb = json.loads(path.read_text(encoding="utf-8"))
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "markdown":
            continue
        source = "".join(c["source"]).strip()
        assert source, f"markdown cell {i} rỗng"


@pytest.mark.parametrize("name", NOTEBOOK_NAMES)
def test_code_cells_have_required_keys(name):
    """Mỗi code cell phải có execution_count + outputs (để Jupyter render đúng)."""
    path = NB_DIR / name
    nb = json.loads(path.read_text(encoding="utf-8"))
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        assert "execution_count" in c, f"code cell {i} thiếu execution_count"
        assert "outputs" in c, f"code cell {i} thiếu outputs"
        assert "source" in c, f"code cell {i} thiếu source"
        assert isinstance(c["source"], list), f"code cell {i} source phải là list"
        assert isinstance(c["outputs"], list), f"code cell {i} outputs phải là list"


def test_notebooks_have_preflight_cell():
    """Mỗi notebook phải có cell preflight (bám R9 handoff)."""
    for name in NOTEBOOK_NAMES:
        path = NB_DIR / name
        nb = json.loads(path.read_text(encoding="utf-8"))
        found = False
        for c in nb["cells"]:
            if c["cell_type"] != "code":
                continue
            source = "".join(c["source"])
            if "preflight" in source and "manifest" in source:
                found = True
                break
        assert found, f"{name} thiếu preflight cell"


def test_notebooks_have_export_cell_with_manifest():
    """Mỗi notebook phải có cell export + ghi manifest hash (R9 handoff)."""
    for name in NOTEBOOK_NAMES:
        path = NB_DIR / name
        nb = json.loads(path.read_text(encoding="utf-8"))
        found = False
        for c in nb["cells"]:
            if c["cell_type"] != "code":
                continue
            source = "".join(c["source"])
            if "hashlib" in source and "sha256" in source and "manifest" in source:
                found = True
                break
        assert found, f"{name} thiếu cell ghi manifest hash"


def test_cct_explains_weights_vs_resume():
    """cct notebook phải có cảnh báo --weights-path KHÔNG phải resume đầy đủ."""
    path = NB_DIR / "cct_plate_ocr.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"
    )
    assert "--weights-path" in source or "weights-path" in source
    assert "resume" in source.lower()
    assert "initial_epoch" in source


def test_helmet_separate_tasks():
    """Helmet notebook phải train 2 task riêng (helmet + electric) — không gộp."""
    path = NB_DIR / "yolo11_helmet_electric.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))
    source = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"
    )
    # Có 2 lệnh train
    train_count = source.count("model.train(")
    assert train_count >= 2, f"helmet notebook chỉ có {train_count} train, cần ≥2 (helmet + electric)"
    # Có slug riêng cho helmet & ev
    assert "HELMET_DATASET_SLUG" in source
    assert "EV_DATASET_SLUG" in source or "ev_dir" in source
    # Có doc cảnh báo KHÔNG gộp model
    md = "\n".join(
        "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown"
    )
    assert "gộp" in md or "riêng" in md or "riêng biệt" in md