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
_SCALAR_TYPES = {"string", "integer", "number", "boolean"}
_BASE_TYPES = set(_SCALAR_TYPES) | {"array", "object"}


@dataclass(frozen=True)
class _Options:
    remove_tags: tuple[str, ...] = ()


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

    if "defaults" in options:
        raise ExtractError("'options.defaults' is not supported. Remove defaults/text_transform; string outputs are stripped automatically.")

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
    return _Options(remove_tags=tuple(remove_tags))


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

    if "items" in field_spec:
        raise ExtractError(f"{path}.items is not supported; use type:'array<...>' (e.g. array<string>, array<object>).")
    if "list" in field_spec:
        raise ExtractError(f"{path}.list is not supported; use type:'array<...>' (e.g. array<string>, array<object>).")
    if "text" in field_spec:
        raise ExtractError(f"{path}.text is not supported; text is the default scalar mode.")
    if "html" in field_spec:
        raise ExtractError(f"{path}.html is not supported; use attr:'innerHTML' instead.")

    declared_type, array_items_type = _parse_field_type(field_spec.get("type", _MISSING), path=path)
    if declared_type is None:
        raise ExtractError(f"{path}.type is required.")
    nullable = _parse_nullable(field_spec.get("nullable", _MISSING), path=path)
    default_value = field_spec.get("defaultValue", _MISSING)

    required = field_spec.get("required", False)
    if "required" in field_spec and not isinstance(required, bool):
        raise ExtractError(f"{path}.required must be a boolean when provided.")
    if nullable is True and bool(required):
        raise ExtractError(f"{path}: nullable:true cannot be combined with required:true.")

    is_list = declared_type == "array"

    has_fields = "fields" in field_spec
    if declared_type == "array" and array_items_type is None:
        raise ExtractError(
            f"{path}.type must include an element type, e.g. array<string>, array<integer>, array<number>, array<boolean>, array<object>."
        )
    if declared_type == "array" and array_items_type == "object" and not has_fields:
        raise ExtractError(f"{path}.fields is required for type:'array<object>'.")
    if declared_type == "array" and array_items_type in _SCALAR_TYPES and has_fields:
        raise ExtractError(f"{path}.fields is only allowed for type:'array<object>'.")

    if declared_type == "object" and not has_fields:
        raise ExtractError(f"{path}.type is 'object' so {path}.fields is required.")
    if declared_type in ("string", "integer", "number", "boolean") and has_fields:
        raise ExtractError(f"{path}.fields is not allowed when {path}.type is {declared_type!r}.")
    if declared_type == "object" and default_value is not _MISSING and not isinstance(default_value, Mapping):
        raise ExtractError(f"{path}.defaultValue must be a mapping for type:'object'.")
    if declared_type == "array" and array_items_type == "object" and default_value is not _MISSING and not isinstance(default_value, list):
        raise ExtractError(f"{path}.defaultValue must be a list for type:'array<object>'.")

    css = field_spec.get("css")
    if css is None and context is None:
        value = [] if is_list else None
        value = _enforce_nullable(value, nullable=nullable, path=path)
        return _enforce_required(value, bool(required), path=path)

    if has_fields:
        fields = field_spec.get("fields")
        if not isinstance(fields, Mapping):
            raise ExtractError(f"{path}.fields must be a mapping.")

        if is_list:
            if not isinstance(css, str) or not css:
                raise ExtractError(f"{path}.css must be a non-empty string for type:'array<object>'.")
            nodes = _css(context, css)
            value = [_eval_fields(node, fields, options=options) for node in nodes]
            if value == [] and isinstance(default_value, list):
                value = list(default_value)
            value = _enforce_nullable(value, nullable=nullable, path=path)
            return _enforce_required(value, bool(required), path=path)

        if css is None:
            value = _eval_fields(context, fields, options=options)
            if value is None and default_value is not _MISSING:
                value = default_value
            value = _enforce_nullable(value, nullable=nullable, path=path)
            return _enforce_required(value, bool(required), path=path)

        if not isinstance(css, str) or not css:
            raise ExtractError(f"{path}.css must be a non-empty string when provided.")
        nodes = _css(context, css)
        if not nodes:
            value = _enforce_nullable(None, nullable=nullable, path=path)
            if value is None and default_value is not _MISSING:
                value = default_value
            return _enforce_required(value, bool(required), path=path)
        value = _eval_fields(nodes[0], fields, options=options)
        if value is None and default_value is not _MISSING:
            value = default_value
        value = _enforce_nullable(value, nullable=nullable, path=path)
        return _enforce_required(value, bool(required), path=path)

    # Scalar extraction
    if not isinstance(css, str) or not css:
        raise ExtractError(f"{path}.css is required for scalar fields.")

    if declared_type == "object":
        raise ExtractError(f"{path}.type is 'object' but no {path}.fields mapping was provided.")

    nodes = _css(context, css)
    extractor = _build_scalar_extractor(field_spec, path=path)
    is_inner_html = isinstance(field_spec.get("attr"), str) and field_spec.get("attr") == "innerHTML"
    should_strip_strings = not is_inner_html

    has_transform_key = "transform" in field_spec
    if has_transform_key:
        transforms = field_spec.get("transform", [])
        transforms_path = f"{path}.transform"
    else:
        transforms = []
        transforms_path = f"{path}.transform"

    if not is_list and _has_split_transform(transforms):
        raise ExtractError(f"{path}.transform: split requires type:'array<...>'.")

    # Numeric / boolean coercion is driven by declared `type`, so we don't need
    # to model conversion as a transform step.

    if is_list:
        values: list[Any] = []
        for node in nodes:
            raw = extractor(node)
            transformed = _apply_transforms(raw, transforms, path=transforms_path)
            if transformed is None or transformed == "" or transformed == []:
                if default_value is not _MISSING and not isinstance(default_value, list):
                    transformed = default_value
                else:
                    continue
            if isinstance(transformed, list):
                for item in transformed:
                    coerced = _coerce_scalar_type(item, declared_type=array_items_type, path=f"{path}")
                    if array_items_type == "string" and should_strip_strings and isinstance(coerced, str):
                        coerced = coerced.strip()
                    if _is_empty(coerced) and default_value is not _MISSING and not isinstance(default_value, list):
                        coerced = _coerce_scalar_type(default_value, declared_type=array_items_type, path=f"{path}.defaultValue")
                        if array_items_type == "string" and should_strip_strings and isinstance(coerced, str):
                            coerced = coerced.strip()
                    if _is_empty(coerced):
                        continue
                    values.append(coerced)
            else:
                coerced = _coerce_scalar_type(transformed, declared_type=array_items_type, path=f"{path}")
                if array_items_type == "string" and should_strip_strings and isinstance(coerced, str):
                    coerced = coerced.strip()
                if _is_empty(coerced) and default_value is not _MISSING and not isinstance(default_value, list):
                    coerced = _coerce_scalar_type(default_value, declared_type=array_items_type, path=f"{path}.defaultValue")
                    if array_items_type == "string" and should_strip_strings and isinstance(coerced, str):
                        coerced = coerced.strip()
                if _is_empty(coerced):
                    continue
                values.append(coerced)
        if values == [] and isinstance(default_value, list):
            values = [_coerce_scalar_type(v, declared_type=array_items_type, path=f"{path}.defaultValue") for v in default_value]
            if array_items_type == "string" and should_strip_strings:
                values = [v.strip() if isinstance(v, str) else v for v in values]
        values = _enforce_nullable(values, nullable=nullable, path=path)
        return _enforce_required(values, bool(required), path=path)

    if not nodes:
        raw = None
    else:
        raw = extractor(nodes[0])
    value = _apply_transforms(raw, transforms, path=transforms_path)
    if _is_empty(value) and default_value is not _MISSING:
        value = default_value
    value = _coerce_scalar_type(value, declared_type=declared_type, path=path)
    if declared_type == "string" and should_strip_strings and isinstance(value, str):
        value = value.strip()
    if _is_empty(value) and default_value is not _MISSING:
        value = _coerce_scalar_type(default_value, declared_type=declared_type, path=path)
        if declared_type == "string" and should_strip_strings and isinstance(value, str):
            value = value.strip()
    value = _enforce_nullable(value, nullable=nullable, path=path)
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

    if "items" in field_spec:
        raise ExtractError(f"{path}.items is not supported; use type:'array<...>' (e.g. array<string>, array<object>).")
    if "list" in field_spec:
        raise ExtractError(f"{path}.list is not supported; use type:'array<...>' (e.g. array<string>, array<object>).")
    if "text" in field_spec:
        raise ExtractError(f"{path}.text is not supported; text is the default scalar mode.")
    if "html" in field_spec:
        raise ExtractError(f"{path}.html is not supported; use attr:'innerHTML' instead.")

    declared_type, array_items_type = _parse_field_type(field_spec.get("type", _MISSING), path=path)
    if declared_type is None:
        raise ExtractError(f"{path}.type is required.")
    nullable = _parse_nullable(field_spec.get("nullable", _MISSING), path=path)
    default_value = field_spec.get("defaultValue", _MISSING)

    required = field_spec.get("required", False)
    if "required" in field_spec and not isinstance(required, bool):
        raise ExtractError(f"{path}.required must be a boolean when provided.")
    if nullable is True and bool(required):
        raise ExtractError(f"{path}: nullable:true cannot be combined with required:true.")

    is_list = declared_type == "array"

    has_fields = "fields" in field_spec
    if declared_type == "array" and array_items_type is None:
        raise ExtractError(
            f"{path}.type must include an element type, e.g. array<string>, array<integer>, array<number>, array<boolean>, array<object>."
        )
    if declared_type == "array" and array_items_type == "object" and not has_fields:
        raise ExtractError(f"{path}.fields is required for type:'array<object>'.")
    if declared_type == "array" and array_items_type in _SCALAR_TYPES and has_fields:
        raise ExtractError(f"{path}.fields is only allowed for type:'array<object>'.")

    if declared_type == "object" and not has_fields:
        raise ExtractError(f"{path}.type is 'object' so {path}.fields is required.")
    if declared_type in ("string", "integer", "number", "boolean") and has_fields:
        raise ExtractError(f"{path}.fields is not allowed when {path}.type is {declared_type!r}.")
    if declared_type == "array" and array_items_type == "object" and default_value is not _MISSING and not isinstance(default_value, list):
        raise ExtractError(f"{path}.defaultValue must be a list for type:'array<object>'.")
    css = field_spec.get("css")

    if has_fields:
        nested = field_spec.get("fields")
        if not isinstance(nested, Mapping):
            raise ExtractError(f"{path}.fields must be a mapping.")

        obj_schema = _schema_for_fields(nested, options=options, path=f"{path}.fields")

        if is_list:
            if not isinstance(css, str) or not css:
                raise ExtractError(f"{path}.css must be a non-empty string for type:'array<object>'.")
            arr_schema: dict[str, Any] = {"type": "array", "items": obj_schema}
            if required:
                arr_schema["minItems"] = 1
            if nullable is True:
                arr_schema["type"] = ["array", "null"]
            if default_value is not _MISSING and isinstance(default_value, list):
                arr_schema["default"] = default_value
            return arr_schema

        if css is None:
            # Object scoped to current context: never null in successful extraction.
            if nullable is True:
                out = _schema_nullable(obj_schema, "object")
                if default_value is not _MISSING and isinstance(default_value, Mapping):
                    out["default"] = default_value
                return out
            if default_value is not _MISSING and isinstance(default_value, Mapping):
                out = dict(obj_schema)
                out["default"] = default_value
                return out
            return obj_schema

        if not isinstance(css, str) or not css:
            raise ExtractError(f"{path}.css must be a non-empty string when provided.")

        if required or nullable is False:
            out = dict(obj_schema)
            if default_value is not _MISSING and isinstance(default_value, Mapping):
                out["default"] = default_value
            return out

        out = _schema_nullable(obj_schema, "object")
        if default_value is not _MISSING and isinstance(default_value, Mapping):
            out["default"] = default_value
        return out

    # Scalar field
    if not isinstance(css, str) or not css:
        raise ExtractError(f"{path}.css is required for scalar fields.")

    transforms = _effective_transforms(field_spec)
    _apply_transforms("x", transforms, path=f"{path}.transform")  # validate
    if not is_list and _has_split_transform(transforms):
        raise ExtractError(f"{path}.transform: split requires type:'array<...>'.")

    # Numeric / boolean coercion is driven by declared `type`.

    if is_list:
        base: dict[str, Any] = {"type": array_items_type}
        if default_value is not _MISSING and not isinstance(default_value, list):
            base["default"] = default_value

        arr_schema = {"type": "array", "items": base}
        if required:
            arr_schema["minItems"] = 1
        if nullable is True:
            arr_schema["type"] = ["array", "null"]
        if default_value is not _MISSING and isinstance(default_value, list):
            arr_schema["default"] = default_value
        return arr_schema

    base = {"type": declared_type}
    if default_value is not _MISSING:
        base["default"] = default_value

    if required:
        if declared_type == "string":
            return {"type": "string", "minLength": 1}
        return base

    if nullable is False:
        return base
    out: dict[str, Any] = {"type": [declared_type, "null"]}
    if default_value is not _MISSING:
        out["default"] = default_value
    return out


def _effective_transforms(field_spec: Mapping[str, Any]) -> list[Any]:
    if "transform" in field_spec:
        transforms = field_spec.get("transform", [])
        return [] if transforms is None else transforms
    return []


def _has_split_transform(transforms: Any) -> bool:
    if transforms in (None, []):
        return False
    if not isinstance(transforms, (list, tuple)):
        return False
    for step in transforms:
        if isinstance(step, Mapping) and len(step) == 1 and "split" in step:
            return True
    return False


def _parse_field_type(value: Any, *, path: str) -> tuple[str | None, str | None]:
    if value is _MISSING:
        return None, None
    if value is None:
        return None, None
    if not isinstance(value, str):
        raise ExtractError(f"{path}.type must be a string when provided.")

    value = value.strip()
    if value == "array":
        raise ExtractError(
            f"{path}.type for arrays must include an element type, e.g. array<string>, array<integer>, array<number>, array<boolean>, array<object>."
        )

    m = re.fullmatch(r"array<\s*(string|integer|number|boolean|object)\s*>", value)
    if m:
        return "array", m.group(1)

    if value not in (_SCALAR_TYPES | {"object"}):
        allowed_list = ", ".join(sorted(_SCALAR_TYPES | {"object"}))
        raise ExtractError(
            f"{path}.type must be one of: {allowed_list}, array<string>, array<integer>, array<number>, array<boolean>, array<object>."
        )
    return value, None


def _parse_nullable(value: Any, *, path: str) -> bool | None:
    if value is _MISSING:
        return None
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ExtractError(f"{path}.nullable must be a boolean when provided.")
    return value


def _schema_nullable(schema: Mapping[str, Any], kind: str) -> dict[str, Any]:
    out = dict(schema)
    out["type"] = [kind, "null"]
    return out


def _enforce_nullable(value: Any, *, nullable: bool | None, path: str) -> Any:
    if nullable is False and value is None:
        raise ValidationError(f"{path} cannot be null.")
    return value


def _coerce_scalar_type(value: Any, *, declared_type: str | None, path: str) -> Any:
    if declared_type is None:
        return value
    if value is None:
        return None

    if declared_type == "string":
        return str(value)

    if declared_type == "integer":
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value) if value.is_integer() else None
        return _safe_int(str(value))

    if declared_type == "number":
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        return _safe_float(str(value))

    if declared_type == "boolean":
        return _coerce_boolean(value)

    return value


def _coerce_boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value == 0:
            return False
        if value == 1:
            return True
        return None

    s = str(value).strip().lower()
    if s == "":
        return None
    if s in {"true", "t", "yes", "y", "on", "1"}:
        return True
    if s in {"false", "f", "no", "n", "off", "0"}:
        return False
    return None


def _scalar_mode(field_spec: Mapping[str, Any], path: str) -> str:
    attr = field_spec.get("attr", _MISSING)
    if attr is not _MISSING:
        return "attr"
    return "text"


def _build_scalar_extractor(field_spec: Mapping[str, Any], path: str):
    mode = _scalar_mode(field_spec, path=path)

    if mode == "text":
        return _node_text
    if mode == "attr":
        attr = field_spec.get("attr", _MISSING)
        if not isinstance(attr, str) or not attr:
            raise ExtractError(f"{path}.attr must be a non-empty string.")
        if attr == "innerHTML":
            return _node_html_content
        if attr == "ownText":
            return _node_own_text
        return lambda node: _node_attr(node, attr)

    raise ExtractError(f"{path}: unsupported extractor mode {mode!r}.")


def _node_text(node: Any) -> str | None:
    if node is None:
        return None

    # scrapling.parser.Selector exposes the underlying lxml element on `._root`.
    # Use it to approximate DOM `textContent` semantics, including descendant text
    # *and* tails (text after child elements).
    root = getattr(node, "_root", None)
    if root is not None:
        if isinstance(root, str):
            return root

        ignore_tags = {"script", "style"}
        ignored_elements: set[Any] = set()
        try:
            for element in root.iter(*ignore_tags):
                for ignored in element.iter():
                    ignored_elements.add(ignored)
        except TypeError:
            ignored_elements = set()

        parts: list[str] = []
        try:
            for el in root.iter():
                tag = getattr(el, "tag", None)
                if el not in ignored_elements:
                    text = getattr(el, "text", None)
                    if text and isinstance(text, str):
                        parts.append(text)

                tail = getattr(el, "tail", None)
                if tail and isinstance(tail, str):
                    if el not in ignored_elements or tag in ignore_tags:
                        parts.append(tail)
        except TypeError:
            parts = []

        if parts:
            return "".join(parts)

    # scrapling.parser.Selector: `.text` is *direct* text only; use `.get_all_text()`
    # as a best-effort fallback.
    get_all_text = getattr(node, "get_all_text", None)
    if callable(get_all_text):
        try:
            val = get_all_text()
        except TypeError:
            val = None
        if val is not None:
            return str(val)

    # lxml-ish APIs often expose `.text_content()`.
    text_content = getattr(node, "text_content", None)
    if callable(text_content):
        try:
            val = text_content()
        except TypeError:
            val = None
        if val is not None:
            return str(val)

    # Fallback to direct `.text` attribute or method.
    text = getattr(node, "text", None)
    if callable(text):
        try:
            val = text()
        except TypeError:
            val = None
        if val is not None:
            return str(val)

    if text is None:
        return None
    return str(text)


def _node_own_text(node: Any) -> str | None:
    """
    Direct text for the current node (does not include descendant text).

    This is closer to "own text" / "direct text node" semantics than jQuery's
    `$(el).text()` / DOM `textContent`, which include descendant text.
    """
    if node is None:
        return None

    root = getattr(node, "_root", None)
    if root is not None:
        parts: list[str] = []
        text = getattr(root, "text", None)
        if text:
            parts.append(str(text))
        try:
            children = list(root)
        except TypeError:
            children = []
        for child in children:
            tail = getattr(child, "tail", None)
            if tail:
                parts.append(str(tail))

        out = "".join(parts)
        return None if out.strip() == "" else out

    text = getattr(node, "text", None)
    if callable(text):
        try:
            text = text()
        except TypeError:
            text = None
    if text is None:
        return None
    out = str(text)
    return None if out.strip() == "" else out


def _node_html_content(node: Any) -> str | None:
    val = getattr(node, "html_content", None)
    if val is None:
        # Fallbacks for similar node implementations.
        val = getattr(node, "html", None)
        if callable(val):
            try:
                val = val()
            except TypeError:
                val = None
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
            raise ExtractError(f"{path}: 'strip' is implicit and not supported in transforms.")
        if step in {"to_int", "to_float"}:
            raise ExtractError(
                f"{path}: {step!r} is no longer supported; set the field type instead "
                f"(type:'integer' / type:'number' / type:'array<integer>' / type:'array<number>')."
            )
        raise ExtractError(f"{path}: unknown transform {step!r}.")

    if not isinstance(step, Mapping) or len(step) != 1:
        raise ExtractError(f"{path} must be a string or a single-key mapping.")

    (name, cfg), = step.items()
    if name == "strip":
        raise ExtractError(f"{path}.strip is implicit and not supported in transforms.")

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
        raise ExtractError(
            f"{path}.to_int is no longer supported; set the field type instead "
            f"(type:'integer' / type:'array<integer>')."
        )

    if name == "to_float":
        raise ExtractError(
            f"{path}.to_float is no longer supported; set the field type instead "
            f"(type:'number' / type:'array<number>')."
        )

    if name == "default":
        raise ExtractError(
            f"{path}.default is not supported; use field-level defaultValue instead."
        )

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
