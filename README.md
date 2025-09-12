## SIS Workflow Translator

This tool upgrades a Sign In Solutions (tractionguest.com) workflow to support translated language paths. It finds the language choice page in a workflow, uses the English branch as a template, and creates or updates parallel paths for each existing non-English language choice. In dry-run mode, it shows what would change; in write mode, it updates the workflow via the API.

### What you need

- **Python 3.10+**
- An SIS **API token** (Bearer token)
- Internet access to `https://us.tractionguest.com`

### Quick start (easiest)

1) Run the one-time setup script
```bash
bash activate.sh
```
This creates a local virtual environment, installs dependencies, and prepares your `.env` file.

2) Open `.env` and fill in at least:
```
SIS_API_KEY=your_api_token_here
SIS_WORKFLOW_ID=123456
```
Notes:
- `SIS_API_KEY` is preferred. `SIS_API_TOKEN` also works for backward compatibility.
- The script auto-loads `.env` every run; you do not need to export variables manually.

3) Try a safe self-test
```bash
python3 sis_translate_workflow.py --self-test
```

4) Run a dry run against your workflow (no changes made)
```bash
python3 sis_translate_workflow.py
```

5) Apply changes
```bash
python3 sis_translate_workflow.py --write
```

### Alternative setup (manual)

If you prefer manual steps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit .env
```

### Get your API token

Generate a Bearer token through the developer portal: https://us.tractionguest.com/dev_portal/login
If your account is not in the "US" data centre, change the subdomain to your account tenant.

### Dry run example

Dry-run is safe and does not modify anything. It prints a summary of changes.
```bash
python3 sis_translate_workflow.py
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
python3 sis_translate_workflow.py --write
```

The script will PUT the updated `workflow.body` back to the same endpoint.

### Options you might need

- **Use a CLI token instead of .env**
```bash
python3 sis_translate_workflow.py --token "<YOUR_BEARER_TOKEN>"
```

- **Change the source (template) language label** (default `English`)
```bash
python3 sis_translate_workflow.py --source-label "English"
```

- **Choose logging level** (default `INFO`)
```bash
python3 sis_translate_workflow.py --log-level DEBUG
```

- **Configure language codes** (optional). Map choice labels to ISO codes (in `.env` or CLI env):
```bash
SIS_LANGUAGE_MAP='{"English":"en","Spanish":"es","French":"fr"}'
```
If not set, common languages are inferred by label.

- **Select a translator**
  - Default is `mock` (safe testing): it wraps text like `[es] Hello`.
  - To use Google Translate, DeepL, or LibreTranslate, set provider and credentials in `.env`:
```bash
SIS_TRANSLATOR=google
SIS_TRANSLATOR_API_KEY="<GOOGLE_API_KEY>"
# or
SIS_TRANSLATOR=deepl
SIS_TRANSLATOR_API_KEY="<DEEPL_API_KEY>"
# or
SIS_TRANSLATOR=libretranslate
# Optional if your instance requires it:
SIS_TRANSLATOR_API_KEY="<LIBRETRANSLATE_API_KEY>"
# Optional custom endpoint (defaults to https://libretranslate.com/translate):
SIS_TRANSLATOR_ENDPOINT="https://your-libretranslate.example.com/translate"
```

When using `libretranslate`, the script will send requests to the endpoint above with JSON payloads. If `SIS_TRANSLATOR_ENDPOINT` is not set, it uses `https://libretranslate.com/translate`. If your instance requires an API key, set `SIS_TRANSLATOR_API_KEY`.

### Use LibreTranslate locally for free (no account, no billing)

Run a local LibreTranslate service and the script will auto-detect it.

```bash
bash run_local_libretranslate.sh start           # Uses Docker if available, otherwise pip
python3 sis_translate_workflow.py --translator libretranslate
```

Notes:
- Auto-detection checks `http://localhost:5000/languages` and `http://127.0.0.1:5000/languages`.
- You can explicitly set the endpoint if desired:
```bash
python3 sis_translate_workflow.py --translator libretranslate \
  --translator-endpoint http://localhost:5000/translate
```
- Stop the local service with:
```bash
bash run_local_libretranslate.sh stop
```

- **Rate limiting** (requests per second; default 8):
```bash
SIS_RATE_LIMIT_QPS=6
```

- **Force dry-run or write via env**
```bash
SIS_DRY_RUN=true  # or false
```

### What the script changes

- Finds the language choice page where `configuration.data_name == "language"`.
- Uses the English branch as the template.
- For each existing non-English choice: creates or updates a parallel path so it matches the English structure and translates user-facing text.
- Does not modify the language choice page conditions; only branches for languages that already have a start node are processed.
- Only `workflow.body` is changed on PUT.

### Safe testing without the API

Run the built-in self-test:
```bash
python3 sis_translate_workflow.py --self-test
```

### Troubleshooting

- `ModuleNotFoundError: No module named 'requests'`
  - Run `bash activate.sh` again, or inside the venv run `pip install -r requirements.txt`.

- `API unauthorized (401)` or `forbidden (403)`
  - Check the token value and permissions. Ensure `.env` has `SIS_API_KEY` (or pass `--token`).

- `Language page not found`
  - The workflow must contain a page with `configuration.data_name == "language"` and choices.

- Script runs but nothing changes
  - Only existing non-English choices are processed. The script does not add new language choices.

### Security notes

- Your API token is never printed. Logs redact sensitive values.
- Use `.env` (not shell history) to store secrets. `.env` is ignored by git.

### Full command examples

Dry run with .env values:
```bash
python3 sis_translate_workflow.py
```

Write changes with CLI token and verbose logs:
```bash
python3 sis_translate_workflow.py --token "<TOKEN>" --write --log-level DEBUG
```

