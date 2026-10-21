import random
import string
from django.utils.text import slugify
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings


def send_email(user, subject, msg):
    send_mail(
        subject,
        msg,
        settings.EMAIL_FROM_ADDRESS,
        [user.email],
        fail_silently=True,
    )


def send_html_email(subject, recipient_list, template, context):
    """A function responsible for sending HTML email"""
    # Render the HTML template
    html_message = render_to_string(template, context)

    # Generate plain text version of the email (optional)
    plain_message = strip_tags(html_message)

    # Send the email
    send_mail(
        subject,
        plain_message,
        settings.EMAIL_FROM_ADDRESS,
        recipient_list,
        html_message=html_message,
        fail_silently=True,
    )


def random_string_generator(size=10, chars=string.ascii_lowercase + string.digits):
    return "".join(random.choice(chars) for _ in range(size))


def unique_slug_generator(instance, new_slug=None):
    """
    Assumes the instance has a model with a slug field and a title
    character (char) field.
    """
    if new_slug is not None:
        slug = new_slug
    else:
        slug = slugify(instance.title)

    klass = instance.__class__
    qs_exists = klass.objects.filter(slug=slug).exists()
    if qs_exists:
        new_slug = f"{slug}-{random_string_generator(size=4)}"
        return unique_slug_generator(instance, new_slug=new_slug)
    return slug


def notify_assignment_created(assignment):
    """Notify all students enrolled in the course about a newly created assignment."""
    from result.models import TakenCourse  # pylint: disable=import-outside-toplevel
    from core.models import Notification  # pylint: disable=import-outside-toplevel

    enrolled_records = TakenCourse.objects.filter(
        course=assignment.course
    ).select_related("student__student")

    due_str = assignment.due_date.strftime("%b %d, %Y %I:%M %p")
    title = f"New Assignment: {assignment.title} ({assignment.course.code})"
    message = (
        f"A new assignment '{assignment.title}' has been published for {assignment.course}. "
        f"Deadline: {due_str}. Maximum marks: {assignment.maximum_marks}."
    )
    link = assignment.get_absolute_url()

    notifications = []
    for record in enrolled_records:
        student_user = getattr(record.student, "student", None)
        if student_user:
            notifications.append(
                Notification(
                    user=student_user,
                    title=title,
                    message=message,
                    notification_type="assignment_created",
                    link=link,
                )
            )

    if notifications:
        Notification.objects.bulk_create(notifications)


def notify_assignment_graded(submission):
    """Notify the student when their assignment submission is graded."""
    from core.models import Notification  # pylint: disable=import-outside-toplevel

    assignment = submission.assignment
    student_user = getattr(submission.student, "student", None)
    if not student_user:
        return

    title = f"Assignment Graded: {assignment.title} ({assignment.course.code})"
    score_str = f"{submission.marks} / {assignment.maximum_marks}"
    message = (
        f"Your submission for '{assignment.title}' has been graded. "
        f"Score: {score_str}."
    )
    link = assignment.get_absolute_url()

    Notification.objects.create(
        user=student_user,
        title=title,
        message=message,
        notification_type="assignment_graded",
        link=link,
    )
