"""
Python type structures for scrapling-schema specs.

Instead of writing raw YAML/dicts, define your spec with full IDE type hints:

    from scrapling_schema.types import Schema, Field, Options, Clear, RegexSub

    spec = Schema(
        options=Options(clear=Clear(remove_tags=["script", "style"])),
        fields={
            "price": Field(css=".price", text=True, transform=["strip", RegexSub(pattern=r"[^0-9.]+"), "to_float"]),
            "tags":  Field(css=".tags li", list=True, text=True, transform=["strip"]),
        }
    )

    result = spec.extract(html)
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

@dataclass
class RegexSub:
    pattern: str
    repl: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"regex_sub": {"pattern": self.pattern, "repl": self.repl}}


@dataclass
class Split:
    delimiter: str

    def to_dict(self) -> dict[str, Any]:
        return {"split": self.delimiter}


@dataclass
class ToInt:
    def to_dict(self) -> dict[str, Any]:
        return {"to_int": True}


@dataclass
class ToFloat:
    def to_dict(self) -> dict[str, Any]:
        return {"to_float": True}


@dataclass
class Default:
    value: Any

    def to_dict(self) -> dict[str, Any]:
        return {"default": self.value}


# A transform step is either a shorthand string or one of the above objects.
# Shorthand strings: "strip", "to_int", "to_float"
TransformStep = str | RegexSub | Split | ToInt | ToFloat | Default | Callable


def _serialize_transform(steps: list[TransformStep]) -> list[Any]:
    out: list[Any] = []
    for step in steps:
        if callable(step) and not isinstance(step, (str, RegexSub, Split, ToInt, ToFloat, Default)):
            out.append({"__callable__": step})
        elif isinstance(step, str):
            out.append(step)
        else:
            out.append(step.to_dict())
    return out


# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------

@dataclass
class Clear:
    remove_tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"remove_tags": list(self.remove_tags)}


@dataclass
class Defaults:
    text_transform: list[TransformStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"text_transform": _serialize_transform(self.text_transform)}


@dataclass
class Options:
    clear: Clear | None = None
    defaults: Defaults | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.clear:
            out["clear"] = self.clear.to_dict()
        if self.defaults:
            out["defaults"] = self.defaults.to_dict()
        return out


# ---------------------------------------------------------------------------
# Field
# ---------------------------------------------------------------------------

@dataclass
class Field:
    css: str
    # extraction mode — at most one should be set
    text: bool = False
    attr: str | None = None
    html: bool = False
    # list / nested
    list: bool = False
    fields: dict[str, "Field"] | None = None
    # transforms
    transform: list[TransformStep] | None = None
    # validation
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"css": self.css}
        if self.text:
            out["text"] = True
        if self.attr is not None:
            out["attr"] = self.attr
        if self.html:
            out["html"] = True
        if self.list:
            out["list"] = True
        if self.fields is not None:
            out["fields"] = {k: v.to_dict() for k, v in self.fields.items()}
        if self.transform is not None:
            out["transform"] = _serialize_transform(self.transform)
        if self.required:
            out["required"] = True
        return out


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass
class Schema:
    fields: dict[str, Field]
    options: Options | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.options:
            out["options"] = self.options.to_dict()
        out["fields"] = {k: v.to_dict() for k, v in self.fields.items()}
        return out

    def extract(self, html: str) -> Any:
        from .core import extract as _extract
        return _extract(html, self.to_dict())

    def json_schema(self, *, title: str | None = None) -> dict[str, Any]:
        from .core import schema as _schema
        return _schema(self.to_dict(), title=title)
