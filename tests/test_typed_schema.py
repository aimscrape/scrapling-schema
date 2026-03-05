import pytest

from scrapling_schema import (
    Clear,
    ExtractError,
    Field,
    Options,
    RegexSub,
    Schema,
    Split,
    ValidationError,
)


HTML_BASE = """
<html>
  <head>
    <style>.x{color:red}</style>
  </head>
  <body>
    <noscript>ignore me</noscript>
    <h1>  Hello   </h1>

    <div id="product" data-sku="ABC-123" data-cats="a, b, c">
      <span class="price">$12.34</span>
      <a class="buy" href="/buy">Buy</a>
    </div>

    <ul>
      <li class="item"><span class="name">A</span><a href="u1">Link</a></li>
      <li class="item"><span class="name">B</span><a href="u2">Link</a></li>
    </ul>
  </body>
</html>
""".strip()


def test_typed_schema_scalar_text_strips_automatically():
    spec = Schema(fields={"title": Field(css="h1", type="string")})
    data = spec.extract(HTML_BASE)
    assert data["title"] == "Hello"


def test_typed_schema_text_includes_descendants_and_tail_text():
    html = "<div id='d'>Prefix<span>Child</span>Suffix</div>"
    spec = Schema(fields={"d": Field(css="#d", type="string")})
    data = spec.extract(html)
    assert data["d"] == "PrefixChildSuffix"


def test_typed_schema_attr_own_text_is_none_when_only_descendant_text():
    html = """
<div id="description">
  <span>Description ...</span>
</div>
""".strip()
    spec = Schema(
        fields={
            "desc": Field(css="#description", type="string", attr="ownText"),
        }
    )
    data = spec.extract(html)
    assert data["desc"] is None


def test_typed_schema_attr_own_text_excludes_descendants_but_keeps_direct_text_nodes():
    html = "<div id='description'>Prefix<span>Child</span>Suffix</div>"
    spec = Schema(
        fields={
            "all_text": Field(css="#description", type="string"),
            "own_text": Field(css="#description", type="string", attr="ownText"),
        }
    )
    data = spec.extract(html)
    assert data["all_text"] == "PrefixChildSuffix"
    assert data["own_text"] == "PrefixSuffix"


def test_typed_schema_attr_inner_html_is_not_stripped_and_contains_html():
    html = "<div id='x'>  <span> A </span>  </div>"
    spec = Schema(fields={"x": Field(css="#x", type="string", attr="innerHTML")})
    data = spec.extract(html)
    assert isinstance(data["x"], str)
    assert "<div" in data["x"]
    assert "<span" in data["x"]
    assert "A" in data["x"]


def test_typed_schema_transforms_regex_sub_and_split():
    spec = Schema(
        fields={
            "price": Field(
                css="#product .price",
                type="number",
                transform=[RegexSub(pattern=r"[^0-9.]+", repl="")],
            ),
            "cats": Field(
                css="#product",
                type="array<string>",
                attr="data-cats",
                transform=[Split(delimiter=",")],
            ),
        }
    )
    data = spec.extract(HTML_BASE)
    assert data["price"] == 12.34
    assert data["cats"] == ["a", "b", "c"]


def test_typed_schema_callable_transform_step():
    def normalize(s: str | None):
        if s is None:
            return None
        return s.replace(" ", "").lower()

    html = "<div id='x'> Ab C </div>"
    spec = Schema(fields={"x": Field(css="#x", type="string", transform=[normalize])})
    data = spec.extract(html)
    assert data["x"] == "abc"


def test_typed_schema_list_of_objects_and_object_scope():
    spec = Schema(
        fields={
            "product": Field(
                css="#product",
                type="object",
                fields={
                    "sku": Field(css="SELF", type="string", attr="data-sku"),
                    "buy": Field(css="a.buy", type="string", attr="href"),
                },
            ),
            "items": Field(
                css=".item",
                type="array<object>",
                fields={
                    "name": Field(css=".name", type="string"),
                    "url": Field(css="a", type="string", attr="href"),
                },
            ),
        }
    )
    data = spec.extract(HTML_BASE)
    assert data["product"]["sku"] == "ABC-123"
    assert data["product"]["buy"] == "/buy"
    assert data["items"] == [{"name": "A", "url": "u1"}, {"name": "B", "url": "u2"}]


def test_typed_schema_default_value_required_and_nullable_errors():
    spec = Schema(
        fields={
            "missing_with_default": Field(
                css="#nope",
                type="string",
                defaultValue="N/A",
                required=True,
            ),
        }
    )
    data = spec.extract(HTML_BASE)
    assert data["missing_with_default"] == "N/A"

    required_spec = Schema(
        fields={
            "missing_required": Field(css="#nope", type="string", required=True),
        }
    )
    with pytest.raises(ValidationError):
        required_spec.extract(HTML_BASE)

    non_nullable_spec = Schema(
        fields={
            "missing_non_nullable": Field(css="#nope", type="string", nullable=False),
        }
    )
    with pytest.raises(ValidationError):
        non_nullable_spec.extract(HTML_BASE)


def test_typed_schema_options_clear_remove_tags():
    spec = Schema(
        options=Options(clear=Clear(remove_tags=["style", "noscript"])),
        fields={
            "style_html": Field(css="style", type="string", attr="innerHTML"),
            "noscript_text": Field(css="noscript", type="string"),
        },
    )
    data = spec.extract(HTML_BASE)
    assert data["style_html"] is None
    assert data["noscript_text"] is None


def test_typed_schema_invalid_attr_raises_extract_error():
    spec = Schema(fields={"x": Field(css="#product", type="string", attr="")})
    with pytest.raises(ExtractError):
        spec.extract(HTML_BASE)

