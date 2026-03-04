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


def test_scalar_text_default_and_strip_transform():
    spec = """
fields:
  title:
    css: "h1"
    transform: ["strip"]
"""
    data = extract_from_yaml(HTML, spec)
    assert data["title"] == "Hello"


def test_scalar_attr_list():
    spec = """
fields:
  hrefs:
    css: "a"
    list: true
    attr: "href"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["hrefs"] == ["/buy", "u1", "u2"]


def test_scalar_outer_html():
    spec = """
fields:
  first_item:
    css: ".item"
    html: true
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
    fields:
      sku:
        css: "SELF"
        attr: "data-sku"
      buy:
        css: "a.buy"
        attr: "href"

  missing:
    css: "#does-not-exist"
    fields:
      x: { css: "a", text: true }
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
    list: true
    fields:
      name: { css: ".name", text: true, transform: ["strip"] }
      url: { css: "a", attr: "href" }
"""
    data = extract_from_yaml(HTML, spec)
    assert data["items"] == [
        {"name": "A", "url": "u1"},
        {"name": "B", "url": "u2"},
    ]


def test_transforms_regex_sub_to_float_split_default():
    spec = """
fields:
  price:
    css: "#product .price"
    transform:
      - regex_sub: { pattern: "[^0-9.]", repl: "" }
      - to_float: true

  cats:
    css: "#product"
    list: true
    attr: "data-cats"
    transform:
      - split: ","
      - strip: true

  missing_with_default:
    css: ".nope"
    transform:
      - default: "N/A"
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
    list: true
    attr: "data-cats"
    transform:
      - split: ","
      - strip: true
"""
    data = extract_from_yaml(HTML, spec)
    assert data["cats_flat"] == ["a", "b", "c"]


def test_list_scalar_drops_empty_items_when_transform_produces_list():
    html = "<div id='x' data-nums='1, x, 2'></div>"
    spec = """
fields:
  nums:
    css: "#x"
    list: true
    attr: "data-nums"
    transform:
      - split: ","
      - strip: true
      - to_int: true
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
    html: true
  noscript_text:
    css: "noscript"
    text: true
"""
    data = extract_from_yaml(HTML, spec)
    assert data["style_html"] is None
    assert data["noscript_text"] is None


def test_invalid_field_modes_raise():
    spec = """
fields:
  bad:
    css: "a"
    attr: "href"
    html: true
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)
