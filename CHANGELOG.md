## [Unreleased]

### Added

### Changed

### Fixed

### Removed

## [1.1.4] - 2026-11-12

### Added

- Memory lifecycle regression coverage for retained exceptions, recovered hooks,
  nested object arrays, and all four extraction entry points.
- Shared VS Code interpreter, Pylance, and Ruff development settings.

### Changed

- Release preprocessed HTML and Scrapling's raw-body cache after parsing by
  reusing the existing DOM for field extraction.
- Clear finished internal and Scrapling parser traceback locals on failure while
  preserving exception identity, traceback locations, and user callback locals.

### Fixed

- Release DOM references on both successful and failed extraction, including
  callbacks and transforms that catch and retain an exception.
- Release DOM references held by invalid CSS selector exceptions and avoid
  retaining object-array nodes through comprehension frames on older Python.
- Convert text and attribute pseudo-element results to plain strings before
  transforms so retained values do not keep the source document alive.
- Reject invalid top-level fields before parsing HTML and release input references
  from every extraction entry point.

### Removed

## [1.1.3] - 2026-03-05

### Added

- Field-level `outputSchema` override to keep generated JSON Schema in sync when `callback` changes the output type/shape.

### Changed

### Fixed

### Removed

## [1.1.2] - 2026-03-05

### Added

- Field-level `callback` hook (typed schema via `Field(callback=...)` and raw spec via `callback: ...`) to post-process the extracted field value.

### Changed

- Object and `array<object>` fields now support `transform` (applied after nested field extraction).

### Fixed

- `callback` validation now raises an `ExtractError` when a non-callable value is provided (instead of silently ignoring it).
- Fixed object extraction with `css` selectors and scalar extraction when no nodes match (avoid unbound local errors).

### Removed

## [1.1.1] - 2026-03-05

### Added

### Changed

### Fixed

- Scalar text extraction now includes element tail text (text after child elements), matching DOM `textContent` / jQuery `.text()` semantics more closely.
- Added `attr: "ownText"` to extract only the current node's direct text (excluding descendant text).

### Removed

## [1.1.0] - 2026-03-05

### Added

- `attr: "innerHTML"` for HTML content extraction (replaces the legacy `html: true` flag).

### Changed

- `type` is now required for every field.
- Arrays must be declared with a typed generic: `type: "array<string>"`, `type: "array<integer>"`, `type: "array<number>"`, `type: "array<boolean>"`, or `type: "array<object>"` (plain `type: "array"` is rejected).
- String outputs are stripped automatically; `innerHTML` is never stripped.
- Numeric/boolean coercion is driven by `type` (no conversion transforms).
- `defaultValue` is a field-level key (same level as `css/type/transform`), not part of transforms.

### Fixed

### Removed

- Removed legacy field flags `text: true` and `html: true`.
- Removed `list: true` and `items: { type: ... }` in favor of `type: "array<...>"`.
- Removed `options.defaults` / `text_transform`.
- Removed transforms: `strip`, `to_int`, `to_float`, and `{ default: ... }`.
- Python typed spec: removed `Field.list` and the `Default` transform helper.

## [0.1.1] - 2026-03-04

INIT
