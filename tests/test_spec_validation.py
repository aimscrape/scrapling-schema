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
    text: true
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_list_of_objects_requires_css():
    spec = """
fields:
  items:
    list: true
    fields:
      x: { css: "a", text: true }
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_attr_must_be_string():
    spec = """
fields:
  x:
    css: "a"
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
  x: { css: "a", text: true }
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_multiple_extractor_modes_rejected():
    spec = """
fields:
  x:
    css: "a"
    text: true
    html: true
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_required_must_be_boolean_when_provided():
    spec = """
fields:
  x:
    css: "a"
    text: true
    required: "yes"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_required_scalar_missing_raises_validation_error():
    spec = """
fields:
  title:
    css: "h1"
    text: true
    required: true
"""
    with pytest.raises(ValidationError):
        extract_from_yaml(HTML, spec)


def test_required_list_of_objects_missing_raises_validation_error():
    spec = """
fields:
  items:
    css: ".item"
    list: true
    required: true
    fields:
      href: { css: "a", attr: "href" }
"""
    with pytest.raises(ValidationError):
        extract_from_yaml(HTML, spec)


def test_required_list_of_scalars_missing_raises_validation_error():
    spec = """
fields:
  hrefs:
    css: ".missing"
    list: true
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
    _comment: "should be ignored by extractor"
    text: true
    transform: ["strip"]
"""
    assert extract_from_yaml(html, spec) == {"title": "Hello"}


def test_split_requires_list_true():
    spec = """
fields:
  cats:
    css: "#product"
    attr: "data-cats"
    transform:
      - split: ","
      - strip: true
"""
    with pytest.raises(ExtractError):
        extract_from_yaml("<div id='product' data-cats='a,b'></div>", spec)


def test_options_defaults_text_transform_strip_applies_to_text_fields():
    html = "<h1>  Hello \n</h1>"
    spec = """
options:
  defaults:
    text_transform: ["strip"]
fields:
  title:
    css: "h1"
    text: true
"""
    assert extract_from_yaml(html, spec) == {"title": "Hello"}


def test_options_defaults_text_transform_does_not_override_explicit_transform():
    html = "<h1>  Hello \n</h1>"
    spec = """
options:
  defaults:
    text_transform: ["strip"]
fields:
  title:
    css: "h1"
    text: true
    transform: []
"""
    assert extract_from_yaml(html, spec) == {"title": "  Hello \n"}


def test_options_defaults_text_transform_applies_to_implicit_text_mode():
    html = "<h1>  Hello \n</h1>"
    spec = """
options:
  defaults:
    text_transform: ["strip"]
fields:
  title:
    css: "h1"
"""
    assert extract_from_yaml(html, spec) == {"title": "Hello"}


def test_options_defaults_text_transform_does_not_apply_to_attr_mode():
    html = "<a href='  x '></a>"
    spec = """
options:
  defaults:
    text_transform: ["strip"]
fields:
  href:
    css: "a"
    attr: "href"
"""
    assert extract_from_yaml(html, spec) == {"href": "  x "}
