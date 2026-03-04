from __future__ import annotations

from scrapling_schema import schema_from_yaml


def test_schema_has_expected_top_level_shape() -> None:
    s = schema_from_yaml(
        """
options:
  defaults:
    text_transform: ["strip"]
fields:
  title:
    css: "h1"
    required: true
  hrefs:
    css: "a"
    list: true
    attr: "href"
  price:
    css: ".price"
    transform: ["strip", "to_float"]
""",
        title="Example",
    )

    assert s["title"] == "Example"
    assert s["type"] == "object"
    assert s["additionalProperties"] is False

    props = s["properties"]
    assert set(s["required"]) == {"title", "hrefs", "price"}

    assert props["title"]["type"] == "string"
    assert props["title"]["minLength"] == 1

    assert props["hrefs"]["type"] == "array"
    assert props["hrefs"]["items"]["type"] == "string"

    assert props["price"]["type"] == ["number", "null"]


def test_schema_required_list_enforces_min_items() -> None:
    s = schema_from_yaml(
        """
fields:
  items:
    css: ".item"
    list: true
    required: true
    fields:
      name: { css: ".name", text: true }
""",
    )
    assert s["properties"]["items"]["type"] == "array"
    assert s["properties"]["items"]["minItems"] == 1
    assert s["properties"]["items"]["items"]["type"] == "object"

