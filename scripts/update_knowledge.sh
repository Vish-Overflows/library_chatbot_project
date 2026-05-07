#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMPORT_DIR="$ROOT_DIR/data/imports"
FAQ_PATH="${FAQ_PATH:-$ROOT_DIR/FAQs.csv}"
WEBSITE_KNOWLEDGE_PATH="${WEBSITE_KNOWLEDGE_PATH:-$ROOT_DIR/data/library_website_knowledge.csv}"
if [[ -z "${PYTHON_BIN:-}" && -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
fi
PYTHON_BIN="${PYTHON_BIN:-python3}"

usage() {
  cat <<'USAGE'
Usage:
  scripts/update_knowledge.sh [--faq path/to/FAQs.csv] [--catalog path/to/file.csv|xlsx]...

Examples:
  scripts/update_knowledge.sh \
    --catalog ~/Downloads/new_ejournals.xlsx \
    --catalog ~/Downloads/new_publications.csv

  scripts/update_knowledge.sh \
    --faq ~/Downloads/FAQs.csv \
    --catalog ~/Downloads/new_ejournals.xlsx

What this does:
  1. Copies supplied files into data/imports/.
  2. Validates the FAQ + all configured catalog/resource files.
  3. Prints the CATALOG_PATHS value to put in .env.

After a successful update, restart the chatbot service so the new data is loaded.
USAGE
}

catalog_inputs=()
faq_input=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --faq)
      [[ $# -ge 2 ]] || { echo "ERROR: --faq needs a file path." >&2; exit 2; }
      faq_input="$2"
      shift 2
      ;;
    --catalog)
      [[ $# -ge 2 ]] || { echo "ERROR: --catalog needs a file path." >&2; exit 2; }
      catalog_inputs+=("$2")
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage
      exit 2
      ;;
  esac
done

mkdir -p "$IMPORT_DIR"

if [[ -n "$faq_input" ]]; then
  [[ -f "$faq_input" ]] || { echo "ERROR: FAQ file not found: $faq_input" >&2; exit 1; }
  cp "$faq_input" "$FAQ_PATH"
  echo "Updated FAQ file: $FAQ_PATH"
fi

catalog_paths=()

if [[ -n "${CATALOG_PATHS:-}" ]]; then
  IFS=',' read -r -a existing_paths <<< "$CATALOG_PATHS"
  for path in "${existing_paths[@]}"; do
    trimmed="$(echo "$path" | xargs)"
    [[ -n "$trimmed" ]] && catalog_paths+=("$trimmed")
  done
else
  [[ -f "$ROOT_DIR/data/ejournals_2026-04-20.xlsx" ]] && catalog_paths+=("$ROOT_DIR/data/ejournals_2026-04-20.xlsx")
  [[ -f "$ROOT_DIR/data/iitgn_publications_2026-04-24.csv" ]] && catalog_paths+=("$ROOT_DIR/data/iitgn_publications_2026-04-24.csv")
fi

for input_path in "${catalog_inputs[@]:-}"; do
  [[ -n "$input_path" ]] || continue
  [[ -f "$input_path" ]] || { echo "ERROR: catalog file not found: $input_path" >&2; exit 1; }
  extension="${input_path##*.}"
  case "${extension,,}" in
    csv|xlsx) ;;
    *) echo "ERROR: unsupported catalog file type: $input_path. Use .csv or .xlsx." >&2; exit 1 ;;
  esac
  destination="$IMPORT_DIR/$(basename "$input_path")"
  cp "$input_path" "$destination"
  catalog_paths+=("$destination")
  echo "Copied catalog/resource file: $destination"
done

if [[ -f "$WEBSITE_KNOWLEDGE_PATH" ]]; then
  catalog_paths+=("$WEBSITE_KNOWLEDGE_PATH")
fi

deduped_catalog_paths=()
for path in "${catalog_paths[@]:-}"; do
  [[ -n "$path" ]] || continue
  skip="false"
  for existing in "${deduped_catalog_paths[@]:-}"; do
    if [[ "$existing" == "$path" ]]; then
      skip="true"
      break
    fi
  done
  [[ "$skip" == "false" ]] && deduped_catalog_paths+=("$path")
done

validate_args=(--faq "$FAQ_PATH")
for path in "${deduped_catalog_paths[@]:-}"; do
  [[ -n "$path" ]] || continue
  validate_args+=(--catalog "$path")
done

echo
echo "Validating knowledge sources..."
"$PYTHON_BIN" -m library_chatbot.ingest "${validate_args[@]}"

catalog_paths_env=""
for path in "${deduped_catalog_paths[@]:-}"; do
  [[ -n "$path" ]] || continue
  if [[ -z "$catalog_paths_env" ]]; then
    catalog_paths_env="$path"
  else
    catalog_paths_env="$catalog_paths_env,$path"
  fi
done

echo
echo "Knowledge update validated successfully."
echo
echo "Put this in .env if you want these exact resource files loaded:"
echo "CATALOG_PATHS=$catalog_paths_env"
echo "FAQ_PATH=$FAQ_PATH"
echo "WEBSITE_KNOWLEDGE_PATH=$WEBSITE_KNOWLEDGE_PATH"
echo
echo "Restart the chatbot service after updating data."
echo "Example:"
echo "  sudo systemctl restart iitgn-library-chatbot"
echo "or, for a manual run:"
echo "  .venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000"
