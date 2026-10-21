from core.models import Notification


def notification_context(request):
    """Provide unread notification count to all templates for authenticated users."""
    if hasattr(request, "user") and request.user.is_authenticated:
        unread_count = Notification.objects.filter(
            user=request.user, is_read=False
        ).count()
        return {"unread_notifications_count": unread_count}
    return {"unread_notifications_count": 0}
