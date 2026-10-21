from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _


NEWS = _("News")
EVENTS = _("Event")

POST = (
    (NEWS, _("News")),
    (EVENTS, _("Event")),
)

FIRST = _("First")
SECOND = _("Second")
THIRD = _("Third")

SEMESTER = (
    (FIRST, _("First")),
    (SECOND, _("Second")),
    (THIRD, _("Third")),
)


class NewsAndEventsQuerySet(models.query.QuerySet):
    def search(self, query):
        lookups = (
            Q(title__icontains=query)
            | Q(summary__icontains=query)
            | Q(posted_as__icontains=query)
        )
        return self.filter(lookups).distinct()


class NewsAndEventsManager(models.Manager):
    def get_queryset(self):
        return NewsAndEventsQuerySet(self.model, using=self._db)

    def all(self):
        return self.get_queryset()

    def get_by_id(self, id):
        qs = self.get_queryset().filter(
            id=id
        )  # NewsAndEvents.objects == self.get_queryset()
        if qs.count() == 1:
            return qs.first()
        return None

    def search(self, query):
        return self.get_queryset().search(query)


class NewsAndEvents(models.Model):
    title = models.CharField(max_length=200, null=True)
    summary = models.TextField(max_length=200, blank=True, null=True)
    posted_as = models.CharField(choices=POST, max_length=10)
    updated_date = models.DateTimeField(auto_now=True, auto_now_add=False, null=True)
    upload_time = models.DateTimeField(auto_now=False, auto_now_add=True, null=True)

    objects = NewsAndEventsManager()

    def __str__(self):
        return f"{self.title}"


class Session(models.Model):
    session = models.CharField(max_length=200, unique=True)
    is_current_session = models.BooleanField(default=False, blank=True, null=True)
    next_session_begins = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"{self.session}"


class Semester(models.Model):
    semester = models.CharField(max_length=10, choices=SEMESTER, blank=True)
    is_current_semester = models.BooleanField(default=False, blank=True, null=True)
    session = models.ForeignKey(
        Session, on_delete=models.CASCADE, blank=True, null=True
    )
    next_semester_begins = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.semester}"


class ActivityLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"[{self.created_at}]{self.message}"


class Notification(models.Model):
    NOTIFICATION_TYPES = (
        ("assignment_created", _("New Assignment")),
        ("assignment_graded", _("Assignment Graded")),
        ("assignment_deadline", _("Upcoming Deadline")),
        ("general", _("General")),
    )

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
        verbose_name=_("User"),
    )
    title = models.CharField(max_length=200, verbose_name=_("Title"))
    message = models.TextField(verbose_name=_("Message"))
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPES,
        default="general",
        verbose_name=_("Type"),
    )
    link = models.CharField(
        max_length=255, blank=True, null=True, verbose_name=_("Link URL")
    )
    is_read = models.BooleanField(default=False, verbose_name=_("Is Read"))
    created_at = models.DateTimeField(
        auto_now_add=True, verbose_name=_("Created At")
    )

    class Meta:
        ordering = ("-created_at",)
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")

    def __str__(self):
        status = "Read" if self.is_read else "Unread"
        return f"{self.user.username} - {self.title} ({status})"

    def mark_as_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])
