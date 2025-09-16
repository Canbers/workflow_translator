
import base64
import io
import logging
import json
import re
from types import SimpleNamespace
from contextlib import redirect_stdout
from typing import Dict, List, Tuple, Any, Optional

import streamlit as st

import sis_translate_workflow as stw


# -----------------------------
# Logging -> Streamlit console
# -----------------------------
class StreamlitLogHandler(logging.Handler):
    """
    Route Python logging to a live "console" area in the Streamlit app,
    and opportunistically extract translation pairs from log lines for a
    lightweight preview.
    """
    def __init__(self, placeholder: "st.delta_generator.DeltaGenerator", level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self.placeholder = placeholder
        self._lines: List[str] = []
        self.translations: List[Dict[str, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001
            msg = record.getMessage()
        self._lines.append(msg)

        # Extract translation pairs from messages like:
        # "Translating 'Hello' to 'Hola' [es]"
        self._extract_translations(msg)

        # Keep a sensible cap so the UI stays snappy
        max_lines = 1200
        if len(self._lines) > max_lines:
            self._lines = self._lines[-max_lines:]
        self.placeholder.code("\n".join(self._lines))

    def _extract_translations(self, msg: str) -> None:
        pattern = r"Translating\\s+'([^']+)'\\s+to\\s+'([^']+)'"
        m = re.search(pattern, msg)
        if m:
            original, translated = m.groups()
            self.translations.append({
                "original": original,
                "translated": translated,
                "language": self._extract_language_from_msg(msg),
            })

    def _extract_language_from_msg(self, msg: str) -> str:
        m = re.search(r"\\[([a-z]{2})\\]", msg)
        return m.group(1) if m else "unknown"


def run_pipeline_with_logs(cfg: stw.Config, log_placeholder) -> Tuple[str, List[Dict[str, str]]]:
    # Ensure the module-level 'args' used by the pipeline exists
    stw.args = SimpleNamespace(self_test=False)  # type: ignore[attr-defined]

    # Configure logging to stream to Streamlit
    handler = StreamlitLogHandler(log_placeholder)
    formatter = logging.Formatter("%(asctime)s  %(levelname)s  %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, cfg.log_level.upper(), logging.INFO))

    # Capture stdout prints (e.g., summary)
    stdout_buffer = io.StringIO()
    with redirect_stdout(stdout_buffer):
        try:
            stw.process_workflow_pipeline(cfg)
        except Exception as exc:  # noqa: BLE001
            logging.error("Run failed: %s", exc)
            raise

    return stdout_buffer.getvalue(), handler.translations


# -----------------------------
# UI
# -----------------------------
def _read_logo_b64(path: str) -> Optional[str]:
    import os
    try:
        # Try the path as-is first
        if os.path.exists(path):
            with open(path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        
        # If not found, try relative to the script directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, path)
        if os.path.exists(full_path):
            with open(full_path, "rb") as f:
                return base64.b64encode(f.read()).decode()
        
        return None
    except (FileNotFoundError, OSError):
        return None


def main() -> None:
    st.set_page_config(page_title="SIS Workflow Translator", page_icon="🌐", layout="wide")

    # ---------- Global styles (glass + dark) ----------
    st.markdown(
        """
        <style>
            :root {
                --bg: #0b1220;
                --surface: rgba(255,255,255,0.06);
                --border: rgba(255,255,255,0.12);
                --text: #e6e8ef;
                --muted: #b4b7c1;
                --accent: #7c5cff;
                --accent2: #22d3ee;
                --success: #22c55e;
                --radius: 16px;
                --shadow: 0 10px 30px rgba(0,0,0,0.35);
            }
            html, body, [data-testid="stAppViewContainer"] {
                background: radial-gradient(1200px 600px at 10% -10%, rgba(124,92,255,0.20), transparent 60%),
                            radial-gradient(1000px 500px at 90% 0%, rgba(34,211,238,0.18), transparent 60%),
                            var(--bg) !important;
                color: var(--text);
            }
            .hero {
                padding: 28px 28px;
                margin-bottom: 8px;
                background: linear-gradient(180deg, rgba(124,92,255,0.25), rgba(124,92,255,0.08));
                border: 1px solid rgba(124,92,255,0.35);
                border-radius: 20px;
                box-shadow: var(--shadow);
            }
            .hero h1 { margin: 0; font-weight: 800; letter-spacing: 0.2px; }
            .hero p { margin: 4px 0 0; color: var(--muted); }
            .pill {
                display:inline-flex;align-items:center;gap:8px;
                border:1px solid var(--border);
                padding:6px 12px;border-radius:999px;font-size:12px;color:var(--muted);
                background: rgba(255,255,255,0.04);
            }
            .section-title {
                margin: 6px 0 6px 0;
                font-weight: 700;
                letter-spacing: .2px;
                font-size: 1.1rem;
            }
            .t-item{padding:12px;border-radius:12px;border:1px solid var(--border);margin:8px 0;background:rgba(255,255,255,0.03)}
            .t-original{font-weight:600;color:#c7c9d3}
            .t-arrow{opacity:.7;margin:0 6px}
            .t-lang{float:right;font-size:11px;color:var(--muted)}
            
            code, pre { border-radius: 10px !important; }
            /* Console / code blocks: wrap long lines, keep line breaks, vertical scroll after height */
            [data-testid="stCodeBlock"] pre, pre code, pre {
                white-space: pre-wrap !important;  /* respect \n and wrap long lines */
                word-break: break-word !important;
                overflow-wrap: anywhere !important;
                max-height: 420px !important;
                overflow-y: auto !important;
                overflow-x: hidden !important;
                margin: 0;
            }
            /* Add a bit of left padding to labels and expander headers */
            [data-testid="stWidgetLabel"] { padding-left: 6px !important; }
            [data-testid="stExpander"] details summary { padding-left: 6px !important; }
            /* Also add subtle inner padding to widget containers so labels don't feel squished */
            div[data-baseweb="select"], .stTextInput, .stTextArea, .stSelectbox, .stCheckbox, .stNumberInput {
                padding-left: 4px !important;
            }
    
            .block-container { padding-top: 20px; padding-bottom: 40px; }
            /* Make widgets feel more card-like */
            .stTextInput, .stSelectbox, .stTextArea, .stCheckbox, .stNumberInput {
                background: var(--surface) !important;
                border: 1px solid var(--border) !important;
                border-radius: 12px !important;
            }
            /* Hide the deploy button and related elements */
            .stDeployButton {
                display: none !important;
            }
            #MainMenu {
                visibility: hidden !important;
            }
            footer {
                visibility: hidden !important;
            }
            #stDecoration {
                display: none !important;
            }
            /* Hide the hamburger menu that contains deploy */
            [data-testid="stHeader"] {
                display: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---------- Header ----------
    logo_b64 = _read_logo_b64("SIS_logo.png")
    if logo_b64:
        logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width:42px;height:42px;border-radius:10px" />'
        header_html = f"""
        <div class="hero">
            <div style="display:flex;align-items:center;gap:14px;">
                {logo_html}
                <div>
                    <h1>SIS Workflow Translator</h1>
                    <p>Copies English branches to non-English branches and auto translates the text.</p>
                </div>
            </div>
        </div>
        """
    else:
        header_html = """
        <div class="hero">
            <div style="display:flex;align-items:center;gap:14px;">
                <div>
                    <h1>SIS Workflow Translator</h1>
                    <p>Copies English branches to non-English branches and auto translates the text.</p>
                </div>
            </div>
        </div>
        """
    
    st.markdown(header_html, unsafe_allow_html=True)

    # ---------- Layout: left config / right console ----------
    left, right = st.columns([0.58, 0.42], gap="large")

    with left:
        with st.form("config_form", border=False):
            st.markdown('<div class="section-title">SIS Configuration</div>', unsafe_allow_html=True)

            c1, c2 = st.columns(2)
            with c1:
                exp_opts = ["kiosk", "registration"]
                experience_type = st.selectbox(
                    "Experience Type",
                    options=exp_opts,
                    index=exp_opts.index(getattr(stw, "EXPERIENCE_TYPE", exp_opts[0])) if getattr(stw, "EXPERIENCE_TYPE", exp_opts[0]) in exp_opts else 0,
                    help="Pick the workflow family. They use different endpoints and data structures.",
                )
                workflow_id = st.text_input("Workflow ID", value=str(stw.WORKFLOW_ID or ""))
            with c2:
                api_token = st.text_input("API Token", type="password", help="Your SIS API bearer token")

            st.markdown('<div class="section-title">Translator</div>', unsafe_allow_html=True)

            c3, c4 = st.columns(2)
            with c3:
                t_opts = ["mock", "libretranslate", "google", "deepl"]
                translator = st.selectbox(
                    "Provider",
                    options=t_opts,
                    index=t_opts.index(getattr(stw, "TRANSLATOR", t_opts[0])) if getattr(stw, "TRANSLATOR", t_opts[0]) in t_opts else 0,
                    help="Use 'mock' for safe dry‑runs and development.",
                )
            with c4:
                translator_api_key = st.text_input("Provider API Key", type="password", help="Needed for Google / DeepL.")

            with st.expander("Advanced", expanded=False):
                c5, c6 = st.columns(2)
                with c5:
                    api_base_url = st.text_input("API Base URL", value=stw.API_BASE_URL)
                    lvl_opts = ["DEBUG", "INFO", "WARNING", "ERROR"]
                    log_level = st.selectbox(
                        "Log Level",
                        options=lvl_opts,
                        index=lvl_opts.index(getattr(stw, "LOG_LEVEL", "INFO")) if getattr(stw, "LOG_LEVEL", "INFO") in lvl_opts else 1,
                    )
                with c6:
                    translator_endpoint = st.text_input("Translator Endpoint (optional)", value=stw.TRANSLATOR_ENDPOINT)

            apply_changes = st.checkbox("Apply changes (PUT to API)", value=False, help="Unchecked = dry run only")
            submitted = st.form_submit_button("Run Translation", use_container_width=True, type="primary")

    with right:
        st.markdown('<div class="section-title">Console & Results</div>', unsafe_allow_html=True)
        console_placeholder = st.empty()

    # ---------- On submit ----------
    if submitted:
        args_ns = getattr(stw, "args", SimpleNamespace(self_test=False))
        if not api_token and not getattr(args_ns, "self_test", False):
            st.error("API token is required.")
            return
        if not workflow_id and not getattr(args_ns, "self_test", False):
            st.error("Workflow ID is required.")
            return

        cfg = stw.Config(
            workflow_id=str(workflow_id),
            api_base_url=str((api_base_url or stw.API_BASE_URL)),
            api_token=str(api_token),
            source_language_label=stw.SOURCE_LANGUAGE_LABEL,
            language_map=stw.LANGUAGE_MAP,
            dry_run=not bool(apply_changes),
            translator=str(translator),
            translator_api_key=str(translator_api_key or ""),
            translator_endpoint=str(translator_endpoint or ""),
            rate_limit_qps=stw.RATE_LIMIT_QPS,
            log_level=str(log_level or "INFO"),
            experience_type=str(experience_type),
        )

        try:
            with st.status("Running translation pipeline…", expanded=True):
                summary_text, translations = run_pipeline_with_logs(cfg, console_placeholder)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error: {exc}")
            return

        # ---- Results ----
        st.markdown("---")
        st.subheader("Translation Results")

        # Translation Preview
        if translations:
            st.markdown("**Preview** — extracted from logs for quick validation.")
            # Group by language
            by_lang: Dict[str, List[Dict[str, str]]] = {}
            for t in translations:
                by_lang.setdefault(t.get("language", "unknown"), []).append(t)

            if len(by_lang) > 1:
                tabs = st.tabs([f"{k.upper()}" for k in sorted(by_lang.keys())])
                for tab, lang in zip(tabs, sorted(by_lang.keys())):
                    with tab:
                        for t in by_lang[lang]:
                            st.markdown(
                                f"<div class='t-item'><span class='t-lang'>{lang.upper()}</span>"
                                f"<div class='t-original'>“{t['original']}”</div>"
                                f"<div class='t-arrow'>→</div>"
                                f"<div>“{t['translated']}”</div></div>",
                                unsafe_allow_html=True,
                            )
            else:
                for t in translations:
                    st.markdown(
                        f"<div class='t-item'><span class='t-lang'>{t.get('language','unknown').upper()}</span>"
                        f"<div class='t-original'>“{t['original']}”</div>"
                        f"<div class='t-arrow'>→</div>"
                        f"<div>“{t['translated']}”</div></div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("---")

        # Summary
        if summary_text.strip():
            st.markdown("**Summary**")
            st.code(summary_text.strip())

        # Final notice
        if apply_changes:
            st.success("Changes were applied to your workflow.")
        else:
            st.info("Dry run completed. Review above and enable **Apply changes** to update the workflow.")


if __name__ == "__main__":
    main()
