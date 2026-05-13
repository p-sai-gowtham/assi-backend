from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import QuerySet
from django.utils import timezone

from ingestion.models import Event
from organizations.models import Organization

BLUE = "#3B82F6"
PURPLE = "#8B5CF6"
AMBER = "#F59E0B"
GREEN = "#10B981"
RED = "#EF4444"
CYAN = "#06B6D4"
PINK = "#EC4899"

RANGES = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
    "12m": timedelta(days=365),
}


def range_start(range_key: str):
    return timezone.now() - RANGES.get(range_key, RANGES["7d"])


def org_events(organization: Organization, range_key: str = "7d") -> QuerySet[Event]:
    return Event.objects.filter(organization=organization, timestamp__gte=range_start(range_key)).order_by("timestamp")


def bucket_specs(range_key: str) -> list[tuple[datetime, datetime, str]]:
    now = timezone.now()
    specs: list[tuple[datetime, datetime, str]] = []
    if range_key == "24h":
        start = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
        for index in range(24):
            bucket_start = start + timedelta(hours=index)
            specs.append((bucket_start, bucket_start + timedelta(hours=1), bucket_start.strftime("%H:00")))
        return specs
    if range_key == "90d":
        start_date = (now - timedelta(days=89)).date()
        current = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.get_current_timezone())
        for index in range(13):
            bucket_start = current + timedelta(days=index * 7)
            bucket_end = bucket_start + timedelta(days=7)
            specs.append((bucket_start, bucket_end, bucket_start.strftime("%b %d")))
        return specs
    days = 30 if range_key == "30d" else 7
    start_date = (now - timedelta(days=days - 1)).date()
    for index in range(days):
        bucket_start = datetime.combine(start_date + timedelta(days=index), datetime.min.time(), tzinfo=timezone.get_current_timezone())
        specs.append((bucket_start, bucket_start + timedelta(days=1), bucket_start.strftime("%b %d")))
    return specs


def bucket_index(event: Event, specs: list[tuple[datetime, datetime, str]]) -> int | None:
    timestamp = timezone.localtime(event.timestamp)
    for index, (start, end, _label) in enumerate(specs):
        if start <= timestamp < end:
            return index
    return None


def bucket_counts(events: list[Event], specs: list[tuple[datetime, datetime, str]]) -> list[int]:
    counts = [0 for _ in specs]
    for event in events:
        index = bucket_index(event, specs)
        if index is not None:
            counts[index] += 1
    return counts


def percent_change(current: float, previous: float) -> float:
    if previous == 0:
        return 0 if current == 0 else 100
    return round(((current - previous) / previous) * 100, 1)


def previous_period_events(organization: Organization, range_key: str, event_type: str | None = None):
    duration = RANGES.get(range_key, RANGES["7d"])
    end = range_start(range_key)
    start = end - duration
    queryset = Event.objects.filter(organization=organization, timestamp__gte=start, timestamp__lt=end)
    if event_type:
        queryset = queryset.filter(event_type=event_type)
    return queryset


def chart_dataset(label: str, data: list[float], color: str, fill: bool = False) -> dict[str, Any]:
    return {
        "label": label,
        "data": data,
        "borderColor": color,
        "backgroundColor": f"{color}22" if fill else color,
        "fill": fill,
        "tension": 0.4,
        "pointRadius": 0,
        "pointHoverRadius": 6,
        "borderRadius": 4,
        "borderSkipped": False,
    }


def overview_widgets(organization: Organization, range_key: str = "7d") -> list[dict[str, Any]]:
    cache_key = f"overview:{organization.id}:{range_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    specs = bucket_specs(range_key)
    labels = [label for _start, _end, label in specs]
    events = list(org_events(organization, range_key))
    pageviews = [event for event in events if event.event_type == "pageview"]
    purchases = [event for event in events if event.event_type == "purchase"]

    traffic_counts = bucket_counts(pageviews, specs)
    total_sessions = sum(traffic_counts)
    previous_sessions = previous_period_events(organization, range_key, "pageview").count()

    source_counts = Counter(event.properties.get("source") or "Direct" for event in pageviews)
    source_labels = [source for source, _count in source_counts.most_common(5)]
    source_values = [count for _source, count in source_counts.most_common(5)]
    source_total = sum(source_values)
    source_percentages = [round((value / source_total) * 100, 1) for value in source_values] if source_total else []

    feature_events = [event for event in events if event.event_type in {"api_call", "pageview", "export"}]
    feature_counts = Counter(event.properties.get("feature") or "Unknown" for event in feature_events)
    feature_labels = [feature for feature, _count in feature_counts.most_common(6)]
    feature_values = [count for _feature, count in feature_counts.most_common(6)]

    revenue_chart = revenue_series(organization, range_key)
    current_revenue = sum(float(event.properties.get("amount", 0) or 0) for event in purchases)
    previous_revenue = sum(
        float(event.properties.get("amount", 0) or 0)
        for event in previous_period_events(organization, range_key, "purchase")
    )

    widgets = [
        {
            "id": "traffic",
            "type": "line",
            "title": "Traffic Overview",
            "data": {
                "labels": labels,
                "datasets": [
                    chart_dataset("Sessions", traffic_counts, BLUE, fill=True)
                    | {
                        "backgroundColor": "rgba(59, 130, 246, 0.1)",
                        "pointHoverBackgroundColor": BLUE,
                        "pointHoverBorderColor": "#fff",
                        "pointHoverBorderWidth": 2,
                    }
                ],
                "kpi": {
                    "value": total_sessions,
                    "change": percent_change(total_sessions, previous_sessions),
                    "label": "Total Sessions",
                },
            },
            "position": {"x": 0, "y": 0},
        },
        {
            "id": "sources",
            "type": "doughnut",
            "title": "Traffic Sources",
            "data": {
                "labels": source_labels,
                "datasets": [
                    {
                        "data": source_percentages,
                        "backgroundColor": [BLUE, PURPLE, AMBER, GREEN, RED],
                        "borderWidth": 0,
                        "hoverOffset": 8,
                    }
                ],
                "kpi": {
                    "value": source_labels[0] if source_labels else "No data",
                    "change": source_percentages[0] if source_percentages else 0,
                    "label": "Top Source",
                },
            },
            "position": {"x": 1, "y": 0},
        },
        {
            "id": "usage",
            "type": "bar",
            "title": "Product Usage",
            "data": {
                "labels": feature_labels,
                "datasets": [
                    {
                        "label": "Events",
                        "data": feature_values,
                        "backgroundColor": BLUE,
                        "borderRadius": 4,
                        "borderSkipped": False,
                        "hoverBackgroundColor": "#60A5FA",
                    }
                ],
                "kpi": {"value": sum(feature_values), "change": 0, "label": "Feature Events"},
            },
            "position": {"x": 0, "y": 1},
        },
        {
            "id": "revenue",
            "type": "area",
            "title": "Revenue",
            "data": {
                "labels": revenue_chart["labels"],
                "datasets": revenue_chart["datasets"],
                "kpi": {
                    "value": round(current_revenue, 2),
                    "change": percent_change(current_revenue, previous_revenue),
                    "label": "Revenue",
                    "prefix": "$",
                    "isCurrency": True,
                },
            },
            "position": {"x": 1, "y": 1},
        },
    ]
    cache.set(cache_key, widgets, 60)
    return widgets


def widget_data(organization: Organization, widget_type: str, query_config: dict[str, Any] | None, range_key: str = "7d") -> dict[str, Any]:
    config = query_config or {}
    metric = config.get("metric", "traffic")
    resolved_range = config.get("range") or range_key
    overview_by_id = {widget["id"]: widget for widget in overview_widgets(organization, resolved_range)}
    if metric in overview_by_id:
        return overview_by_id[metric]["data"]

    events = list(org_events(organization, resolved_range))
    if metric == "error_rate":
        total = len(events)
        errors = sum(1 for event in events if event.event_type == "error")
        value = round((errors / total) * 100, 2) if total else 0
    elif metric == "sessions":
        value = sum(1 for event in events if event.event_type == "pageview")
    elif metric == "revenue":
        value = round(sum(float(event.properties.get("amount", 0) or 0) for event in events if event.event_type == "purchase"), 2)
    elif metric == "api_latency":
        latencies = [float(event.properties.get("latency_ms", 0) or 0) for event in events if event.event_type == "api_call"]
        value = round(sum(latencies) / len(latencies), 2) if latencies else 0
    elif metric == "new_users":
        value = sum(1 for event in events if event.event_type == "signup")
    elif metric == "purchases":
        value = sum(1 for event in events if event.event_type == "purchase")
    elif metric == "exports":
        value = sum(1 for event in events if event.event_type == "export")
    else:
        value = sum(1 for event in events if event.event_type == metric)

    if widget_type == "table":
        return {
            "rows": [
                {
                    "id": str(event.id),
                    "timestamp": event.timestamp.isoformat(),
                    "type": event.event_type,
                    "userId": event.external_user_id,
                    "message": event.message,
                    "metadata": event.properties,
                }
                for event in sorted(events, key=lambda item: item.timestamp, reverse=True)[:25]
            ]
        }

    return {
        "labels": [metric],
        "datasets": [{"label": metric.replace("_", " ").title(), "data": [value], "backgroundColor": BLUE}],
        "kpi": {"value": value, "change": 0, "label": metric.replace("_", " ").title()},
    }


def traffic_sources(organization: Organization, range_key: str = "7d") -> dict[str, Any]:
    cache_key = f"traffic_sources:{organization.id}:{range_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    specs = bucket_specs(range_key)
    events = list(org_events(organization, range_key).filter(event_type="pageview"))
    by_source: dict[str, list[Event]] = defaultdict(list)
    for event in events:
        by_source[event.properties.get("source") or "Direct"].append(event)
    rows = []
    for source, source_events in sorted(by_source.items(), key=lambda item: len(item[1]), reverse=True):
        visitors = len(source_events)
        bounces = sum(1 for event in source_events if event.properties.get("bounced"))
        conversions = sum(1 for event in source_events if event.properties.get("converted") or event.properties.get("amount"))
        rows.append(
            {
                "source": source,
                "visitors": visitors,
                "bounceRate": round((bounces / visitors) * 100, 1) if visitors else 0,
                "conversionRate": round((conversions / visitors) * 100, 1) if visitors else 0,
                "trend": bucket_counts(source_events, specs),
                "change": 0,
            }
        )
    payload = {"sources": rows}
    cache.set(cache_key, payload, 60)
    return payload


def product_usage(organization: Organization, range_key: str = "7d") -> dict[str, Any]:
    cache_key = f"product_usage:{organization.id}:{range_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    events = list(org_events(organization, range_key))
    feature_events = [event for event in events if event.event_type in {"api_call", "export", "pageview"}]
    counts = Counter(event.properties.get("feature") or "Unknown" for event in feature_events)
    colors = [BLUE, PURPLE, GREEN, AMBER, RED, CYAN, PINK]
    features = [
        {"name": name, "users": count, "change": 0, "color": colors[index % len(colors)]}
        for index, (name, count) in enumerate(counts.most_common(7))
    ]
    user_ids = {event.external_user_id for event in events if event.external_user_id}
    total_feature_catalog = 6
    payload = {
        "kpis": {
            "totalActiveUsers": len(user_ids),
            "avgSessionDuration": "0m" if not events else f"{max(1, round(len(events) / max(len(user_ids), 1)))}m",
            "featureAdoption": f"{round((len(features) / total_feature_catalog) * 100)}%" if features else "0%",
            "powerUsers": sum(1 for _user, count in Counter(event.external_user_id for event in events).items() if _user and count >= 5),
        },
        "features": features,
    }
    cache.set(cache_key, payload, 60)
    return payload


def month_specs(months: int = 12) -> list[tuple[datetime, datetime, str]]:
    now = timezone.now()
    year = now.year
    month = now.month
    starts: list[datetime] = []
    for offset in range(months - 1, -1, -1):
        m = month - offset
        y = year
        while m <= 0:
            m += 12
            y -= 1
        starts.append(datetime(y, m, 1, tzinfo=timezone.get_current_timezone()))
    specs = []
    for index, start in enumerate(starts):
        if index + 1 < len(starts):
            end = starts[index + 1]
        elif start.month == 12:
            end = datetime(start.year + 1, 1, 1, tzinfo=timezone.get_current_timezone())
        else:
            end = datetime(start.year, start.month + 1, 1, tzinfo=timezone.get_current_timezone())
        specs.append((start, end, start.strftime("%b")))
    return specs


def revenue_series(organization: Organization, range_key: str = "12m") -> dict[str, Any]:
    specs = month_specs(12) if range_key == "12m" else bucket_specs(range_key)
    revenue_values = [0.0 for _ in specs]
    expense_values = [0.0 for _ in specs]
    events = Event.objects.filter(organization=organization, timestamp__gte=specs[0][0])
    for event in events:
        index = bucket_index(event, specs)
        if index is None:
            continue
        amount = float(event.properties.get("amount", 0) or 0)
        if event.event_type == "purchase":
            revenue_values[index] += amount
        if event.properties.get("expense"):
            expense_values[index] += abs(amount)
    return {
        "labels": [label for _start, _end, label in specs],
        "datasets": [
            chart_dataset("Revenue", [round(value, 2) for value in revenue_values], GREEN, fill=True)
            | {"backgroundColor": "rgba(16, 185, 129, 0.08)"},
            chart_dataset("Expenses", [round(value, 2) for value in expense_values], "rgba(255, 255, 255, 0.2)")
            | {
                "backgroundColor": "transparent",
                "borderDash": [5, 5],
                "fill": False,
            },
        ],
    }


def currency(value: float) -> str:
    return f"${value:,.0f}" if value >= 1000 else f"${value:,.2f}"


def revenue(organization: Organization, range_key: str = "12m") -> dict[str, Any]:
    cache_key = f"revenue:{organization.id}:{range_key}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    events = list(org_events(organization, range_key))
    purchases = [event for event in events if event.event_type == "purchase"]
    revenue_total = sum(float(event.properties.get("amount", 0) or 0) for event in purchases)
    expense_total = sum(abs(float(event.properties.get("amount", 0) or 0)) for event in events if event.properties.get("expense"))
    net_income = revenue_total - expense_total
    mrr = revenue_total if range_key == "30d" else revenue_total / 12
    transactions = []
    for event in sorted(events, key=lambda item: item.timestamp, reverse=True):
        amount = float(event.properties.get("amount", 0) or 0)
        if event.event_type == "purchase" or event.properties.get("expense"):
            is_expense = bool(event.properties.get("expense"))
            transactions.append(
                {
                    "id": str(event.id),
                    "date": event.timestamp.date().isoformat(),
                    "description": event.message or ("Expense" if is_expense else "Purchase"),
                    "amount": -abs(amount) if is_expense else amount,
                    "type": "expense" if is_expense else "income",
                    "status": event.properties.get("status", "completed"),
                }
            )
    payload = {
        "chart": revenue_series(organization, range_key),
        "kpis": {
            "netIncome": currency(net_income),
            "mrr": currency(mrr),
            "arr": currency(mrr * 12),
            "activeSubscriptions": len({event.external_user_id for event in purchases if event.external_user_id}),
        },
        "transactions": transactions[:20],
    }
    cache.set(cache_key, payload, 60)
    return payload
