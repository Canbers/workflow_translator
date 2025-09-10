## SIS Workflow Translator

This script upgrades a Sign In Solutions (tractionguest.com) workflow to support translated language paths. It finds the language choice page in a workflow, uses the English branch as a template, and creates or updates parallel paths for each existing non-English language choice. In dry-run mode, it shows what would change; in write mode, it updates the workflow via the API.

### What you need

- **Python 3.10+** installed
- An **API token** for your Sign In Solutions account (Bearer token)
- Internet access to `https://us.tractionguest.com`

### Download the script

Ensure `sis_translate_workflow.py` is in your working directory.

### Set up Python (first time only)

1) Check Python version
```bash
python3 --version
```

2) Create and activate a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```

3) Install the required package
```bash
pip install requests
```

If your system prevents venv creation, you can install `requests` user-wide:
```bash
python3 -m pip install --user requests
```

### Get your API token

Ask your SIS admin or generate a personal access token from your account settings. You will use it as a Bearer token. Keep it secret.

### Quick start (dry run)

Dry-run is safe and does not modify anything. It prints a summary of changes.
```bash
export SIS_API_TOKEN="<YOUR_BEARER_TOKEN>"
python3 sis_translate_workflow.py --workflow 105386
```

Expected output includes a summary like:
```
Nodes created       : 4
Nodes updated       : 0
Strings translated  : 25
Languages processed : 2
Warnings            : 0
```

### Perform the update (write)

When you are satisfied with the dry run, add `--write` to save changes back to the API.
```bash
export SIS_API_TOKEN="<YOUR_BEARER_TOKEN>"
python3 sis_translate_workflow.py --workflow 105386 --write
```

The script will PUT the updated `workflow.body` back to the same endpoint.

### Options you might need

- **Use a CLI token instead of env var**
```bash
python3 sis_translate_workflow.py --workflow 105386 --token "<YOUR_BEARER_TOKEN>"
```

- **Change the source (template) language label** (default is `English`)
```bash
python3 sis_translate_workflow.py --workflow 105386 --source-label "English"
```

- **Choose logging level** (default `INFO`)
```bash
python3 sis_translate_workflow.py --workflow 105386 --log-level DEBUG
```

- **Configure language codes** (optional). Map choice labels to ISO codes:
```bash
export SIS_LANGUAGE_MAP='{"English":"en","Spanish":"es","French":"fr"}'
```
If not set, common languages are inferred by label.

- **Select a translator**
  - Default is `mock` (safe testing): it wraps text like `[es] Hello`.
  - To use Google Translate or DeepL, set provider and API key:
```bash
export SIS_TRANSLATOR=google
export SIS_TRANSLATOR_API_KEY="<GOOGLE_API_KEY>"
# or
export SIS_TRANSLATOR=deepl
export SIS_TRANSLATOR_API_KEY="<DEEPL_API_KEY>"
```

- **Rate limiting** (requests per second; default 8):
```bash
export SIS_RATE_LIMIT_QPS=6
```

- **Force dry-run or write via env**
```bash
export SIS_DRY_RUN=true  # or false
```

### What the script changes

- Finds the language choice page where `configuration.data_name == "language"`.
- Uses the English branch as the template.
- For each existing non-English choice: creates or updates a parallel path so it matches the English structure and translates user-facing text.
- Adds `meta.lang` and `meta.cloned_from` to cloned/updated nodes for idempotent re-runs.
- Only `workflow.body` is changed on PUT.

### Safe testing without the API

Run the built-in self-test:
```bash
python3 sis_translate_workflow.py --self-test
```

### Troubleshooting

- `ModuleNotFoundError: No module named 'requests'`
  - Activate your venv and run `pip install requests`, or use `python3 -m pip install --user requests`.

- `API unauthorized (401)` or `forbidden (403)`
  - Check the token value and permissions. Ensure you exported `SIS_API_TOKEN` or passed `--token`.

- `Language page not found`
  - The workflow must contain a page with `configuration.data_name == "language"` and choices.

- Script runs but nothing changes
  - Only existing non-English choices are processed. The script does not add new language choices.

### Security notes

- Your API token is never printed. Logs redact sensitive values.
- Prefer environment variables over pasting tokens into shell history.

### Full command examples

Dry run with environment token:
```bash
export SIS_API_TOKEN="<TOKEN>"
python3 sis_translate_workflow.py --workflow 105386
```

Write changes with CLI token and verbose logs:
```bash
python3 sis_translate_workflow.py --workflow 105386 --token "<TOKEN>" --write --log-level DEBUG
```

