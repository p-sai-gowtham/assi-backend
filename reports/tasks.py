from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from analytics.services import widget_data
from reports.models import ReportRun, ReportSchedule


def advance_next_run(schedule: ReportSchedule):
    if schedule.frequency == ReportSchedule.Frequency.DAILY:
        return schedule.next_run_at + timedelta(days=1)
    if schedule.frequency == ReportSchedule.Frequency.WEEKLY:
        return schedule.next_run_at + timedelta(days=7)
    return schedule.next_run_at + timedelta(days=30)


def render_report_html(run: ReportRun) -> str:
    schedule = run.schedule
    dashboard = schedule.dashboard
    generated_at = timezone.now()
    widget_rows = []
    for widget in dashboard.widgets.all():
        data = widget_data(schedule.organization, widget.type, widget.query_config, widget.query_config.get("range", "7d"))
        kpi = data.get("kpi") if isinstance(data, dict) else None
        value = kpi.get("value") if isinstance(kpi, dict) else ""
        widget_rows.append(
            f"<tr><td>{widget.title}</td><td>{widget.type}</td><td>{value}</td><td>{widget.query_config}</td></tr>"
        )
    rows = "\n".join(widget_rows) or "<tr><td colspan='4'>No widgets configured.</td></tr>"
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>{dashboard.name} report</title>
  <style>
    body {{ font-family: Arial, sans-serif; color: #111827; margin: 32px; }}
    h1 {{ margin-bottom: 4px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 24px; }}
    th, td {{ border: 1px solid #E5E7EB; padding: 8px; text-align: left; }}
    th {{ background: #F3F4F6; }}
  </style>
</head>
<body>
  <h1>{dashboard.name}</h1>
  <p>{dashboard.description}</p>
  <p>Generated at {generated_at.isoformat()}</p>
  <table>
    <thead><tr><th>Widget</th><th>Type</th><th>Value</th><th>Query</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>"""


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def generate_report_run(self, run_id: str) -> None:
    run = ReportRun.objects.select_related("schedule", "schedule__dashboard").get(id=run_id)
    run.status = "processing"
    run.save(update_fields=["status", "updated_at"])
    try:
        reports_dir = settings.MEDIA_ROOT / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        file_path = reports_dir / f"{run.id}.html"
        file_path.write_text(render_report_html(run), encoding="utf-8")
        run.status = "completed"
        run.generated_at = timezone.now()
        run.file_url = f"{settings.MEDIA_URL}reports/{run.id}.html"
        run.error_message = ""
        run.save(update_fields=["status", "generated_at", "file_url", "error_message", "updated_at"])
        recipients = [email for email in run.schedule.recipients if isinstance(email, str) and email]
        if recipients:
            try:
                send_mail(
                    subject=f"Scheduled report: {run.schedule.dashboard.name}",
                    message=f"Your report is ready: {run.file_url}",
                    from_email="reports@nexus.local",
                    recipient_list=recipients,
                    fail_silently=False,
                )
            except Exception as exc:
                run.error_message = f"Report generated, email delivery failed: {exc}"
                run.save(update_fields=["error_message", "updated_at"])
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        run.save(update_fields=["status", "error_message", "updated_at"])
        raise


@shared_task
def process_due_report_schedules() -> int:
    now = timezone.now()
    created = 0
    schedules = ReportSchedule.objects.select_related("dashboard", "organization").filter(
        enabled=True,
        next_run_at__lte=now,
    )
    for schedule in schedules:
        with transaction.atomic():
            schedule = ReportSchedule.objects.select_for_update().get(id=schedule.id)
            if not schedule.enabled or schedule.next_run_at > now:
                continue
            run = ReportRun.objects.create(schedule=schedule, status="queued")
            schedule.next_run_at = advance_next_run(schedule)
            schedule.save(update_fields=["next_run_at", "updated_at"])
            transaction.on_commit(lambda run_id=str(run.id): generate_report_run.delay(run_id))
            created += 1
    return created
