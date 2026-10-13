# -*- coding: utf-8 -*-
from __future__ import print_function

import io
import os
import re

from .prompts import SYSTEM_PROMPT


DEFAULT_AGENT_ID = "default"
KMRAG_AGENT_ID = "kmrag-knowledge-agent"
DEFAULT_AGENT_NAME = u"\u9ed8\u8ba4\u52a9\u624b"
DEFAULT_AGENT_DESCRIPTION = u"\u4f7f\u7528\u5185\u7f6e 3DMPS \u52a9\u624b\u63d0\u793a\u8bcd\u3002"
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
PROJECT_AGENTS_DIR = os.path.join(PROJECT_ROOT, "agents")
USER_AGENTS_DIR = os.path.expanduser(r"~\.config\opencode\agents")
ENABLE_USER_AGENTS_ENV = "KMAI_ENABLE_USER_AGENTS"

COMMAND_NAME_REWRITES = {
    "get-ai-process-route-input": "get_ai_process_route_input",
    "submit-ai-process-route-output": "submit_ai_process_route_output",
    "get-ai-process-route-status": "get_ai_process_route_status",
    "click-generate-all-button": "click_generate_all_button",
    "click-one-click-generate-button": "click_one_click_generate_button",
    "click-auto-reasoning-button": "click_auto_reasoning_button",
    "click-group-template-button": "click_group_template_button",
    "group-template-dialog-ok": "group_template_dialog_ok",
    "group-template-dialog-cancel": "group_template_dialog_cancel",
    "get-all-group-template-list": "get_all_group_template_list",
    "specify-group-template-index": "specify_group_template_index",
    "specify-group-template-name": "specify_group_template_name",
    "click-autoidentify-button": "click_autoidentify_button",
    "check-autoidentify-btn-ok": "check_autoidentify_btn_ok",
    "check-autoidentify-btn-cancel": "check_autoidentify_btn_cancel",
    "check-autoidentify-btn-selectall": "check_autoidentify_btn_selectall",
    "check-autoidentify-btn-deselectall": "check_autoidentify_btn_deselectall",
    "get-autoidentify-template-list": "get_autoidentify_template_list",
    "use-autoidentify-template": "use_autoidentify_template",
    "use-autoidentify-template-by-index": "use_autoidentify_template_by_index",
    "get-autoidentify-checkbox-list": "get_autoidentify_checkbox_list",
    "set-autoidentify-checkbox-list": "set_autoidentify_checkbox_list",
    "run-autoidentify-with-no-dlg": "run_autoidentify_with_no_dlg",
}


def _default_agent():
    return {
        "id": DEFAULT_AGENT_ID,
        "name": DEFAULT_AGENT_NAME,
        "description": DEFAULT_AGENT_DESCRIPTION,
        "prompt": SYSTEM_PROMPT,
        "source": "builtin",
        "path": "",
    }


def _iter_agent_sources():
    sources = [("project", PROJECT_AGENTS_DIR)]
    value = os.environ.get(ENABLE_USER_AGENTS_ENV, "")
    if value.strip().lower() in ("1", "true", "yes", "on"):
        sources.append(("user", USER_AGENTS_DIR))
    return sources


def _normalize_agent_id(name):
    value = os.path.splitext(name)[0].strip().lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    value = value.strip("-_")
    return value or "agent"


def _normalize_prompt(prompt_text):
    normalized = prompt_text or ""
    for old_name, new_name in COMMAND_NAME_REWRITES.items():
        normalized = normalized.replace("`" + old_name + "`", "`" + new_name + "`")
        normalized = normalized.replace(old_name, new_name)
    return normalized


def _read_text(path):
    encodings = ("utf-8-sig", "utf-8", "gb18030", "gbk")
    for encoding in encodings:
        try:
            with io.open(path, "r", encoding=encoding) as fp:
                return fp.read()
        except UnicodeDecodeError:
            continue
    with io.open(path, "r", encoding="utf-8", errors="replace") as fp:
        return fp.read()


def _parse_front_matter(text):
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines(True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    end_index = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_index = idx
            break
    if end_index is None:
        return {}, text

    metadata = {}
    for line in lines[1:end_index]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        metadata[key] = value

    body = "".join(lines[end_index + 1:])
    return metadata, body


def _is_agent_file(filename):
    lower_name = filename.lower()
    if not lower_name.endswith(".md"):
        return False
    if lower_name.endswith("-test-prompt.md"):
        return False
    if lower_name == "skill-bound-template.md":
        return False
    return True


def _load_agent_file(path, source_name):
    text = _read_text(path)
    metadata, body = _parse_front_matter(text)
    prompt = _normalize_prompt(body.strip())
    filename = os.path.basename(path)
    agent_id = _normalize_agent_id(filename)
    base_name = os.path.splitext(filename)[0]
    name = metadata.get("name") or base_name
    description = metadata.get("description") or u"\u4f7f\u7528\u5916\u90e8 agent markdown \u63d0\u793a\u8bcd\u3002"
    return {
        "id": agent_id,
        "name": name,
        "description": description,
        "prompt": prompt,
        "source": source_name,
        "path": path,
    }


def list_agent_profiles():
    profiles = [_default_agent()]
    seen_ids = set([DEFAULT_AGENT_ID])
    for source_name, source_dir in _iter_agent_sources():
        if not os.path.isdir(source_dir):
            continue
        names = [name for name in os.listdir(source_dir) if _is_agent_file(name)]
        names.sort(key=lambda item: item.lower())
        for name in names:
            path = os.path.join(source_dir, name)
            try:
                profile = _load_agent_file(path, source_name)
            except Exception:
                continue
            agent_id = profile.get("id") or ""
            if not agent_id or agent_id in seen_ids:
                continue
            seen_ids.add(agent_id)
            profiles.append(profile)
    return profiles


def list_agent_summaries():
    items = []
    for profile in list_agent_profiles():
        items.append({
            "id": profile.get("id", ""),
            "name": profile.get("name", ""),
            "description": profile.get("description", ""),
            "source": profile.get("source", ""),
            "path": profile.get("path", ""),
        })
    return items


def get_agent_profile(agent_id):
    profile, _found = resolve_agent_profile(agent_id)
    return profile


def resolve_agent_profile(agent_id):
    target = (agent_id or DEFAULT_AGENT_ID).strip() or DEFAULT_AGENT_ID
    for profile in list_agent_profiles():
        if profile.get("id") == target:
            profile["agent_found"] = True
            profile["requested_agent_id"] = target
            return profile, True
    fallback = _default_agent()
    fallback["agent_found"] = False
    fallback["requested_agent_id"] = target
    return fallback, False
