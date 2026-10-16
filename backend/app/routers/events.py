from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query
from ..database import engine
from ..security import get_current_user, require_role
from ..schemas import CampusEventCreate
from typing import Any
from datetime import datetime, timedelta, timezone
from sqlalchemy import text

router = APIRouter()


def _campus_local_datetime(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    # Browser datetime-local values are campus local time; Alliance is in India.
    return value.replace(tzinfo=timezone(timedelta(hours=5, minutes=30)))

@router.get("/events")
def list_campus_events(
    limit: int = Query(default=200, ge=1, le=500),
    _current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, list[dict[str, Any]]]:
    with engine.connect() as connection:
        rows = connection.execute(text("""
            SELECT id, title, description, event_type, start_at, end_at, location
            FROM campus_events
            ORDER BY start_at, id
            LIMIT :limit
        """), {"limit": limit}).mappings().all()
    return {"events": [dict(row) for row in rows]}

@router.post("/admin/events", status_code=201)
def create_campus_event(
    event: CampusEventCreate,
    admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    start_at = _campus_local_datetime(event.start_at)
    end_at = _campus_local_datetime(event.end_at)
    if end_at and end_at < start_at:
        raise HTTPException(status_code=422, detail="The end time must be after the start time.")
    with engine.begin() as connection:
        row = connection.execute(text("""
            INSERT INTO campus_events (title, description, event_type, start_at, end_at, location, created_by)
            VALUES (:title, :description, :event_type, :start_at, :end_at, :location, :created_by)
            RETURNING id, title, description, event_type, start_at, end_at, location
        """), {
            "title": event.title.strip(),
            "description": event.description.strip() if event.description and event.description.strip() else None,
            "event_type": event.event_type,
            "start_at": start_at,
            "end_at": end_at,
            "location": event.location.strip() if event.location and event.location.strip() else None,
            "created_by": admin["id"],
        }).mappings().one()
    return dict(row)

@router.patch("/admin/events/{event_id}")
def update_campus_event(
    event_id: int,
    event: CampusEventCreate,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, Any]:
    start_at = _campus_local_datetime(event.start_at)
    end_at = _campus_local_datetime(event.end_at)
    if end_at and end_at < start_at:
        raise HTTPException(status_code=422, detail="The end time must be after the start time.")
    with engine.begin() as connection:
        row = connection.execute(text("""
            UPDATE campus_events
            SET title = :title, description = :description, event_type = :event_type,
                start_at = :start_at, end_at = :end_at, location = :location, updated_at = NOW()
            WHERE id = :event_id
            RETURNING id, title, description, event_type, start_at, end_at, location
        """), {
            "event_id": event_id,
            "title": event.title.strip(),
            "description": event.description.strip() if event.description and event.description.strip() else None,
            "event_type": event.event_type,
            "start_at": start_at,
            "end_at": end_at,
            "location": event.location.strip() if event.location and event.location.strip() else None,
        }).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return dict(row)

@router.delete("/admin/events/{event_id}")
def delete_campus_event(
    event_id: int,
    _admin: dict[str, Any] = Depends(require_role("admin")),
) -> dict[str, str]:
    with engine.begin() as connection:
        deleted_id = connection.execute(text("""
            DELETE FROM campus_events WHERE id = :event_id RETURNING id
        """), {"event_id": event_id}).scalar_one_or_none()
    if deleted_id is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return {"message": "Event removed."}
