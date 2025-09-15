import io
import logging
from types import SimpleNamespace
from contextlib import redirect_stdout

import streamlit as st

import sis_translate_workflow as stw


class StreamlitLogHandler(logging.Handler):
    def __init__(self, placeholder: "st.delta_generator.DeltaGenerator", level: int = logging.INFO) -> None:
        super().__init__(level)
        self.placeholder = placeholder
        self._lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001
            msg = record.getMessage()
        self._lines.append(msg)
        # Limit displayed log lines to keep UI responsive
        max_lines = 1000
        if len(self._lines) > max_lines:
            self._lines = self._lines[-max_lines:]
        self.placeholder.code("\n".join(self._lines))


def run_pipeline_with_logs(cfg: stw.Config) -> str:
    # Ensure the module-level 'args' used by the pipeline exists
    stw.args = SimpleNamespace(self_test=False)  # type: ignore[attr-defined]

    # Configure logging to stream to Streamlit
    log_placeholder = st.empty()
    handler = StreamlitLogHandler(log_placeholder)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    # Clear existing handlers to avoid duplicate logs
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
    return stdout_buffer.getvalue()


def main() -> None:
    st.set_page_config(page_title="SIS Workflow Translator", layout="centered")
    st.title("SIS Workflow Translator")
    st.caption("Make language branches match the English template and translate text.")

    with st.form("config_form"):
        st.subheader("Configuration")
        workflow_id = st.text_input("Workflow ID", value=str(stw.WORKFLOW_ID or ""))
        api_token = st.text_input("API token", type="password")

        translator = st.selectbox(
            "Translator",
            options=["mock", "libretranslate", "google", "deepl"],
            index=["mock", "libretranslate", "google", "deepl"].index(stw.TRANSLATOR)
            if stw.TRANSLATOR in {"mock", "libretranslate", "google", "deepl"}
            else 0,
            help="Choose the translation provider. 'mock' is safe for testing.",
        )
        translator_api_key = st.text_input("Translator API key", type="password")

        apply_changes = st.checkbox("Apply changes (PUT to API)", value=False, help="Unchecked = dry run only")

        with st.expander("Advanced options", expanded=False):
            api_base_url = st.text_input("API base URL", value=stw.API_BASE_URL)
            log_level = st.selectbox("Log level", options=["DEBUG", "INFO", "WARNING", "ERROR"], index=["DEBUG", "INFO", "WARNING", "ERROR"].index(stw.LOG_LEVEL if stw.LOG_LEVEL in {"DEBUG", "INFO", "WARNING", "ERROR"} else "INFO"))
            translator_endpoint = st.text_input("Translator endpoint (optional)", value=stw.TRANSLATOR_ENDPOINT)

        submitted = st.form_submit_button("Run")

    if submitted:
        if not api_token and not stw.args.__dict__.get("self_test", False):  # type: ignore[attr-defined]
            st.error("API token is required.")
            return
        if not workflow_id and not stw.args.__dict__.get("self_test", False):  # type: ignore[attr-defined]
            st.error("Workflow ID is required.")
            return

        cfg = stw.Config(
            workflow_id=str(workflow_id),
            api_base_url=str(api_base_url or stw.API_BASE_URL),
            api_token=str(api_token),
            source_language_label=stw.SOURCE_LANGUAGE_LABEL,
            language_map=stw.LANGUAGE_MAP,
            dry_run=not bool(apply_changes),
            translator=str(translator),
            translator_api_key=str(translator_api_key or ""),
            translator_endpoint=str(translator_endpoint or ""),
            rate_limit_qps=stw.RATE_LIMIT_QPS,
            log_level=str(log_level or "INFO"),
        )

        try:
            with st.status("Running...", expanded=True):
                summary_text = run_pipeline_with_logs(cfg)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Error: {exc}")
            return

        if summary_text.strip():
            st.subheader("Summary")
            st.code(summary_text.strip())
        st.success("Run complete.")


if __name__ == "__main__":
    main()


