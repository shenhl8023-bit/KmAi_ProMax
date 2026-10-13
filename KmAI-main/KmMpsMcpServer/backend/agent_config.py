# -*- coding: utf-8 -*-
from __future__ import print_function

import configparser
import os
import sys
from urllib.parse import urlparse

CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "config.ini")
)

CONFIG_BASE_DIR = os.path.dirname(CONFIG_PATH)


def _resolve_config_path(value):
    value = os.path.expandvars(os.path.expanduser(str(value or "").strip()))
    if not value:
        return ""
    if not os.path.isabs(value):
        value = os.path.join(CONFIG_BASE_DIR, value)
    return os.path.normpath(os.path.abspath(value))


def _load_config():
    """Load config.ini, return dict with LLM settings and paths."""
    config = {
        "provider": "",
        "api_key": "",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "max_tokens": 4096,
        "temperature": 0.3,
        "kmrag_enabled": False,
        "kmrag_base_url": "",
        "kmrag_api_key": "",
        "kmrag_bearer_token": "",
        "kmrag_timeout": 30,
        "group_template_dir": os.path.join(CONFIG_BASE_DIR, "..", "..", "Resources", "GroupTemplate"),
        "feature_template_file": os.path.join("..", "Resources", "FeatureTemplate", "FeatureTemplate.xml"),
        "autoidentify_with_direction_dir": os.path.join("..", "Resources", "AutoIdentifyWithDirection"),
        "similar_parts_enabled": True,
        "similar_parts_matching_backend": "feature_vector",
        "similar_parts_feature_api_base_url": "",
        "similar_parts_feature_api_timeout_seconds": 120,
        "similar_parts_feature_model_version": "",
        "similar_parts_feature_index_file": os.path.join("cache", "similar_parts_features.sqlite3"),
        "similar_parts_step_viewer_root": os.path.join("..", "..", "step-compare-main", "step-compare-main"),
        "similar_parts_xml_library_dir": os.path.join("..", "..", "PartClassification-main", "PartClassification-main", "source", "XML样本"),
        "similar_parts_step_library_dir": os.path.join("..", "..", "PartClassification-main", "PartClassification-main", "source", "STEP样本"),
        "similar_parts_current_part_dir": "",
        "similar_parts_current_xml_file": "",
        "similar_parts_current_step_file": "",
        "similar_parts_win7_lite_mode": False,
        "similar_parts_prebuilt_model_dir": "",
        "similar_parts_top_k": 5,
        "similar_parts_template_map_file": os.path.join("..", "..", "PartClassification-main", "PartClassification-main", "source", "模板", "模板映射.json"),
        "similar_parts_upload_max_bytes": 5 * 1024 * 1024,
        "similar_parts_cache_ttl_seconds": 30 * 60,
        "similar_parts_model_cache_entries": 8,
        "similar_parts_model_cache_bytes": 256 * 1024 * 1024,
    }
    try:
        cp = configparser.ConfigParser()
        if os.path.exists(CONFIG_PATH):
            cp.read(CONFIG_PATH, encoding="utf-8-sig")
        else:
            cp = None
        if cp is not None and cp.has_section("LLM"):
            config["provider"] = cp.get("LLM", "provider", fallback="")
            config["api_key"] = cp.get("LLM", "api_key", fallback="")
            config["base_url"] = cp.get("LLM", "base_url", fallback=config["base_url"])
            config["model"] = cp.get("LLM", "model", fallback=config["model"])
            config["max_tokens"] = cp.getint("LLM", "max_tokens", fallback=config["max_tokens"])
            config["temperature"] = cp.getfloat("LLM", "temperature", fallback=config["temperature"])
        if cp is not None and cp.has_section("Paths"):
            config["group_template_dir"] = cp.get(
                "Paths", "group_template_dir", fallback=config["group_template_dir"]
            )
            config["autoidentify_with_direction_dir"] = cp.get(
                "Paths", "autoidentify_with_direction_dir", fallback=config["autoidentify_with_direction_dir"]
            )
            config["feature_template_file"] = cp.get(
                "Paths", "feature_template_file", fallback=config["feature_template_file"]
            )
        if cp is not None and cp.has_section("KMRAG"):
            enabled = cp.get("KMRAG", "enabled", fallback="false")
            config["kmrag_enabled"] = enabled.strip().lower() in ("1", "true", "yes", "on")
            config["kmrag_base_url"] = cp.get("KMRAG", "base_url", fallback="").strip().rstrip("/")
            config["kmrag_api_key"] = cp.get("KMRAG", "api_key", fallback="").strip()
            config["kmrag_bearer_token"] = cp.get("KMRAG", "bearer_token", fallback="").strip()
            config["kmrag_timeout"] = cp.getint("KMRAG", "timeout", fallback=config["kmrag_timeout"])
        if cp is not None and cp.has_section("SimilarParts"):
            enabled = cp.get("SimilarParts", "enabled", fallback="true")
            config["similar_parts_enabled"] = enabled.strip().lower() in ("1", "true", "yes", "on")
            for key in (
                "step_viewer_root",
                "xml_library_dir",
                "step_library_dir",
                "current_part_dir",
                "current_xml_file",
                "current_step_file",
                "prebuilt_model_dir",
                "template_map_file",
                "feature_index_file",
            ):
                config["similar_parts_" + key] = cp.get(
                    "SimilarParts", key, fallback=config["similar_parts_" + key]
                )
            for key in ("matching_backend", "feature_api_base_url", "feature_model_version"):
                config["similar_parts_" + key] = cp.get(
                    "SimilarParts", key, fallback=config["similar_parts_" + key]
                ).strip()
            config["similar_parts_feature_api_base_url"] = config["similar_parts_feature_api_base_url"].rstrip("/")
            try:
                timeout = cp.getfloat("SimilarParts", "feature_api_timeout_seconds", fallback=120)
                config["similar_parts_feature_api_timeout_seconds"] = timeout if 0 < timeout <= 3600 else 120
            except (ValueError, configparser.Error):
                config["similar_parts_feature_api_timeout_seconds"] = 120
            config["similar_parts_upload_max_bytes"] = cp.getint(
                "SimilarParts", "upload_max_bytes", fallback=config["similar_parts_upload_max_bytes"]
            )
            config["similar_parts_cache_ttl_seconds"] = cp.getint(
                "SimilarParts", "cache_ttl_seconds", fallback=config["similar_parts_cache_ttl_seconds"]
            )
            config["similar_parts_model_cache_entries"] = cp.getint(
                "SimilarParts", "model_cache_entries", fallback=config["similar_parts_model_cache_entries"]
            )
            config["similar_parts_model_cache_bytes"] = cp.getint(
                "SimilarParts", "model_cache_bytes", fallback=config["similar_parts_model_cache_bytes"]
            )
            lite_mode = cp.get("SimilarParts", "win7_lite_mode", fallback="false")
            config["similar_parts_win7_lite_mode"] = lite_mode.strip().lower() in (
                "1", "true", "yes", "on"
            )
            try:
                top_k = cp.getint(
                    "SimilarParts", "top_k", fallback=config["similar_parts_top_k"]
                )
            except (TypeError, ValueError, configparser.Error):
                top_k = config["similar_parts_top_k"]
            config["similar_parts_top_k"] = top_k if 1 <= top_k <= 1000 else 5
    except Exception as exc:
        sys.stderr.write("[config] load error: %s\n" % exc)
    for key in (
        "similar_parts_feature_index_file",
        "similar_parts_step_viewer_root",
        "similar_parts_xml_library_dir",
        "similar_parts_step_library_dir",
        "similar_parts_current_part_dir",
        "similar_parts_current_xml_file",
        "similar_parts_current_step_file",
        "similar_parts_prebuilt_model_dir",
        "similar_parts_template_map_file",
    ):
        config[key] = _resolve_config_path(config.get(key))
    return config


def _is_llm_config_enabled(config):
    return bool(config.get("api_key") and config.get("api_key") != "YOUR_API_KEY_HERE")


def _mask_secret(value):
    value = value or ""
    if not value:
        return ""
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * (len(value) - 8) + value[-4:]


def _public_llm_config():
    return {
        "provider": CONFIG.get("provider", ""),
        "base_url": CONFIG.get("base_url", ""),
        "model": CONFIG.get("model", ""),
        "max_tokens": CONFIG.get("max_tokens", 4096),
        "temperature": CONFIG.get("temperature", 0.3),
        "llm_enabled": _is_llm_config_enabled(CONFIG),
        "api_key_set": bool(CONFIG.get("api_key")),
        "api_key_masked": _mask_secret(CONFIG.get("api_key", "")),
        "config_path": os.path.abspath(CONFIG_PATH),
    }


def _public_kmrag_config(config=None):
    config = CONFIG if config is None else config
    has_api_key = bool(config.get("kmrag_api_key"))
    has_bearer_token = bool(config.get("kmrag_bearer_token"))
    if has_api_key:
        auth_mode = "api_key"
    elif has_bearer_token:
        auth_mode = "bearer_token"
    else:
        auth_mode = "none"
    return {
        "enabled": bool(config.get("kmrag_enabled")),
        "configured": bool(config.get("kmrag_base_url")) and (has_api_key or has_bearer_token),
        "auth_mode": auth_mode,
    }


def _kmrag_runtime_env(config=None):
    config = CONFIG if config is None else config
    base_url = str(config.get("kmrag_base_url", "")).strip()
    host = urlparse(base_url).hostname if base_url else ""
    runtime_env = {
        "KMRAG_ENABLED": "true" if config.get("kmrag_enabled") else "false",
        "KMRAG_BASE_URL": base_url,
        "KMRAG_API_KEY": str(config.get("kmrag_api_key", "")),
        "KMRAG_BEARER_TOKEN": str(config.get("kmrag_bearer_token", "")),
        "KMRAG_TIMEOUT": str(config.get("kmrag_timeout", 30)),
    }
    if host:
        for name in ("NO_PROXY", "no_proxy"):
            existing = os.environ.get(name, "").strip()
            entries = [item.strip() for item in existing.split(",") if item.strip()]
            if host not in entries:
                entries.append(host)
            runtime_env[name] = ",".join(entries)
    return runtime_env


def _parse_int_field(data, name, default, min_value, max_value):
    raw = data.get(name, default)
    try:
        value = int(raw)
    except Exception:
        raise ValueError(u"%s \u5fc5\u987b\u662f\u6574\u6570" % name)
    if value < min_value or value > max_value:
        raise ValueError(u"%s \u5fc5\u987b\u5728 %d \u5230 %d \u4e4b\u95f4" % (name, min_value, max_value))
    return value


def _parse_float_field(data, name, default, min_value, max_value):
    raw = data.get(name, default)
    try:
        value = float(raw)
    except Exception:
        raise ValueError(u"%s \u5fc5\u987b\u662f\u6570\u5b57" % name)
    if value < min_value or value > max_value:
        raise ValueError(u"%s \u5fc5\u987b\u5728 %.2f \u5230 %.2f \u4e4b\u95f4" % (name, min_value, max_value))
    return value


def _save_llm_config(data):
    global CONFIG, LLM_ENABLED

    provider = (data.get("provider", CONFIG.get("provider", "")) or "").strip()
    base_url = (data.get("base_url", CONFIG.get("base_url", "")) or "").strip().rstrip("/")
    model = (data.get("model", CONFIG.get("model", "")) or "").strip()
    if not base_url:
        raise ValueError(u"base_url \u4e0d\u80fd\u4e3a\u7a7a")
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise ValueError(u"base_url \u5fc5\u987b\u4ee5 http:// \u6216 https:// \u5f00\u5934")
    if not model:
        raise ValueError(u"model \u4e0d\u80fd\u4e3a\u7a7a")

    max_tokens = _parse_int_field(data, "max_tokens", CONFIG.get("max_tokens", 4096), 1, 200000)
    temperature = _parse_float_field(data, "temperature", CONFIG.get("temperature", 0.3), 0.0, 2.0)

    api_key = CONFIG.get("api_key", "")
    if data.get("clear_api_key"):
        api_key = ""
    elif "api_key" in data and str(data.get("api_key") or "").strip():
        api_key = str(data.get("api_key") or "").strip()

    cp = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cp.read(CONFIG_PATH, encoding="utf-8-sig")
    if not cp.has_section("LLM"):
        cp.add_section("LLM")
    cp.set("LLM", "provider", provider)
    cp.set("LLM", "api_key", api_key)
    cp.set("LLM", "base_url", base_url)
    cp.set("LLM", "model", model)
    cp.set("LLM", "max_tokens", str(max_tokens))
    cp.set("LLM", "temperature", str(temperature))

    config_dir = os.path.dirname(CONFIG_PATH)
    if config_dir and not os.path.isdir(config_dir):
        os.makedirs(config_dir)
    with open(CONFIG_PATH, "w", encoding="utf-8") as fp:
        cp.write(fp)

    CONFIG = _load_config()
    LLM_ENABLED = _is_llm_config_enabled(CONFIG)
    return _public_llm_config()


CONFIG = _load_config()
LLM_ENABLED = _is_llm_config_enabled(CONFIG)

# 分组模板保存目录：相对路径（相对 config.ini），加载时已规范化为绝对路径
# 用户在 XML 编辑器中显式点击保存时，模板 XML 才会写入此目录。
# 3DMPS 主程序启动时扫描该目录，写入后下次打开 3DMPS 即可看到新模板。
GROUP_TEMPLATE_SAVE_DIR = os.path.normpath(
    os.path.join(CONFIG_BASE_DIR, CONFIG["group_template_dir"])
)

AUTOIDENTIFY_WITH_DIRECTION_DIR = os.path.normpath(
    os.path.join(CONFIG_BASE_DIR, CONFIG["autoidentify_with_direction_dir"])
)

FEATURE_TEMPLATE_FILE = os.path.normpath(
    os.path.join(CONFIG_BASE_DIR, CONFIG["feature_template_file"])
)

# ============================================
# 工具调用配置（魔法数字集中管理）
# ============================================

# 对话框轮询配置（模板列表读取等）
DIALOG_POLL_MAX_ATTEMPTS = 20       # 最大轮询次数
DIALOG_POLL_INTERVAL_SEC = 0.25     # 轮询间隔（秒）
DIALOG_POLL_TIMEOUT_SEC = DIALOG_POLL_MAX_ATTEMPTS * DIALOG_POLL_INTERVAL_SEC  # 总超时约5秒

# 管道调用配置
PIPE_CONNECT_TIMEOUT_MS = 3000      # 连接超时（毫秒）
PIPE_CONNECT_RETRY_COUNT = 2        # 连接重试次数
PIPE_CONNECT_RETRY_DELAY = 0.5       # 重试间隔（秒）
PIPE_DEFAULT_TIMEOUT_SEC = 30.0     # 默认调用超时（秒）

# LLM 对话配置
LLM_MAX_TOOL_ITERATIONS = 5         # 最大工具调用迭代次数
LLM_STREAM_TIMEOUT_SEC = 120        # LLM API 调用超时（秒）
