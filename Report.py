from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from html import escape
from pathlib import Path
import argparse
import sqlite3
import statistics


DEFAULT_DATABASE = Path("instance/chatbot.db")
DEFAULT_OUTPUT = Path("Chatbot_Report.html")


CONTRIBUTIONS = [
    (
        "Deployable FastAPI backend",
        "Moved the project from a local Streamlit prototype toward a production-style HTTP API with /api/chat, /api/feedback, /api/health, CORS support, Docker support, and a standalone static web client.",
    ),
    (
        "OpenAI-compatible LLM integration",
        "Added a provider-neutral chat completions client configured for Groq, with model/config driven by environment variables instead of hardcoded secrets.",
    ),
    (
        "Grounded answer generation",
        "The LLM receives retrieved IITGN Library context and is instructed to answer only from supplied evidence, reducing hallucinated policies, timings, links, and staff details.",
    ),
    (
        "Metadata-ready knowledge layer",
        "Reworked FAQs and catalog rows into a common KnowledgeDocument model so tomorrow's real book/library metadata file can replace sample data without rewriting chatbot logic.",
    ),
    (
        "Catalog search preparation",
        "Added support for catalog CSV fields such as title, author, ISBN, subject, call number, location, availability, description, and source URL with common column aliases.",
    ),
    (
        "Persistent chat and feedback logging",
        "Replaced loose CSV logging with SQLite tables for chat messages and user feedback, enabling more reliable analytics and reporting.",
    ),
    (
        "Automated tests",
        "Added tests for FAQ retrieval, contextual follow-up handling, catalog title search, ISBN lookup, and grounded catalog responses.",
    ),
    (
        "Deployment readiness",
        "Prepared environment-based configuration, Docker startup, local demo flow, and README instructions for cloud or institute-server deployment.",
    ),
]


NEXT_STEPS = [
    "Replace data/sample_catalog.csv with the official IITGN Library metadata export.",
    "Tune the parser after inspecting the real metadata columns and data quality.",
    "Add persistent semantic or hybrid retrieval for large-scale natural-language catalog search.",
    "Improve citation display in the web UI so users can inspect source records directly.",
    "Create an evaluation set of real student questions for answer quality and hallucination checks.",
    "Deploy to a public/staging URL and store API keys as server environment variables.",
]


def fetch_rows(database_path: Path, query: str) -> list[sqlite3.Row]:
    if not database_path.exists():
        return []

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute(query).fetchall()
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def load_chat_rows(database_path: Path) -> list[sqlite3.Row]:
    return fetch_rows(
        database_path,
        """
        SELECT session_id, user_message, assistant_message, source_url, response_mode, confidence, created_at
        FROM chat_messages
        ORDER BY id ASC
        """,
    )


def load_feedback_rows(database_path: Path) -> list[sqlite3.Row]:
    return fetch_rows(
        database_path,
        """
        SELECT session_id, helpful, comment, created_at
        FROM feedback
        ORDER BY id ASC
        """,
    )


def format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def summarize_chats(rows: list[sqlite3.Row]) -> dict[str, object]:
    response_modes = Counter(row["response_mode"] for row in rows)
    questions = Counter(row["user_message"] for row in rows)
    source_urls = Counter(row["source_url"] for row in rows if row["source_url"])
    confidences = [float(row["confidence"]) for row in rows if row["confidence"] is not None]
    timestamps = [parse_timestamp(row["created_at"]) for row in rows]
    timestamps = [timestamp for timestamp in timestamps if timestamp is not None]
    recent_cutoff = datetime.now() - timedelta(days=7)
    recent_count = sum(1 for timestamp in timestamps if timestamp >= recent_cutoff)

    return {
        "total_messages": len(rows),
        "unique_sessions": len({row["session_id"] for row in rows}),
        "response_modes": response_modes,
        "top_questions": questions.most_common(10),
        "top_sources": source_urls.most_common(8),
        "avg_confidence": statistics.mean(confidences) if confidences else 0.0,
        "recent_count": recent_count,
    }


def summarize_feedback(rows: list[sqlite3.Row]) -> dict[str, object]:
    helpful_count = sum(1 for row in rows if int(row["helpful"]) == 1)
    needs_work_count = sum(1 for row in rows if int(row["helpful"]) == 0)
    comments = [row["comment"] for row in rows if row["comment"]]
    return {
        "total_feedback": len(rows),
        "helpful_count": helpful_count,
        "needs_work_count": needs_work_count,
        "comments": comments[-10:],
    }


def render_stat_cards(summary: dict[str, object], feedback: dict[str, object]) -> str:
    total_messages = int(summary["total_messages"])
    total_feedback = int(feedback["total_feedback"])
    helpful_count = int(feedback["helpful_count"])
    helpful_rate = helpful_count / total_feedback if total_feedback else 0.0
    return f"""
      <section class="grid">
        <article><span>Total chat messages</span><strong>{total_messages}</strong></article>
        <article><span>Unique sessions</span><strong>{summary["unique_sessions"]}</strong></article>
        <article><span>Messages in last 7 days</span><strong>{summary["recent_count"]}</strong></article>
        <article><span>Average retrieval confidence</span><strong>{float(summary["avg_confidence"]):.2f}</strong></article>
        <article><span>Feedback entries</span><strong>{total_feedback}</strong></article>
        <article><span>Helpful rate</span><strong>{format_percent(helpful_rate)}</strong></article>
      </section>
    """


def render_counter(title: str, rows: list[tuple[str, int]]) -> str:
    if not rows:
        return f"<section><h2>{escape(title)}</h2><p>No data recorded yet.</p></section>"

    items = "\n".join(
        f"<tr><td>{escape(label)}</td><td>{count}</td></tr>"
        for label, count in rows
    )
    return f"""
      <section>
        <h2>{escape(title)}</h2>
        <table>
          <tbody>{items}</tbody>
        </table>
      </section>
    """


def render_response_modes(response_modes: Counter[str]) -> str:
    rows = response_modes.most_common()
    if not rows:
        return "<section><h2>Response Modes</h2><p>No chat responses recorded yet.</p></section>"

    total = sum(response_modes.values())
    items = "\n".join(
        f"<tr><td>{escape(mode)}</td><td>{count}</td><td>{format_percent(count / total)}</td></tr>"
        for mode, count in rows
    )
    return f"""
      <section>
        <h2>Response Modes</h2>
        <table>
          <thead><tr><th>Mode</th><th>Count</th><th>Share</th></tr></thead>
          <tbody>{items}</tbody>
        </table>
      </section>
    """


def render_list(title: str, items: list[str]) -> str:
    rendered = "\n".join(f"<li>{escape(item)}</li>" for item in items)
    return f"""
      <section>
        <h2>{escape(title)}</h2>
        <ul>{rendered}</ul>
      </section>
    """


def render_contributions() -> str:
    cards = "\n".join(
        f"""
        <article class="contribution">
          <h3>{escape(title)}</h3>
          <p>{escape(description)}</p>
        </article>
        """
        for title, description in CONTRIBUTIONS
    )
    return f"""
      <section>
        <h2>Contributions Above The Baseline Project</h2>
        <div class="contributions">{cards}</div>
      </section>
    """


def render_recent_examples(rows: list[sqlite3.Row]) -> str:
    recent_rows = rows[-8:]
    if not recent_rows:
        return "<section><h2>Recent Chat Examples</h2><p>No chat logs recorded yet.</p></section>"

    examples = "\n".join(
        f"""
        <article class="example">
          <p><b>User:</b> {escape(row["user_message"])}</p>
          <p><b>Assistant:</b> {escape(row["assistant_message"])}</p>
          <p class="muted">Mode: {escape(row["response_mode"])} | Confidence: {float(row["confidence"]):.2f} | Source: {escape(row["source_url"])}</p>
        </article>
        """
        for row in recent_rows
    )
    return f"""
      <section>
        <h2>Recent Chat Examples</h2>
        {examples}
      </section>
    """


def build_report(database_path: Path, output_path: Path) -> None:
    chat_rows = load_chat_rows(database_path)
    feedback_rows = load_feedback_rows(database_path)
    chat_summary = summarize_chats(chat_rows)
    feedback_summary = summarize_feedback(feedback_rows)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>IITGN Library Chatbot Progress Report</title>
  <style>
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; background: #f6f8fb; color: #17202a; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 56px; }}
    header {{ margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; font-size: 34px; }}
    h2 {{ margin: 0 0 14px; font-size: 22px; }}
    h3 {{ margin: 0 0 8px; font-size: 16px; }}
    p {{ line-height: 1.55; }}
    section {{ background: white; border: 1px solid #dbe3ec; border-radius: 10px; padding: 20px; margin-top: 18px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e8eef5; padding: 10px 8px; vertical-align: top; }}
    th {{ color: #4d5b6a; font-size: 13px; text-transform: uppercase; }}
    ul {{ margin: 0; padding-left: 20px; }}
    li {{ margin: 8px 0; line-height: 1.5; }}
    .muted {{ color: #607080; font-size: 13px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; background: transparent; border: 0; padding: 0; }}
    .grid article, .contribution, .example {{ background: white; border: 1px solid #dbe3ec; border-radius: 10px; padding: 16px; }}
    .grid span {{ display: block; color: #607080; font-size: 13px; margin-bottom: 8px; }}
    .grid strong {{ font-size: 28px; }}
    .contributions {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }}
    .contribution p, .example p {{ margin: 0 0 8px; }}
    .badge {{ display: inline-block; background: #e8f4ef; color: #0b604b; border: 1px solid #bcded2; border-radius: 999px; padding: 5px 10px; font-size: 13px; }}
    @media print {{ body {{ background: white; }} section, .grid article, .contribution, .example {{ break-inside: avoid; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <span class="badge">Generated {escape(generated_at)}</span>
      <h1>IITGN Library Chatbot Progress Report</h1>
      <p class="muted">Database: {escape(str(database_path))}</p>
      <p>This report summarizes the current deployable chatbot work, usage logs from the SQLite backend, and the concrete improvements made above the original baseline prototype.</p>
    </header>

    {render_stat_cards(chat_summary, feedback_summary)}
    {render_contributions()}
    {render_response_modes(chat_summary["response_modes"])}
    {render_counter("Top User Questions", chat_summary["top_questions"])}
    {render_counter("Top Source URLs", chat_summary["top_sources"])}
    {render_recent_examples(chat_rows)}
    {render_list("Remaining Work Before Final Submission", NEXT_STEPS)}
  </main>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the IITGN Library Chatbot progress report.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE, help="Path to chatbot SQLite database.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path to output HTML report.")
    args = parser.parse_args()

    build_report(args.database, args.output)
    print(f"Report saved to {args.output}")


if __name__ == "__main__":
    main()
