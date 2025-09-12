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
import html
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

WORKFLOW_ID: str | int = ""  # must be provided via --workflow or env
API_BASE_URL: str = "https://us.tractionguest.com"
API_TOKEN: str = ""  # must be provided via --token or env
SOURCE_LANGUAGE_LABEL: str = "English"
LANGUAGE_MAP: Dict[str, str] = {"English": "en"}
DRY_RUN: bool = True
TRANSLATOR: str = "mock"  # "deepl", "google", "libretranslate", or "mock"
TRANSLATOR_API_KEY: str = ""
RATE_LIMIT_QPS: float = 8.0
LOG_LEVEL: str = "INFO"

# Optional translator-specific settings
TRANSLATOR_ENDPOINT: str = ""  # e.g., LibreTranslate endpoint


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
    translator_endpoint: str
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
# .env loader (no external dependency)
# =============================


def load_env_file(path: str = ".env") -> None:
    """Load KEY=VALUE pairs from a .env file into os.environ if not already set.

    Lines starting with '#' are comments. Quotes around values are stripped.
    """
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception as exc:  # noqa: BLE001
        logging.debug("Could not load .env file: %s", exc)


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
    def __init__(self, provider: str, api_key: str, qps: float, endpoint: str = "") -> None:
        self.provider = provider.lower()
        self.api_key = api_key
        self.rate_limiter = RateLimiter(qps)
        self.endpoint = endpoint

        if self.provider not in {"mock", "deepl", "google", "libretranslate"}:
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
        if self.provider == "libretranslate":
            return self._translate_libretranslate(text, target_iso)
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
            translated = translations[0].get("text", text)
            return html.unescape(translated)
        except Exception as exc:  # noqa: BLE001
            logging.warning("DeepL translate error: %s", exc)
            return text

    def _translate_google(self, text: str, target_iso: str) -> str:
        self.rate_limiter.wait()
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {"key": self.api_key}
        data = {"q": text, "target": target_iso, "format": "text"}
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
            translated = translations[0].get("translatedText", text)
            return html.unescape(translated)
        except Exception as exc:  # noqa: BLE001
            logging.warning("Google translate error: %s", exc)
            return text

    def _translate_libretranslate(self, text: str, target_iso: str) -> str:
        # LibreTranslate typically uses two-letter lowercase codes (e.g., 'es').
        target_lang = target_iso.split("-")[0].lower()
        self.rate_limiter.wait()
        url = self.endpoint.strip() or "https://libretranslate.com/translate"
        headers = {"Content-Type": "application/json"}
        data = {
            "q": text,
            "source": "auto",
            "target": target_lang,
            "format": "text",
        }
        # Some instances require an API key; include if provided
        if self.api_key:
            data["api_key"] = self.api_key
        try:
            resp = requests.post(url, json=data, headers=headers, timeout=20)
            if resp.status_code != 200:
                raise RuntimeError(f"LibreTranslate HTTP {resp.status_code}: {resp.text[:200]}")
            payload = resp.json()
            translated = payload.get("translatedText") or payload.get("translation")
            if not translated:
                raise RuntimeError("LibreTranslate: missing 'translatedText'")
            return html.unescape(str(translated))
        except Exception as exc:  # noqa: BLE001
            logging.warning("LibreTranslate translate error: %s", exc)
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


def strip_mock_prefix(text: str, target_iso: str) -> str:
    """Remove leading mock prefix like "[es] " when translating with a real provider.

    Only strips if the code matches the target_iso (case-insensitive) to avoid
    accidentally removing legitimate bracketed content.
    """
    m = re.match(r"^\[([A-Za-z]{2}(?:-[A-Za-z]{2})?)\]\s+", text)
    if not m:
        return text
    code = m.group(1)
    if code.lower() == target_iso.lower():
        return text[m.end():]
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
    default_result = next_obj.get("default")
    label_to_start: Dict[str, Optional[str]] = {}
    # Build explicit mappings from conditions
    for cond in conditions:
        if cond.get("lval") != "reason_id":
            continue
        try:
            rval = int(cond.get("rval"))
        except Exception:  # noqa: BLE001
            continue
        result = cond.get("result")
        label = id_to_label.get(rval)
        if label is not None:
            label_to_start[label] = str(result) if result is not None else None
    # Any choice without an explicit condition should inherit the page default
    if default_result is not None:
        for choice_id, label in id_to_label.items():
            if label not in label_to_start:
                label_to_start[label] = str(default_result)
    logging.debug(
        "Language routing map built: %s (default=%s)", label_to_start, default_result
    )
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
        # English and variants
        "english": "en",
        "en": "en",
        "en-us": "en-US",
        "us english": "en-US",
        "american english": "en-US",
        "en-gb": "en-GB",
        "british english": "en-GB",
        "uk english": "en-GB",
        "en-ca": "en-CA",
        "canadian english": "en-CA",
        "en-au": "en-AU",
        "australian english": "en-AU",
        "en-in": "en-IN",
        "indian english": "en-IN",

        # Spanish and variants
        "spanish": "es",
        "español": "es",
        "espanol": "es",
        "castellano": "es",
        "es-es": "es-ES",
        "spain spanish": "es-ES",
        "es-mx": "es-MX",
        "mexican spanish": "es-MX",
        "es-419": "es-419",
        "latin american spanish": "es-419",
        "es-ar": "es-AR",

        # French and variants
        "french": "fr",
        "français": "fr",
        "francais": "fr",
        "fr-ca": "fr-CA",
        "canadian french": "fr-CA",
        "fr-be": "fr-BE",
        "belgian french": "fr-BE",
        "fr-ch": "fr-CH",
        "swiss french": "fr-CH",

        # Portuguese and variants
        "portuguese": "pt",
        "português": "pt",
        "portugues": "pt",
        "pt-br": "pt-BR",
        "brazilian portuguese": "pt-BR",
        "pt-pt": "pt-PT",
        "european portuguese": "pt-PT",

        # German and variants
        "german": "de",
        "deutsch": "de",
        "de-at": "de-AT",
        "austrian german": "de-AT",
        "de-ch": "de-CH",
        "swiss german": "de-CH",

        # Italian
        "italian": "it",
        "italiano": "it",

        # Dutch and Flemish
        "dutch": "nl",
        "nederlands": "nl",
        "vlaams": "nl-BE",
        "flemish": "nl-BE",
        "nl-be": "nl-BE",

        # Nordic languages
        "swedish": "sv",
        "svenska": "sv",
        "norwegian": "no",
        "norsk": "no",
        "bokmål": "nb",
        "bokmal": "nb",
        "nynorsk": "nn",
        "danish": "da",
        "dansk": "da",
        "finnish": "fi",
        "suomi": "fi",
        "icelandic": "is",
        "íslenska": "is",
        "islenska": "is",

        # Baltic languages
        "estonian": "et",
        "eesti": "et",
        "latvian": "lv",
        "latviešu": "lv",
        "lithuanian": "lt",
        "lietuvių": "lt",

        # Central/Eastern Europe
        "polish": "pl",
        "polski": "pl",
        "czech": "cs",
        "čeština": "cs",
        "cestina": "cs",
        "slovak": "sk",
        "slovenčina": "sk",
        "slovencina": "sk",
        "slovenian": "sl",
        "slovenščina": "sl",
        "slovenscina": "sl",
        "hungarian": "hu",
        "magyar": "hu",
        "romanian": "ro",
        "română": "ro",
        "romana": "ro",
        "moldovan": "ro-MD",
        "bulgarian": "bg",
        "български": "bg",
        "greek": "el",
        "ελληνικά": "el",

        # Balkans
        "serbian": "sr",
        "srpski": "sr",
        "српски": "sr",
        "croatian": "hr",
        "hrvatski": "hr",
        "bosnian": "bs",
        "bosanski": "bs",
        "macedonian": "mk",
        "македонски": "mk",
        "albanian": "sq",
        "shqip": "sq",

        # Slavic East
        "ukrainian": "uk",
        "українська": "uk",
        "belarusian": "be",
        "беларуская": "be",
        "russian": "ru",
        "русский": "ru",

        # Caucasus and Central Asia
        "armenian": "hy",
        "հայերեն": "hy",
        "georgian": "ka",
        "ქართული": "ka",
        "azerbaijani": "az",
        "azerbaijan": "az",
        "azeri": "az",
        "azərbaycan": "az",
        "kazakh": "kk",
        "қазақ": "kk",
        "uzbek": "uz",
        "oʻzbekcha": "uz",
        "ozbekcha": "uz",
        "tajik": "tg",
        "tojiki": "tg",
        "kyrgyz": "ky",
        "кыргызча": "ky",
        "turkmen": "tk",
        "türkmençe": "tk",
        "turkmence": "tk",
        "mongolian": "mn",
        "монгол": "mn",

        # Middle East
        "turkish": "tr",
        "türkçe": "tr",
        "turkce": "tr",
        "arabic": "ar",
        "العربية": "ar",
        "persian": "fa",
        "farsi": "fa",
        "فارسی": "fa",
        "dari": "fa-AF",
        "pashto": "ps",
        "پښتو": "ps",
        "kurdish": "ku",
        "kurdî": "ku",

        # Hebrew and Yiddish
        "hebrew": "he",
        "עברית": "he",
        "ivrit": "he",
        "yiddish": "yi",
        "יידיש": "yi",

        # South Asia
        "hindi": "hi",
        "हिंदी": "hi",
        # Note: Urdu is written right-to-left
        "urdu": "ur",
        "اردو": "ur",
        "bengali": "bn",
        "bangla": "bn",
        "বাংলা": "bn",
        "punjabi": "pa",
        "panjabi": "pa",
        "ਪੰਜਾਬੀ": "pa",
        "gujarati": "gu",
        "ગુજરાતી": "gu",
        "marathi": "mr",
        "मराठी": "mr",
        "tamil": "ta",
        "தமிழ்": "ta",
        "telugu": "te",
        "తెలుగు": "te",
        "kannada": "kn",
        "ಕನ್ನಡ": "kn",
        "malayalam": "ml",
        "മലയാളം": "ml",
        "sinhala": "si",
        "sinhalese": "si",
        "සිංහල": "si",
        "odia": "or",
        "oriya": "or",
        "ଓଡ଼ିଆ": "or",
        "assamese": "as",
        "অসমীয়া": "as",
        "nepali": "ne",
        "नेपाली": "ne",

        # Southeast Asia
        "burmese": "my",
        "myanmar": "my",
        "မြန်မာ": "my",
        "khmer": "km",
        "cambodian": "km",
        "ខ្មែរ": "km",
        "lao": "lo",
        "ລາວ": "lo",
        "thai": "th",
        "ไทย": "th",
        "vietnamese": "vi",
        "tiếng việt": "vi",
        "tieng viet": "vi",
        "indonesian": "id",
        "bahasa indonesia": "id",
        "bahasa": "id",
        "malay": "ms",
        "bahasa melayu": "ms",
        "melayu": "ms",
        "filipino": "fil",
        "tagalog": "fil",
        "tl": "tl",

        # East Asia
        "japanese": "ja",
        "nihongo": "ja",
        "日本語": "ja",
        "にほんご": "ja",
        "korean": "ko",
        "한국어": "ko",
        "조선말": "ko",
        "chinese": "zh",
        "中文": "zh",
        "simplified chinese": "zh-CN",
        "traditional chinese": "zh-TW",
        "简体中文": "zh-CN",
        "繁體中文": "zh-TW",
        "zh-cn": "zh-CN",
        "zh-tw": "zh-TW",
        "zh-hk": "zh-HK",
        "cantonese": "zh-HK",
        "粤语": "zh-HK",
        "粵語": "zh-HK",

        # Africa
        "afrikaans": "af",
        "hausa": "ha",
        "igbo": "ig",
        "yoruba": "yo",
        "swahili": "sw",
        "kiswahili": "sw",
        "amharic": "am",
        "አማርኛ": "am",
        "somali": "so",
        "af-soomaali": "so",
        "zulu": "zu",
        "xhosa": "xh",
        "sesotho": "st",
        "setswana": "tn",
        "tswana": "tn",
        "shona": "sn",
        "malagasy": "mg",

        # Americas and Pacific
        "haitian creole": "ht",
        "kreyòl ayisyen": "ht",
        "maori": "mi",
        "te reo māori": "mi",
        "te reo maori": "mi",
        "samoan": "sm",
        "gagana sāmoa": "sm",
        "tongan": "to",
        "lea fakatonga": "to",
        "fijian": "fj",
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

    def translate_string(text: str) -> str:
        nonlocal translated_count
        if not text or looks_like_url_or_html(text) or is_only_tokens_or_whitespace(text):
            return text
        base_text = text
        if translator.provider != "mock":
            base_text = strip_mock_prefix(base_text, target_iso)
        sanitized, placeholders = extract_tokens(base_text)
        out = translator.translate(sanitized, target_iso)
        out = restore_tokens(out, placeholders)
        if out != text:
            translated_count += 1
        return out

    template_id = str(node.get("template_id") or "")
    # Determine which keys are considered translatable for this node type
    translatable_keys_for_node: Set[str] = set(TRANSLATABLE_KEYS)
    # For auto-routing pages, never translate any 'title' fields (admin-only),
    # but ensure 'loading' may be translated via labels handling below.
    if template_id in {"invitecheck", "watchlistcheck", "hostcheck"}:
        if "title" in translatable_keys_for_node:
            translatable_keys_for_node.remove("title")

    def translate_conf_value(value: Any, parent_key: Optional[str] = None, ancestor_translatable: bool = False) -> Any:
        # Only translate user-visible strings. Never translate any 'data_name'.
        if isinstance(value, dict):
            out: Dict[str, Any] = {}
            for k, v in value.items():
                if k == "data_name" or k == "name":
                    out[k] = v
                    continue
                current_translatable = ancestor_translatable or (k in translatable_keys_for_node)
                if isinstance(v, str) and (k in translatable_keys_for_node or ancestor_translatable):
                    out[k] = translate_string(v)
                else:
                    out[k] = translate_conf_value(v, k, current_translatable)
            return out
        if isinstance(value, list):
            # Translate strings inside lists if any ancestor key is marked translatable
            new_list: List[Any] = []
            for item in value:
                if isinstance(item, dict):
                    new_list.append(translate_conf_value(item, parent_key, ancestor_translatable))
                elif isinstance(item, str) and ancestor_translatable:
                    new_list.append(translate_string(item))
                else:
                    new_list.append(item)
            return new_list
        if isinstance(value, str) and ancestor_translatable and (parent_key not in {"data_name", "name"}):
            return translate_string(value)
        return value

    # Translate labels
    label_keys_to_translate: Set[str] = set(TRANSLATABLE_KEYS)
    # Special case: for invitecheck and watchlistcheck, do NOT translate 'title';
    # instead translate 'loading'.
    if template_id in {"invitecheck", "watchlistcheck", "hostcheck"}:
        label_keys_to_translate.add("loading")
        if "title" in label_keys_to_translate:
            label_keys_to_translate.remove("title")
    labels = node.get("labels")
    if isinstance(labels, dict):
        for key in list(labels.keys()):
            if key in label_keys_to_translate and isinstance(labels.get(key), str):
                labels[key] = translate_string(labels[key])

    # Translate configuration strings (only user-visible; exclude identifiers like data_name)
    conf = node.get("configuration")
    if isinstance(conf, dict):
        node["configuration"] = translate_conf_value(conf)

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
        nxt_val = node.get("next")
        if isinstance(nxt_val, dict):
            nxt = nxt_val
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


def graft_clone_subgraph(
    inner: Dict[str, Any],
    template_start_id: str,
    existing_start_id: str,
) -> Dict[str, str]:
    """Deprecated grafting: kept for backward compatibility but currently unused."""
    new_start_id, mapping = clone_subgraph(inner, template_start_id)
    return mapping


def adjust_cloned_branch_for_end_thanks_and_crumbs(
    inner: Dict[str, Any],
    mapping: Dict[str, str],
    template_start_id: str,
    language_label: str,
    existing_end_thanks_id: Optional[str],
) -> None:
    """Adjust a cloned branch:
    - Set crumb on the start node to the language label
    - If a visitreason exists in the cloned branch, set crumbs of its targets to the reason titles
    - If existing_end_thanks_id is provided, redirect default edges that point to a cloned thanks to reuse it,
      and delete the unused cloned thanks nodes.
    - Preserve next=null for thanks pages.
    """
    nodes = inner.get("nodes", {})
    # Set crumb on start
    start_new_id = mapping.get(str(template_start_id))
    if start_new_id and start_new_id in nodes:
        nodes[start_new_id]["crumb"] = language_label

    # Build reverse map new_id -> old_id
    new_to_old = {v: k for k, v in mapping.items()}

    # Prepare English (template) defaults map and thanks info
    english_nodes: Dict[str, Dict[str, Any]] = inner.get("nodes", {})
    english_default_map: Dict[str, Optional[str]] = {}
    english_is_thanks: Set[str] = set()
    for old_id in mapping.keys():
        en_node = english_nodes.get(str(old_id))
        if not isinstance(en_node, dict):
            continue
        if str(en_node.get("template_id")) == "thanks":
            english_is_thanks.add(str(old_id))
        nxt = en_node.get("next") or {}
        english_default_map[str(old_id)] = nxt.get("default") if isinstance(nxt, dict) else None

    # Force-correct defaults in cloned branch based on English defaults; always point to the cloned counterpart
    for old_id, new_id in mapping.items():
        new_node = nodes.get(new_id)
        if not isinstance(new_node, dict):
            continue
        if str(new_node.get("template_id")) == "thanks":
            new_node["next"] = None
            continue
        en_default = english_default_map.get(str(old_id))
        # Ensure next is a dict structure
        nxt_val = new_node.get("next")
        nxt_obj: Dict[str, Any] = nxt_val if isinstance(nxt_val, dict) else {"conditions": [], "default": None}
        if en_default is not None:
            en_default_str = str(en_default)
            mapped_new = mapping.get(en_default_str)
            if mapped_new is not None:
                nxt_obj["default"] = str(mapped_new)
        # Avoid cycles: don't let a node default to itself or to the start node
        if str(nxt_obj.get("default")) in {str(new_id), mapping.get(str(template_start_id), ""), str(template_start_id)}:
            # If cycle detected and English default was a thanks, map to its cloned counterpart if available
            if en_default is not None and str(en_default) in mapping:
                nxt_obj["default"] = str(mapping[str(en_default)])
        new_node["next"] = nxt_obj

    # Collect cloned thanks ids
    cloned_thanks_ids: Set[str] = set()
    for old_id, new_id in mapping.items():
        node = nodes.get(new_id)
        if not node:
            continue
        if str(node.get("template_id")) == "thanks":
            cloned_thanks_ids.add(new_id)
        # Preserve null next for thanks
        if str(node.get("template_id")) == "thanks":
            if node.get("next") is None:
                pass
            elif isinstance(node.get("next"), dict) and not node.get("next"):  # empty dict
                node["next"] = None

    # Set crumbs for targets of visitreason in cloned branch
    for old_id, new_id in mapping.items():
        node = nodes.get(new_id)
        if not node:
            continue
        if str(node.get("template_id")) == "visitreason":
            # Set the visitreason node's crumb to the language label
            node["crumb"] = language_label
            conf = node.get("configuration") or {}
            reasons = conf.get("reasons") or []
            rid_to_title = {int(r.get("id")): str(r.get("title")) for r in reasons if r.get("id") is not None}
            nxt = node.get("next") or {}
            for cond in (nxt.get("conditions") or []):
                rid = int(cond.get("rval", -1))
                target = cond.get("result")
                if target is not None and str(target) in nodes:
                    nodes[str(target)]["crumb"] = rid_to_title.get(rid, nodes[str(target)].get("crumb"))
            # Propagate crumb down the branch from each condition target (default and conditions)
            def propagate_crumb(from_id: Any, crumb_value: str) -> None:
                stack: List[str] = [str(from_id)]
                seen: Set[str] = set()
                mapped_values: Set[str] = set(mapping.values())
                while stack:
                    nid = stack.pop()
                    if nid in seen or nid not in nodes or nid not in mapped_values:
                        continue
                    seen.add(nid)
                    n = nodes[nid]
                    if not isinstance(n, dict):
                        continue
                    # Do not change visitreason nodes' crumb here; they will set their children
                    if str(n.get("template_id")) != "visitreason":
                        if "crumb" not in n or not n.get("crumb"):
                            n["crumb"] = crumb_value
                    nxt2 = n.get("next") or {}
                    for c in (nxt2.get("conditions") or []):
                        if c.get("result") is not None:
                            stack.append(str(c.get("result")))
                    if nxt2.get("default") is not None:
                        stack.append(str(nxt2.get("default")))

            # Propagate for each condition target
            for cond in (nxt.get("conditions") or []):
                target = cond.get("result")
                rid = int(cond.get("rval", -1))
                if target is not None:
                    propagate_crumb(target, rid_to_title.get(rid, language_label))
            # And also for default if it exists, keep current language label
            if (node.get("next") or {}).get("default") is not None:
                propagate_crumb((node.get("next") or {}).get("default"), language_label)

    # No redirection to existing end thanks; cloned branch retains its own thanks topology


def ensure_meta_lang(node: Dict[str, Any], iso: str) -> None:
    # No-op: do not inject meta into nodes
    return


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
        # Fallback: use the language page default if present
        nxt = language_node.get("next") or {}
        default_result = nxt.get("default")
        if default_result is not None:
            logging.warning(
                "No explicit start for '%s'; using page default %s",
                source_label,
                default_result,
            )
            label_to_start[source_label] = str(default_result)
        else:
            logging.error(
                "Language routing conditions: %s",
                (nxt.get("conditions") or []),
            )
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
            # Graft template English path onto existing start node; do not edit conditions
            logging.info("Grafting template for '%s' at start node %s", label, existing_start)
            # Capture existing end thanks reachable from this language path (default)
            # by walking from current start and taking default chain to a thanks, if present
            existing_end_thanks_id: Optional[str] = None
            try:
                order, _ = walk_subgraph(inner, str(existing_start))
                for nid in reversed(order):
                    node = inner["nodes"][nid]
                    if str(node.get("template_id")) == "thanks":
                        existing_end_thanks_id = nid
                        break
            except Exception:  # noqa: BLE001
                pass

            new_start, mapping = clone_subgraph(inner, english_start)
            # Repoint the language page's condition result remains unchanged (existing_start),
            # so copy the newly cloned start onto that existing id and shift mapping to reflect
            if str(existing_start) in inner["nodes"] and new_start in inner["nodes"]:
                # Replace existing start node content with the cloned start content
                existing_node = inner["nodes"][str(existing_start)]
                cloned_start_node = inner["nodes"][new_start]
                preserved_id = existing_node["id"]
                for k in list(existing_node.keys()):
                    if k != "id":
                        del existing_node[k]
                for k, v in cloned_start_node.items():
                    if k == "id":
                        continue
                    existing_node[k] = v
                existing_node["id"] = preserved_id
                # Remove the cloned start node and update mapping to point to existing_start
                try:
                    del inner["nodes"][new_start]
                except Exception:  # noqa: BLE001
                    pass
                mapping = {k: (str(existing_start) if v == new_start else v) for k, v in mapping.items()}

            # Adjust thanks reuse and crumbs
            adjust_cloned_branch_for_end_thanks_and_crumbs(
                inner=inner,
                mapping=mapping,
                template_start_id=english_start,
                language_label=label,
                existing_end_thanks_id=existing_end_thanks_id,
            )
            translated_here = 0
            for old_id, new_id in list(mapping.items()):
                if new_id not in inner["nodes"]:
                    continue
                node = inner["nodes"][new_id]
                translated_here += translate_node_strings(node, target_iso, translator)
            summary.nodes_created += max(0, len(mapping) - 1)  # excluding the grafted start
            summary.nodes_updated += 1  # start node overwritten
            summary.strings_translated += translated_here
        else:
            # No explicit start for this language; do not modify language choice page
            logging.info("No existing path for '%s'; skipping per requirements (no condition edits)", label)
            summary.warnings.append(f"Skipping '{label}' because no start node is wired on language page")

        # Validate
        new_start_for_label = _get_language_result(language_node, label, id_to_label, label_to_id)
        if new_start_for_label is not None and str(new_start_for_label) in inner.get("nodes", {}):
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
        if cond.get("lval") == "reason_id" and int(cond.get("rval", -1)) == int(choice_id):
            res = cond.get("result")
            return str(res) if res is not None else None
    return None


def _wire_language_condition(*args: Any, **kwargs: Any) -> None:  # deprecated: do nothing
    # Intentionally left blank per requirement: do not edit language choice page conditions.
    return


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
# Validation and diff utilities
# =============================


def validate_inner(inner: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    nodes = inner.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        errors.append("Inner body missing or empty 'nodes'")
        return errors, warnings

    start_id = str(inner.get("starting_node_id") or "")
    if start_id and start_id not in nodes:
        errors.append(f"starting_node_id '{start_id}' not found in nodes")

    for nid, node in nodes.items():
        node_id = str(node.get("id"))
        if node_id != str(nid):
            warnings.append(f"Node key/id mismatch: key={nid} id={node_id}")
        nxt = node.get("next") or {}
        conditions = nxt.get("conditions") or []
        for cond in conditions:
            res = cond.get("result")
            if res is not None and str(res) not in nodes:
                errors.append(f"Node {nid} condition result -> {res} not found")
        def_res = nxt.get("default")
        if def_res is not None and str(def_res) not in nodes:
            errors.append(f"Node {nid} default -> {def_res} not found")
        # Enforce rule: only template_id == 'thanks' may have next == null
        template_id = str(node.get("template_id") or "")
        if template_id != "thanks":
            # For non-thanks pages, next.default must not be None
            if nxt is None or nxt.get("default") is None:
                errors.append(f"Node {nid} (template_id={template_id}) must have non-null next.default")

    # Language page existence is important but not fatal for general validation
    try:
        _ = find_language_page(inner)
    except Exception as exc:  # noqa: BLE001
        warnings.append(str(exc))

    return errors, warnings


def diff_summary(old_inner: Dict[str, Any], new_inner: Dict[str, Any]) -> Dict[str, Any]:
    old_nodes = set((old_inner.get("nodes") or {}).keys())
    new_nodes = set((new_inner.get("nodes") or {}).keys())
    added = sorted(new_nodes - old_nodes)
    removed = sorted(old_nodes - new_nodes)
    return {
        "total_nodes": len(new_nodes),
        "added_nodes": added,
        "removed_nodes": removed,
    }


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
    # Prefer CLI --token, then SIS_API_KEY (recommended), then SIS_API_TOKEN (legacy)
    token_env = os.getenv("SIS_API_KEY") or os.getenv("SIS_API_TOKEN") or API_TOKEN
    api_token = str(args.token or token_env)
    source_label = str(args.source_label or os.getenv("SIS_SOURCE_LANGUAGE_LABEL") or SOURCE_LANGUAGE_LABEL)

    lm = LANGUAGE_MAP.copy()
    env_lm = os.getenv("SIS_LANGUAGE_MAP")
    if env_lm:
        lm.update(parse_language_map_env(env_lm))

    dry_run = not bool(args.write) if args.write is not None else (
        (os.getenv("SIS_DRY_RUN") or str(DRY_RUN)).lower() in {"1", "true", "yes"}
    )
    translator = str(args.translator or os.getenv("SIS_TRANSLATOR") or TRANSLATOR)
    translator_api_key = str(args.translator_api_key or os.getenv("SIS_TRANSLATOR_API_KEY") or TRANSLATOR_API_KEY)
    translator_endpoint = str(args.translator_endpoint or os.getenv("SIS_TRANSLATOR_ENDPOINT") or TRANSLATOR_ENDPOINT)
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
        translator_endpoint=translator_endpoint,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="SIS Workflow language translator")
    p.add_argument("--workflow", "-w", help="Workflow ID", required=False)
    p.add_argument("--write", action="store_true", help="Perform PUT (default is dry-run)")
    p.add_argument("--token", help="API bearer token", required=False)
    p.add_argument("--source-label", help="Source language label (e.g., English)", required=False)
    p.add_argument("--log-level", help="Logging level (DEBUG, INFO, ...)", required=False)
    p.add_argument("--translator", choices=["mock", "deepl", "google", "libretranslate"], help="Translation provider", required=False)
    p.add_argument("--translator-api-key", help="Translator API key for the chosen provider", required=False)
    p.add_argument("--translator-endpoint", help="Translator endpoint URL (e.g., LibreTranslate instance)", required=False)
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
        raise ValueError(
            "API token is required. Provide via --token, or set SIS_API_KEY (preferred) or SIS_API_TOKEN in a .env file."
        )

    if (not config.workflow_id or str(config.workflow_id).strip() == "") and not args.self_test:  # type: ignore[name-defined]
        raise ValueError(
            "Workflow ID is required. Provide via --workflow or set SIS_WORKFLOW_ID in a .env file."
        )

    if args.self_test:  # type: ignore[name-defined]
        workflow, inner = sample_workflow_and_inner()
        logging.info("Loaded sample workflow for self-test")
    else:
        client = SISClient(config.api_base_url, config.api_token)
        logging.info("Fetching workflow %s", redact(config.workflow_id))
        workflow = client.get_workflow(config.workflow_id)
        inner = parse_inner_body(workflow)
        original_inner = json.loads(json.dumps(inner))

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
        # Validate before PUT
        errors, warns = validate_inner(inner)
        for w in warns:
            logging.warning("Validation warning: %s", w)
        if errors:
            for e in errors:
                logging.error("Validation error: %s", e)
            logging.error("Aborting PUT due to validation errors.")
            return

        # Diff summary
        try:
            old_inner = original_inner  # type: ignore[name-defined]
        except NameError:
            old_inner = inner
        diff = diff_summary(old_inner, inner)
        logging.info("Diff summary: added=%s removed=%s total_nodes=%s", diff.get("added_nodes"), diff.get("removed_nodes"), diff.get("total_nodes"))

        # Serialize and PUT
        # Normalize IDs and link targets to strings for consistency
        try:
            nmap = inner.get("nodes") or {}
            new_nodes: Dict[str, Any] = {}
            for k, node in list(nmap.items()):
                sk = str(k)
                if isinstance(node, dict):
                    node["id"] = str(node.get("id"))
                    nxt = node.get("next")
                    if isinstance(nxt, dict):
                        for cond in (nxt.get("conditions") or []):
                            if cond.get("result") is not None:
                                cond["result"] = str(cond["result"])
                        if nxt.get("default") is not None:
                            nxt["default"] = str(nxt["default"])
                        node["next"] = nxt
                new_nodes[sk] = node
            inner["nodes"] = new_nodes
        except Exception as _:
            pass

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
    # Load .env before reading env variables into config
    load_env_file(".env")
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

