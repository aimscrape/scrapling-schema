from __future__ import annotations

import gc
import sys
import weakref
from contextlib import contextmanager
from types import FunctionType

import pytest
from lxml.etree import _Element
from scrapling.parser import Selector

from scrapling_schema import (
    Clear,
    ExtractError,
    Field,
    Options,
    Schema,
    ValidationError,
    core,
    extract,
    extract_from_file,
    extract_from_yaml,
)


@contextmanager
def _without_cyclic_gc():
    was_enabled = gc.isenabled()
    gc.collect()
    gc.disable()
    try:
        yield
    finally:
        if was_enabled:
            gc.enable()
        gc.collect()


def _live_extraction_objects(*, include_functions: bool = False) -> dict[str, int]:
    objects = gc.get_objects()
    counts = {
        "selectors": sum(isinstance(obj, Selector) for obj in objects),
        "elements": sum(isinstance(obj, _Element) for obj in objects),
    }
    # Retained tracebacks can legitimately keep comprehension functions alive
    # on Python versions that give comprehensions their own frames.
    if include_functions:
        counts["functions"] = sum(
            isinstance(obj, FunctionType) and obj.__module__ == core.__name__
            for obj in objects
        )
    return counts


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
def test_repeated_extractions_release_objects_without_cyclic_gc() -> None:
    html = "<div>before<span>child</span>after</div>"
    spec = {"fields": {"text": {"css": "div", "type": "string"}}}
    extract(html, spec)

    with _without_cyclic_gc():
        before = _live_extraction_objects(include_functions=True)
        for _ in range(100):
            assert extract(html, spec) == {"text": "beforechildafter"}
        assert _live_extraction_objects(include_functions=True) == before


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.parametrize("entrypoint", ["dict", "yaml", "file", "typed"])
def test_preprocessed_html_is_released_before_field_evaluation(
    monkeypatch, tmp_path, entrypoint
) -> None:
    class HTML(str):
        """Allow a weak reference to the preprocessed string."""

    prepared_refs = []
    preprocess = core._preprocess_html
    eval_fields = core._eval_fields

    def track_preprocessed_html(html, options):
        prepared = HTML(preprocess(html, options))
        prepared_refs.append(weakref.ref(prepared))
        return prepared

    def check_released_before_fields(context, fields, options):
        assert len(prepared_refs) == 1
        assert prepared_refs[0]() is None
        return eval_fields(context, fields, options)

    monkeypatch.setattr(core, "_preprocess_html", track_preprocessed_html)
    monkeypatch.setattr(core, "_eval_fields", check_released_before_fields)

    html = "<div>before<script>discard()</script><span>after</span></div>"
    spec = {
        "options": {"clear": {"remove_tags": ["script"]}},
        "fields": {
            "text": {"css": "div", "type": "string"},
            "html": {"css": "div", "type": "string", "attr": "innerHTML"},
        },
    }
    yaml_spec = (
        "options:\n  clear:\n    remove_tags: [script]\n"
        "fields:\n"
        "  text: {css: div, type: string}\n"
        "  html: {css: div, type: string, attr: innerHTML}\n"
    )
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(yaml_spec, encoding="utf-8")
    typed_spec = Schema(
        fields={
            "text": Field(css="div", type="string"),
            "html": Field(css="div", type="string", attr="innerHTML"),
        },
        options=Options(clear=Clear(remove_tags=["script"])),
    )

    with _without_cyclic_gc():
        if entrypoint == "dict":
            result = extract(html, spec)
        elif entrypoint == "yaml":
            result = extract_from_yaml(html, yaml_spec)
        elif entrypoint == "file":
            result = extract_from_file(html, str(spec_path))
        else:
            result = typed_spec.extract(html)

        assert result == {
            "text": "beforeafter",
            "html": "<div>before<span>after</span></div>",
        }


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.parametrize(
    "field",
    [
        {"css": "h1", "type": "string", "required": True},
        {"css": "div", "type": "number", "required": True},
        {"css": "div", "type": "array<number>", "required": True},
        {
            "css": "div",
            "type": "object",
            "fields": {"title": {"css": "h1", "type": "string", "required": True}},
        },
        {
            "css": "div",
            "type": "array<object>",
            "fields": {"title": {"css": "h1", "type": "string", "required": True}},
        },
    ],
    ids=["missing", "scalar", "scalar-array", "object", "object-array"],
)
def test_retained_validation_errors_release_dom_without_cyclic_gc(field) -> None:
    errors = []
    with _without_cyclic_gc():
        before = _live_extraction_objects()
        for _ in range(10):
            try:
                extract(
                    "<div>not a number</div><div>another</div>",
                    {"fields": {"value": field}},
                )
            except ValidationError as error:
                errors.append(error)

        assert len(errors) == 10
        assert all("is required" in str(error) for error in errors)
        assert all(error.__traceback__ is not None for error in errors)
        assert _live_extraction_objects() == before


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.filterwarnings("ignore:.*callback is deprecated:DeprecationWarning")
@pytest.mark.parametrize("hook", ["postprocess", "callback", "transform"])
def test_chained_hook_errors_release_dom_and_preserve_user_frame(hook: str) -> None:
    marker = object()

    def fail(value):
        _local_marker = marker
        try:
            extract(
                "<p>inner document</p>",
                {
                    "fields": {
                        "title": {"css": "h1", "type": "string", "required": True}
                    }
                },
            )
        except ValidationError as error:
            raise RuntimeError("hook failed") from error

    field = {
        "css": "div",
        "type": "string",
        hook: [fail] if hook == "transform" else fail,
    }
    with _without_cyclic_gc():
        before = _live_extraction_objects()
        with pytest.raises(RuntimeError, match="hook failed") as caught:
            extract("<div>outer document</div>", {"fields": {"value": field}})

        assert isinstance(caught.value.__cause__, ValidationError)
        assert caught.value.__context__ is caught.value.__cause__
        frames = []
        tb = caught.value.__traceback__
        while tb is not None:
            frames.append(tb.tb_frame)
            tb = tb.tb_next
        user_frame = next(frame for frame in frames if frame.f_code is fail.__code__)
        assert user_frame.f_locals["value"] == "outer document"
        assert user_frame.f_locals["_local_marker"] is marker
        assert any(frame.f_code.co_name == "_eval_field" for frame in frames)
        assert _live_extraction_objects() == before


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.parametrize("error_type", [RuntimeError, KeyboardInterrupt])
@pytest.mark.filterwarnings("ignore:.*callback is deprecated:DeprecationWarning")
@pytest.mark.parametrize("hook", ["postprocess", "callback"])
def test_hook_error_identity_and_cyclic_cause_are_preserved(error_type, hook) -> None:
    error = error_type("stop extraction")
    error.__cause__ = error

    def fail(value):
        raise error

    with _without_cyclic_gc():
        before = _live_extraction_objects()
        with pytest.raises(error_type) as caught:
            extract(
                "<div>text</div>",
                {
                    "fields": {
                        "value": {"css": "div", "type": "string", hook: fail}
                    }
                },
            )

        assert caught.value is error
        assert error.__cause__ is error
        assert _live_extraction_objects() == before


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.parametrize("entrypoint", ["dict", "yaml", "file", "typed"])
def test_entrypoints_release_html_when_validation_error_is_retained(
    entrypoint, tmp_path
) -> None:
    class HTML(str):
        """Allow a weak reference to the input string."""

    spec = {"fields": {"title": {"css": "h1", "type": "string", "required": True}}}
    yaml_spec = 'fields:\n  title: {css: "h1", type: "string", required: true}\n'
    spec_path = tmp_path / "spec.yml"
    spec_path.write_text(yaml_spec, encoding="utf-8")
    typed_spec = Schema(fields={"title": Field(css="h1", type="string", required=True)})

    with _without_cyclic_gc():
        before = _live_extraction_objects()
        html = HTML("<div>missing title</div>")
        html_ref = weakref.ref(html)
        with pytest.raises(ValidationError) as caught:
            if entrypoint == "dict":
                extract(html, spec)
            elif entrypoint == "yaml":
                extract_from_yaml(html, yaml_spec)
            elif entrypoint == "file":
                extract_from_file(html, str(spec_path))
            else:
                typed_spec.extract(html)
        del html

        assert caught.value.__traceback__ is not None
        assert html_ref() is None
        assert _live_extraction_objects() == before


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
def test_invalid_css_error_releases_dom() -> None:
    with _without_cyclic_gc():
        before = _live_extraction_objects()
        with pytest.raises(Exception, match="CSS selector") as caught:
            extract(
                "<div>text</div>",
                {"fields": {"value": {"css": "[", "type": "string"}}},
            )

        assert caught.value.__traceback__ is not None
        assert _live_extraction_objects() == before


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.filterwarnings("ignore:.*callback is deprecated:DeprecationWarning")
@pytest.mark.parametrize("hook", ["postprocess", "callback", "transform"])
@pytest.mark.parametrize("error_source", ["nested-extraction", "hook-local"])
@pytest.mark.parametrize(
    "shape",
    ["scalar", "scalar-array", "object", "object-array", "nested-object-array"],
)
def test_recovered_hook_errors_release_outer_dom(hook, error_source, shape) -> None:
    errors = []
    marker = object()

    def recover(value):
        _local_marker = marker
        try:
            if error_source == "nested-extraction":
                extract(
                    "<p>inner document</p>",
                    {
                        "fields": {
                            "title": {
                                "css": "h1",
                                "type": "string",
                                "required": True,
                            }
                        }
                    },
                )
            else:
                raise RuntimeError("recoverable hook error")
        except (ValidationError, RuntimeError) as error:
            errors.append(error)
        return value

    leaf = {"css": "span", "type": "string"}
    object_fields = {"text": leaf}
    fields = {
        "scalar": {"css": "span", "type": "string"},
        "scalar-array": {"css": "span", "type": "array<string>"},
        "object": {"css": "article", "type": "object", "fields": object_fields},
        "object-array": {
            "css": "article",
            "type": "array<object>",
            "fields": object_fields,
        },
        "nested-object-array": {
            "css": "section",
            "type": "array<object>",
            "fields": {
                "items": {
                    "css": "article",
                    "type": "array<object>",
                    "fields": object_fields,
                }
            },
        },
    }
    field = fields[shape]
    # Exercise a hook inside active object-array traversal, including the
    # separate comprehension frames used by Python 3.10 and 3.11.
    hook_field = leaf if shape == "nested-object-array" else field
    hook_field[hook] = [recover] if hook == "transform" else recover
    expected = {
        "scalar": "one",
        "scalar-array": ["one", "two"],
        "object": {"text": "one"},
        "object-array": [{"text": "one"}, {"text": "two"}],
        "nested-object-array": [{"items": [{"text": "one"}, {"text": "two"}]}],
    }
    html = (
        "<section><article><span>one</span></article>"
        "<article><span>two</span></article></section>"
    )

    with _without_cyclic_gc():
        before = _live_extraction_objects()
        for _ in range(5):
            assert extract(html, {"fields": {"result": field}}) == {
                "result": expected[shape]
            }

        assert len(errors) >= 5
        assert all(error.__traceback__ is not None for error in errors)
        user_frame = errors[0].__traceback__.tb_frame
        assert user_frame.f_code is recover.__code__
        assert user_frame.f_locals["_local_marker"] is marker
        assert "value" in user_frame.f_locals
        assert _live_extraction_objects() == before


@pytest.mark.parametrize("spec", [{}, {"fields": None}, {"fields": []}])
def test_invalid_top_level_fields_do_not_construct_parser(monkeypatch, spec) -> None:
    def unexpected_parser(html):
        pytest.fail("Invalid top-level fields should be rejected before parsing HTML.")

    monkeypatch.setattr(core, "Selector", unexpected_parser)
    with pytest.raises(ExtractError, match="top-level 'fields' mapping"):
        extract("<div>text</div>", spec)


@pytest.mark.skipif(
    sys.implementation.name != "cpython", reason="Checks reference-counted cleanup."
)
@pytest.mark.parametrize("css", ["div::text", "div::attr(data-value)"])
def test_retained_transform_inputs_do_not_keep_lxml_document_alive(css) -> None:
    saved_values = []

    def retain_input(value):
        saved_values.append(value)
        return value

    spec = {
        "fields": {"value": {"css": css, "type": "string", "transform": [retain_input]}}
    }
    with _without_cyclic_gc():
        before = _live_extraction_objects()
        assert extract('<div data-value="value">value</div>', spec) == {
            "value": "value"
        }
        assert saved_values == ["value"]
        assert type(saved_values[0]) is str
        assert _live_extraction_objects() == before
