from sqlalchemy.ext.asyncio import AsyncSession
from models.notification import Notification
from socket_manager import emit_to_user


async def create_notification(
    db: AsyncSession,
    dropshipper_id: int,
    type: str,
    title: str,
    body: str = "",
    reference_type: str = None,
    reference_id: int = None,
) -> Notification:
    notification = Notification(
        dropshipper_id=dropshipper_id,
        type=type,
        title=title,
        body=body,
        reference_type=reference_type,
        reference_id=reference_id,
    )
    db.add(notification)
    await db.commit()
    await db.refresh(notification)

    # Emit real-time via Socket.io
    await emit_to_user(dropshipper_id, "notification", {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "is_read": False,
        "created_at": notification.created_at.isoformat(),
    })

    return notification
