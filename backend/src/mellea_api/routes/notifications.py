"""Notification routes with REST API and WebSocket support."""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from mellea_api.core.deps import AdminUser, CurrentUser
from mellea_api.core.security import decode_access_token
from mellea_api.models.notification import (
    Notification,
    NotificationCreateRequest,
    NotificationListResponse,
    NotificationType,
    NotificationUpdateRequest,
)
from mellea_api.services.auth import get_auth_service
from mellea_api.services.notification import NotificationService, get_notification_service

logger = logging.getLogger(__name__)

NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
async def get_notifications(
    current_user: CurrentUser,
    notification_service: NotificationServiceDep,
    unread_only: bool = Query(False, alias="unreadOnly", description="Only return unread"),
    type: NotificationType | None = Query(None, description="Filter by notification type"),
    since: datetime | None = Query(None, description="Filter by date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=200, description="Maximum notifications to return"),
    offset: int = Query(0, ge=0, description="Number of notifications to skip"),
) -> NotificationListResponse:
    """Get notifications for the current user.

    Returns a paginated list of notifications with unread count.
    """
    notifications, total, unread_count = notification_service.get_notifications(
        user_id=current_user.id,
        unread_only=unread_only,
        type=type,
        since=since,
        limit=limit,
        offset=offset,
    )

    return NotificationListResponse(
        notifications=notifications,
        total=total,
        unread_count=unread_count,
        limit=limit,
        offset=offset,
    )


@router.get("/{notification_id}", response_model=Notification)
async def get_notification(
    notification_id: str,
    current_user: CurrentUser,
    notification_service: NotificationServiceDep,
) -> Notification:
    """Get a specific notification by ID."""
    notification = notification_service.store.get_by_id(notification_id)
    if notification is None or notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notification


@router.patch("/{notification_id}", response_model=Notification)
async def update_notification(
    notification_id: str,
    update: NotificationUpdateRequest,
    current_user: CurrentUser,
    notification_service: NotificationServiceDep,
) -> Notification:
    """Update a notification's read status."""
    if update.is_read:
        notification = notification_service.mark_as_read(notification_id, current_user.id)
    else:
        # Allow marking as unread (re-setting is_read to False)
        notification = notification_service.store.get_by_id(notification_id)
        if notification and notification.user_id == current_user.id:
            notification.is_read = False
            notification.read_at = None
            notification_service.store.update(notification_id, notification)

    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    return notification


@router.post("/mark-all-read")
async def mark_all_as_read(
    current_user: CurrentUser,
    notification_service: NotificationServiceDep,
) -> dict[str, int]:
    """Mark all notifications as read for the current user."""
    count = notification_service.mark_all_as_read(current_user.id)
    return {"marked": count}


@router.delete("/{notification_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_notification(
    notification_id: str,
    current_user: CurrentUser,
    notification_service: NotificationServiceDep,
) -> None:
    """Delete a notification."""
    if not notification_service.delete_notification(notification_id, current_user.id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )


# Admin endpoints for creating system notifications
admin_router = APIRouter(prefix="/api/v1/admin/notifications", tags=["admin-notifications"])


@admin_router.post("", response_model=Notification, status_code=status.HTTP_201_CREATED)
async def create_notification(
    request: NotificationCreateRequest,
    current_user: AdminUser,
    notification_service: NotificationServiceDep,
) -> Notification:
    """Create a notification for a user (admin only).

    Used for system announcements or administrative notifications.
    """
    notification = await notification_service.create_notification(
        user_id=request.user_id,
        type=request.type,
        title=request.title,
        message=request.message,
        priority=request.priority,
        resource_type=request.resource_type,
        resource_id=request.resource_id,
        action_url=request.action_url,
        metadata=request.metadata,
    )
    return notification


@admin_router.get("/stats")
async def get_notification_stats(
    current_user: AdminUser,
    notification_service: NotificationServiceDep,
) -> dict[str, int]:
    """Get notification system statistics (admin only)."""
    all_notifications = notification_service.store.list_all()
    connected_users = notification_service.connection_manager.get_connected_users()
    total_connections = notification_service.connection_manager.get_connection_count()

    return {
        "total_notifications": len(all_notifications),
        "connected_users": len(connected_users),
        "total_connections": total_connections,
    }


# WebSocket endpoint for real-time notifications
ws_router = APIRouter(tags=["notifications-ws"])


@ws_router.websocket("/api/v1/notifications/ws")
async def websocket_notifications(
    websocket: WebSocket,
    token: str | None = Query(None, description="JWT token for authentication"),
) -> None:
    """WebSocket endpoint for real-time notifications.

    Connect to receive notifications in real-time. Authentication is done
    via the `token` query parameter since WebSocket doesn't support custom headers.

    Example connection URL:
        ws://localhost:8000/api/v1/notifications/ws?token=<jwt_token>

    Messages sent to connected clients:
        {
            "type": "notification",
            "payload": { ...notification object... }
        }

    You can also send messages to the server:
        {"type": "ping"} - Server will respond with {"type": "pong"}
    """
    notification_service = get_notification_service()

    # Authenticate the user
    if token is None:
        await websocket.close(code=4001, reason="Authentication required")
        return

    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token payload")
        return

    # Verify user exists and is active
    auth_service = get_auth_service()
    user = auth_service.get_user_by_id(user_id)
    if user is None or user.status.value != "active":
        await websocket.close(code=4001, reason="User not found or inactive")
        return

    # Register the connection
    await notification_service.connection_manager.connect(websocket, user_id)

    try:
        # Send initial connection success message
        await websocket.send_json({
            "type": "connected",
            "payload": {"userId": user_id},
        })

        # Handle incoming messages
        while True:
            try:
                data = await websocket.receive_json()
                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                # Can add more message types here for future functionality

            except Exception as e:
                # Log but don't break - could be malformed message
                logger.debug(f"WebSocket message handling error: {e}")

    except WebSocketDisconnect:
        logger.debug(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.warning(f"WebSocket error for user {user_id}: {e}")
    finally:
        await notification_service.connection_manager.disconnect(websocket, user_id)
