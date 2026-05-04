from datetime import datetime

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from app.api.auth import decode_user_id
from app.storage.ledger import Conversation, Message, session_scope

router = APIRouter()


@router.get("/conversations")
def list_conversations(session_token: str | None = Cookie(default=None)):
    uid = decode_user_id(session_token)
    with session_scope() as s:
        q = s.query(Conversation)
        if uid is not None:
            q = q.filter_by(user_id=uid)
        else:
            q = q.filter(Conversation.user_id.is_(None))
        rows = q.order_by(
            Conversation.pinned.desc(),
            Conversation.pinned_at.desc().nullslast(),
            Conversation.created_at.desc(),
        ).limit(100).all()
        return [
            {
                "id": r.id,
                "title": r.title or "Untitled",
                "created_at": str(r.created_at),
                "pinned": bool(r.pinned),
            }
            for r in rows
        ]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, session_token: str | None = Cookie(default=None)):
    uid = decode_user_id(session_token)
    with session_scope() as s:
        conv = s.get(Conversation, conv_id)
        if conv is None:
            raise HTTPException(404, "not found")
        if conv.user_id != uid:
            raise HTTPException(403, "forbidden")
        msgs = (
            s.query(Message)
            .filter_by(conversation_id=conv_id)
            .order_by(Message.created_at.asc())
            .all()
        )
        return {
            "id": conv.id,
            "title": conv.title or "Untitled",
            "created_at": str(conv.created_at),
            "pinned": bool(conv.pinned),
            "messages": [
                {"role": m.role, "content": m.content, "hits": m.hits_json or []}
                for m in msgs
            ],
        }


class PatchBody(BaseModel):
    title: str | None = None
    pinned: bool | None = None


@router.patch("/conversations/{conv_id}")
def patch_conversation(
    conv_id: int,
    body: PatchBody,
    session_token: str | None = Cookie(default=None),
):
    uid = decode_user_id(session_token)
    with session_scope() as s:
        conv = s.get(Conversation, conv_id)
        if conv is None:
            raise HTTPException(404, "not found")
        if conv.user_id != uid:
            raise HTTPException(403, "forbidden")
        if body.title is not None:
            title = body.title.strip()[:200]
            if not title:
                raise HTTPException(422, "title cannot be empty")
            conv.title = title
        if body.pinned is not None:
            conv.pinned = body.pinned
            conv.pinned_at = datetime.utcnow() if body.pinned else None
    return {"id": conv_id, "title": conv.title, "pinned": conv.pinned}
