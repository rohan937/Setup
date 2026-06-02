"""Timeline analytics service (M43).

Provides deterministic activity analytics for strategy audit timelines:
bucketed event counts, inactivity gap detection, staleness scoring,
and suggested checks.  No AI, no live market data, no external calls.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.services.strategy_timeline import EVIDENCE_CATEGORY_MAP, SOURCE_TYPE_CATEGORY_MAP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_ts(dt: datetime | None) -> datetime | None:
    """Return dt with UTC tzinfo; handles naive datetimes from SQLite."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _truncate_to_bucket(dt: datetime, bucket: str) -> datetime:
    dt = _normalize_ts(dt)
    if bucket == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif bucket == "week":
        monday = dt - timedelta(days=dt.weekday())
        return monday.replace(hour=0, minute=0, second=0, microsecond=0)
    elif bucket == "month":
        return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket_end(bucket_start: datetime, bucket: str) -> datetime:
    if bucket == "day":
        return bucket_start + timedelta(days=1)
    elif bucket == "week":
        return bucket_start + timedelta(weeks=1)
    elif bucket == "month":
        if bucket_start.month == 12:
            return bucket_start.replace(year=bucket_start.year + 1, month=1)
        return bucket_start.replace(month=bucket_start.month + 1)
    return bucket_start + timedelta(days=1)


def _generate_bucket_starts(start: datetime, end: datetime, bucket: str) -> list[datetime]:
    buckets: list[datetime] = []
    curr = _truncate_to_bucket(start, bucket)
    while curr <= end:
        buckets.append(curr)
        curr = _bucket_end(curr, bucket)
    return buckets


def _get_category(event_type: str | None, source_type: str | None) -> str:
    """Determine evidence category from event_type or source_type."""
    if event_type is not None and event_type in EVIDENCE_CATEGORY_MAP:
        return EVIDENCE_CATEGORY_MAP[event_type]
    if source_type is not None and source_type in SOURCE_TYPE_CATEGORY_MAP:
        return SOURCE_TYPE_CATEGORY_MAP[source_type]
    return "other"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TimelineAnalyticsBucketData:
    bucket_start: datetime
    bucket_end: datetime
    total_events: int
    event_type_counts: dict
    source_type_counts: dict
    evidence_category_counts: dict


@dataclass
class TimelineInactivityGapData:
    gap_start: datetime
    gap_end: datetime
    gap_days: int
    previous_event_title: str | None
    next_event_title: str | None


@dataclass
class StrategyTimelineAnalyticsData:
    strategy_id: uuid.UUID
    strategy_name: str
    generated_at: datetime
    bucket: str
    lookback_days: int
    total_events: int
    buckets: list  # list[TimelineAnalyticsBucketData], chronological
    active_bucket_count: int
    empty_bucket_count: int
    latest_event_at: datetime | None
    days_since_latest_event: int | None
    most_active_bucket_start: datetime | None
    most_active_bucket_event_count: int
    dominant_event_type: str | None
    dominant_evidence_category: str | None
    longest_inactivity_gap_days: int | None
    gaps: list  # list[TimelineInactivityGapData]
    staleness_status: str  # active / watch / stale / no_activity
    deterministic_summary: str
    suggested_checks: list


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------

def compute_strategy_timeline_analytics(
    strategy_id: uuid.UUID,
    db: Session,
    *,
    bucket: str = "week",
    lookback_days: int = 180,
) -> StrategyTimelineAnalyticsData:
    """Compute deterministic timeline analytics for a strategy.

    Staleness rules:
      - active      : latest event within 14 days
      - watch       : 15–45 days since latest event
      - stale       : > 45 days since latest event
      - no_activity : no events in lookback window
    """
    from app.models.strategy import Strategy
    from app.models.audit_timeline_event import AuditTimelineEvent

    if bucket not in ("day", "week", "month"):
        raise ValueError(f"Invalid bucket: {bucket!r}. Must be day, week, or month.")
    if not 1 <= lookback_days <= 730:
        raise ValueError(f"lookback_days must be 1-730, got {lookback_days}")

    strategy = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if strategy is None:
        raise ValueError(f"Strategy {strategy_id} not found")

    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=lookback_days)

    # Query events within lookback window, oldest first
    events = (
        db.query(AuditTimelineEvent)
        .filter(
            AuditTimelineEvent.strategy_id == strategy_id,
            AuditTimelineEvent.event_time >= lookback_start,
        )
        .order_by(AuditTimelineEvent.event_time.asc())
        .all()
    )

    total_events = len(events)

    # -----------------------------------------------------------------------
    # No events — return early
    # -----------------------------------------------------------------------
    if total_events == 0:
        return StrategyTimelineAnalyticsData(
            strategy_id=strategy_id,
            strategy_name=strategy.name,
            generated_at=now,
            bucket=bucket,
            lookback_days=lookback_days,
            total_events=0,
            buckets=[],
            active_bucket_count=0,
            empty_bucket_count=0,
            latest_event_at=None,
            days_since_latest_event=None,
            most_active_bucket_start=None,
            most_active_bucket_event_count=0,
            dominant_event_type=None,
            dominant_evidence_category=None,
            longest_inactivity_gap_days=None,
            gaps=[],
            staleness_status="no_activity",
            deterministic_summary=(
                f"No timeline events for {strategy.name} in the last {lookback_days} days."
            ),
            suggested_checks=["Log strategy evidence to begin tracking activity."],
        )

    # -----------------------------------------------------------------------
    # Build time buckets
    # -----------------------------------------------------------------------
    earliest_bucket_start = _truncate_to_bucket(lookback_start, bucket)
    all_bucket_starts = _generate_bucket_starts(earliest_bucket_start, now, bucket)

    # Group events into buckets by their truncated timestamp
    bucket_map: dict[datetime, list] = {}
    for ev in events:
        ev_ts = _normalize_ts(ev.event_time) or now
        bstart = _truncate_to_bucket(ev_ts, bucket)
        if bstart not in bucket_map:
            bucket_map[bstart] = []
        bucket_map[bstart].append(ev)

    # Build bucket data objects
    bucket_data: list[TimelineAnalyticsBucketData] = []
    for bstart in all_bucket_starts:
        bend = _bucket_end(bstart, bucket)
        evs = bucket_map.get(bstart, [])
        etc: dict[str, int] = {}
        stc: dict[str, int] = {}
        ecc: dict[str, int] = {}
        for e in evs:
            etc[e.event_type] = etc.get(e.event_type, 0) + 1
            st = e.source_type or "unknown"
            stc[st] = stc.get(st, 0) + 1
            cat = _get_category(e.event_type, e.source_type)
            ecc[cat] = ecc.get(cat, 0) + 1
        bucket_data.append(
            TimelineAnalyticsBucketData(
                bucket_start=bstart,
                bucket_end=bend,
                total_events=len(evs),
                event_type_counts=etc,
                source_type_counts=stc,
                evidence_category_counts=ecc,
            )
        )

    active_buckets = [b for b in bucket_data if b.total_events > 0]
    empty_buckets = [b for b in bucket_data if b.total_events == 0]

    # -----------------------------------------------------------------------
    # Latest event metrics
    # -----------------------------------------------------------------------
    latest_ev = events[-1]
    latest_ts = _normalize_ts(latest_ev.event_time)
    days_since = (now - latest_ts).days if latest_ts else None

    # -----------------------------------------------------------------------
    # Most active bucket
    # -----------------------------------------------------------------------
    most_active = max(bucket_data, key=lambda b: b.total_events, default=None)

    # -----------------------------------------------------------------------
    # Dominant event type and evidence category
    # -----------------------------------------------------------------------
    all_etc: dict[str, int] = {}
    all_ecc: dict[str, int] = {}
    for b in bucket_data:
        for k, v in b.event_type_counts.items():
            all_etc[k] = all_etc.get(k, 0) + v
        for k, v in b.evidence_category_counts.items():
            all_ecc[k] = all_ecc.get(k, 0) + v
    dominant_et = max(all_etc, key=all_etc.get) if all_etc else None
    dominant_ec = max(all_ecc, key=all_ecc.get) if all_ecc else None

    # -----------------------------------------------------------------------
    # Gap analysis (gaps >= 14 days)
    # -----------------------------------------------------------------------
    gaps: list[TimelineInactivityGapData] = []
    for i in range(len(events) - 1):
        curr_ts = _normalize_ts(events[i].event_time)
        next_ts = _normalize_ts(events[i + 1].event_time)
        if curr_ts and next_ts:
            gap_days = (next_ts - curr_ts).days
            if gap_days >= 14:
                gaps.append(
                    TimelineInactivityGapData(
                        gap_start=curr_ts,
                        gap_end=next_ts,
                        gap_days=gap_days,
                        previous_event_title=(
                            events[i].title[:100] if events[i].title else None
                        ),
                        next_event_title=(
                            events[i + 1].title[:100] if events[i + 1].title else None
                        ),
                    )
                )

    # Gap from last event to now
    if events and latest_ts:
        tail_gap = (now - latest_ts).days
        if tail_gap >= 14:
            gaps.append(
                TimelineInactivityGapData(
                    gap_start=latest_ts,
                    gap_end=now,
                    gap_days=tail_gap,
                    previous_event_title=(
                        latest_ev.title[:100] if latest_ev.title else None
                    ),
                    next_event_title=None,
                )
            )

    gaps.sort(key=lambda g: -g.gap_days)
    gaps = gaps[:10]
    longest_gap = gaps[0].gap_days if gaps else None

    # -----------------------------------------------------------------------
    # Staleness status
    # -----------------------------------------------------------------------
    if days_since is None:
        staleness = "no_activity"
    elif days_since <= 14:
        staleness = "active"
    elif days_since <= 45:
        staleness = "watch"
    else:
        staleness = "stale"

    # -----------------------------------------------------------------------
    # Deterministic summary
    # -----------------------------------------------------------------------
    summary_parts = [
        f"Strategy has {total_events} timeline event(s) over the last {lookback_days} days."
    ]
    if dominant_ec:
        summary_parts.append(f"Activity is concentrated in {dominant_ec} evidence.")
    if days_since is not None:
        summary_parts.append(
            f"Latest evidence event was {days_since} day(s) ago — strategy is {staleness}."
        )
    if longest_gap:
        summary_parts.append(f"Longest inactivity gap was {longest_gap} day(s).")
    summary_parts.append(
        "This is a deterministic activity summary, not an investment recommendation."
    )

    # -----------------------------------------------------------------------
    # Suggested checks
    # -----------------------------------------------------------------------
    checks: list[str] = []
    if staleness == "stale":
        checks.append("Log new evidence to refresh strategy activity.")
    if staleness == "watch":
        checks.append(
            "Consider logging a new run or reliability score to maintain activity."
        )
    if longest_gap and longest_gap > 60:
        checks.append(
            f"Inactivity gap of {longest_gap} days detected. Review whether strategy is still active."
        )
    if dominant_ec in ("other", None):
        checks.append(
            "Log more typed evidence (runs, audits, snapshots) for richer analytics."
        )

    return StrategyTimelineAnalyticsData(
        strategy_id=strategy_id,
        strategy_name=strategy.name,
        generated_at=now,
        bucket=bucket,
        lookback_days=lookback_days,
        total_events=total_events,
        buckets=bucket_data,
        active_bucket_count=len(active_buckets),
        empty_bucket_count=len(empty_buckets),
        latest_event_at=latest_ts,
        days_since_latest_event=days_since,
        most_active_bucket_start=(
            most_active.bucket_start
            if most_active and most_active.total_events > 0
            else None
        ),
        most_active_bucket_event_count=most_active.total_events if most_active else 0,
        dominant_event_type=dominant_et,
        dominant_evidence_category=dominant_ec,
        longest_inactivity_gap_days=longest_gap,
        gaps=gaps,
        staleness_status=staleness,
        deterministic_summary=" ".join(summary_parts),
        suggested_checks=checks,
    )
