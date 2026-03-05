import pytest

from scrapling_schema import ExtractError, extract_from_yaml


HTML = """
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


def test_scalar_text_default_strips_automatically():
    spec = """
fields:
  title:
    css: "h1"
    type: "string"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["title"] == "Hello"


def test_scalar_text_includes_descendants_like_jquery_text():
    html = """
<div id="description">
  <span>Description ...</span>
</div>
""".strip()
    spec = """
fields:
  description:
    css: "#description"
    type: "string"
"""
    data = extract_from_yaml(html, spec)
    assert data["description"] == "Description ..."


def test_scalar_attr_own_text_excludes_descendants_and_none_when_empty():
    html = """
<div id="description">
  <span>Description ...</span>
</div>
""".strip()
    spec = """
fields:
  description:
    css: "#description"
    type: "string"
    attr: "ownText"
"""
    data = extract_from_yaml(html, spec)
    assert data["description"] is None


def test_scalar_attr_own_text_returns_direct_text_nodes_only():
    html = """<div id="description">Prefix<span>Child</span>Suffix</div>"""
    spec = """
fields:
  all_text:
    css: "#description"
    type: "string"
  own_text:
    css: "#description"
    type: "string"
    attr: "ownText"
"""
    data = extract_from_yaml(html, spec)
    assert data["all_text"] == "PrefixChildSuffix"
    assert data["own_text"] == "PrefixSuffix"


def test_scalar_attr_list():
    spec = """
fields:
  hrefs:
    css: "a"
    type: "array<string>"
    attr: "href"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["hrefs"] == ["/buy", "u1", "u2"]


def test_scalar_outer_html():
    spec = """
fields:
  first_item:
    css: ".item"
    type: "string"
    attr: "innerHTML"
"""
    data = extract_from_yaml(HTML, spec)
    html = data["first_item"]
    assert isinstance(html, str)
    assert "<li" in html
    assert "class" in html
    assert "item" in html
    assert "A" in html


def test_object_scope_and_missing_object_is_null():
    spec = """
fields:
  product:
    css: "#product"
    type: "object"
    fields:
      sku:
        css: "SELF"
        type: "string"
        attr: "data-sku"
      buy:
        css: "a.buy"
        type: "string"
        attr: "href"

  missing:
    css: "#does-not-exist"
    type: "object"
    fields:
      x: { css: "a", type: "string" }
"""
    data = extract_from_yaml(HTML, spec)
    assert data["product"]["sku"] == "ABC-123"
    assert data["product"]["buy"] == "/buy"
    assert data["missing"] is None


def test_list_of_objects():
    spec = """
fields:
  items:
    css: ".item"
    type: "array<object>"
    fields:
      name: { css: ".name", type: "string" }
      url: { css: "a", type: "string", attr: "href" }
"""
    data = extract_from_yaml(HTML, spec)
    assert data["items"] == [
        {"name": "A", "url": "u1"},
        {"name": "B", "url": "u2"},
    ]


def test_transforms_regex_sub_number_split_and_default_value():
    spec = """
fields:
  price:
    css: "#product .price"
    type: "number"
    transform:
      - regex_sub: { pattern: "[^0-9.]", repl: "" }

  cats:
    css: "#product"
    type: "array<string>"
    attr: "data-cats"
    transform:
      - split: ","

  missing_with_default:
    css: ".nope"
    type: "string"
    defaultValue: "N/A"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["price"] == 12.34
    assert data["cats"] == ["a", "b", "c"]
    assert data["missing_with_default"] == "N/A"


def test_list_scalar_flattens_when_transform_produces_list():
    spec = """
fields:
  cats_flat:
    css: "#product"
    type: "array<string>"
    attr: "data-cats"
    transform:
      - split: ","
"""
    data = extract_from_yaml(HTML, spec)
    assert data["cats_flat"] == ["a", "b", "c"]


def test_list_scalar_drops_empty_items_when_transform_produces_list():
    html = "<div id='x' data-nums='1, x, 2'></div>"
    spec = """
fields:
  nums:
    css: "#x"
    type: "array<integer>"
    attr: "data-nums"
    transform:
      - split: ","
"""
    data = extract_from_yaml(html, spec)
    assert data["nums"] == [1, 2]


def test_options_clear_remove_tags_removes_style_and_noscript():
    spec = """
options:
  clear:
    remove_tags: ["style", "noscript"]
fields:
  style_html:
    css: "style"
    type: "string"
    attr: "innerHTML"
  noscript_text:
    css: "noscript"
    type: "string"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["style_html"] is None
    assert data["noscript_text"] is None


def test_html_key_is_ignored():
    spec = """
fields:
  bad:
    css: "a"
    type: "string"
    attr: "href"
    html: true
"""
    data = extract_from_yaml(HTML, spec)
    assert data["bad"] == "/buy"
