"""Helper tạo Jupyter Notebook (.ipynb) chuẩn nbformat v4.5.

Tại sao không dùng nbformat package: dự án không cài nbformat trong venv local;
Kaggle install nbformat theo image Python mặc định. Helper này viết JSON thủ
công, đúng schema Jupyter — Jupyter/Lab/JupyterLite đọc OK; nếu Kaggle có
nbformat thì vẫn validate.

Cấu trúc ipynb v4.5:
    {
      "cells": [{"cell_type": "code|markdown", "metadata": {}, "source": ["..."],
                      "outputs": [], "execution_count": null}],
      "metadata": {"kernelspec": {...}, "language_info": {...}},
      "nbformat": 4,
      "nbformat_minor": 5,
    }

`source` là list các dòng (mỗi dòng kết thúc bằng \\n). Khi serialize,
mỗi phần tử list là 1 dòng; joined lại bằng "" → kết quả cuối có \\n.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def make_cell(code: str, cell_type: str = "code") -> dict:
    """Tạo 1 cell từ code string. Tự động tách dòng theo \\n."""
    if not isinstance(code, str):
        raise TypeError(f"code phải là str, nhận {type(code).__name__}")
    source = code.splitlines(keepends=True)
    cell_def: dict = {
        "cell_type": cell_type,
        "metadata": {},
        "source": source,
    }
    if cell_type == "code":
        cell_def["execution_count"] = None
        cell_def["outputs"] = []
    return cell_def


def make_notebook(
    cells: Iterable[dict],
    *,
    kernel_display_name: str = "Python 3",
    kernel_name: str = "python3",
    language: str = "python",
) -> dict:
    """Đóng gói cells thành notebook JSON."""
    return {
        "cells": list(cells),
        "metadata": {
            "kernelspec": {
                "display_name": kernel_display_name,
                "language": language,
                "name": kernel_name,
            },
            "language_info": {"name": language},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def save_notebook(nb: dict, path: Path) -> None:
    """Ghi file .ipynb. Tạo parent dir nếu cần."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(nb, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )


# Định nghĩa schema version + nbformat version cho tự kiểm
NOTEBOOK_FORMAT_VERSION = (4, 5)
REQUIRED_KEYS = {"cells", "metadata", "nbformat", "nbformat_minor"}