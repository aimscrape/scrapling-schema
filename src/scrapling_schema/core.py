from __future__ import annotations

from dataclasses import dataclass
import re
from functools import lru_cache
from typing import Any, Mapping

import yaml
from scrapling.parser import Selector


class ExtractError(ValueError):
    pass


class ValidationError(ValueError):
    pass


_MISSING = object()


@dataclass(frozen=True)
class _Options:
    remove_tags: tuple[str, ...] = ()
    default_text_transform: tuple[Any, ...] = ()


def extract_from_yaml(html: str, yaml_spec: str) -> Any:
    spec = _load_yaml_spec(yaml_spec)
    return extract(html, spec)


def schema_from_yaml(yaml_spec: str, *, title: str | None = None) -> dict[str, Any]:
    spec = _load_yaml_spec(yaml_spec)
    return schema(spec, title=title)


def extract_from_file(html: str, spec_path: str) -> Any:
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    return extract(html, spec)


def schema_from_file(spec_path: str, *, title: str | None = None) -> dict[str, Any]:
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = yaml.safe_load(f)
    if not isinstance(spec, Mapping):
        raise ExtractError("Spec must be a mapping (dict-like).")
    return schema(spec, title=title)


def extract(html: str, spec: Mapping[str, Any]) -> Any:
    if not isinstance(spec, Mapping):
        raise ExtractError("Spec must be a mapping (dict-like).")

    options = _parse_options(spec.get("options", {}))
    html = _preprocess_html(html, options)

    parser = Selector(html)
    fields = spec.get("fields")
    if not isinstance(fields, Mapping):
        raise ExtractError("Spec must contain top-level 'fields' mapping.")

    return _eval_fields(parser, fields, options=options)


def schema(spec: Mapping[str, Any], *, title: str | None = None) -> dict[str, Any]:
    if not isinstance(spec, Mapping):
        raise ExtractError("Spec must be a mapping (dict-like).")

    options = _parse_options(spec.get("options", {}))

    fields = spec.get("fields")
    if not isinstance(fields, Mapping):
        raise ExtractError("Spec must contain top-level 'fields' mapping.")

    out: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
    }
    if title:
        out["title"] = title

    field_schema = _schema_for_fields(fields, options=options, path="fields")
    out["properties"] = field_schema["properties"]
    out["required"] = field_schema["required"]
    return out

def _load_yaml_spec(yaml_spec: str) -> Mapping[str, Any]:
    loaded = yaml.safe_load(yaml_spec)
    if not isinstance(loaded, Mapping):
        raise ExtractError("YAML spec must parse to a mapping (dict-like).")
    return loaded


def _parse_options(options: Any) -> _Options:
    if options in (None, {}):
        return _Options()
    if not isinstance(options, Mapping):
        raise ExtractError("'options' must be a mapping when provided.")

    defaults = options.get("defaults", {})
    if defaults in (None, {}):
        defaults = {}
    if not isinstance(defaults, Mapping):
        raise ExtractError("'options.defaults' must be a mapping when provided.")

    default_text_transform = defaults.get("text_transform", [])
    if default_text_transform is None:
        default_text_transform = []
    if not isinstance(default_text_transform, list):
        raise ExtractError("'options.defaults.text_transform' must be a list when provided.")
    if _has_split_transform(default_text_transform):
        raise ExtractError("'options.defaults.text_transform' cannot include split; use a list:true field transform instead.")

    clear = options.get("clear", {})
    if clear in (None, {}):
        clear = {}
    if not isinstance(clear, Mapping):
        raise ExtractError("'options.clear' must be a mapping when provided.")

    remove_tags = clear.get("remove_tags", [])
    if remove_tags is None:
        remove_tags = []
    if not isinstance(remove_tags, list) or not all(isinstance(t, str) for t in remove_tags):
        raise ExtractError("'options.clear.remove_tags' must be a list of strings.")
    return _Options(
        remove_tags=tuple(remove_tags),
        default_text_transform=tuple(default_text_transform),
    )


@lru_cache(maxsize=256)
def _compile_regex(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern)


@lru_cache(maxsize=64)
def _compile_remove_tags_pattern(remove_tags: tuple[str, ...]) -> re.Pattern[str]:
    tags = "|".join(re.escape(tag) for tag in remove_tags)
    return re.compile(
        rf"(<(?P<tag>{tags})\b[^>]*>[\s\S]*?</(?P=tag)>)",
        re.IGNORECASE,
    )


def _preprocess_html(html: str, options: _Options) -> str:
    if not options.remove_tags:
        return html

    # Keep it intentionally simple and predictable: strip full tag blocks.
    # This is not a full HTML sanitizer.
    pattern = _compile_remove_tags_pattern(options.remove_tags)
    return pattern.sub("", html)


def _eval_fields(context: Any, fields: Mapping[str, Any], options: _Options) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, field_spec in fields.items():
        out[key] = _eval_field(context, field_spec, path=f"fields.{key}", options=options)
    return out


def _eval_field(context: Any, field_spec: Any, path: str, options: _Options) -> Any:
    if not isinstance(field_spec, Mapping):
        raise ExtractError(f"{path} must be a mapping.")

    required = field_spec.get("required", False)
    if "required" in field_spec and not isinstance(required, bool):
        raise ExtractError(f"{path}.required must be a boolean when provided.")

    is_list = bool(field_spec.get("list", False))
    has_fields = "fields" in field_spec

    css = field_spec.get("css")
    if css is None and context is None:
        value = [] if is_list else None
        return _enforce_required(value, bool(required), path=path)

    if has_fields:
        fields = field_spec.get("fields")
        if not isinstance(fields, Mapping):
            raise ExtractError(f"{path}.fields must be a mapping.")

        if is_list:
            if not isinstance(css, str) or not css:
                raise ExtractError(f"{path}.css must be a non-empty string when list:true and fields is present.")
            nodes = _css(context, css)
            value = [_eval_fields(node, fields, options=options) for node in nodes]
            return _enforce_required(value, bool(required), path=path)

        if css is None:
            value = _eval_fields(context, fields, options=options)
            return _enforce_required(value, bool(required), path=path)

        if not isinstance(css, str) or not css:
            raise ExtractError(f"{path}.css must be a non-empty string when provided.")
        nodes = _css(context, css)
        if not nodes:
            return _enforce_required(None, bool(required), path=path)
        value = _eval_fields(nodes[0], fields, options=options)
        return _enforce_required(value, bool(required), path=path)

    # Scalar extraction
    if not isinstance(css, str) or not css:
        raise ExtractError(f"{path}.css is required for scalar fields.")

    nodes = _css(context, css)
    extractor = _build_scalar_extractor(field_spec, path=path)
    mode = _scalar_mode(field_spec, path=path)

    has_transform_key = "transform" in field_spec
    if has_transform_key:
        transforms = field_spec.get("transform", [])
        transforms_path = f"{path}.transform"
    else:
        if mode == "text" and options.default_text_transform:
            transforms = options.default_text_transform
            transforms_path = f"options.defaults.text_transform (for {path})"
        else:
            transforms = []
            transforms_path = f"{path}.transform"

    if not is_list and _has_split_transform(transforms):
        raise ExtractError(f"{path}.transform: split requires list:true for scalar fields.")

    if is_list:
        values: list[Any] = []
        for node in nodes:
            raw = extractor(node)
            transformed = _apply_transforms(raw, transforms, path=transforms_path)
            if transformed is None or transformed == "" or transformed == []:
                continue
            if isinstance(transformed, list):
                for item in transformed:
                    if _is_empty(item):
                        continue
                    values.append(item)
            else:
                values.append(transformed)
        return _enforce_required(values, bool(required), path=path)

    if not nodes:
        raw = None
    else:
        raw = extractor(nodes[0])
    value = _apply_transforms(raw, transforms, path=transforms_path)
    return _enforce_required(value, bool(required), path=path)


def _css(context: Any, selector: str) -> list[Any]:
    if context is None:
        return []
    if selector == "SELF":
        return [context]

    css_method = getattr(context, "css", None)
    if css_method is None or not callable(css_method):
        raise ExtractError("Context does not support CSS selection via .css().")
    nodes = css_method(selector)
    if nodes is None:
        return []
    return nodes if isinstance(nodes, list) else list(nodes)


def _enforce_required(value: Any, required: bool, path: str) -> Any:
    if not required:
        return value
    if _is_empty(value):
        raise ValidationError(f"{path} is required.")
    return value


def _schema_for_fields(fields: Mapping[str, Any], *, options: _Options, path: str) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required_keys: list[str] = []
    for key, field_spec in fields.items():
        required_keys.append(str(key))
        properties[str(key)] = _schema_for_field(field_spec, options=options, path=f"{path}.{key}")

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required_keys,
    }


def _schema_for_field(field_spec: Any, *, options: _Options, path: str) -> dict[str, Any]:
    if not isinstance(field_spec, Mapping):
        raise ExtractError(f"{path} must be a mapping.")

    required = field_spec.get("required", False)
    if "required" in field_spec and not isinstance(required, bool):
        raise ExtractError(f"{path}.required must be a boolean when provided.")

    is_list = bool(field_spec.get("list", False))
    has_fields = "fields" in field_spec
    css = field_spec.get("css")

    if has_fields:
        nested = field_spec.get("fields")
        if not isinstance(nested, Mapping):
            raise ExtractError(f"{path}.fields must be a mapping.")

        obj_schema = _schema_for_fields(nested, options=options, path=f"{path}.fields")

        if is_list:
            if not isinstance(css, str) or not css:
                raise ExtractError(f"{path}.css must be a non-empty string when list:true and fields is present.")
            arr_schema: dict[str, Any] = {"type": "array", "items": obj_schema}
            if required:
                arr_schema["minItems"] = 1
            return arr_schema

        if css is None:
            # Object scoped to current context: never null in successful extraction.
            return obj_schema

        if not isinstance(css, str) or not css:
            raise ExtractError(f"{path}.css must be a non-empty string when provided.")

        if required:
            return obj_schema

        return {"type": ["object", "null"], **obj_schema}

    # Scalar field
    if not isinstance(css, str) or not css:
        raise ExtractError(f"{path}.css is required for scalar fields.")

    mode = _scalar_mode(field_spec, path=path)
    transforms = _effective_transforms(field_spec, options=options, mode=mode)
    _apply_transforms("x", transforms, path=f"{path}.transform")  # validate
    if not is_list and _has_split_transform(transforms):
        raise ExtractError(f"{path}.transform: split requires list:true for scalar fields.")

    scalar_kind, returns_list = _infer_scalar_kind(transforms)
    base: dict[str, Any] = {"type": scalar_kind}

    if is_list:
        arr_schema = {"type": "array", "items": base}
        if required:
            arr_schema["minItems"] = 1
        return arr_schema

    if returns_list:
        raise ExtractError(f"{path}.transform: split requires list:true for scalar fields.")

    if required:
        if scalar_kind == "string":
            return {"type": "string", "minLength": 1}
        return base

    return {"type": [scalar_kind, "null"]}


def _effective_transforms(field_spec: Mapping[str, Any], *, options: _Options, mode: str) -> list[Any]:
    if "transform" in field_spec:
        transforms = field_spec.get("transform", [])
        return [] if transforms is None else transforms
    if mode == "text" and options.default_text_transform:
        return options.default_text_transform
    return []


def _has_split_transform(transforms: Any) -> bool:
    if transforms in (None, []):
        return False
    if not isinstance(transforms, list):
        return False
    for step in transforms:
        if isinstance(step, Mapping) and len(step) == 1 and "split" in step:
            return True
    return False


def _infer_scalar_kind(transforms: list[Any]) -> tuple[str, bool]:
    kind = "string"
    returns_list = False
    for step in transforms:
        if step == "to_int":
            kind = "integer"
        elif step == "to_float":
            kind = "number"
        elif isinstance(step, Mapping) and len(step) == 1:
            (name, _cfg), = step.items()
            if name == "split":
                returns_list = True
            elif name == "to_int":
                kind = "integer"
            elif name == "to_float":
                kind = "number"
    return kind, returns_list


def _scalar_mode(field_spec: Mapping[str, Any], path: str) -> str:
    text = field_spec.get("text", _MISSING)
    attr = field_spec.get("attr", _MISSING)
    html = field_spec.get("html", _MISSING)

    modes: list[str] = []
    if text is not _MISSING and bool(text):
        modes.append("text")
    if attr is not _MISSING:
        modes.append("attr")
    if html is not _MISSING and bool(html):
        modes.append("html")

    if not modes:
        return "text"
    if len(modes) > 1:
        raise ExtractError(f"{path}: choose only one of text/attr/html (or omit to default text).")
    return modes[0]


def _build_scalar_extractor(field_spec: Mapping[str, Any], path: str):
    mode = _scalar_mode(field_spec, path=path)

    if mode == "text":
        return _node_text
    if mode == "html":
        return _node_outer_html
    if mode == "attr":
        attr = field_spec.get("attr", _MISSING)
        if not isinstance(attr, str) or not attr:
            raise ExtractError(f"{path}.attr must be a non-empty string.")
        return lambda node: _node_attr(node, attr)

    raise ExtractError(f"{path}: unsupported extractor mode {mode!r}.")


def _node_text(node: Any) -> str | None:
    val = getattr(node, "text", None)
    if val is None:
        return None
    return str(val)


def _node_outer_html(node: Any) -> str | None:
    val = getattr(node, "html_content", None)
    if val is None:
        return None
    return str(val)


def _node_attr(node: Any, name: str) -> str | None:
    attrs = getattr(node, "attrib", None)
    if isinstance(attrs, Mapping):
        val = attrs.get(name)
        return None if val is None else str(val)

    attr_method = getattr(node, "attr", None)
    if callable(attr_method):
        val = attr_method(name)
        return None if val is None else str(val)

    return None


def _apply_transforms(value: Any, transforms: Any, path: str) -> Any:
    if not transforms:
        return value
    if not isinstance(transforms, (list, tuple)):
        raise ExtractError(f"{path} must be a list.")

    current = value
    for i, t in enumerate(transforms):
        step_path = f"{path}[{i}]"
        current = _apply_transform_step(current, t, step_path)
    return current


def _apply_transform_step(value: Any, step: Any, path: str) -> Any:
    if callable(step) and not isinstance(step, Mapping):
        return step(value)

    if isinstance(step, Mapping) and "__callable__" in step:
        return step["__callable__"](value)

    if isinstance(step, str):
        if step == "strip":
            return _map_str(value, str.strip)
        if step == "to_int":
            return _map_str(value, _safe_int)
        if step == "to_float":
            return _map_str(value, _safe_float)
        raise ExtractError(f"{path}: unknown transform {step!r}.")

    if not isinstance(step, Mapping) or len(step) != 1:
        raise ExtractError(f"{path} must be a string or a single-key mapping.")

    (name, cfg), = step.items()
    if name == "strip":
        if cfg not in (True, None, {}):
            raise ExtractError(f"{path}.strip must be true.")
        return _map_str(value, str.strip)

    if name == "regex_sub":
        if not isinstance(cfg, Mapping):
            raise ExtractError(f"{path}.regex_sub must be a mapping.")
        pattern = cfg.get("pattern")
        repl = cfg.get("repl", "")
        if not isinstance(pattern, str) or pattern == "":
            raise ExtractError(f"{path}.regex_sub.pattern must be a non-empty string.")
        if not isinstance(repl, str):
            raise ExtractError(f"{path}.regex_sub.repl must be a string.")
        regex = _compile_regex(pattern)
        return _map_str(value, lambda s: regex.sub(repl, s))

    if name == "split":
        if not isinstance(cfg, str):
            raise ExtractError(f"{path}.split must be a string delimiter.")
        return _split_value(value, cfg)

    if name == "to_int":
        if cfg not in (True, None, {}):
            raise ExtractError(f"{path}.to_int must be true.")
        return _map_str(value, _safe_int)

    if name == "to_float":
        if cfg not in (True, None, {}):
            raise ExtractError(f"{path}.to_float must be true.")
        return _map_str(value, _safe_float)

    if name == "default":
        return cfg if _is_empty(value) else value

    raise ExtractError(f"{path}: unknown transform {name!r}.")


def _map_str(value: Any, fn):
    if value is None:
        return None
    if isinstance(value, list):
        return [fn(str(v)) for v in value]
    return fn(str(value))


def _split_value(value: Any, delim: str):
    if value is None:
        return None
    if isinstance(value, list):
        out: list[str] = []
        for v in value:
            out.extend(str(v).split(delim))
        return out
    return str(value).split(delim)


def _safe_int(s: str):
    s = s.strip()
    if s == "":
        return None
    try:
        return int(s, 10)
    except ValueError:
        return None


def _safe_float(s: str):
    s = s.strip()
    if s == "":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    if isinstance(value, list) and len(value) == 0:
        return True
    return False
