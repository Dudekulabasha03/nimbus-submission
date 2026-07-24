# Nimbus Retail Ticket Processor

This project provides an automated pipeline for parsing, classifying, and reporting on customer support tickets from CSV exports. It leverages the Claude API to classify tickets by category, urgency, and to flag them for escalation, while providing cost-saving measures such as caching and pre-filtering obvious spam.

## Features
- **Robust CSV Parsing**: Handles extra columns cleanly (using `csv.DictReader.get()`) and gracefully processes dirty data, logging skipped rows.
- **Date Normalization**: Implements deterministic parsing for common dates, with a fallback to `dateutil`, preventing misinterpretation of international dates like "05/01/2026".
- **Prompt Injection Defense**: Uses structured `<ticket_content>` XML tags in the API request to strictly separate system instructions from potentially malicious user-provided text.
- **Local Model Support**: Supports bypassing Anthropic API to classify locally via Ollama using the `.env` configuration.
- **Caching Mechanism**: Keys results using a hash of the ticket ID, subject, and message, alongside a 24-hour timestamp to automatically invalidate stale data, preventing double-billing on repeated identical tickets.
- **Spam Pre-filtering**: Catches and tags common spam keywords locally, avoiding API calls entirely for obvious junk.
- **Resilient API Calls**: Retries automatically with exponential backoff on API errors, handles missing JSON elegantly by falling back to safe default categorizations.
- **Report Generation**: Aggregates ticket data dynamically using Python and produces a readable markdown report summarizing categories, urgency levels, and escalations.

## Setup Instructions

1. **Install Python 3.8+**
2. **Create a Virtual Environment (Recommended)**
   ```bash
   python -m venv venv
   # On Windows:
   venv\Scripts\activate
   # On macOS/Linux:
   source venv/bin/activate
   ```
3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure Environment Variables**
   Rename `.env.example` to `.env` and fill in your configuration:
   ```bash
   cp .env.example .env
   ```
   Open `.env` and add your Anthropic API key or set `USE_OLLAMA=true` if using a local model.

## Usage

Run the script by passing the path to the CSV file:
```bash
python process_tickets.py path/to/tickets.csv
```

### Dry-Run Mode
To see what would be sent to the API without actually calling it (and without spending credits), use the `--dry-run` flag:
```bash
python process_tickets.py path/to/tickets.csv --dry-run
```

## Output
The script will print the daily summary to the console and save it to `report.md` in the current directory.
