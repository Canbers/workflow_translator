#!/usr/bin/env python3
"""
Sign In Solutions (tractionguest.com) workflow translator.

Given a workflow JSON from the SIS API, this script finds the language choice page
and ensures all existing non-English language branches mirror the English template
path and have translated user-visible strings. It supports a dry-run mode with a
concise summary and minimal diff, and an update mode that PUTs the modified
workflow body back to the API.

Python 3.10+
Dependencies: requests
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

import requests


# =============================
# Configuration defaults
# =============================

WORKFLOW_ID: str | int = 0
API_BASE_URL: str = "https://us.tractionguest.com"
API_TOKEN: str = ""
SOURCE_LANGUAGE_LABEL: str = "English"
LANGUAGE_MAP: Dict[str, str] = {"English": "en"}
DRY_RUN: bool = True
TRANSLATOR: str = "mock"  # "deepl", "google", or "mock"
TRANSLATOR_API_KEY: str = ""
RATE_LIMIT_QPS: float = 8.0
LOG_LEVEL: str = "INFO"


# =============================
# Data classes
# =============================


@dataclass
class Config:
    workflow_id: str
    api_base_url: str
    api_token: str
    source_language_label: str
    language_map: Dict[str, str]
    dry_run: bool
    translator: str
    translator_api_key: str
    rate_limit_qps: float
    log_level: str


@dataclass
class Summary:
    nodes_created: int = 0
    nodes_updated: int = 0
    strings_translated: int = 0
    languages_processed: int = 0
    warnings: List[str] = None  # type: ignore

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


# =============================
# Logging setup
# =============================


def setup_logging(level: str) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s %(levelname)s %(message)s",
    )


# =============================
# Rate limiter
# =============================


class RateLimiter:
    def __init__(self, qps: float) -> None:
        self.qps = max(0.01, float(qps))
        self.min_interval = 1.0 / self.qps
        self._last_time: float = 0.0

    def wait(self) -> None:
        now = time.time()
        elapsed = now - self._last_time
        to_sleep = self.min_interval - elapsed
        if to_sleep > 0:
            time.sleep(to_sleep)
        self._last_time = time.time()


# =============================
# Translator abstraction
# =============================


class Translator:
    def __init__(self, provider: str, api_key: str, qps: float) -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.rate_limiter = RateLimiter(qps)

        if self.provider not in {"mock", "deepl", "google"}:
            raise ValueError(f"Unsupported translator provider: {provider}")
        if self.provider in {"deepl", "google"} and not self.api_key:
            raise ValueError("Translator API key is required for non-mock providers.")

    def translate(self, text: str, target_iso: str) -> str:
        if not text:
            return text
        if self.provider == "mock":
            return f"[{target_iso}] {text}"
        if self.provider == "deepl":
            return self._translate_deepl(text, target_iso)
        if self.provider == "google":
            return self._translate_google(text, target_iso)
        raise ValueError(f"Unsupported provider: {self.provider}")

    def _translate_deepl(self, text: str, target_iso: str) -> str:
        # DeepL target lang codes are typically uppercase like 'ES', 'EN-GB'
        target_lang = target_iso.upper()
        self.rate_limiter.wait()
        url = "https://api.deepl.com/v2/translate"
        data = {
            "auth_key": self.api_key,
            "text": text,
            "target_lang": target_lang,
        }
        try:
            resp = requests.post(url, data=data, timeout=20)
            if resp.status_code != 200:
                raise RuntimeError(f"DeepL HTTP {resp.status_code}: {resp.text[:200]}")
            payload = resp.json()
            translations = payload.get("translations", [])
            if not translations:
                raise RuntimeError("DeepL: empty translations")
            return translations[0].get("text", text)
        except Exception as exc:  # noqa: BLE001
            logging.warning("DeepL translate error: %s", exc)
            return text

    def _translate_google(self, text: str, target_iso: str) -> str:
        self.rate_limiter.wait()
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {"key": self.api_key}
        data = {"q": text, "target": target_iso}
        headers = {"Content-Type": "application/json"}
        try:
            resp = requests.post(url, params=params, json=data, headers=headers, timeout=20)
            if resp.status_code != 200:
                raise RuntimeError(f"Google Translate HTTP {resp.status_code}: {resp.text[:200]}")
            payload = resp.json()
            data_obj = payload.get("data", {})
            translations = data_obj.get("translations", [])
            if not translations:
                raise RuntimeError("Google: empty translations")
            return translations[0].get("translatedText", text)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Google translate error: %s", exc)
            return text


# =============================
# Token preservation utilities
# =============================


TOKEN_PATTERNS: List[re.Pattern[str]] = [
    re.compile(r"\{\{[^}]+\}\}"),  # handlebars-like
    re.compile(r"%[A-Za-z0-9_]+%"),  # %TOKEN%
    re.compile(r"#[^#]+#"),  # #TOKEN#
]


def extract_tokens(text: str) -> Tuple[str, Dict[str, str]]:
    """Replace token patterns with placeholders T0, T1 ... and return sanitized text and map."""
    placeholders: Dict[str, str] = {}
    idx = 0

    def repl(match: re.Match[str]) -> str:
        nonlocal idx
        key = f"[[T{idx}]]"
        placeholders[key] = match.group(0)
        idx += 1
        return key

    sanitized = text
    for pat in TOKEN_PATTERNS:
        sanitized = pat.sub(repl, sanitized)
    return sanitized, placeholders


def restore_tokens(text: str, placeholders: Dict[str, str]) -> str:
    for key, original in placeholders.items():
        text = text.replace(key, original)
    return text


def looks_like_url_or_html(text: str) -> bool:
    if "http://" in text or "https://" in text:
        return True
    if "<" in text and ">" in text:
        return True
    return False


def is_only_tokens_or_whitespace(text: str) -> bool:
    if text.strip() == "":
        return True
    sanitized, placeholders = extract_tokens(text)
    leftover = sanitized.replace(" ", "").replace("\n", "")
    # If removing spaces leaves only placeholders
    placeholder_only = re.fullmatch(r"(\[\[T\d+\]\])+", leftover)
    return placeholder_only is not None


# =============================
# API client and helpers
# =============================


class SISClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        })

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/workflows/{workflow_id}"
        resp = self.session.get(url, timeout=30)
        if resp.status_code == 401:
            raise PermissionError("API unauthorized (401)")
        if resp.status_code == 403:
            raise PermissionError("API forbidden (403)")
        if resp.status_code == 404:
            raise FileNotFoundError("Workflow not found (404)")
        if resp.status_code >= 400:
            raise RuntimeError(f"GET failed: HTTP {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        if not isinstance(payload, dict) or "workflow" not in payload:
            raise ValueError("Unexpected API response shape: missing 'workflow'")
        return payload["workflow"]

    def put_workflow(self, workflow: Dict[str, Any]) -> None:
        workflow_id = str(workflow.get("id") or workflow.get("workflow_id") or "")
        url = f"{self.base_url}/workflows/{workflow_id}"
        resp = self.session.put(url, data=json.dumps({"workflow": workflow}), timeout=60)
        if resp.status_code >= 400:
            raise RuntimeError(f"PUT failed: HTTP {resp.status_code}: {resp.text[:500]}")


def parse_inner_body(workflow: Dict[str, Any]) -> Dict[str, Any]:
    body_str = workflow.get("body")
    if not isinstance(body_str, str) or body_str.strip() == "":
        raise ValueError("Workflow 'body' missing or not a string")
    try:
        inner = json.loads(body_str)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("Failed to parse workflow.body as JSON") from exc
    if not isinstance(inner, dict) or "nodes" not in inner:
        raise ValueError("Inner body missing 'nodes'")
    return inner


# =============================
# Graph utilities
# =============================


def find_language_page(inner: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    for node_id, node in inner.get("nodes", {}).items():
        if node.get("type") == "page":
            config = node.get("configuration", {}) or {}
            if config.get("data_name") == "language":
                return str(node_id), node
    raise ValueError("Language page with configuration.data_name == 'language' not found")


def build_choice_maps(language_node: Dict[str, Any]) -> Tuple[Dict[int, str], Dict[str, int]]:
    reasons = (language_node.get("configuration") or {}).get("reasons") or []
    id_to_label: Dict[int, str] = {}
    label_to_id: Dict[str, int] = {}
    for r in reasons:
        try:
            rid = int(r.get("id"))
        except Exception:  # noqa: BLE001
            continue
        label = str(r.get("title") or r.get("label") or "").strip()
        if label:
            id_to_label[rid] = label
            label_to_id[label] = rid
    if not id_to_label:
        raise ValueError("Language page has no reasons/choices")
    return id_to_label, label_to_id


def build_label_to_startnode(language_node: Dict[str, Any], id_to_label: Dict[int, str]) -> Dict[str, Optional[str]]:
    next_obj = language_node.get("next") or {}
    conditions = next_obj.get("conditions") or []
    label_to_start: Dict[str, Optional[str]] = {}
    for cond in conditions:
        if cond.get("lval") != "language_id":
            continue
        try:
            rval = int(cond.get("rval"))
        except Exception:  # noqa: BLE001
            continue
        result = cond.get("result")
        label = id_to_label.get(rval)
        if label is not None:
            label_to_start[label] = str(result) if result is not None else None
    return label_to_start


def walk_subgraph(inner: Dict[str, Any], start_id: str) -> Tuple[List[str], Set[str]]:
    """Depth-first walk to collect ordered node visitation and visited set, preserving branching.

    The order is deterministic: visit node, then iterate conditions in order, then default.
    Cycles are avoided via visited set; repeated nodes are not revisited.
    """
    nodes = inner.get("nodes", {})
    visited: Set[str] = set()
    order: List[str] = []

    def dfs(node_id: Optional[str]) -> None:
        if node_id is None:
            return
        nid = str(node_id)
        if nid in visited:
            return
        node = nodes.get(nid)
        if not node:
            return
        visited.add(nid)
        order.append(nid)
        nxt = node.get("next") or {}
        conditions = nxt.get("conditions") or []
        for cond in conditions:
            dfs(cond.get("result"))
        dfs(nxt.get("default"))

    dfs(str(start_id))
    return order, visited


def compute_shape_signature(inner: Dict[str, Any], start_id: str) -> Tuple[Tuple[str, ...], Tuple[Tuple[int, int], ...]]:
    """Return a shape signature as:
    - template_id sequence in deterministic DFS order
    - for each node in that order: (num_conditions, has_default)
    """
    order, _ = walk_subgraph(inner, start_id)
    templ_seq: List[str] = []
    branch_seq: List[Tuple[int, int]] = []
    for nid in order:
        node = inner["nodes"][nid]
        templ_seq.append(str(node.get("template_id")))
        nxt = node.get("next") or {}
        conds = nxt.get("conditions") or []
        has_default = 1 if nxt.get("default") is not None else 0
        branch_seq.append((len(conds), has_default))
    return tuple(templ_seq), tuple(branch_seq)


def max_node_id(inner: Dict[str, Any]) -> int:
    max_id = 0
    for k in inner.get("nodes", {}).keys():
        try:
            max_id = max(max_id, int(str(k)))
        except Exception:  # noqa: BLE001
            continue
    return max_id


def iso_from_label(label: str, language_map: Dict[str, str]) -> str:
    if label in language_map:
        return language_map[label]
    normalized = label.strip().lower()
    heuristics = {
        "english": "en",
        "en": "en",
        "spanish": "es",
        "español": "es",
        "espanol": "es",
        "french": "fr",
        "français": "fr",
        "francais": "fr",
        "german": "de",
        "deutsch": "de",
        "italian": "it",
        "italiano": "it",
        "portuguese": "pt",
        "português": "pt",
        "portugues": "pt",
        "japanese": "ja",
        "日本語": "ja",
        "chinese": "zh",
        "中文": "zh",
        "简体中文": "zh-CN",
        "繁體中文": "zh-TW",
        "korean": "ko",
        "한국어": "ko",
        "arabic": "ar",
        "русский": "ru",
        "russian": "ru",
        "hindi": "hi",
    }
    return heuristics.get(normalized, normalized[:2] if len(normalized) >= 2 else "")


TRANSLATABLE_KEYS: Set[str] = {
    "title",
    "message",
    "back",
    "forward",
    "label",
    "placeholder",
    "help",
    "description",
    "error",
    "errors",
    "validation_message",
    "subtitle",
    "hint",
}


def translate_node_strings(
    node: Dict[str, Any],
    target_iso: str,
    translator: Translator,
) -> int:
    """Translate user-visible strings in node in-place. Returns number of translated strings."""
    translated_count = 0

    def maybe_translate(value: Any) -> Any:
        nonlocal translated_count
        if isinstance(value, str):
            if not value or looks_like_url_or_html(value) or is_only_tokens_or_whitespace(value):
                return value
            sanitized, placeholders = extract_tokens(value)
            out = translator.translate(sanitized, target_iso)
            out = restore_tokens(out, placeholders)
            if out != value:
                translated_count += 1
            return out
        if isinstance(value, list):
            return [maybe_translate(v) for v in value]
        if isinstance(value, dict):
            return {k: maybe_translate(v) for k, v in value.items()}
        return value

    # Translate labels
    labels = node.get("labels")
    if isinstance(labels, dict):
        for key in list(labels.keys()):
            if key in TRANSLATABLE_KEYS and isinstance(labels.get(key), str):
                labels[key] = maybe_translate(labels[key])

    # Translate configuration strings (common fields)
    conf = node.get("configuration")
    if isinstance(conf, dict):
        for key, val in list(conf.items()):
            # Reasons on non-language pages may exist; translate their titles/labels
            if key in TRANSLATABLE_KEYS and isinstance(val, str):
                conf[key] = maybe_translate(val)
            elif isinstance(val, list):
                conf[key] = [maybe_translate(v) for v in val]
            elif isinstance(val, dict):
                conf[key] = maybe_translate(val)

    return translated_count


def clone_subgraph(
    inner: Dict[str, Any],
    start_id: str,
) -> Tuple[str, Dict[str, str]]:
    """Clone the subgraph reachable from start_id. Returns (new_start_id, old_to_new_map)."""
    nodes = inner.get("nodes", {})
    order, visited = walk_subgraph(inner, start_id)
    next_id = max_node_id(inner) + 1
    old_to_new: Dict[str, str] = {}

    # First pass: create shallow copies with new IDs
    for old_id in order:
        new_id = str(next_id)
        next_id += 1
        old_to_new[old_id] = new_id
        node = nodes[old_id]
        new_node = json.loads(json.dumps(node))  # deep copy
        new_node["id"] = new_id
        nodes[new_id] = new_node

    # Second pass: fix next pointers within the cloned set
    for old_id, new_id in old_to_new.items():
        node = nodes[new_id]
        nxt = node.get("next") or {}
        conditions = nxt.get("conditions") or []
        for cond in conditions:
            res = cond.get("result")
            if res is not None:
                res_str = str(res)
                if res_str in old_to_new:
                    cond["result"] = old_to_new[res_str]
        if nxt.get("default") is not None:
            def_res = str(nxt.get("default"))
            if def_res in old_to_new:
                nxt["default"] = old_to_new[def_res]
        node["next"] = nxt

    new_start_id = old_to_new[str(start_id)]
    return new_start_id, old_to_new


def ensure_meta_lang(node: Dict[str, Any], iso: str) -> None:
    meta = node.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        node["meta"] = meta
    meta["lang"] = iso


def process_languages(
    inner: Dict[str, Any],
    language_node_id: str,
    language_node: Dict[str, Any],
    source_label: str,
    language_map: Dict[str, str],
    translator: Translator,
) -> Summary:
    id_to_label, label_to_id = build_choice_maps(language_node)
    label_to_start = build_label_to_startnode(language_node, id_to_label)

    if source_label not in label_to_id:
        raise ValueError(f"Source language label '{source_label}' not found among choices")
    if source_label not in label_to_start or not label_to_start[source_label]:
        raise ValueError(f"No start node found for source language '{source_label}'")

    english_start = str(label_to_start[source_label])

    # Compute template shape
    template_shape = compute_shape_signature(inner, english_start)
    template_order, template_visited = walk_subgraph(inner, english_start)

    summary = Summary()

    for label, choice_id in label_to_id.items():
        if label == source_label:
            continue
        target_iso = iso_from_label(label, language_map)
        if not target_iso:
            summary.warnings.append(f"Could not infer ISO code for '{label}', skipping.")
            continue

        summary.languages_processed += 1
        existing_start = label_to_start.get(label)

        if existing_start and str(existing_start) in inner.get("nodes", {}):
            # Update in place if meta.lang matches
            start_node = inner["nodes"][str(existing_start)]
            meta = start_node.get("meta") or {}
            if meta.get("lang") == target_iso:
                logging.info("Updating existing path for '%s' (start node %s)", label, existing_start)
                # Walk this path limited to template visited nodes shape if possible
                order, _ = walk_subgraph(inner, str(existing_start))
                translated_here = 0
                for nid in order:
                    node = inner["nodes"][nid]
                    translated_here += translate_node_strings(node, target_iso, translator)
                    ensure_meta_lang(node, target_iso)
                summary.nodes_updated += len(order)
                summary.strings_translated += translated_here
            else:
                # Either different lang or not set; treat as clone to avoid breaking other uses
                logging.info("Cloning template for '%s' (existing start %s ignored)", label, existing_start)
                new_start, mapping = clone_subgraph(inner, english_start)
                # Translate cloned nodes
                translated_here = 0
                for old_id, new_id in mapping.items():
                    node = inner["nodes"][new_id]
                    translated_here += translate_node_strings(node, target_iso, translator)
                    ensure_meta_lang(node, target_iso)
                    # mark where it came from
                    meta2 = node.get("meta") or {}
                    meta2["cloned_from"] = "en"
                    node["meta"] = meta2
                # Wire the language condition to new_start
                _wire_language_condition(language_node, label, new_start, id_to_label, label_to_id)
                summary.nodes_created += len(mapping)
                summary.strings_translated += translated_here
        else:
            # No path yet: clone from English
            logging.info("Creating new path for '%s'", label)
            new_start, mapping = clone_subgraph(inner, english_start)
            translated_here = 0
            for old_id, new_id in mapping.items():
                node = inner["nodes"][new_id]
                translated_here += translate_node_strings(node, target_iso, translator)
                ensure_meta_lang(node, target_iso)
                meta2 = node.get("meta") or {}
                meta2["cloned_from"] = "en"
                node["meta"] = meta2
            _wire_language_condition(language_node, label, new_start, id_to_label, label_to_id)
            summary.nodes_created += len(mapping)
            summary.strings_translated += translated_here

        # Validate
        new_start_for_label = _get_language_result(language_node, label, id_to_label, label_to_id)
        if new_start_for_label is None or str(new_start_for_label) not in inner.get("nodes", {}):
            summary.warnings.append(f"Language '{label}' has dangling start node reference")
        else:
            tgt_shape = compute_shape_signature(inner, str(new_start_for_label))
            if tgt_shape != template_shape:
                summary.warnings.append(
                    f"Topology mismatch for '{label}': template {template_shape[:1]} vs target {tgt_shape[:1]}"
                )

    return summary


def _get_language_result(
    language_node: Dict[str, Any],
    label: str,
    id_to_label: Dict[int, str],
    label_to_id: Dict[str, int],
) -> Optional[str]:
    choice_id = label_to_id.get(label)
    nxt = language_node.get("next") or {}
    conditions = nxt.get("conditions") or []
    for cond in conditions:
        if cond.get("lval") == "language_id" and int(cond.get("rval", -1)) == int(choice_id):
            res = cond.get("result")
            return str(res) if res is not None else None
    return None


def _wire_language_condition(
    language_node: Dict[str, Any],
    label: str,
    new_start_id: str,
    id_to_label: Dict[int, str],
    label_to_id: Dict[str, int],
) -> None:
    choice_id = label_to_id.get(label)
    if choice_id is None:
        raise ValueError(f"Choice label '{label}' not found on language page")
    nxt = language_node.get("next") or {}
    conditions = nxt.get("conditions") or []
    updated = False
    for cond in conditions:
        if cond.get("lval") == "language_id" and int(cond.get("rval", -1)) == int(choice_id):
            cond["result"] = new_start_id
            updated = True
            break
    if not updated:
        # Do not add new choices; but routing existed without condition? Unlikely
        raise ValueError(f"Routing condition for label '{label}' not found; cannot wire new start node")


# =============================
# Diff / Summary output
# =============================


def print_summary(summary: Summary) -> None:
    logging.info("=== Summary ===")
    lines = [
        ("Nodes created", summary.nodes_created),
        ("Nodes updated", summary.nodes_updated),
        ("Strings translated", summary.strings_translated),
        ("Languages processed", summary.languages_processed),
        ("Warnings", len(summary.warnings)),
    ]
    width = max(len(k) for k, _ in lines)
    for k, v in lines:
        print(f"{k:<{width}} : {v}")
    if summary.warnings:
        print("Warnings:")
        for w in summary.warnings:
            print(f" - {w}")


# =============================
# CLI / Config
# =============================


def parse_language_map_env(value: str) -> Dict[str, str]:
    try:
        obj = json.loads(value)
        if isinstance(obj, dict):
            return {str(k): str(v) for k, v in obj.items()}
    except Exception:  # noqa: BLE001
        pass
    # Fallback: CSV like "English:en,Spanish:es"
    result: Dict[str, str] = {}
    for part in value.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            result[k.strip()] = v.strip()
    return result


def load_config_from_env_and_args(args: argparse.Namespace) -> Config:
    workflow_id = str(
        args.workflow
        or os.getenv("SIS_WORKFLOW_ID")
        or WORKFLOW_ID
    )
    api_base_url = str(os.getenv("SIS_API_BASE_URL") or API_BASE_URL)
    api_token = str(args.token or os.getenv("SIS_API_TOKEN") or API_TOKEN)
    source_label = str(args.source_label or os.getenv("SIS_SOURCE_LANGUAGE_LABEL") or SOURCE_LANGUAGE_LABEL)

    lm = LANGUAGE_MAP.copy()
    env_lm = os.getenv("SIS_LANGUAGE_MAP")
    if env_lm:
        lm.update(parse_language_map_env(env_lm))

    dry_run = not bool(args.write) if args.write is not None else (
        (os.getenv("SIS_DRY_RUN") or str(DRY_RUN)).lower() in {"1", "true", "yes"}
    )
    translator = str(os.getenv("SIS_TRANSLATOR") or TRANSLATOR)
    translator_api_key = str(os.getenv("SIS_TRANSLATOR_API_KEY") or TRANSLATOR_API_KEY)
    rate_limit_qps = float(os.getenv("SIS_RATE_LIMIT_QPS") or RATE_LIMIT_QPS)
    log_level = str(args.log_level or os.getenv("SIS_LOG_LEVEL") or LOG_LEVEL)

    return Config(
        workflow_id=workflow_id,
        api_base_url=api_base_url,
        api_token=api_token,
        source_language_label=source_label,
        language_map=lm,
        dry_run=dry_run,
        translator=translator,
        translator_api_key=translator_api_key,
        rate_limit_qps=rate_limit_qps,
        log_level=log_level,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SIS Workflow language translator")
    p.add_argument("--workflow", "-w", help="Workflow ID", required=False)
    p.add_argument("--write", action="store_true", help="Perform PUT (default is dry-run)")
    p.add_argument("--token", help="API bearer token", required=False)
    p.add_argument("--source-label", help="Source language label (e.g., English)", required=False)
    p.add_argument("--log-level", help="Logging level (DEBUG, INFO, ...)", required=False)
    p.add_argument("--self-test", action="store_true", help="Run self test on sample payload")
    return p


# =============================
# Main pipeline
# =============================


def process_workflow_pipeline(config: Config) -> None:
    if config.dry_run:
        logging.info("Running in DRY RUN mode (no PUT)")
    else:
        logging.info("Running in WRITE mode (will PUT changes)")

    translator = Translator(config.translator, config.translator_api_key, config.rate_limit_qps)

    if not config.api_token and not args.self_test:  # type: ignore[name-defined]
        raise ValueError("API token is required. Provide via --token or SIS_API_TOKEN.")

    if args.self_test:  # type: ignore[name-defined]
        workflow, inner = sample_workflow_and_inner()
        logging.info("Loaded sample workflow for self-test")
    else:
        client = SISClient(config.api_base_url, config.api_token)
        logging.info("Fetching workflow %s", redact(config.workflow_id))
        workflow = client.get_workflow(config.workflow_id)
        inner = parse_inner_body(workflow)

    lang_node_id, lang_node = find_language_page(inner)
    logging.info("Language page found: node %s", lang_node_id)

    summary = process_languages(
        inner=inner,
        language_node_id=lang_node_id,
        language_node=lang_node,
        source_label=config.source_language_label,
        language_map=config.language_map,
        translator=translator,
    )

    print_summary(summary)

    if not config.dry_run:
        # Serialize and PUT
        workflow["body"] = json.dumps(inner, separators=(",", ":"))
        if args.self_test:  # type: ignore[name-defined]
            logging.info("Self-test mode: would PUT updated workflow; skipping")
        else:
            client = SISClient(config.api_base_url, config.api_token)
            logging.info("PUT updated workflow to API")
            client.put_workflow(workflow)
            logging.info("PUT completed successfully")


def redact(text: Any) -> str:
    s = str(text)
    if len(s) <= 4:
        return "***"
    return s[:2] + "***" + s[-2:]


# =============================
# Self-test
# =============================


def sample_workflow_and_inner() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    # Minimal workflow wrapper
    inner: Dict[str, Any] = {
        "starting_node_id": "1",
        "nodes": {}
    }

    def add_node(node_id: str, node: Dict[str, Any]) -> None:
        inner["nodes"][node_id] = node

    # Language page id=1
    add_node("1", {
        "id": "1",
        "type": "page",
        "template_id": "choice",
        "labels": {"title": "Choose language", "forward": "Continue", "back": "Back"},
        "configuration": {
            "data_name": "language",
            "reasons": [
                {"id": 1, "title": "English"},
                {"id": 2, "title": "Spanish"}
            ]
        },
        "next": {
            "conditions": [
                {"lval": "language_id", "op": "==", "rval": 1, "rval_type": "constant", "result": "2"},
                {"lval": "language_id", "op": "==", "rval": 2, "rval_type": "constant", "result": None}
            ],
            "default": None
        }
    })

    # English path: node 2 -> node 3
    add_node("2", {
        "id": "2",
        "type": "page",
        "template_id": "welcome",
        "labels": {"title": "Welcome {{name}}", "forward": "Next"},
        "configuration": {"fields": [{"label": "Company", "placeholder": "Enter company"}]},
        "next": {"conditions": [], "default": "3"}
    })

    add_node("3", {
        "id": "3",
        "type": "page",
        "template_id": "confirm",
        "labels": {"title": "Confirm details", "forward": "Finish"},
        "configuration": {"summary": {"title": "Summary"}},
        "next": {"conditions": [], "default": None}
    })

    workflow: Dict[str, Any] = {"id": "SAMPLE", "body": json.dumps(inner)}
    return workflow, inner


def self_test_on_sample() -> None:
    cfg = Config(
        workflow_id="SAMPLE",
        api_base_url=API_BASE_URL,
        api_token="dummy",
        source_language_label="English",
        language_map={"English": "en", "Spanish": "es"},
        dry_run=True,
        translator="mock",
        translator_api_key="",
        rate_limit_qps=RATE_LIMIT_QPS,
        log_level=LOG_LEVEL,
    )
    setup_logging(cfg.log_level)
    global args  # noqa: PLW0603
    class A:  # simple shim for args
        self_test = True
    args = A()  # type: ignore[assignment]
    process_workflow_pipeline(cfg)


# =============================
# Entry point
# =============================


def main() -> None:
    parser = build_arg_parser()
    global args  # noqa: PLW0603
    args = parser.parse_args()
    cfg = load_config_from_env_and_args(args)
    setup_logging(cfg.log_level)
    if args.self_test:
        self_test_on_sample()
        return
    process_workflow_pipeline(cfg)


if __name__ == "__main__":
    main()

