import pytest

from scrapling_schema import ExtractError, extract_from_yaml


HTML = """
<html>
  <body>
    <div class="container">
      <h2>Title A</h2>
      <h2>Title B</h2>

      <div class="card" data-id="1">
        <a class="url" href="u1"> One </a>
        <span class="score"> 0010 </span>
      </div>
      <div class="card" data-id="2">
        <a class="url" href="u2"> Two </a>
        <span class="score"> x </span>
      </div>
    </div>
  </body>
</html>
""".strip()


def test_default_scalar_extractor_is_text():
    spec = """
fields:
  first_h2:
    css: "h2"
    type: "string"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["first_h2"] == "Title A"


def test_list_of_text_scalars():
    spec = """
fields:
  titles:
    css: "h2"
    type: "array<string>"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["titles"] == ["Title A", "Title B"]


def test_type_list_is_equivalent_to_list_true_for_scalars():
    spec = """
fields:
  titles:
    css: "h2"
    type: "array<string>"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["titles"] == ["Title A", "Title B"]


def test_object_without_css_uses_current_scope():
    spec = """
fields:
  container:
    css: ".container"
    type: "object"
    fields:
      headings:
        css: "h2"
        type: "array<string>"

      meta:
        type: "object"
        fields:
          link_count:
            css: "a"
            type: "array<string>"
            attr: "href"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["container"]["headings"] == ["Title A", "Title B"]
    assert data["container"]["meta"]["link_count"] == ["u1", "u2"]


def test_nested_object_inside_list_items():
    spec = """
fields:
  cards:
    css: ".card"
    type: "array<object>"
    fields:
      id:
        css: "SELF"
        type: "string"
        attr: "data-id"
      url:
        css: "a.url"
        type: "string"
        attr: "href"
      content:
        type: "object"
        fields:
          text:
            css: "a.url"
            type: "string"
          outer:
            css: "a.url"
            type: "string"
            attr: "innerHTML"
"""
    data = extract_from_yaml(HTML, spec)
    assert data["cards"][0]["id"] == "1"
    assert data["cards"][0]["url"] == "u1"
    assert data["cards"][0]["content"]["text"] == "One"
    assert "<a" in data["cards"][0]["content"]["outer"]


def test_array_integer_drops_invalid_and_default_can_fill():
    spec = """
fields:
  scores:
    css: ".card .score"
    type: "array<integer>"
    transform:
  scores_with_default:
    css: ".card .score"
    type: "array<integer>"
    defaultValue: 0
    transform:
"""
    data = extract_from_yaml(HTML, spec)
    assert data["scores"] == [10]  # invalid "x" is dropped in list mode
    assert data["scores_with_default"] == [10, 0]


def test_unknown_transform_raises():
    spec = """
fields:
  bad:
    css: "h2"
    type: "string"
    transform: ["nope"]
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_transform_shape_validation_raises():
    spec = """
fields:
  bad:
    css: "h2"
    type: "string"
    transform:
      - { regex_sub: { pattern: "x", repl: "" }, extra: "y" }
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_type_bool_coerces_text_to_boolean():
    html = "<span class='flag'> true </span>"
    spec = """
fields:
  flag:
    css: ".flag"
    type: "boolean"
"""
    assert extract_from_yaml(html, spec) == {"flag": True}


def test_type_bool_invalid_value_raises_validation_error():
    html = "<span class='flag'> maybe </span>"
    spec = """
fields:
  flag:
    css: ".flag"
    type: "boolean"
    nullable: false
"""
    with pytest.raises(Exception) as excinfo:
        extract_from_yaml(html, spec)
    # Explicitly check error class to avoid masking ExtractError.
    assert excinfo.type.__name__ == "ValidationError"


def test_list_key_is_rejected():
    spec = """
fields:
  titles:
    css: "h2"
    list: true
    type: "string"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_type_dict_requires_fields():
    spec = """
fields:
  x:
    css: "a"
    type: "object"
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


@pytest.mark.parametrize(
    "html",
    [
        "<span class='skills'>python, html, yaml</span>",
        "<span class='skills'>python</span><span class='skills'>html</span><span class='skills'>yaml</span>",
        "<span class='skills'>python</span><span class='skills'>html, yaml</span>",
    ],
)
def test_list_true_split_normalizes_comma_separated_or_multi_node(html: str) -> None:
    spec = """
fields:
  skills:
    css: ".skills"
    type: "array<string>"
    transform:
      - split: ","
"""
    data = extract_from_yaml(html, spec)
    assert data["skills"] == ["python", "html", "yaml"]
