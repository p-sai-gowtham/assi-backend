from __future__ import annotations

import csv
from datetime import datetime, timezone

from celery import shared_task
from pydantic import ValidationError

from ingestion.models import Event, IngestionJob
from ingestion.schemas import EventPayload
from ingestion.services import create_event


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def normalize_event(self, event_id: str) -> None:
    Event.objects.filter(id=event_id).update()


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def process_csv_job(self, job_id: str) -> None:
    job = IngestionJob.objects.select_related("organization").get(id=job_id)
    job.status = IngestionJob.Status.PROCESSING
    job.save(update_fields=["status", "updated_at"])
    try:
        with job.file.open("r") as handle:
            reader = csv.DictReader(handle)
            rows = list(reader)
            if reader.fieldnames is None:
                raise ValueError("CSV header row is required.")
        job.total_rows = len(rows)
        row_errors = []
        job.save(update_fields=["total_rows", "updated_at"])
        reserved = {"event_type", "type", "external_user_id", "userId", "user_id", "message", "timestamp", "ip_address", "ip"}
        for row_number, row in enumerate(rows, start=2):
            try:
                properties = {key: value for key, value in row.items() if key and key not in reserved and value not in (None, "")}
                properties.setdefault("source", row.get("source") or "csv")
                payload = EventPayload.model_validate(
                    {
                        "event_type": row.get("event_type") or row.get("type") or "pageview",
                        "external_user_id": row.get("external_user_id") or row.get("userId") or row.get("user_id") or "",
                        "message": row.get("message") or "",
                        "timestamp": row.get("timestamp") or datetime.now(timezone.utc).isoformat(),
                        "properties": properties,
                        "ip_address": row.get("ip_address") or row.get("ip"),
                    }
                )
                create_event(organization=job.organization, payload=payload)
                job.processed_rows += 1
            except (ValidationError, ValueError) as exc:
                job.failed_rows += 1
                row_errors.append({"row": row_number, "error": str(exc)[:500]})
            if (job.processed_rows + job.failed_rows) % 25 == 0:
                job.row_errors = row_errors[:100]
                job.save(update_fields=["processed_rows", "failed_rows", "row_errors", "updated_at"])
        job.row_errors = row_errors[:100]
        job.status = IngestionJob.Status.FAILED if job.processed_rows == 0 and job.failed_rows else IngestionJob.Status.COMPLETED
        job.error_message = "All rows failed validation." if job.status == IngestionJob.Status.FAILED else ""
        job.save(update_fields=["status", "processed_rows", "failed_rows", "row_errors", "error_message", "updated_at"])
    except Exception as exc:
        job.status = IngestionJob.Status.FAILED
        job.error_message = str(exc)
        job.save(update_fields=["status", "error_message", "updated_at"])
        raise
