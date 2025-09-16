## SIS Workflow Translator

This tool upgrades a Sign In Solutions (tractionguest.com) workflow or registration experience to support translated language paths. It finds the language choice page in a workflow/experience, uses the English branch as a template, and creates or updates parallel paths for each existing non-English language choice. In dry-run mode, it shows what would change; in write mode, it updates the workflow/experience via the API.

### Video walkthrough:
https://signinsolutions.wistia.com/medias/omesvlrctn

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

## Two ways to run this tool

### 🌐 Option 1: Web App (Recommended for most users)

**Easiest way - just double-click and go!**

The web app provides a simple point-and-click interface where you can:
- Choose between Kiosk workflows or Registration experiences
- Enter your configuration details in a form
- See live logs as the translation runs
- View results in a clean summary

**Quick start:**
1. Download this project folder to your computer
2. **Mac users:** Double-click `Launch_Mac.command` (the app will set itself up and open in your browser)
3. **Windows users:** Double-click `Launch_Windows.bat` (the app will set itself up and open in your browser)
4. When the app opens in your browser, fill in your Workflow ID and API token
5. Click "Run Translation" to start

**Manual launch (if needed):**
```bash
# First time setup
bash src/activate.sh

# Launch the web app
source .venv/bin/activate
streamlit run src/streamlit_app.py
```

### 💻 Option 2: Command Line Script (For advanced users)

**For users comfortable with terminal commands**

Run the Python script directly with command-line arguments for more control and automation.

**Quick start:**
```bash
# First time setup
bash src/activate.sh

# Edit .env file with your settings
# Then run:
python3 src/sis_translate_workflow.py --write
# For registration experiences:
python3 src/sis_translate_workflow.py --write --experience-type registration
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

1) Run the one-time setup script
```bash
bash src/activate.sh
```
This creates a local virtual environment, installs dependencies, and prepares your `.env` file.

2) Create and configure your `.env` file:

If the setup script didn't create a `.env` file for you, create one manually:
```bash
# Create the .env file in the project root
touch .env  # On Mac/Linux
# or on Windows: type nul > .env
```

Then open `.env` in any text editor and add at least:
```
SIS_API_KEY=your_api_token_here
SIS_WORKFLOW_ID=123456
```
Notes:
- `SIS_API_KEY` is preferred. `SIS_API_TOKEN` also works for backward compatibility.
- The script auto-loads `.env` every run; you do not need to export variables manually.

### Command line script detailed usage

3) Try a safe self-test
```bash
python3 src/sis_translate_workflow.py --self-test
```

4) Run a dry run against your workflow (no changes made)
```bash
python3 src/sis_translate_workflow.py
```

5) Apply changes
```bash
python3 src/sis_translate_workflow.py --write
```

### Alternative setup (manual)

If you prefer manual steps:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
touch .env  # Create .env file manually, then edit it
```

### Get your API token

Generate a Bearer token through the developer portal: https://us.tractionguest.com/dev_portal/login
If your account is not in the "US" data centre, change the subdomain to your account tenant.

### Dry run example

Dry-run is safe and does not modify anything. It prints a summary of changes.
```bash
python3 src/sis_translate_workflow.py
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
python3 src/sis_translate_workflow.py --write
```

The script will PUT the updated `workflow.body` back to the same endpoint.

### Options you might need

- **Use a CLI token instead of .env**
```bash
python3 src/sis_translate_workflow.py --token "<YOUR_BEARER_TOKEN>"
```

- **Specify workflow ID via command line** (alternative to .env)
```bash
python3 src/sis_translate_workflow.py --workflow 123456
```

- **Choose experience type** (kiosk workflows or registration experiences)
```bash
python3 src/sis_translate_workflow.py --experience-type registration
```

- **Run self-test** (safe demo with sample data)
```bash
python3 src/sis_translate_workflow.py --self-test
```

- **Change the source (template) language label** (default `English`)
```bash
python3 src/sis_translate_workflow.py --source-label "English"
```

- **Choose logging level** (default `INFO`)
```bash
python3 src/sis_translate_workflow.py --log-level DEBUG
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
bash src/run_local_libretranslate.sh start           # Uses Docker if available, otherwise pip
python3 src/sis_translate_workflow.py --translator libretranslate
```

Notes:
- Auto-detection checks `http://localhost:5000/languages` and `http://127.0.0.1:5000/languages`.
- You can explicitly set the endpoint if desired:
```bash
python3 src/sis_translate_workflow.py --translator libretranslate \
  --translator-endpoint http://localhost:5000/translate
```
- Stop the local service with:
```bash
bash src/run_local_libretranslate.sh stop
```

### Auto-start/stop local LibreTranslate

If you run with `--translator libretranslate` and no `--translator-endpoint` is provided, the script will:
- First try to connect to `http://localhost:5000/translate`.
- If not found, it will attempt to auto-start a local LibreTranslate using `src/run_local_libretranslate.sh` (Docker if available, otherwise pip) and will auto-stop it when the script exits.

To disable auto-start behavior, explicitly set a public endpoint via `--translator-endpoint` or `SIS_TRANSLATOR_ENDPOINT`.

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
python3 src/sis_translate_workflow.py --self-test
```

### Troubleshooting

#### Common Launch Issues

- **Mac: "Permission denied" when double-clicking Launch_Mac.command**
  - Right-click the file → "Open With" → "Terminal" 
  - Or open Terminal, navigate to the folder, and run: `chmod +x Launch_Mac.command && ./Launch_Mac.command`

- **Windows: Script won't run or opens briefly then closes**
  - The Windows launcher has a known issue - it references `activate.bat` but the file is `activate.sh`
  - Use the manual setup instead: Open Command Prompt in the project folder and run `bash src/activate.sh`

- **Browser doesn't open automatically**
  - Manually open your web browser and go to: `http://localhost:8501`
  - If that doesn't work, try: `http://127.0.0.1:8501`

#### Setup Issues

- `ModuleNotFoundError: No module named 'requests'`
  - Run `bash src/activate.sh` again, or inside the venv run `pip install -r src/requirements.txt`.

- **Python not found or wrong version**
  - Make sure you have Python 3.10+ installed
  - On Mac: `python3 --version` should show 3.10 or higher
  - On Windows: Check if Python is added to your system PATH

- **Virtual environment issues**
  - Delete the `.venv` folder and run `bash src/activate.sh` again
  - Make sure you're in the correct project directory

#### API and Configuration Issues

- `API unauthorized (401)` or `forbidden (403)`
  - Check the token value and permissions. Ensure `.env` has `SIS_API_KEY` (or pass `--token`).
  - Verify your API token is still valid in the SIS developer portal

- **Workflow ID not found**
  - Double-check the workflow ID number
  - Make sure you have access to that workflow in your SIS account

- `Language page not found`
  - The workflow must contain a page with `configuration.data_name == "language"` and choices.
  - For registration experiences, it should have `flex_field: "language"`

#### Translation Issues

- **Script runs but nothing changes**
  - Only existing non-English choices are processed. The script does not add new language choices.
  - Make sure your workflow already has non-English language options set up

- **LibreTranslate connection issues**
  - Port 5000 might be in use by another application
  - Try a different port: `bash src/run_local_libretranslate.sh start 5001`
  - Check if Docker is running (if using Docker mode)

- **Translation quality issues**
  - Try different translation providers (Google, DeepL vs LibreTranslate)
  - Check if the source language is correctly identified

#### Web Interface Issues

- **Streamlit app won't start**
  - Make sure no other app is using port 8501
  - Check the terminal/command prompt for error messages
  - Try restarting the launcher script

- **App is slow or unresponsive**
  - Large workflows with many translations can take time
  - Check the console output for progress updates
  - Consider using a more powerful translation service (Google/DeepL vs LibreTranslate)

### Security notes

- Your API token is never printed. Logs redact sensitive values.
- Use `.env` (not shell history) to store secrets. `.env` is ignored by git.

### Full command examples

Dry run with .env values:
```bash
python3 src/sis_translate_workflow.py
```

Write changes with CLI token and verbose logs:
```bash
python3 src/sis_translate_workflow.py --token "<TOKEN>" --write --log-level DEBUG
```
