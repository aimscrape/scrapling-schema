"""
Python type structures for scrapling-schema specs.

Instead of writing raw YAML/dicts, define your spec with full IDE type hints:

    from scrapling_schema.types import Schema, Field, Options, Clear, RegexSub

    spec = Schema(
        options=Options(clear=Clear(remove_tags=["script", "style"])),
        fields={
            "price": Field(css=".price", type="number", transform=[RegexSub(pattern=r"[^0-9.]+")]),
            "tags":  Field(css=".tags li", type="array<string>"),
        }
    )

    result = spec.extract(html)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal


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


# A transform step is either a shorthand string or one of the below objects.
TransformStep = str | RegexSub | Split | Callable


def _serialize_transform(steps: list[TransformStep]) -> list[Any]:
    out: list[Any] = []
    for step in steps:
        if callable(step) and not isinstance(step, (str, RegexSub, Split)):
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
class Options:
    clear: Clear | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.clear:
            out["clear"] = self.clear.to_dict()
        return out


# ---------------------------------------------------------------------------
# Field
# ---------------------------------------------------------------------------

ScalarType = Literal["string", "integer", "number", "boolean"]
ArrayType = Literal[
    "array<string>",
    "array<integer>",
    "array<number>",
    "array<boolean>",
    "array<object>",
]
FieldType = ScalarType | Literal["object"] | ArrayType


@dataclass
class Field:
    css: str | None
    # output type (required)
    type: FieldType
    nullable: bool | None = None
    defaultValue: Any | None = None
    # extraction mode
    attr: str | None = None
    # nested
    fields: dict[str, "Field"] | None = None
    # transforms
    transform: list[TransformStep] | None = None
    # whole-field hook
    callback: Callable[[Any], Any] | None = None
    # validation
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if self.css is not None:
            out["css"] = self.css
        out["type"] = self.type
        if self.nullable is not None:
            out["nullable"] = bool(self.nullable)
        if self.defaultValue is not None:
            out["defaultValue"] = self.defaultValue
        if self.attr is not None:
            out["attr"] = self.attr
        if self.fields is not None:
            out["fields"] = {k: v.to_dict() for k, v in self.fields.items()}
        if self.transform is not None:
            out["transform"] = _serialize_transform(self.transform)
        if self.callback is not None:
            out["callback"] = {"__callable__": self.callback}
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
