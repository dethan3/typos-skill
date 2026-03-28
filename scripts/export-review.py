#!/usr/bin/env python3
"""Export typos findings into a review JSONL with conservative triage."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re
import sys


def die(message: str) -> None:
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)


def iter_items(handle):
    for idx, raw in enumerate(handle, 1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            die(f"invalid JSON from typos at line {idx}: {exc}")
        if item.get("type") != "typo":
            continue
        if "typo" not in item or "path" not in item:
            continue
        yield item


def line_starts(data: bytes) -> list[int]:
    starts = [0]
    for idx, byte in enumerate(data):
        if byte == 10:
            starts.append(idx + 1)
    return starts


class FileCache:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, object]] = {}

    def get(self, path: str) -> dict[str, object]:
        cached = self._cache.get(path)
        if cached is not None:
            return cached

        file_path = Path(path)
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            die(f"cannot read source file '{path}': {exc}")

        starts = line_starts(data)
        cached = {"data": data, "starts": starts}
        self._cache[path] = cached
        return cached


def decode_text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def get_line_context(item: dict[str, object], cache: FileCache) -> dict[str, object]:
    path = str(item.get("path", ""))
    line_num = item.get("line_num")
    byte_offset = item.get("byte_offset")
    typo = str(item.get("typo", ""))
    typo_bytes = typo.encode("utf-8")

    if not isinstance(line_num, int) or line_num < 1:
        return {
            "line_text": "",
            "line_start": None,
            "line_end": None,
            "relative_byte_offset": None,
            "char_index": None,
        }

    cached = cache.get(path)
    data = cached["data"]
    starts = cached["starts"]
    assert isinstance(data, bytes)
    assert isinstance(starts, list)

    if line_num > len(starts):
        return {
            "line_text": "",
            "line_start": None,
            "line_end": None,
            "relative_byte_offset": None,
            "char_index": None,
        }

    line_start = starts[line_num - 1]
    line_end = starts[line_num] if line_num < len(starts) else len(data)
    segment = data[line_start:line_end]
    line_text = decode_text(segment).rstrip("\n")

    relative_byte_offset = None
    char_index = None
    if isinstance(byte_offset, int) and byte_offset >= line_start:
        rel = byte_offset - line_start
        if segment[rel:rel + len(typo_bytes)] == typo_bytes:
            relative_byte_offset = rel
            char_index = len(decode_text(segment[:rel]))

    if relative_byte_offset is None and typo:
        char_index = line_text.find(typo)
        if char_index >= 0:
            relative_byte_offset = len(line_text[:char_index].encode("utf-8"))
        else:
            char_index = None

    return {
        "line_text": line_text,
        "line_start": line_start,
        "line_end": line_end,
        "relative_byte_offset": relative_byte_offset,
        "char_index": char_index,
    }


def detect_test_artifact(path: str) -> bool:
    candidate = Path(path)
    lowered_parts = [part.lower() for part in candidate.parts]
    artifact_dirs = {
        "__snapshots__",
        "__fixtures__",
        "__mocks__",
        "snapshots",
        "fixtures",
        "mocks",
    }
    if any(part in artifact_dirs for part in lowered_parts):
        return True
    return candidate.name.lower().endswith(".snap")


def detect_hex_token(token: str, line_text: str, char_index: int | None) -> bool:
    if re.fullmatch(r"(?:0x)?[0-9a-fA-F]{6,}", token):
        return True
    if char_index is None or not token:
        return False

    start = char_index
    end = char_index + len(token)
    left = line_text[max(0, start - 2):start]
    right = line_text[end:end + 2]
    merged = f"{left}{token}{right}"
    return bool(re.fullmatch(r"(?:0x)?[0-9a-fA-F]{6,}", merged))


def detect_url_or_query(line_text: str, char_index: int | None, token: str) -> tuple[bool, str | None]:
    if char_index is None or not token:
        return False, None

    token_end = char_index + len(token)
    for match in re.finditer(r"\b[a-zA-Z][a-zA-Z0-9+.-]*://\S+", line_text):
        start, end = match.span()
        if start <= char_index < end or start < token_end <= end:
            url_text = match.group(0)
            prefix = line_text[start:char_index]
            suffix = line_text[token_end:end]
            if ("?" in prefix or "&" in prefix) or suffix.startswith("="):
                return True, "query parameter inside URL"
            return True, "inside URL"

    prefix = line_text[:char_index]
    suffix = line_text[token_end:]
    query_key = re.search(r"[?&][^=&\s\"']*$", prefix) and suffix.startswith("=")
    query_value = re.search(r"[?&][^=&\s\"']+=$", prefix)
    if query_key or query_value:
        return True, "query parameter"
    return False, None


def detect_json_key(line_text: str, char_index: int | None, token: str) -> bool:
    if char_index is None or not token:
        return False
    for match in re.finditer(r'"([^"\\]|\\.)*"\s*:', line_text):
        start, end = match.span()
        if start <= char_index < end:
            return True
    return False


def detect_css_class(path: str, line_text: str, char_index: int | None, token: str) -> bool:
    if char_index is None or not token:
        return False

    attr_patterns = (
        r'class(?:Name)?\s*=\s*["\'][^"\']*$',
        r'class(?:Name)?\s*:\s*["\'][^"\']*$',
    )
    prefix = line_text[:char_index]
    for pattern in attr_patterns:
        if re.search(pattern, prefix):
            return True

    stylesheet_suffixes = {".css", ".scss", ".sass", ".less", ".styl"}
    if Path(path).suffix.lower() in stylesheet_suffixes:
        token_end = char_index + len(token)
        for match in re.finditer(r"\.[A-Za-z0-9_-]+", line_text):
            start, end = match.span()
            if start < token_end and char_index < end:
                return True

    return False


def detect_dom_selector(line_text: str, char_index: int | None, token: str) -> bool:
    if char_index is None or not token:
        return False

    prefix = line_text[:char_index]
    selector_calls = (
        "querySelector",
        "querySelectorAll",
        "getElementById",
        "getElementsByClassName",
        "locator(",
        "$(",
        "$$(",
    )
    if any(call in prefix for call in selector_calls):
        return True

    token_end = char_index + len(token)
    for match in re.finditer(r'["\'][^"\']*[.#\[][^"\']*["\']', line_text):
        start, end = match.span()
        if start <= char_index < end or start < token_end <= end:
            return True
    return False


def is_identifier_token(token: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", token))


def split_identifier_words(identifier: str) -> list[str]:
    if not identifier:
        return []

    parts = re.split(r"[_-]+", identifier)
    words: list[str] = []
    for part in parts:
        if not part:
            continue
        camel_parts = re.findall(r"[A-Z]+(?=[A-Z][a-z]|$)|[A-Z]?[a-z]+|\d+", part)
        if camel_parts:
            words.extend(camel_parts)
        else:
            words.append(part)
    return words


def abbreviate_identifier(identifier: str) -> str:
    words = split_identifier_words(identifier)
    letters = [word[0].lower() for word in words if word and word[0].isalpha()]
    return "".join(letters)


def choose_rename_candidate(token: str, rhs_text: str) -> str:
    candidates = re.findall(r"[A-Za-z_$][A-Za-z0-9_$]*", rhs_text)
    preferred = []
    for candidate in candidates:
        if candidate == token:
            continue
        if len(candidate) <= len(token):
            continue
        preferred.append(candidate)

    token_abbr = token.lower()
    matching = [
        candidate
        for candidate in preferred
        if abbreviate_identifier(candidate) == token_abbr
    ]
    if matching:
        matching.sort(key=len, reverse=True)
        return matching[0]

    return ""


def detect_short_identifier_rename(line_text: str, char_index: int | None, token: str) -> str:
    if char_index is None or len(token) > 3 or not is_identifier_token(token):
        return ""

    escaped = re.escape(token)
    match = re.search(rf"\b(?:const|let|var)\s+({escaped})\b\s*=\s*(.+)", line_text)
    if not match:
        return ""

    start, end = match.span(1)
    if not (start <= char_index < end):
        return ""

    rhs_text = match.group(2).strip()
    return choose_rename_candidate(token, rhs_text)


def choose_word_section(token: str) -> str:
    if re.fullmatch(r"[a-z0-9-]+", token):
        return "default.extend-words"
    return "default.extend-identifiers"


def build_word_snippet(token: str) -> tuple[str, str]:
    section = choose_word_section(token)
    snippet = f"[{section}]\n\"{token}\" = \"{token}\""
    return section, snippet


def build_exclude_snippet(path: str) -> tuple[str, str]:
    target = Path(path)
    lowered_parts = [part.lower() for part in target.parts]
    marker_index = None
    for idx, part in enumerate(lowered_parts):
        if any(key in part for key in ("snapshot", "fixture", "mock")):
            marker_index = idx
            break

    if marker_index is None:
        value = path
    else:
        prefix = Path(*target.parts[: marker_index + 1])
        value = prefix.as_posix()
        if Path(value).suffix:
            pass
        else:
            value = f"{value}/**"

    snippet = f"[files]\nextend-exclude = [\n  \"{value}\"\n]"
    return "files.extend-exclude", snippet


def classify(item: dict[str, object], context: dict[str, object]) -> dict[str, object]:
    path = str(item.get("path", ""))
    token = str(item.get("typo", ""))
    line_text = str(context.get("line_text", ""))
    char_index = context.get("char_index")
    char_index = char_index if isinstance(char_index, int) else None

    if detect_hex_token(token, line_text, char_index):
        return {
            "bucket": "false_positive.hex",
            "status": "FALSE POSITIVE",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "KEEP_SOURCE",
            "reason": "Matched a hexadecimal-like token; technical literals should not be auto-corrected.",
            "rename_candidate": "",
        }

    is_url, url_reason = detect_url_or_query(line_text, char_index, token)
    if is_url:
        return {
            "bucket": "false_positive.url",
            "status": "FALSE POSITIVE",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "KEEP_SOURCE",
            "reason": f"Matched {url_reason}; URLs and query parameters default to false positives.",
            "rename_candidate": "",
        }

    if detect_css_class(path, line_text, char_index, token):
        return {
            "bucket": "false_positive.css_class",
            "status": "FALSE POSITIVE",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "KEEP_SOURCE",
            "reason": "Matched a CSS class or selector-like token; styling identifiers default to false positives.",
            "rename_candidate": "",
        }

    if detect_json_key(line_text, char_index, token):
        return {
            "bucket": "false_positive.json_key",
            "status": "FALSE POSITIVE",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "KEEP_SOURCE",
            "reason": "Matched a JSON key; data/schema keys default to false positives.",
            "rename_candidate": "",
        }

    if detect_dom_selector(line_text, char_index, token):
        return {
            "bucket": "false_positive.dom_selector",
            "status": "FALSE POSITIVE",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "KEEP_SOURCE",
            "reason": "Matched a DOM selector; selector strings default to false positives.",
            "rename_candidate": "",
        }

    rename_candidate = detect_short_identifier_rename(line_text, char_index, token)
    if rename_candidate:
        return {
            "bucket": "manual_review.rename_candidate",
            "status": "PENDING",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "RENAME_SYMBOL",
            "reason": (
                f"Matched a short internal variable name; a semantic rename such as "
                f"'{rename_candidate}' is safer than a spelling auto-fix."
            ),
            "rename_candidate": rename_candidate,
        }

    if len(token) <= 2:
        return {
            "bucket": "manual_review.short_token",
            "status": "PENDING",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "REVIEW_SOURCE",
            "reason": "Matched a very short token; short abbreviations have high false-positive risk, so do not auto-fix.",
            "rename_candidate": "",
        }

    if detect_test_artifact(path):
        return {
            "bucket": "manual_review.test_artifact",
            "status": "PENDING",
            "suggested_status": "FALSE POSITIVE",
            "preferred_action": "CONSIDER_TYPOS_TOML",
            "reason": "Matched snapshot/fixture/mock data; test artifacts default to manual review instead of auto-fix.",
            "rename_candidate": "",
        }

    return {
        "bucket": "candidate.source_fix",
        "status": "PENDING",
        "suggested_status": "ACCEPT CORRECT",
        "preferred_action": "REVIEW_SOURCE",
        "reason": "No conservative false-positive rule matched; review source context before accepting the suggested fix.",
        "rename_candidate": "",
    }


def load_records(path: Path) -> list[dict[str, object]]:
    cache = FileCache()
    records = []
    occurrence_counts: dict[tuple[str, object, str], int] = {}

    try:
        with path.open("r", encoding="utf-8") as handle:
            for item in iter_items(handle):
                file_path = str(item.get("path", "<unknown>"))
                line_num = item.get("line_num", "?")
                typo = str(item.get("typo", ""))
                corrections = item.get("corrections", []) or []

                key = (file_path, line_num, typo)
                occurrence_index = occurrence_counts.get(key, 0) + 1
                occurrence_counts[key] = occurrence_index

                context = get_line_context(item, cache)
                triage = classify(item, context)

                records.append(
                    {
                        "path": file_path,
                        "line_num": item.get("line_num"),
                        "byte_offset": item.get("byte_offset"),
                        "occurrence_index": occurrence_index,
                        "typo": typo,
                        "corrections": corrections,
                        "status": triage["status"],
                        "correction": "",
                        "reason": triage["reason"],
                        "bucket": triage["bucket"],
                        "suggested_status": triage["suggested_status"],
                        "preferred_action": triage["preferred_action"],
                        "rename_candidate": triage["rename_candidate"],
                        "line_text": context["line_text"],
                        "toml_section": "",
                        "toml_snippet": "",
                    }
                )
    except OSError as exc:
        die(f"cannot read typos output '{path}': {exc}")

    return records


def annotate_toml_advice(records: list[dict[str, object]]) -> list[dict[str, object]]:
    token_groups: dict[str, list[dict[str, object]]] = defaultdict(list)
    test_artifact_groups: dict[str, list[dict[str, object]]] = defaultdict(list)

    for record in records:
        typo = str(record["typo"]).lower()
        token_groups[typo].append(record)
        if record["bucket"] == "manual_review.test_artifact":
            test_artifact_groups[str(record["path"])].append(record)

    for typo, items in token_groups.items():
        conservative = [
            item
            for item in items
            if not str(item["bucket"]).startswith("candidate.")
            and item["bucket"] != "manual_review.test_artifact"
            and item["bucket"] != "manual_review.rename_candidate"
        ]
        if len(conservative) < 2:
            continue
        section, snippet = build_word_snippet(str(items[0]["typo"]))
        for item in conservative:
            item["preferred_action"] = "UPDATE_TYPOS_TOML"
            item["toml_section"] = section
            item["toml_snippet"] = snippet
            item["reason"] = (
                f"{item['reason']} Repeated false positive for '{item['typo']}' "
                f"({len(conservative)} hits); prefer `.typos.toml` over editing source one by one."
            )

    if len(test_artifact_groups) >= 1:
        by_pattern: dict[str, tuple[str, str, list[dict[str, object]]]] = {}
        for path, items in test_artifact_groups.items():
            section, snippet = build_exclude_snippet(path)
            key = snippet
            previous = by_pattern.get(key)
            if previous is None:
                by_pattern[key] = (section, snippet, list(items))
            else:
                previous[2].extend(items)

        for section, snippet, items in by_pattern.values():
            if len(items) < 2:
                continue
            for item in items:
                item["preferred_action"] = "UPDATE_TYPOS_TOML"
                item["toml_section"] = section
                item["toml_snippet"] = snippet
                item["reason"] = (
                    f"{item['reason']} Similar hits repeat in test artifacts ({len(items)} hits); "
                    "prefer excluding them in `.typos.toml` before editing fixture data."
                )

    return records


def print_summary(records: list[dict[str, object]]) -> None:
    files = {str(record["path"]) for record in records}
    print(f"Found {len(records)} spelling errors in {len(files)} files.")
    print("")

    counts = Counter(str(record["bucket"]).split(".", 1)[0] for record in records)
    print("Bucket summary:")
    print(f"- candidate source fixes: {counts.get('candidate', 0)}")
    print(f"- default false positives: {counts.get('false_positive', 0)}")
    print(f"- manual review only: {counts.get('manual_review', 0)}")
    print("")

    snippets = []
    seen = set()
    for record in records:
        snippet = str(record["toml_snippet"])
        if not snippet or snippet in seen:
            continue
        seen.add(snippet)
        snippets.append((str(record["typo"]), snippet))

    if snippets:
        print("Suggested `.typos.toml` updates:")
        for typo, snippet in snippets:
            print(f"- For `{typo}`:")
            for line in snippet.splitlines():
                print(f"    {line}")
        print("")


def print_records(records: list[dict[str, object]]) -> None:
    for record in records:
        suggestion_text = ", ".join(record["corrections"])
        print(f"### `{record['path']}`:{record['line_num']}")
        print(f"  **Error**: `{record['typo']}`")
        print(f"  **Suggestions**: [{suggestion_text}]")
        print(f"  **Bucket**: `{record['bucket']}`")
        print(f"  **Suggested Status**: `{record['suggested_status']}`")
        print(f"  **Preferred Action**: `{record['preferred_action']}`")
        print(f"  **Reason**: {record['reason']}")
        if record["rename_candidate"]:
            print(f"  **Rename Candidate**: `{record['rename_candidate']}`")
        line_text = str(record["line_text"]).strip()
        if line_text:
            print(f"  **Line**: `{line_text}`")
        if record["toml_snippet"]:
            print("  **.typos.toml Suggestion**:")
            for line in str(record["toml_snippet"]).splitlines():
                print(f"    {line}")
        print("")


def write_review_file(path: Path, records: list[dict[str, object]]) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
    except OSError as exc:
        die(f"cannot write review file '{path}': {exc}")


def main(argv: list[str]) -> int:
    if len(argv) < 2 or len(argv) > 3:
        die("usage: export-review.py <typos-output.jsonl> [review.jsonl]")

    input_path = Path(argv[1])
    review_path = Path(argv[2]) if len(argv) == 3 else None

    records = annotate_toml_advice(load_records(input_path))
    if not records:
        print("Found 0 spelling errors in 0 files.")
        return 0

    print_summary(records)
    print_records(records)

    if review_path is not None:
        write_review_file(review_path, records)
        print(f"Review file written to: {review_path}")
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
