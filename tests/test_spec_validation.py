import pytest

from scrapling_schema import ExtractError, ValidationError, extract_from_yaml


HTML = "<html><body><a href='x'>x</a></body></html>"


def test_top_level_fields_required():
    spec = """
options: {}
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_fields_must_be_mapping():
    spec = """
fields: []
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_scalar_requires_css():
    spec = """
fields:
  x:
    type: "string"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_type_is_required():
    spec = """
fields:
  x:
    css: "a"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_list_of_objects_requires_css():
    spec = """
fields:
  items:
    type: "array<object>"
    fields:
      x: { css: "a", type: "string" }
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_attr_must_be_string():
    spec = """
fields:
  x:
    css: "a"
    type: "string"
    attr: 123
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_options_remove_tags_validation():
    spec = """
options:
  clear:
    remove_tags: "style"
fields:
  x: { css: "a", type: "string" }
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_text_key_is_rejected():
    spec = """
fields:
  x:
    css: "a"
    type: "string"
    text: true
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_html_key_is_rejected():
    spec = """
fields:
  x:
    css: "a"
    type: "string"
    html: true
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_required_must_be_boolean_when_provided():
    spec = """
fields:
  x:
    css: "a"
    type: "string"
    required: "yes"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_required_scalar_missing_raises_validation_error():
    spec = """
fields:
  title:
    css: "h1"
    type: "string"
    required: true
"""
    with pytest.raises(ValidationError):
        extract_from_yaml(HTML, spec)


def test_required_list_of_objects_missing_raises_validation_error():
    spec = """
fields:
  items:
    css: ".item"
    type: "array<object>"
    required: true
    fields:
      href: { css: "a", type: "string", attr: "href" }
"""
    with pytest.raises(ValidationError):
        extract_from_yaml(HTML, spec)


def test_required_list_of_scalars_missing_raises_validation_error():
    spec = """
fields:
  hrefs:
    css: ".missing"
    type: "array<string>"
    required: true
    attr: "href"
"""
    with pytest.raises(ValidationError):
        extract_from_yaml(HTML, spec)


def test_unknown_metadata_keys_are_ignored():
    html = "<h1>  Hello </h1>"
    spec = """
meta:
  owner: "data-team"
  purpose: "example"
fields:
  title:
    css: "h1"
    type: "string"
    _comment: "should be ignored by extractor"
"""
    assert extract_from_yaml(html, spec) == {"title": "Hello"}


def test_split_requires_array_type():
    spec = """
fields:
  cats:
    css: "#product"
    type: "string"
    attr: "data-cats"
    transform:
      - split: ","
"""
    with pytest.raises(ExtractError):
        extract_from_yaml("<div id='product' data-cats='a,b'></div>", spec)


def test_options_defaults_is_rejected():
    html = "<h1>  Hello \n</h1>"
    spec = """
options:
  defaults:
    text_transform: ["strip"]
fields:
  title:
    css: "h1"
    type: "string"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(html, spec)
