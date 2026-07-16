from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Request, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import get_db, SessionLocal, Conversation, ConversationMember, Message, User
from app.auth import require_login, get_current_user, NotAuthorizedException, NotFoundException, log_action
from jose import jwt, JWTError
from app.config import SECRET_KEY, ALGORITHM

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


class ConnectionManager:
    def __init__(self):
        # Maps conversation_id -> dict of (user_id -> list of WebSocket connections)
        self.active_connections: Dict[int, Dict[int, List[WebSocket]]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: int, user_id: int):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = {}
        if user_id not in self.active_connections[conversation_id]:
            self.active_connections[conversation_id][user_id] = []
        self.active_connections[conversation_id][user_id].append(websocket)

    def disconnect(self, websocket: WebSocket, conversation_id: int, user_id: int):
        if conversation_id in self.active_connections:
            if user_id in self.active_connections[conversation_id]:
                if websocket in self.active_connections[conversation_id][user_id]:
                    self.active_connections[conversation_id][user_id].remove(websocket)
                if not self.active_connections[conversation_id][user_id]:
                    del self.active_connections[conversation_id][user_id]
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]

    async def broadcast(self, conversation_id: int, message: dict):
        if conversation_id in self.active_connections:
            for user_id, sockets in self.active_connections[conversation_id].items():
                for ws in sockets:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass


manager = ConnectionManager()


def get_user_from_token(token: Optional[str], db: Session) -> Optional[User]:
    """Helper to decode JWT and return user for WebSocket authentication."""
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            return None
        return db.query(User).filter(User.id == int(user_id)).first()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Chat Page
# ---------------------------------------------------------------------------


@router.get("/chat")
def chat_home(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    message = request.query_params.get("message", "")
    message_type = request.query_params.get("type", "info")

    enriched_conversations = []

    # 1. Fetch or dynamically create the community chat for the user's organization
    community = db.query(Conversation).filter_by(type="community", organization_id=user.organization_id).first()
    if not community:
        community = Conversation(
            type="community",
            name="Community Chat",
            organization_id=user.organization_id
        )
        db.add(community)
        db.commit()
        db.refresh(community)

    # Prepend community chat to the top of list
    latest_msg = (
        db.query(Message)
        .filter(Message.conversation_id == community.id)
        .order_by(Message.timestamp.desc())
        .first()
    )
    enriched_conversations.append({
        "id": community.id,
        "type": community.type,
        "name": community.name,
        "latest_message": latest_msg.content if latest_msg else "Welcome to the Community Chat!",
        "latest_message_time": latest_msg.timestamp if latest_msg else None,
    })

    # Fetch all user conversations (DMs and Groups) in this organization
    conversations = (
        db.query(Conversation)
        .filter(Conversation.organization_id == user.organization_id)
        .join(ConversationMember)
        .filter(ConversationMember.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )

    for conv in conversations:
        # Skip community chat since it's already prepended at the top
        if conv.type == "community":
            continue

        conv_name = conv.name
        if conv.type == "dm":
            other_member = [m for m in conv.members if m.id != user.id]
            conv_name = other_member[0].name if other_member else "Unknown User"
        
        latest_msg = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.timestamp.desc())
            .first()
        )

        enriched_conversations.append({
            "id": conv.id,
            "type": conv.type,
            "name": conv_name,
            "latest_message": latest_msg.content if latest_msg else "No messages yet",
            "latest_message_time": latest_msg.timestamp if latest_msg else None,
        })

    # Fetch all other users inside the same organization for starting DMs or creating groups
    all_users = db.query(User).filter(User.organization_id == user.organization_id, User.id != user.id).order_by(User.name).all()

    # Active conversation configuration
    active_conv_id_str = request.query_params.get("id")
    active_conversation = None
    active_conversation_members = []
    
    if active_conv_id_str:
        try:
            active_conv_id = int(active_conv_id_str)
            conv_obj = db.query(Conversation).filter_by(id=active_conv_id, organization_id=user.organization_id).first()
            if conv_obj:
                if conv_obj.type == "community":
                    active_conversation = {
                        "id": conv_obj.id,
                        "type": conv_obj.type,
                        "display_name": conv_obj.name,
                    }
                    # For community, all active users in the same organization are members
                    active_conversation_members = db.query(User).filter(User.organization_id == user.organization_id).order_by(User.name).all()
                else:
                    # Verify membership
                    is_member = db.query(ConversationMember).filter_by(
                        conversation_id=active_conv_id, user_id=user.id
                    ).first()
                    
                    if is_member:
                        display_name = conv_obj.name
                        if conv_obj.type == "dm":
                            other = [m for m in conv_obj.members if m.id != user.id]
                            display_name = other[0].name if other else "Unknown User"
                        
                        active_conversation = {
                            "id": conv_obj.id,
                            "type": conv_obj.type,
                            "display_name": display_name,
                        }
                        active_conversation_members = conv_obj.members
        except ValueError:
            pass

    return templates.TemplateResponse(
        "chat.html",
        {
            "request": request,
            "user": user,
            "conversations": enriched_conversations,
            "all_users": all_users,
            "active_conversation": active_conversation,
            "active_conversation_members": active_conversation_members,
            "message": message,
            "message_type": message_type,
        },
    )


# ---------------------------------------------------------------------------
# Create DM Conversation
# ---------------------------------------------------------------------------


@router.post("/chat/conversations/dm")
async def create_dm(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    form = await request.form()
    
    try:
        recipient_id = int(form.get("recipient_id", ""))
    except (ValueError, TypeError):
        return RedirectResponse(url="/chat?message=Invalid+recipient&type=error", status_code=303)

    if recipient_id == user.id:
        return RedirectResponse(url="/chat?message=Cannot+start+chat+with+yourself&type=error", status_code=303)

    recipient = db.query(User).filter_by(id=recipient_id, organization_id=user.organization_id).first()
    if not recipient:
        return RedirectResponse(url="/chat?message=User+not+found&type=error", status_code=303)

    # Check if a 1-to-1 DM already exists in this organization between these users
    user_dms = (
        db.query(Conversation)
        .filter(Conversation.type == "dm", Conversation.organization_id == user.organization_id)
        .join(ConversationMember)
        .filter(ConversationMember.user_id == user.id)
        .all()
    )
    
    existing_dm = None
    for dm in user_dms:
        member_ids = {m.id for m in dm.members}
        if recipient_id in member_ids and len(member_ids) == 2:
            existing_dm = dm
            break

    if existing_dm:
        return RedirectResponse(url=f"/chat?id={existing_dm.id}", status_code=303)

    # Create new DM
    conv = Conversation(type="dm", created_by=user.id, organization_id=user.organization_id)
    db.add(conv)
    db.flush()  # Populate ID
    
    db.add(ConversationMember(conversation_id=conv.id, user_id=user.id))
    db.add(ConversationMember(conversation_id=conv.id, user_id=recipient_id))
    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "create_dm",
        resource_type="conversation",
        resource_id=conv.id,
        details=f"Started DM with {recipient.name}",
    )

    return RedirectResponse(url=f"/chat?id={conv.id}", status_code=303)


# ---------------------------------------------------------------------------
# Create Group Conversation
# ---------------------------------------------------------------------------


@router.post("/chat/conversations/group")
async def create_group(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    form = await request.form()
    
    name = form.get("name", "").strip()
    if not name:
        return RedirectResponse(url="/chat?message=Group+name+is+required&type=error", status_code=303)

    raw_member_ids = form.getlist("member_ids")
    if not raw_member_ids:
        single = form.get("member_ids")
        if single:
            raw_member_ids = [single]

    member_ids = []
    for mid in raw_member_ids:
        try:
            member_ids.append(int(mid))
        except (ValueError, TypeError):
            continue

    # Create group
    conv = Conversation(type="group", name=name, created_by=user.id, organization_id=user.organization_id)
    db.add(conv)
    db.flush()

    # Add creator
    db.add(ConversationMember(conversation_id=conv.id, user_id=user.id))
    
    # Add other valid members belonging to the same organization
    added_count = 1
    for mid in member_ids:
        if mid != user.id:
            exists = db.query(User).filter_by(id=mid, organization_id=user.organization_id).first()
            if exists:
                db.add(ConversationMember(conversation_id=conv.id, user_id=mid))
                added_count += 1

    db.commit()

    log_action(
        db,
        user.id,
        user.email,
        "create_group_chat",
        resource_type="conversation",
        resource_id=conv.id,
        details=f"Created group chat '{name}' with {added_count} members",
    )

    return RedirectResponse(url=f"/chat?id={conv.id}", status_code=303)


# ---------------------------------------------------------------------------
# Fetch Conversation Message History
# ---------------------------------------------------------------------------


@router.get("/chat/conversations/{conversation_id}/history")
def get_history(conversation_id: int, request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)

    conv = db.query(Conversation).filter_by(id=conversation_id, organization_id=user.organization_id).first()
    if not conv:
        raise NotFoundException()
    
    if conv.type != "community":
        # Security check: Verify user is a member of the conversation
        is_member = db.query(ConversationMember).filter_by(
            conversation_id=conversation_id, user_id=user.id
        ).first()
        
        if not is_member:
            raise NotAuthorizedException("You do not have access to this conversation.")

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
        .all()
    )

    return JSONResponse(content=[
        {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "sender_name": msg.sender.name,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat(),
        }
        for msg in messages
    ])


# ---------------------------------------------------------------------------
# Real-Time WebSocket Endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws/chat/{conversation_id}")
async def chat_ws(websocket: WebSocket, conversation_id: int):
    db = SessionLocal()
    try:
        # 1. Authenticate user from cookie
        user = get_user_from_token(websocket.cookies.get("access_token"), db)
        if not user:
            await websocket.accept()
            await websocket.close(code=4003)  # Forbidden
            return

        # 2. Verify conversation and organization boundaries
        conv = db.query(Conversation).filter_by(id=conversation_id, organization_id=user.organization_id).first()
        if not conv:
            await websocket.accept()
            await websocket.close(code=4003)  # Forbidden
            return

        # 3. Verify membership for non-community rooms
        if conv.type != "community":
            is_member = db.query(ConversationMember).filter_by(
                conversation_id=conversation_id, user_id=user.id
            ).first()
            
            if not is_member:
                await websocket.accept()
                await websocket.close(code=4003)  # Forbidden
                return

        # 4. Accept connection and register
        await manager.connect(websocket, conversation_id, user.id)

        try:
            while True:
                # Wait for JSON message
                data = await websocket.receive_json()
                content = data.get("content", "").strip()
                if not content:
                    continue

                # 5. Strict member-check before persisting or broadcasting
                if conv.type != "community":
                    db.expire_all()
                    is_still_member = db.query(ConversationMember).filter_by(
                        conversation_id=conversation_id, user_id=user.id
                    ).first()
                    
                    if not is_still_member:
                        await websocket.close(code=4003)
                        break

                # 6. Persist message
                msg = Message(
                    conversation_id=conversation_id,
                    sender_id=user.id,
                    content=content,
                    timestamp=datetime.utcnow()
                )
                db.add(msg)
                db.commit()
                db.refresh(msg)

                # 7. Broadcast to participants
                await manager.broadcast(conversation_id, {
                    "id": msg.id,
                    "sender_id": user.id,
                    "sender_name": user.name,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                })

        except WebSocketDisconnect:
            manager.disconnect(websocket, conversation_id, user.id)
    finally:
        db.close()
