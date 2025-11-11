"""
Announcements management endpoints

Provides CRUD for announcements stored in the database. Simple auth: requires a
valid teacher username as `teacher_username` query parameter for create/update/delete.
"""

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, List, Optional
from datetime import datetime, date
from bson import ObjectId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def parse_date(d: Optional[str]) -> Optional[date]:
    if not d:
        return None
    try:
        return date.fromisoformat(d)
    except Exception:
        return None


def serialize_ann(ann: Dict[str, Any]) -> Dict[str, Any]:
    # Convert Mongo document to JSON-serializable dict
    out = {k: v for k, v in ann.items() if k != "_id"}
    out["id"] = str(ann.get("_id"))
    return out


@router.get("/", response_model=List[Dict[str, Any]])
def list_announcements() -> List[Dict[str, Any]]:
    anns = []
    for ann in announcements_collection.find().sort("expire_date", 1):
        anns.append(serialize_ann(ann))
    return anns


@router.get("/active", response_model=List[Dict[str, Any]])
def list_active_announcements() -> List[Dict[str, Any]]:
    today = date.today()
    active = []
    for ann in announcements_collection.find():
        start = parse_date(ann.get("start_date"))
        expire = parse_date(ann.get("expire_date"))
        if not expire:
            # skip malformed entries without expire_date
            continue

        if start and start > today:
            # not started yet
            continue

        if expire >= today:
            active.append(serialize_ann(ann))

    # sort by expire_date asc
    active.sort(key=lambda a: a.get("expire_date", ""))
    return active


@router.post("/")
def create_announcement(
    title: str = Body(...),
    message: str = Body(...),
    expire_date: str = Query(..., description="Expiration date (YYYY-MM-DD)"),
    start_date: Optional[str] = Query(None, description="Optional start date (YYYY-MM-DD)"),
    teacher_username: str = Query(..., description="Teacher username for authentication"),
):
    # Simple auth: teacher must exist
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")

    # expire_date required
    exp = parse_date(expire_date)
    if not exp:
        raise HTTPException(status_code=400, detail="Invalid expire_date format, expected YYYY-MM-DD")

    start = parse_date(start_date)
    if start and start > exp:
        raise HTTPException(status_code=400, detail="start_date cannot be after expire_date")

    doc = {
        "title": title,
        "message": message,
        "start_date": start_date if start else None,
        "expire_date": expire_date,
        "created_by": teacher_username,
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return serialize_ann({**doc, "_id": result.inserted_id})


@router.put("/{announcement_id}")
def update_announcement(
    announcement_id: str,
    title: Optional[str] = Body(None),
    message: Optional[str] = Body(None),
    expire_date: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    teacher_username: str = Query(...),
):
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    ann = announcements_collection.find_one({"_id": oid})
    if not ann:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updates = {}
    if title is not None:
        updates["title"] = title
    if message is not None:
        updates["message"] = message
    if expire_date is not None:
        if not parse_date(expire_date):
            raise HTTPException(status_code=400, detail="Invalid expire_date format")
        updates["expire_date"] = expire_date
    if start_date is not None:
        if start_date != "" and not parse_date(start_date):
            raise HTTPException(status_code=400, detail="Invalid start_date format")
        updates["start_date"] = start_date if start_date != "" else None

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    announcements_collection.update_one({"_id": oid}, {"$set": updates})
    updated = announcements_collection.find_one({"_id": oid})
    return serialize_ann(updated)


@router.delete("/{announcement_id}")
def delete_announcement(announcement_id: str, teacher_username: str = Query(...)):
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        oid = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement id")

    result = announcements_collection.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
