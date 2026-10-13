# -*- coding: utf-8 -*-
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSS = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")


def _rule_body(css: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert match, f"缺少样式规则 {selector}"
    return match.group(1)


def _decl(body: str, prop: str) -> str | None:
    match = re.search(rf"{re.escape(prop)}\s*:\s*([^;]+);", body)
    return match.group(1).strip() if match else None


def test_clear_button_stacks_above_full_slot_file_input():
    """全槽位铺开的透明 file input 不能挡住「清除」，否则点击无效。"""
    slot_input = _rule_body(CSS, ".slot input")
    clear = _rule_body(CSS, ".clear")
    assert _decl(slot_input, "position") == "absolute"
    assert _decl(slot_input, "inset") == "0"
    assert _decl(clear, "position") in {"relative", "absolute"}
    clear_z = _decl(clear, "z-index")
    input_z = _decl(slot_input, "z-index") or "auto"
    assert clear_z not in (None, "auto")
    if input_z == "auto":
        assert int(clear_z) > 0
    else:
        assert int(clear_z) > int(input_z)


def test_clear_slot_resets_file_input_value():
    """清槽后必须重置 input.value，否则同一文件再次选择不会触发 change。"""
    start = JS.index("function clearSlot")
    end = JS.index("\nfunction ", start + 1)
    body = JS[start:end]
    assert re.search(r"\.value\s*=\s*[\"']{2}", body)
