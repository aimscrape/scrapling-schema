import warnings
from contextlib import contextmanager

import pytest

from scrapling_schema import (
    ExtractError,
    Field,
    Schema,
    ValidationError,
    extract,
    schema,
)

HTML = """
<div class="item"><span class="name"> A </span><span class="price">$12.50</span></div>
<div class="item"><span class="name"> B </span><span class="price">$5.00</span></div>
"""


@contextmanager
def _expect_callback_warning():
    with pytest.warns(
        DeprecationWarning, match="callback is deprecated.*postprocess"
    ) as caught:
        # pytest.warns enables all warnings; restore the project's lxml filter.
        warnings.filterwarnings(
            "ignore",
            message=r".*strip_cdata.*HTMLParser\(\).*",
            category=DeprecationWarning,
            module=r"lxml\.html.*",
        )
        yield caught


@pytest.fixture(params=["postprocess", "callback"])
def hook_name(request):
    with warnings.catch_warnings():
        # Keep the project's filter for lxml's unrelated deprecation warning.
        warnings.filterwarnings(
            "error", message=r".*\.callback is deprecated", category=DeprecationWarning
        )
        if request.param == "callback":
            with _expect_callback_warning():
                yield request.param
        else:
            yield request.param


def _run(spec, operation):
    if isinstance(spec, Schema):
        return spec.extract(HTML) if operation == "extract" else spec.json_schema()
    return extract(HTML, spec) if operation == "extract" else schema(spec)


@pytest.mark.parametrize("api", ["typed", "dict"])
@pytest.mark.parametrize("operation", ["extract", "schema"])
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("output_schema", [None, {"type": "string"}])
def test_callback_warns_once_at_caller(api, operation, nested, output_schema):
    calls = []

    def upper(value):
        calls.append(value)
        return value.upper()

    leaf = Field(css=".name", type="string", callback=upper, outputSchema=output_schema)
    field = Field(css=".item", type="object", fields={"name": leaf}) if nested else leaf
    spec = Schema(fields={"value": field})
    if api == "dict":
        spec = spec.to_dict()

    with _expect_callback_warning() as caught:
        result = _run(spec, operation)

    assert len(caught) == 1
    assert caught[0].filename == __file__
    if operation == "extract":
        assert result == {"value": {"name": "A"} if nested else "A"}
        assert calls == ["A"]
    else:
        assert calls == []


@pytest.mark.parametrize("api", ["typed", "dict"])
@pytest.mark.parametrize("operation", ["extract", "schema"])
@pytest.mark.parametrize("output_schema", [None, {"type": "string"}])
def test_conflicting_hooks_are_rejected_before_execution(api, operation, output_schema):
    def fail(value):
        pytest.fail("Conflicting hooks must not run")

    spec = Schema(
        fields={
            "value": Field(
                css=".name",
                type="string",
                postprocess=fail,
                callback=fail,
                outputSchema=output_schema,
            )
        }
    )
    if api == "dict":
        spec = spec.to_dict()

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error", message=r".*\.callback is deprecated", category=DeprecationWarning
        )
        with pytest.raises(
            ExtractError,
            match=r"fields\.value: postprocess and callback cannot be used together",
        ):
            _run(spec, operation)


def test_postprocess_receives_coerced_value_after_transform(hook_name):
    def remove_currency(value):
        assert value == "$12.50"
        return value.removeprefix("$")

    def double(value):
        assert isinstance(value, float)
        assert value == 12.5
        return value * 2

    spec = Schema(
        fields={
            "price": Field(
                css=".price",
                type="number",
                transform=[remove_currency],
                **{hook_name: double},
            )
        }
    )
    assert spec.extract(HTML) == {"price": 25.0}


@pytest.mark.parametrize(
    ("field_spec", "expected"),
    [
        ({"css": ".name", "type": "array<string>"}, ["A", "B"]),
        (
            {
                "css": ".item",
                "type": "object",
                "fields": {"name": {"css": ".name", "type": "string"}},
            },
            {"name": "A"},
        ),
        (
            {
                "css": None,
                "type": "object",
                "fields": {"name": {"css": ".name", "type": "string"}},
            },
            {"name": "A"},
        ),
        (
            {
                "css": ".item",
                "type": "array<object>",
                "fields": {"name": {"css": ".name", "type": "string"}},
            },
            [{"name": "A"}, {"name": "B"}],
        ),
        ({"css": ".missing", "type": "string"}, None),
        ({"css": ".missing", "type": "object", "fields": {}}, None),
        ({"css": ".missing", "type": "array<string>"}, []),
        ({"css": ".missing", "type": "array<object>", "fields": {}}, []),
        ({"css": ".missing", "type": "string", "defaultValue": "fallback"}, "fallback"),
        (
            {
                "css": ".missing",
                "type": "object",
                "fields": {},
                "defaultValue": {"name": "fallback"},
            },
            {"name": "fallback"},
        ),
        (
            {"css": ".missing", "type": "array<string>", "defaultValue": ["fallback"]},
            ["fallback"],
        ),
        (
            {
                "css": ".missing",
                "type": "array<object>",
                "fields": {},
                "defaultValue": [{"name": "fallback"}],
            },
            [{"name": "fallback"}],
        ),
    ],
)
def test_postprocess_receives_whole_field_once(hook_name, field_spec, expected):
    calls = []

    def wrap(value):
        calls.append(value)
        return {"result": value}

    spec = {"fields": {"value": {**field_spec, hook_name: wrap}}}
    assert extract(HTML, spec) == {"value": {"result": expected}}
    assert calls == [expected]


def test_required_is_checked_after_postprocess(hook_name):
    spec = {
        "fields": {
            "value": {
                "css": ".name",
                "type": "string",
                "required": True,
                hook_name: lambda value: None,
            }
        }
    }
    with pytest.raises(ValidationError, match=r"fields\.value is required"):
        extract(HTML, spec)


@pytest.mark.parametrize("invalid_hook", [False, "upper", {"__callable__": None}])
def test_invalid_hook_reports_the_supplied_name(hook_name, invalid_hook):
    spec = {
        "fields": {"value": {"css": ".name", "type": "string", hook_name: invalid_hook}}
    }
    with pytest.raises(
        ExtractError, match=rf"fields\.value\.{hook_name} must be callable"
    ):
        extract(HTML, spec)


@pytest.mark.parametrize("active_hook", [None, "postprocess", "callback"])
def test_none_does_not_conflict_or_warn(active_hook):
    field = {"css": ".name", "type": "string", "postprocess": None, "callback": None}
    if active_hook is not None:
        field[active_hook] = str.lower
    with warnings.catch_warnings(record=True) as caught:
        warnings.filterwarnings(
            "always", message=r".*\.callback is deprecated", category=DeprecationWarning
        )
        assert extract(HTML, {"fields": {"value": field}}) == {
            "value": "a" if active_hook else "A"
        }
    assert len(caught) == (1 if active_hook == "callback" else 0)


def test_callback_positional_arguments_remain_compatible():
    output_schema = {"type": "string"}
    field = Field(
        ".name", "string", None, None, None, None, None, str.lower, output_schema, True
    )
    assert field.callback is str.lower
    assert field.outputSchema is output_schema
    assert field.required is True
    assert field.postprocess is None
    with _expect_callback_warning():
        assert Schema(fields={"value": field}).extract(HTML) == {"value": "a"}
