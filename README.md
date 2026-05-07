# IITGN Library Chatbot

This repository now contains two versions of the project:

- `app.py`: the original Streamlit prototype left behind in the handoff.
- `server.py`: the new deployable backend API with a lightweight web client.

## What the new version does

- Serves a chatbot over HTTP using FastAPI.
- Answers from `FAQs.csv` even without an external LLM key.
- Loads real library metadata for e-journal access and IITGN repository/publication discovery.
- Optionally uses an OpenAI-compatible LLM API, such as Groq, to generate cleaner answers from retrieved FAQ context.
- Stores chat logs and feedback in SQLite instead of loose CSV files.
- Ships with a standalone web UI that can also be embedded in the library website.

## Project structure

- `server.py`: application entrypoint.
- `library_chatbot/`: backend package for config, retrieval, storage, and chat logic.
- `static/`: built-in web client.
- `tests/`: basic unit tests for the retrieval layer.
- `app.py` and `Report.py`: legacy prototype files kept for reference.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn server:app --reload
```

Open `http://127.0.0.1:8000`.

Or use the helper script:

```bash
./start_demo.sh
```

For installation on a library/server machine, see [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md).

## Configuration

Copy `.env.example` to `.env` and update values as needed.

- `FAQ_PATH`: path to the knowledge base CSV.
- `CATALOG_PATHS`: optional comma-separated paths to catalog/resource metadata CSV or XLSX files.
- `WEBSITE_KNOWLEDGE_PATH`: curated library website/service knowledge CSV, defaulting to `data/library_website_knowledge.csv`.
- `DATABASE_PATH`: SQLite database location.
- `ALLOWED_ORIGINS`: comma-separated CORS origins for website integration.
- `LLM_API_KEY`: optional, enables LLM-generated answers.
- `LLM_MODEL`: configurable model name.
- `LLM_API_URL`: OpenAI-compatible chat completions endpoint. The default points to Groq.
- `CATALOG_LIVE_SEARCH_ENABLED`: enables live Koha catalogue lookup for book/title availability questions.
- `CATALOG_BASE_URL`: Koha catalogue base URL. Defaults to `https://catalog.iitgn.ac.in`.
- `CATALOG_TIMEOUT_SECONDS`: timeout for live catalogue requests.
- `GROQ_API_KEY`, `GROQ_MODEL`, and `GROQ_API_URL`: backwards-compatible aliases.

## Website integration options

### Option 1: Standalone deployment

Deploy this app on its own domain or subdomain, for example:

- `https://chat.library.iitgn.ac.in`

This is the recommended first production step. The chatbot can be tested,
updated, and monitored independently before the library website embeds it.

### Option 2: Embed inside the library website

Embed the standalone UI with an iframe:

```html
<iframe
  src="https://chat.library.iitgn.ac.in"
  title="IITGN Library Chatbot"
  style="width:100%;height:720px;border:0;border-radius:16px;"
></iframe>
```

For a floating website widget, the library web administrator can add this
single script near the end of the site template, just before `</body>`:

```html
<script
  src="https://chat.library.iitgn.ac.in/static/widget.js"
  data-chat-url="https://chat.library.iitgn.ac.in/"
></script>
```

Until the live website team grants access, test the same integration locally:

```bash
uvicorn server:app --reload
```

Open `http://127.0.0.1:8000/widget-demo`.

### Option 3: Use only the API

The library website can call:

- `POST /api/chat`
- `POST /api/feedback`
- `GET /api/health`

This is the cleaner option if their web team wants to build the frontend themselves.

## API example

```bash
curl -X POST http://127.0.0.1:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"What are the library hours?"}'
```

## Live catalogue lookup

The chatbot can optionally query the public Koha catalogue for book/title
availability questions such as:

- `is Sipser in the library?`
- `do you have Introduction to Algorithms?`
- `find books by Cormen`

This is not browser automation. The backend calls Koha search URLs, parses
public catalogue/detail pages, and returns structured results with catalogue
links. If the match is weak or the catalogue cannot be reached, the chatbot
redirects the user to the exact catalogue search page instead of guessing.

For a more robust production integration, ask the library/IT team whether Koha
REST API, SRU, Z39.50, or regular MARC/CSV exports are available.
The current public catalogue may show bot-check pages to automated HTTP
clients, so API access, SRU, exports, or server allowlisting is the clean
production path for reliable live availability lookup.

## Metadata ingestion

The production backend uses one internal document model for both FAQs and catalog records. This keeps sample data replaceable: update `CATALOG_PATHS` when the real export arrives instead of changing chatbot logic.

The current configured metadata files are:

- `data/ejournals_2026-04-20.xlsx`: e-journal/e-resource access records, including title, ISSN, provider, collection, URL, active status, subject, and coverage.
- `data/iitgn_publications_2026-04-24.csv`: IITGN repository/publication records, including title, author, DOI, repository URL, type, subject, publisher, date, and department/collection.
- `data/library_website_knowledge.csv`: curated service and navigation facts from the library website, including contacts, hours, off-campus access, ILL, DDS, purchase suggestions, e-resource policy, and research support.

Loaded records are typed as:

- `faq`: library policy and FAQ answers.
- `ejournal`: journal/e-resource access and coverage metadata.
- `repository_publication`: IITGN publications, theses, articles, conference papers, patents, and repository items.
- `library_website`: library website/service pages for front-desk style routing and user guidance.
- `catalog`: generic catalog/resource rows if another metadata export is added later.

Catalog CSVs may use common column names such as:

- `title`, `book_title`, or `name`
- `author`, `authors`, `creator`, or `contributors`
- `isbn`, `isbn10`, or `isbn13`
- `subject`, `subjects`, `keywords`, or `category`
- `call_number`, `callno`, `classification`, or `shelfmark`
- `location`, `shelf_location`, `library_location`, or `branch`
- `availability`, `status`, or `item_status`
- `description`, `summary`, `abstract`, or `notes`
- `source`, `source_url`, `url`, or `catalog_url`

`data/sample_catalog.csv` is only a placeholder for development. Replace it with the real metadata path in `.env` when available.

Before running with a new metadata export, validate that the chatbot can parse it:

```bash
python3 -m library_chatbot.ingest \
  --faq FAQs.csv \
  --catalog data/ejournals_2026-04-20.xlsx \
  --catalog data/iitgn_publications_2026-04-24.csv
```

The validator prints detected headers, recognized fields, usable record count, skipped rows, source type counts, and sample parsed records.

For routine updates, use:

```bash
scripts/update_knowledge.sh \
  --catalog /path/to/new_ejournals.xlsx \
  --catalog /path/to/new_publications.csv
```

To update FAQs as well:

```bash
scripts/update_knowledge.sh \
  --faq /path/to/FAQs.csv \
  --catalog /path/to/new_ejournals.xlsx
```

The script copies new resource files into `data/imports/`, validates them, and prints the `.env` values to use. Restart the chatbot service after a successful update.

## Tests

```bash
python3 -m unittest discover -s tests
```

## Docker

```bash
docker build -t iitgn-library-chatbot .
docker run -p 8000:8000 --env-file .env iitgn-library-chatbot
```

## Notes

- The old Streamlit prototype is still present, but the deployable path should now be based on `server.py`.
- `Report.py` still belongs to the earlier analytics approach and should be modernized separately if the library wants production reporting from SQLite.
