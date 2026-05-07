# IITGN Library Chatbot Deployment Guide

This guide is for installing the FastAPI version of GyanAI on a library/server machine.

## 1. Server Requirements

Recommended:

- Linux server, VM, or container host
- Python 3.11 or newer
- 1 CPU core minimum, 2+ recommended
- 1 GB RAM minimum, 2 GB+ recommended
- 500 MB disk free minimum for the current project and data
- HTTPS reverse proxy for public use, such as Nginx/Apache/Traefik

Not required:

- No JDK is required
- No Node.js is required
- No GPU is required
- No Java application server is required

Current approximate project size:

- Full repository on development machine: about 106 MB
- Current `data/` folder: about 27 MB
- Runtime SQLite logs grow over time under `instance/chatbot.db`

## 2. Network Requirements

Required for LLM answers:

- Outbound HTTPS access to the configured LLM API endpoint
- Environment variable: `LLM_API_KEY` or `GROQ_API_KEY`

Required for live Koha catalogue lookup:

- Outbound HTTPS access to `https://catalog.iitgn.ac.in`
- Important: the current public catalogue may show bot-check pages to automated HTTP clients. For reliable live catalogue lookup, library/IT should provide Koha REST API, SRU, Z39.50, MARC/CSV exports, or allowlist the chatbot server.

Required for embedding:

- The chatbot must be reachable from the library website over HTTPS.
- If using API calls from the website directly, set `ALLOWED_ORIGINS=https://library.iitgn.ac.in`.
- If using iframe/widget, the chatbot must not send `X-Frame-Options: DENY`.

## 3. Install Steps

Clone or copy the repository to the server:

```bash
git clone https://github.com/Vish-Overflows/library_chatbot_project.git
cd library_chatbot_project
```

Create a virtual environment:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

If the server cannot access the internet, prepare dependencies on another
machine with the same OS/Python family:

```bash
mkdir wheelhouse
pip download -r requirements.txt -d wheelhouse
```

Copy `wheelhouse/` to the server, then install offline:

```bash
pip install --no-index --find-links wheelhouse -r requirements.txt
```

Create the environment file:

```bash
cp .env.example .env
```

Edit `.env`:

```env
APP_NAME=IITGN Library Chatbot
FAQ_PATH=FAQs.csv
CATALOG_PATHS=data/ejournals_2026-04-20.xlsx,data/iitgn_publications_2026-04-24.csv
WEBSITE_KNOWLEDGE_PATH=data/library_website_knowledge.csv
DATABASE_PATH=instance/chatbot.db
ALLOWED_ORIGINS=https://library.iitgn.ac.in

LLM_API_KEY=replace-with-key
LLM_MODEL=llama-3.3-70b-versatile
LLM_API_URL=https://api.groq.com/openai/v1/chat/completions

CATALOG_LIVE_SEARCH_ENABLED=true
CATALOG_BASE_URL=https://catalog.iitgn.ac.in
CATALOG_TIMEOUT_SECONDS=8
```

Validate data:

```bash
python3 -m library_chatbot.ingest \
  --faq FAQs.csv \
  --catalog data/ejournals_2026-04-20.xlsx \
  --catalog data/iitgn_publications_2026-04-24.csv \
  --catalog data/library_website_knowledge.csv
```

Run the app:

```bash
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

Open:

```text
http://server-ip-or-domain:8000/
```

## 4. Optional systemd Service

Create `/etc/systemd/system/iitgn-library-chatbot.service`:

```ini
[Unit]
Description=IITGN Library Chatbot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/library_chatbot_project
EnvironmentFile=/opt/library_chatbot_project/.env
ExecStart=/opt/library_chatbot_project/.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5
User=www-data
Group=www-data

[Install]
WantedBy=multi-user.target
```

Adjust `WorkingDirectory`, `EnvironmentFile`, `User`, and `Group` for the actual server.

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable iitgn-library-chatbot
sudo systemctl start iitgn-library-chatbot
sudo systemctl status iitgn-library-chatbot
```

View logs:

```bash
sudo journalctl -u iitgn-library-chatbot -f
```

## 5. Updating Knowledge Data

Use the update script:

```bash
scripts/update_knowledge.sh \
  --catalog /path/to/new_ejournals.xlsx \
  --catalog /path/to/new_publications.csv
```

Optional FAQ update:

```bash
scripts/update_knowledge.sh \
  --faq /path/to/FAQs.csv \
  --catalog /path/to/new_ejournals.xlsx
```

The script:

1. Copies new catalog/resource files to `data/imports/`.
2. Keeps the curated website/service knowledge file loaded.
3. Validates all files using `library_chatbot.ingest`.
4. Prints the `CATALOG_PATHS`, `FAQ_PATH`, and `WEBSITE_KNOWLEDGE_PATH` values to put in `.env`.

After a successful update, restart the service:

```bash
sudo systemctl restart iitgn-library-chatbot
```

Manual restart alternative:

```bash
.venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000
```

## 6. Website Embedding

### Full iframe embed

```html
<iframe
  src="https://chat.library.iitgn.ac.in"
  title="GyanAI Library Chatbot"
  style="width:100%;height:720px;border:0;border-radius:16px;"
></iframe>
```

### Floating widget embed

Add near the end of the library website template, before `</body>`:

```html
<script
  src="https://chat.library.iitgn.ac.in/static/widget.js"
  data-chat-url="https://chat.library.iitgn.ac.in/"
></script>
```

Local demo:

```text
http://127.0.0.1:8000/widget-demo
```

## 7. Important Production Notes

- Keep `.env` private; do not commit real API keys.
- Put the app behind HTTPS before public use.
- Review retention/privacy policy for chat logs in `instance/chatbot.db`.
- If using SQLite in production, back up `instance/chatbot.db`.
- For high traffic, migrate logs to PostgreSQL or another managed database.
- Ask library/IT for Koha API/SRU/export access for reliable live catalogue availability.

## 8. Installation Day Checklist

- Confirm Python 3.11+ is available.
- Confirm server can install Python packages or provide offline `wheelhouse/`.
- Confirm outbound HTTPS to the LLM provider is allowed if LLM answers are required.
- Clone repository and create `.venv`.
- Install `requirements.txt`.
- Create and edit `.env`.
- Run `python3 -m unittest discover -s tests`.
- Run `scripts/update_knowledge.sh`.
- Start Uvicorn manually and check `/api/health`.
- Configure `systemd` or reverse proxy if IT wants a persistent service.
- Share iframe/widget snippet with the website administrator.
