# Nimbus Insight – Deployment Guide

## Overview
Nimbus Insight is a production-grade, containerised web platform that transforms the `process_tickets.py` CLI into a dark-themed, futuristic SPA with real-time KPI dashboards, background CSV processing, and a full job history viewer.

## Prerequisites
- Docker & Docker Compose installed
- An Anthropic API key (or Ollama running locally)

## Quick Start

### 1. Create `.env` file
```bash
cp .env.example .env
```
Edit `.env` and set:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxx
# For local Ollama instead of Claude:
# USE_OLLAMA=true
# OLLAMA_BASE_URL=http://host.docker.internal:11434
# OLLAMA_MODEL=llama3
```

### 2. Build & Run
```bash
docker-compose up --build
```

### 3. Open the App
Navigate to **http://localhost:8000** in your browser.

## Usage
1. Click the **Upload & History** tab
2. Drag-and-drop (or click to browse) your CSV file
3. Click **Process Now** – the job runs in the background
4. Watch status update live every 2 seconds
5. Click **View** to read the full report in a modal
6. Click **Download** to save the `.txt` report
7. Switch to **KPI Dashboard** to see aggregated charts update

## CSV Column Requirements
Your CSV must contain at minimum:
- `ticket_id`
- `message`

Optional (gracefully handled if missing): `customer_name`, `email`, `date`, `channel`, `subject`

## Project Structure
```
nimbus_insight/
├── main.py           # FastAPI app & all endpoints
├── processor.py      # Classification pipeline (refactored from CLI)
├── models.py         # SQLAlchemy ORM models
├── database.py       # DB engine & session setup
├── static/
│   └── index.html    # Futuristic SPA (embedded CSS/JS + Chart.js)
├── data/             # SQLite DB persisted here (volume mounted)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README_DEPLOY.md
```

## Environment Variables
| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | *(required)* | Claude API key |
| `USE_OLLAMA` | `false` | Switch to local Ollama |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Ollama model name |
| `LOG_LEVEL` | `info` | Uvicorn log level |

## Stopping
```bash
docker-compose down
```
The SQLite DB in `./data/` persists between restarts.

## Cost Estimate
- ~40 valid tickets ≈ $0.05 per run (Claude 3.5 Sonnet)
- 10× volume (400 tickets) ≈ $0.50 per run
- Spam pre-filter saves ~5–10% of API calls
- 24h cache prevents re-billing on re-uploads of the same CSV
