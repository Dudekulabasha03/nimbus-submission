import hashlib
import os
import shutil
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import (
    BackgroundTasks, Depends, FastAPI, File, HTTPException,
    UploadFile, status
)
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from database import Base, engine, get_db, safe_migrate
from models import JobStatus, ProcessingJob
from processor import run_pipeline

load_dotenv()  # Ensure .env is loaded before anything else

# ── Bootstrap ─────────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)  # Create tables on startup
safe_migrate()                          # Add new columns to existing DBs

app = FastAPI(title="Nimbus Insight", version="1.0.0")

# Serve static files (SPA)
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── Background Task ────────────────────────────────────────────────────────────

def _process_job(job_id: str, csv_path: str) -> None:
    """
    Background task: run pipeline, update DB record, delete temp file.
    This function MUST NOT raise — all errors are caught and persisted.
    """
    db: Session = next(get_db())
    try:
        # Mark as PROCESSING
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            print(f"[main] Job {job_id} not found in DB — aborting.", flush=True)
            return
        job.status = JobStatus.PROCESSING
        db.commit()

        print(f"[main] Starting pipeline for job {job_id}, file: {csv_path}", flush=True)

        # Run the full pipeline — this never raises
        try:
            result = run_pipeline(csv_path)
        except Exception as pipeline_exc:
            # Absolute last-resort catch
            result = {
                "report_text": f"CRITICAL PIPELINE ERROR: {pipeline_exc}",
                "category_counts": {},
                "urgency_counts": {},
                "escalated_count": 0,
                "ticket_count": 0,
                "cache_snapshot": {},
                "error_log": str(pipeline_exc),
            }

        # Persist results
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if job:
            job.report_text      = result.get("report_text", "")
            job.category_counts  = result.get("category_counts", {})
            job.urgency_counts   = result.get("urgency_counts", {})
            job.escalated_count  = result.get("escalated_count", 0)
            job.ticket_count     = result.get("ticket_count", 0)
            job.cache_snapshot   = result.get("cache_snapshot", {})
            job.error_log        = result.get("error_log")
            # Mark COMPLETED even if there were partial errors — the report is available
            job.status = JobStatus.COMPLETED
            db.commit()
            print(f"[main] Job {job_id} completed. Tickets: {job.ticket_count}", flush=True)

    except Exception as outer_exc:
        # DB or ORM error — mark job as FAILED so user sees it
        print(f"[main] Fatal error for job {job_id}: {outer_exc}", flush=True)
        try:
            db_retry = next(get_db())
            job = db_retry.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED
                job.error_log = f"Fatal system error: {outer_exc}"
                db_retry.commit()
            db_retry.close()
        except Exception:
            pass
    finally:
        db.close()
        # Always clean up temp file
        try:
            if os.path.exists(csv_path):
                os.remove(csv_path)
        except OSError:
            pass


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def serve_spa():
    """Serve the single-page application."""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health_check():
    """Returns API health + which AI providers are configured."""
    from processor import _get_providers
    providers = [name for name, _ in _get_providers()]
    return {
        "status": "ok",
        "providers_configured": providers,
        "primary_provider": providers[0] if providers else None,
        "warning": None if providers else (
            "No AI provider configured. Add OPENAI_API_KEY or ANTHROPIC_API_KEY to .env"
        ),
    }


@app.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Accept a CSV upload. Computes MD5 hash of the file content and checks
    if an identical file has already been successfully processed.
    If yes, returns the existing job (HTTP 200, already_processed=True).
    If no, creates a PENDING job and kicks off background processing.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    # Read file contents and compute MD5 hash
    contents = await file.read()
    file_hash = hashlib.md5(contents).hexdigest()

    # ── Deduplication check ──────────────────────────────────────────────
    existing = (
        db.query(ProcessingJob)
        .filter(
            ProcessingJob.file_hash == file_hash,
            ProcessingJob.status == JobStatus.COMPLETED,
        )
        .order_by(ProcessingJob.uploaded_at.desc())
        .first()
    )
    if existing:
        return {
            "job_id": existing.id,
            "status": existing.status,
            "filename": existing.filename,
            "already_processed": True,
            "message": (
                f"This exact file was already processed on "
                f"{existing.uploaded_at.strftime('%Y-%m-%d %H:%M UTC') if existing.uploaded_at else 'unknown date'}. "
                f"Returning the existing report. Upload a different file to re-process."
            ),
        }

    # ── Save to temp file for background thread ───────────────────────────
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".csv")
    try:
        tmp.write(contents)
        tmp.flush()
        csv_path = tmp.name
    finally:
        tmp.close()

    # Quick column validation before accepting
    import csv as csv_mod
    with open(csv_path, "r", encoding="utf-8", errors="replace") as f:
        reader = csv_mod.DictReader(f)
        fieldnames_lower = {fn.strip().lower() for fn in (reader.fieldnames or [])}
        if not {"ticket_id", "message"}.issubset(fieldnames_lower):
            os.remove(csv_path)
            raise HTTPException(
                status_code=400,
                detail=(
                    f"CSV must contain 'ticket_id' and 'message' columns. "
                    f"Found: {list(reader.fieldnames or [])}"
                ),
            )

    # Create DB record
    job = ProcessingJob(
        filename=file.filename,
        file_hash=file_hash,
        uploaded_at=datetime.now(timezone.utc),
        status=JobStatus.PENDING,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Queue background processing
    background_tasks.add_task(_process_job, job.id, csv_path)

    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "already_processed": False,
        "message": "File accepted and queued for processing.",
    }


@app.get("/status/{job_id}")
def get_status(job_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Poll the current status of a processing job."""
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {
        "job_id": job.id,
        "status": job.status,
        "filename": job.filename,
        "ticket_count": job.ticket_count,
        "escalated_count": job.escalated_count,
        "report_text": job.report_text,
        "error_log": job.error_log,
        "uploaded_at": job.uploaded_at.isoformat() if job.uploaded_at else None,
    }


@app.get("/reports")
def list_reports(db: Session = Depends(get_db)):
    """Return all jobs sorted newest-first (summary only, no large report_text)."""
    jobs = db.query(ProcessingJob).order_by(ProcessingJob.uploaded_at.desc()).all()
    return [
        {
            "id": j.id,
            "filename": j.filename,
            "uploaded_at": j.uploaded_at.isoformat() if j.uploaded_at else None,
            "status": j.status,
            "ticket_count": j.ticket_count,
            "escalated_count": j.escalated_count,
        }
        for j in jobs
    ]


@app.get("/download/{job_id}")
def download_report(job_id: str, db: Session = Depends(get_db)):
    """Download the plain-text report as a file attachment."""
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job or not job.report_text:
        raise HTTPException(status_code=404, detail="Report not available.")
    filename = f"report_{job.filename.replace('.csv', '')}_{job_id[:8]}.txt"
    return PlainTextResponse(
        content=job.report_text,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/kpi")
def get_kpi(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Aggregate KPI metrics across ALL completed jobs.
    Returns zeros and empty arrays when no jobs exist.
    """
    jobs = (
        db.query(ProcessingJob)
        .filter(ProcessingJob.status == JobStatus.COMPLETED)
        .order_by(ProcessingJob.uploaded_at.asc())
        .all()
    )

    if not jobs:
        return {
            "total_tickets": 0,
            "avg_per_day": 0.0,
            "total_escalations": 0,
            "high_urgency_pct": 0.0,
            "category_distribution": {},
            "urgency_distribution": {},
            "trend_data": [],
        }

    total_tickets = sum(j.ticket_count or 0 for j in jobs)
    total_escalations = sum(j.escalated_count or 0 for j in jobs)

    # Aggregate category and urgency distributions
    agg_categories: Dict[str, int] = {}
    agg_urgency: Dict[str, int] = {}

    for j in jobs:
        for cat, count in (j.category_counts or {}).items():
            agg_categories[cat] = agg_categories.get(cat, 0) + count
        for urg, count in (j.urgency_counts or {}).items():
            agg_urgency[urg] = agg_urgency.get(urg, 0) + count

    total_high = agg_urgency.get("High", 0)
    high_urgency_pct = round((total_high / total_tickets * 100), 1) if total_tickets else 0.0

    # Trend data: group by date (use uploaded_at date as proxy)
    trend_by_date: Dict[str, Dict] = {}
    for j in jobs:
        date_key = j.uploaded_at.strftime("%Y-%m-%d") if j.uploaded_at else "Unknown"
        if date_key not in trend_by_date:
            trend_by_date[date_key] = {"date": date_key, "tickets": 0, "escalations": 0}
        trend_by_date[date_key]["tickets"] += j.ticket_count or 0
        trend_by_date[date_key]["escalations"] += j.escalated_count or 0

    trend_data = sorted(trend_by_date.values(), key=lambda x: x["date"])

    # Average daily volume
    unique_days = len(trend_by_date)
    avg_per_day = round(total_tickets / unique_days, 1) if unique_days else 0.0

    return {
        "total_tickets": total_tickets,
        "avg_per_day": avg_per_day,
        "total_escalations": total_escalations,
        "high_urgency_pct": high_urgency_pct,
        "category_distribution": agg_categories,
        "urgency_distribution": agg_urgency,
        "trend_data": trend_data,
    }
