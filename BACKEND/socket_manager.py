import socketio
from services.auth_service import verify_token

# Async Socket.io server – mounted in main.py via ASGI
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)


@sio.event
async def connect(sid, environ, auth):
    token = None
    if auth and isinstance(auth, dict):
        token = auth.get("token")
    if not token:
        # Try query string
        qs = environ.get("QUERY_STRING", "")
        for part in qs.split("&"):
            if part.startswith("token="):
                token = part[6:]
                break

    if not token:
        return False  # Reject connection

    payload = verify_token(token)
    if not payload:
        return False

    user_id = str(payload.get("sub"))
    await sio.enter_room(sid, user_id)
    await sio.save_session(sid, {"user_id": user_id})


@sio.event
async def disconnect(sid):
    pass


async def emit_to_user(user_id: int, event: str, data: dict):
    """Emit an event to a specific user's Socket.io room."""
    await sio.emit(event, data, room=str(user_id))
