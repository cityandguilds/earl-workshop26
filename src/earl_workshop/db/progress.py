"""Persistence helpers for attendee course completion state."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CourseProgress


def completed_page_ids(
    session: Session, *, attendee_id: int, page_ids: Iterable[str]
) -> set[str]:
    """Return completed IDs that are present in the current content set.

    Filtering by the current page IDs is deliberate: old rows are retained for stable
    persistence, but removed pages must not affect current-course percentages.
    """

    current_ids = tuple(page_ids)
    if not current_ids:
        return set()
    records = session.scalars(
        select(CourseProgress).where(
            CourseProgress.attendee_id == attendee_id,
            CourseProgress.page_id.in_(current_ids),
            CourseProgress.completed.is_(True),
        )
    )
    return {record.page_id for record in records}


def set_page_completion(
    session: Session, *, attendee_id: int, page_id: str, completed: bool
) -> CourseProgress:
    """Create or update one attendee/page completion record."""

    record = session.scalar(
        select(CourseProgress).where(
            CourseProgress.attendee_id == attendee_id,
            CourseProgress.page_id == page_id,
        )
    )
    if record is None:
        record = CourseProgress(
            attendee_id=attendee_id,
            page_id=page_id,
            completed=completed,
        )
        session.add(record)
    else:
        record.completed = completed
    session.commit()
    session.refresh(record)
    return record
