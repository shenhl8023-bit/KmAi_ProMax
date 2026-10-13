from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path

MAP_VERSION = 1
MAP_FILENAME = "模板映射.json"
TEMPLATES_DIR_NAME = "模板"
SAMPLES_DIR_NAME = "XML样本"
SAMPLES_DIR_RELATIVE = "source/XML样本"

ERROR_MAP_FILE_CORRUPT = "MAP_FILE_CORRUPT"
ERROR_MAP_VERSION_UNSUPPORTED = "MAP_VERSION_UNSUPPORTED"
ERROR_TEMPLATE_NOT_FOUND = "TEMPLATE_NOT_FOUND"
ERROR_SAMPLE_KEY_EMPTY = "SAMPLE_KEY_EMPTY"
ERROR_MAP_DIR_MISSING = "MAP_DIR_MISSING"
ERROR_MAP_FILE_UNWRITABLE = "MAP_FILE_UNWRITABLE"


class TemplateMapError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _repo_root() -> Path:
    # src/part_classification/template_map.py -> 仓库根
    return Path(__file__).resolve().parents[2]


def default_templates_dir() -> Path:
    return _repo_root() / "source" / TEMPLATES_DIR_NAME


def default_map_path() -> Path:
    return default_templates_dir() / MAP_FILENAME


def default_samples_dir() -> Path:
    return _repo_root() / "source" / SAMPLES_DIR_NAME


def list_templates(templates_dir: str | Path | None = None) -> list[dict]:
    """扫描模板库；目录不存在返回空列表，不创建目录。"""

    directory = Path(templates_dir) if templates_dir is not None else default_templates_dir()
    if not directory.is_dir():
        return []
    found = [
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() == ".xml"
    ]
    found.sort(key=lambda path: path.name.casefold())
    return [{"name": path.name, "path": str(path.resolve())} for path in found]


def _empty_map() -> dict:
    return {"version": MAP_VERSION, "samplesDir": SAMPLES_DIR_RELATIVE, "mappings": {}}


def _expect_object(value: object, target: Path, field: str) -> dict:
    if not isinstance(value, dict):
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT,
            f"清单字段 {field} 不是对象：{target}",
        )
    return value


def _normalise_entry(sample: str, entry: object, target: Path | None = None) -> dict:
    """校验并规范化一条记录。读路径与写路径共用，保证「写得出就读得回」。

    target 只在有具体文件路径时用于错误信息。
    """

    where = f"（{target}）" if target is not None else ""
    if not isinstance(entry, dict):
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 的记录不是对象{where}"
        )
    template = entry.get("template")
    if not isinstance(template, str) or not template:
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 缺少 template 字段{where}"
        )
    note = entry.get("note", "")
    if not isinstance(note, str):
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 的 note 不是字符串{where}"
        )
    updated_at = entry.get("updatedAt", "")
    if not isinstance(updated_at, str):
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT, f"样本 {sample} 的 updatedAt 不是字符串{where}"
        )
    return {"template": template, "note": note, "updatedAt": updated_at}


def load_map(path: str | Path | None = None) -> dict:
    """读取清单。文件不存在返回空清单；损坏或版本不支持抛 TemplateMapError。"""

    target = Path(path) if path is not None else default_map_path()
    if not target.is_file():
        return _empty_map()
    try:
        # utf-8-sig 兼容带 BOM 的 UTF-8：记事本和 PowerShell 重定向都会写 BOM，
        # 而 BOM 仍是合法 UTF-8，不能当成损坏。
        raw = target.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        # 按非 UTF-8（例如本仓库惯用的 GBK）存盘的清单必须报损坏。
        # UnicodeDecodeError 是 ValueError 而不是 OSError，漏出去会让 GUI 打不开
        # 窗口、classify 直接抛异常，所以必须单独捕获。
        raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"清单不是 UTF-8 文本：{target}") from exc
    except OSError as exc:
        raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"清单无法读取：{target}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"清单不是合法 JSON：{target}") from exc

    data = _expect_object(data, target, "根")
    if data.get("version") != MAP_VERSION:
        raise TemplateMapError(
            ERROR_MAP_VERSION_UNSUPPORTED,
            f"清单版本不受支持（期望 {MAP_VERSION}）：{target}",
        )
    mappings = _expect_object(data.get("mappings"), target, "mappings")

    normalised: dict[str, dict] = {}
    for sample, entry in mappings.items():
        if not isinstance(sample, str) or not sample:
            raise TemplateMapError(ERROR_MAP_FILE_CORRUPT, f"样本键无效：{sample!r}")
        normalised[sample] = _normalise_entry(sample, entry, target)

    samples_dir = data.get("samplesDir")
    if not isinstance(samples_dir, str):
        samples_dir = SAMPLES_DIR_RELATIVE
    return {"version": MAP_VERSION, "samplesDir": samples_dir, "mappings": normalised}


def save_map(data: dict, path: str | Path | None = None) -> None:
    """原子写入清单：临时文件 + fsync + os.replace；不创建父目录。"""

    target = Path(path) if path is not None else default_map_path()
    mappings = data.get("mappings")
    if mappings is None:
        mappings = {}
    if not isinstance(mappings, dict):
        # 容器类型不对时报 TemplateMapError，不能漏 AttributeError/TypeError。
        raise TemplateMapError(
            ERROR_MAP_FILE_CORRUPT, f"mappings 不是对象：{mappings!r}"
        )
    # 写路径复用读路径的校验与规范化，保证写出的清单一定能被读回。
    # 排序同时用 casefold 与原始键：仅大小写不同的键在 casefold 下并列，
    # 只按 casefold 排会得到依赖哈希种子的顺序，GUI 列表和 CSV 都会不稳定。
    payload = {
        "version": MAP_VERSION,
        "samplesDir": data.get("samplesDir") or SAMPLES_DIR_RELATIVE,
        "mappings": {
            key: _normalise_entry(key, entry)
            for key, entry in sorted(
                mappings.items(),
                key=lambda item: (str(item[0]).casefold(), str(item[0])),
            )
        },
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    try:
        handle_fd, temp_name = tempfile.mkstemp(
            dir=str(target.parent),
            prefix=".template-map-",
            suffix=".tmp",
        )
    except OSError as exc:
        raise TemplateMapError(
            ERROR_MAP_DIR_MISSING,
            f"清单目录不存在或不可写：{target.parent}",
        ) from exc

    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except OSError as exc:
        # 只读清单、被其他进程占用、磁盘满等都在这里。必须翻译成
        # TemplateMapError：GUI 只捕获这个类型，漏出 OSError 会让用户
        # 点保存后既没有提示、也没有状态栏文字。
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise TemplateMapError(
            ERROR_MAP_FILE_UNWRITABLE,
            f"清单无法写入：{target}（{exc}）",
        ) from exc
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _resolve_templates_dir(
    path: str | Path | None,
    templates_dir: str | Path | None = None,
) -> Path:
    if templates_dir is not None:
        return Path(templates_dir)
    if path is not None:
        # 清单与模板库同目录；自定义清单路径时以清单所在目录为模板库。
        return Path(path).parent
    return default_templates_dir()


def _template_names(templates_dir: Path) -> dict[str, str]:
    return {row["name"]: row["path"] for row in list_templates(templates_dir)}


def _validate_sample_key(sample: str) -> str:
    # 注意：Path(".XML").suffix 是空串、stem 是 ".XML"，所以必须按 suffix 判定，
    # 不能用 stem == ""，否则「只有扩展名」的键会被放过。
    if not isinstance(sample, str) or not sample.strip():
        raise TemplateMapError(ERROR_SAMPLE_KEY_EMPTY, f"样本名无效：{sample!r}")
    path = Path(sample)
    if path.suffix == "" or not path.stem.strip("."):
        raise TemplateMapError(
            ERROR_SAMPLE_KEY_EMPTY,
            f"样本名无效（缺文件名或只有扩展名）：{sample!r}",
        )
    return sample


def get_mapping(sample: str, path: str | Path | None = None) -> dict | None:
    entry = load_map(path)["mappings"].get(sample)
    return dict(entry) if entry is not None else None


def set_mapping(
    sample: str,
    template: str,
    note: str = "",
    path: str | Path | None = None,
) -> dict:
    """登记一条映射。样本名与模板名先校验，校验失败不写盘。"""

    key = _validate_sample_key(sample)
    if template not in _template_names(_resolve_templates_dir(path)):
        raise TemplateMapError(
            ERROR_TEMPLATE_NOT_FOUND,
            f"模板不在模板库中：{template!r}",
        )
    data = load_map(path)
    entry = {
        "template": template,
        "note": note,
        "updatedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    }
    data["mappings"][key] = entry
    save_map(data, path)
    return dict(entry)


def remove_mapping(sample: str, path: str | Path | None = None) -> bool:
    data = load_map(path)
    if sample not in data["mappings"]:
        return False
    del data["mappings"][sample]
    save_map(data, path)
    return True


def _dedupe(samples) -> list[str]:
    """去重并保持传入顺序；样本名必须是字符串。"""

    seen: set[str] = set()
    ordered: list[str] = []
    for sample in samples:
        key = _validate_sample_key(sample)
        if key not in seen:
            seen.add(key)
            ordered.append(key)
    return ordered


def set_mappings(
    samples,
    template: str,
    note: str = "",
    path: str | Path | None = None,
) -> list[str]:
    """批量登记同一模板。先整体校验，再只写一次盘。

    任一校验失败都不修改清单文件。note 留空时保留各样本已有的备注，
    避免一次批量抹掉多行备注；传了 note 才会统一覆盖。
    """

    keys = _dedupe(samples)
    if not keys:
        return []
    if template not in _template_names(_resolve_templates_dir(path)):
        raise TemplateMapError(
            ERROR_TEMPLATE_NOT_FOUND,
            f"模板不在模板库中：{template!r}",
        )

    data = load_map(path)
    stamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    for key in keys:
        existing = data["mappings"].get(key)
        data["mappings"][key] = {
            "template": template,
            "note": note if note else (existing["note"] if existing else ""),
            "updatedAt": stamp,
        }
    save_map(data, path)
    return keys


def remove_mappings(samples, path: str | Path | None = None) -> list[str]:
    """批量解除映射。返回实际删除的样本名；只写一次盘。

    未配置的样本名会被跳过（与 remove_mapping 返回 False 的语义一致），
    不视为错误。
    """

    keys = _dedupe(samples)
    if not keys:
        return []
    data = load_map(path)
    removed = [key for key in keys if key in data["mappings"]]
    if not removed:
        return []
    for key in removed:
        del data["mappings"][key]
    save_map(data, path)
    return removed


def template_for_sample(
    sample: str,
    *,
    templates_dir: str | Path | None = None,
    map_path: str | Path | None = None,
) -> dict | None:
    """给 classify 用：返回 {"name", "path", "note"}；未配置返回 None。

    映射存在但模板文件已缺失时 path 为 None，映射本身不被清除。
    """

    entry = get_mapping(sample, map_path)
    if entry is None:
        return None
    names = _template_names(_resolve_templates_dir(map_path, templates_dir))
    return {
        "name": entry["template"],
        "path": names.get(entry["template"]),
        "note": entry["note"],
    }


def _sample_names(samples_dir: Path) -> set[str]:
    if not samples_dir.is_dir():
        return set()
    return {
        path.name
        for path in samples_dir.iterdir()
        if path.is_file() and path.suffix.lower() == ".xml"
    }


def list_mappings(
    templates_dir: str | Path | None = None,
    samples_dir: str | Path | None = None,
    path: str | Path | None = None,
) -> list[dict]:
    """汇总视图：已配置行按样本名升序在前，未配置行在后。"""

    data = load_map(path)
    templates = _template_names(_resolve_templates_dir(path, templates_dir))
    directory = Path(samples_dir) if samples_dir is not None else default_samples_dir()
    present = _sample_names(directory)
    mappings = data["mappings"]

    rows: list[dict] = []
    for sample in sorted(set(mappings) | present, key=lambda name: (name.casefold(), name)):
        entry = mappings.get(sample)
        template_name = entry["template"] if entry is not None else None
        rows.append(
            {
                "sample": sample,
                "sampleExists": sample in present,
                "template": template_name,
                "templateExists": template_name in templates if template_name else False,
                "templatePath": templates.get(template_name) if template_name else None,
                "note": entry["note"] if entry is not None else "",
                "updatedAt": entry["updatedAt"] if entry is not None else "",
            }
        )
    rows.sort(key=lambda row: (row["template"] is None, row["sample"].casefold(), row["sample"]))
    return rows


__all__ = [
    "MAP_FILENAME",
    "MAP_VERSION",
    "SAMPLES_DIR_RELATIVE",
    "TemplateMapError",
    "default_map_path",
    "default_samples_dir",
    "default_templates_dir",
    "get_mapping",
    "list_mappings",
    "list_templates",
    "load_map",
    "remove_mapping",
    "remove_mappings",
    "save_map",
    "set_mapping",
    "set_mappings",
    "template_for_sample",
]
