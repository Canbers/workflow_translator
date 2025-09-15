## SIS Workflow Translator

This tool upgrades a Sign In Solutions (tractionguest.com) workflow or registration experience to support translated language paths. It finds the language choice page in a workflow/experience, uses the English branch as a template, and creates or updates parallel paths for each existing non-English language choice. In dry-run mode, it shows what would change; in write mode, it updates the workflow/experience via the API.

**Supports both:**
- **Kiosk Workflows** (traditional workflows at `/workflows/` endpoint)
- **Registration Experiences** (new registration flows at `/experiences/` endpoint)

### Key Features

- **Dual Experience Support**: Works with both kiosk workflows and registration experiences
- **Automatic Language Detection**: Finds language choice pages using different strategies for each experience type
- **Smart Translation**: Translates user-visible strings while preserving structural data
- **Registration-Specific Fields**: Handles registration-specific fields like `page_message`, `page_sub_message`, form fields, and branch values
- **Dry Run Mode**: Preview changes before applying them
- **Web Interface**: Easy-to-use web app for non-technical users
- **Command Line**: Full-featured CLI for advanced users and automation

### Experience Types

#### Kiosk Workflows
- **API Endpoint**: `/workflows/{id}`
- **Language Page**: Uses `template_id: "visitreason"` with `data_name: "language"`
- **Language Choices**: Stored in `configuration.reasons` array with `id` and `title` fields
- **Body Format**: JSON string in `workflow.body`
- **Translation Fields**: Standard workflow fields like `title`, `label`, `placeholder`, etc.

#### Registration Experiences  
- **API Endpoint**: `/experiences/{id}`
- **Language Page**: Uses `template_id: "branch"` with `flex_field: "language"`
- **Language Choices**: Stored in `configuration.branches` array with `value` field
- **Body Format**: JSON object in `experience.body`
- **Translation Fields**: Registration-specific fields like `page_message`, `page_sub_message`, `back_button_text`, `next_button_text`, form field labels, etc.

### What you need

- **Python 3.10+**
- An SIS **API token** (Bearer token)
- Internet access to `https://us.tractionguest.com`

<<<<<<< Updated upstream
### Quick start (easiest)
=======
## Two ways to run this tool

### 🌐 Option 1: Web App (Recommended for most users)

**Easiest way - just double-click and go!**

The web app provides a simple point-and-click interface where you can:
- Choose between Kiosk workflows or Registration experiences
- Enter your configuration details in a form
- See live logs as the translation runs
- View results in a clean summary

**Quick start:**
1. Download this project folder
2. **Mac users:** Double-click `Launch_SIS_Translator.command`
3. **Windows users:** Double-click `Launch_SIS_Translator.bat`
4. The app opens in your browser automatically
5. Fill in your Workflow ID and API token, then click "Run"

**Manual launch (if needed):**
```bash
# First time setup
bash activate.sh

# Launch the web app
source .venv/bin/activate
streamlit run streamlit_app.py
```

### 💻 Option 2: Command Line Script (For advanced users)

**For users comfortable with terminal commands**

Run the Python script directly with command-line arguments for more control and automation.

**Quick start:**
```bash
# First time setup
bash activate.sh

# Edit .env file with your settings
# Then run:
python3 sis_translate_workflow.py --write

# For registration experiences:
python3 sis_translate_workflow.py --write --experience-type registration
```

---

## Experience Types

### Kiosk Workflows (Default)
- **API Endpoint:** `/workflows/{id}`
- **Language Page:** Template ID `visitreason` with `data_name: "language"`
- **Data Format:** `body` is a JSON string
- **Translation Fields:** Standard workflow fields like `title`, `message`, `back`, `forward`, etc.

### Registration Experiences
- **API Endpoint:** `/experiences/{id}`
- **Language Page:** Template ID `branch` with `flex_field: "language"`
- **Data Format:** `body` is a JSON object
- **Translation Fields:** Registration-specific fields:
  - Page fields: `page_message`, `page_sub_message`, `back_button_text`, `next_button_text`
  - Form fields: `configuration.fields.title`, `configuration.fields.options[].option`
  - Branch fields: `configuration.branches[].value` (except language choices)

---

## Translation providers at a glance

Choose a provider based on your constraints. The script supports four modes:

- Mock (default)
  - Pros: Free, instant, no setup; safe for testing. Shows output like `[es] Hello` so you can see where translations would happen.
  - Cons: Not real translation; for demos/tests only.
  - Requirements: None.

- LibreTranslate (local, free)
  - Pros: Free, no account or billing. Runs entirely on your machine. Auto-starts/stops when needed.
  - Cons: First run downloads models; uses local CPU/RAM; quality varies by language pair vs commercial APIs.
  - Requirements: None if you let the script auto-start (uses Docker if installed, else a pip-based server). Optional: install Docker for the simplest one-command setup.

- Google Translate API
  - Pros: High quality for many languages; scalable and reliable.
  - Cons: Requires Google Cloud project and billing; paid per character.
  - Requirements: API key (`SIS_TRANSLATOR_API_KEY`).

- DeepL API
  - Pros: Excellent quality for supported languages; nuanced tone control.
  - Cons: Paid; supports fewer languages than Google.
  - Requirements: API key (`SIS_TRANSLATOR_API_KEY`).

Tip: Start with Mock for a dry run, then switch to LibreTranslate local for free real translations. If you need higher quality or scale, use Google or DeepL.



## Detailed setup instructions

### First time setup (both options)
>>>>>>> Stashed changes

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
  - To use Google Translate or DeepL, set provider and API key in `.env`:
```bash
SIS_TRANSLATOR=google
SIS_TRANSLATOR_API_KEY="<GOOGLE_API_KEY>"
# or
SIS_TRANSLATOR=deepl
SIS_TRANSLATOR_API_KEY="<DEEPL_API_KEY>"
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

