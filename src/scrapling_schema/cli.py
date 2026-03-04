from __future__ import annotations

import argparse
import json
import sys

from .core import ExtractError, ValidationError, extract_from_file, schema_from_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scrapling-schema")
    parser.add_argument("--spec", required=True, help="Path to YAML spec file.")
    parser.add_argument(
        "--schema",
        action="store_true",
        help="Emit JSON Schema for the output of the given spec, then exit.",
    )
    parser.add_argument(
        "--schema-out",
        help="Write emitted JSON Schema to a file instead of stdout.",
    )

    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--html", help="HTML string input.")
    group.add_argument("--html-file", help="Path to an HTML file.")

    args = parser.parse_args(argv)

    if args.schema:
        if args.html or args.html_file:
            print("--schema cannot be used with --html/--html-file.", file=sys.stderr)
            return 2
        try:
            s = schema_from_file(args.spec, title="scrapling-schema output")
        except ExtractError as e:
            print(f"Spec error: {e}", file=sys.stderr)
            return 2
        out_fp = open(args.schema_out, "w", encoding="utf-8") if args.schema_out else sys.stdout
        try:
            json.dump(s, out_fp, ensure_ascii=False, indent=2)
            out_fp.write("\n")
        finally:
            if out_fp is not sys.stdout:
                out_fp.close()
        return 0

    if not args.html and not args.html_file:
        print("One of --html or --html-file is required.", file=sys.stderr)
        return 2

    if args.html_file:
        with open(args.html_file, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        html = args.html

    try:
        data = extract_from_file(html, args.spec)
    except ValidationError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        return 3
    except ExtractError as e:
        print(f"Spec error: {e}", file=sys.stderr)
        return 2

    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
