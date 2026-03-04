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
"""
    data = extract_from_yaml(HTML, spec)
    assert data["first_h2"].strip() == "Title A"


def test_list_of_text_scalars():
    spec = """
fields:
  titles:
    css: "h2"
    list: true
    transform: ["strip"]
"""
    data = extract_from_yaml(HTML, spec)
    assert data["titles"] == ["Title A", "Title B"]


def test_object_without_css_uses_current_scope():
    spec = """
fields:
  container:
    css: ".container"
    fields:
      headings:
        css: "h2"
        list: true
        transform: ["strip"]

      meta:
        fields:
          link_count:
            css: "a"
            list: true
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
    list: true
    fields:
      id:
        css: "SELF"
        attr: "data-id"
      url:
        css: "a.url"
        attr: "href"
      content:
        fields:
          text:
            css: "a.url"
            transform: ["strip"]
          outer:
            css: "a.url"
            html: true
"""
    data = extract_from_yaml(HTML, spec)
    assert data["cards"][0]["id"] == "1"
    assert data["cards"][0]["url"] == "u1"
    assert data["cards"][0]["content"]["text"] == "One"
    assert "<a" in data["cards"][0]["content"]["outer"]


def test_to_int_transform_returns_none_on_invalid_and_default_can_replace():
    spec = """
fields:
  scores:
    css: ".card .score"
    list: true
    transform:
      - strip: true
      - to_int: true

  scores_with_default:
    css: ".card .score"
    list: true
    transform:
      - strip: true
      - to_int: true
      - default: 0
"""
    data = extract_from_yaml(HTML, spec)
    assert data["scores"] == [10]  # invalid "x" is dropped in list mode
    assert data["scores_with_default"] == [10, 0]


def test_unknown_transform_raises():
    spec = """
fields:
  bad:
    css: "h2"
    transform: ["nope"]
"""
    with pytest.raises(ExtractError):
        extract_from_yaml(HTML, spec)


def test_transform_shape_validation_raises():
    spec = """
fields:
  bad:
    css: "h2"
    transform:
      - { strip: true, to_int: true }
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
    list: true
    text: true
    transform:
      - split: ","
      - strip: true
"""
    data = extract_from_yaml(html, spec)
    assert data["skills"] == ["python", "html", "yaml"]
