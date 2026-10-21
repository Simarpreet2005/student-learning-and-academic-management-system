"""Academic Calendar Service for aggregating institutional events, deadlines, and terms.

Aggregates:
1. Official master institutional events (AcademicEvent)
2. Semester term commencement and concluding milestones (Semester)
3. Course assignment deadlines and cutoffs (Assignment)
4. Quiz availability sitting windows and deadlines (Quiz)

Strictly role-scoped:
- Student: Institutional events + deadlines/quizzes for enrolled courses.
- Lecturer: Institutional events + deadlines/quizzes for allocated courses.
- Parent: Institutional events + deadlines/quizzes for linked students' enrolled courses.
- Admin: Institutional oversight across all events.
"""
import calendar
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentStudentRelationship, User
from apps.academics.models import Course, EnrollmentStatus, Semester, StudentEnrollment, CourseAllocation
from apps.assessments.models import Assignment, AssignmentSubmission
from apps.core.models import AcademicEvent, EventType
from apps.quizzes.models import AttemptStatus, Quiz, QuizAttempt, QuizStatus


@dataclass
class CalendarItem:
    """Normalized calendar event representation."""

    item_id: str                      # e.g. "event_1", "assignment_2", "quiz_3", "semester_1"
    title: str
    category: str                     # "ACADEMIC", "ASSIGNMENT", "QUIZ", "SEMESTER"
    category_label: str               # "Campus Event", "Assignment Deadline", "Quiz Sitting", "Semester Term"
    badge_class: str
    icon: str
    start_date: datetime
    end_date: Optional[datetime]
    course_id: Optional[int]
    course_code: Optional[str]
    course_title: Optional[str]
    url: Optional[str]
    description: str
    location: Optional[str]
    is_completed: bool = False
    is_overdue: bool = False

    @property
    def is_multi_day(self) -> bool:
        if not self.end_date:
            return False
        return self.end_date.date() > self.start_date.date()


class CalendarService:
    """Aggregates and formats real academic events for calendar presentation."""

    @classmethod
    def get_user_events(
        cls,
        user: User,
        target_student_id: Optional[int] = None,
        course_id: Optional[int] = None,
        event_type_filter: Optional[str] = None,
        start_bound: Optional[datetime] = None,
        end_bound: Optional[datetime] = None,
    ) -> List[CalendarItem]:
        """Collect all permitted calendar items for the user."""
        now = timezone.now()
        items: List[CalendarItem] = []

        # -------------------------------------------------------------
        # 1. Official Institutional Events (AcademicEvent)
        # -------------------------------------------------------------
        if event_type_filter in (None, "ALL", "ACADEMIC"):
            event_qs = AcademicEvent.objects.filter(is_published=True)
            if start_bound:
                event_qs = event_qs.filter(start_date__gte=start_bound)
            if end_bound:
                event_qs = event_qs.filter(start_date__lte=end_bound)

            for ev in event_qs:
                icon_map = {
                    EventType.EXAMINATION: "fa-graduation-cap",
                    EventType.REGISTRATION: "fa-clipboard-check",
                    EventType.HOLIDAY: "fa-umbrella-beach",
                    EventType.CEREMONY: "fa-award",
                    EventType.LECTURE_RECESS: "fa-pause",
                }
                icon = icon_map.get(ev.event_type, "fa-calendar-day")

                items.append(
                    CalendarItem(
                        item_id=f"event_{ev.id}",
                        title=ev.title,
                        category="ACADEMIC",
                        category_label=ev.get_event_type_display(),
                        badge_class="badge-academic-info",
                        icon=icon,
                        start_date=ev.start_date,
                        end_date=ev.end_date,
                        course_id=None,
                        course_code=None,
                        course_title=None,
                        url=None,
                        description=ev.description,
                        location=ev.location,
                    )
                )

        # -------------------------------------------------------------
        # 2. Semester Terms (Commencement & Conclusion)
        # -------------------------------------------------------------
        if event_type_filter in (None, "ALL", "SEMESTER"):
            semesters = Semester.objects.filter(is_active=True).select_related("academic_year")
            for sem in semesters:
                if sem.start_date:
                    sem_start_dt = datetime.combine(sem.start_date, datetime.min.time()).replace(
                        tzinfo=timezone.get_current_timezone()
                    )
                    sem_end_dt = datetime.combine(sem.end_date, datetime.max.time()).replace(
                        tzinfo=timezone.get_current_timezone()
                    ) if sem.end_date else None

                    items.append(
                        CalendarItem(
                            item_id=f"semester_start_{sem.id}",
                            title=f"{sem.name} Begins",
                            category="SEMESTER",
                            category_label="Semester Start",
                            badge_class="badge-academic-success",
                            icon="fa-landmark",
                            start_date=sem_start_dt,
                            end_date=None,
                            course_id=None,
                            course_code=None,
                            course_title=None,
                            url=None,
                            description=f"Official commencement of {sem.name} ({sem.academic_year.name}).",
                            location="Campus Wide",
                        )
                    )

                    if sem_end_dt:
                        items.append(
                            CalendarItem(
                                item_id=f"semester_end_{sem.id}",
                                title=f"{sem.name} Concludes",
                                category="SEMESTER",
                                category_label="Semester End",
                                badge_class="badge-academic-warning",
                                icon="fa-flag-checkered",
                                start_date=sem_end_dt,
                                end_date=None,
                                course_id=None,
                                course_code=None,
                                course_title=None,
                                url=None,
                                description=f"Official conclusion of {sem.name}.",
                                location="Campus Wide",
                            )
                        )

        # -------------------------------------------------------------
        # Determine Scoped Courses based on Role
        # -------------------------------------------------------------
        scoped_courses: List[Course] = []

        if getattr(user, "is_admin_role", False) or user.is_superuser:
            if course_id:
                scoped_courses = list(Course.objects.filter(id=course_id, is_active=True))
            else:
                scoped_courses = list(Course.objects.filter(is_active=True))

        elif getattr(user, "is_lecturer_role", False):
            alloc_qs = CourseAllocation.objects.filter(lecturer=user, is_active=True).select_related("course")
            if course_id:
                alloc_qs = alloc_qs.filter(course_id=course_id)
            scoped_courses = [a.course for a in alloc_qs]

        elif getattr(user, "is_student_role", False):
            enroll_qs = StudentEnrollment.objects.filter(
                student=user,
                status=EnrollmentStatus.ENROLLED,
                is_active=True,
            ).select_related("course")
            if course_id:
                enroll_qs = enroll_qs.filter(course_id=course_id)
            scoped_courses = [e.course for e in enroll_qs]

        elif getattr(user, "is_parent_role", False):
            # Only linked students
            linked_ids = list(
                ParentStudentRelationship.objects.filter(parent=user).values_list("student_id", flat=True)
            )
            if target_student_id:
                if target_student_id in linked_ids:
                    linked_ids = [target_student_id]
                else:
                    linked_ids = []  # Unauthorized student ID -> return empty course scope

            enroll_qs = StudentEnrollment.objects.filter(
                student_id__in=linked_ids,
                status=EnrollmentStatus.ENROLLED,
                is_active=True,
            ).select_related("course")
            if course_id:
                enroll_qs = enroll_qs.filter(course_id=course_id)
            scoped_courses = list(set([e.course for e in enroll_qs]))

        if not scoped_courses:
            items.sort(key=lambda x: x.start_date)
            return items

        # -------------------------------------------------------------
        # 3. Course Assignments (Deadlines)
        # -------------------------------------------------------------
        if event_type_filter in (None, "ALL", "ASSIGNMENT"):
            assign_qs = Assignment.objects.filter(
                course__in=scoped_courses,
                is_published=True,
                is_active=True,
            ).select_related("course")

            # Check student completion map if applicable
            completed_assign_ids = set()
            if getattr(user, "is_student_role", False):
                completed_assign_ids = set(
                    AssignmentSubmission.objects.filter(
                        student=user,
                        assignment__in=assign_qs,
                        is_active=True,
                    ).values_list("assignment_id", flat=True)
                )

            for a in assign_qs:
                if not a.due_date:
                    continue
                is_done = a.id in completed_assign_ids
                is_late = (a.due_date < now) and not is_done

                items.append(
                    CalendarItem(
                        item_id=f"assignment_{a.id}",
                        title=f"{a.course.code}: {a.title}",
                        category="ASSIGNMENT",
                        category_label="Assignment Deadline",
                        badge_class="badge-academic-danger" if is_late else "badge-academic-warning",
                        icon="fa-file-lines",
                        start_date=a.due_date,
                        end_date=a.cutoff_date,
                        course_id=a.course.id,
                        course_code=a.course.code,
                        course_title=a.course.title,
                        url=None,
                        description=a.description or f"Due date for {a.title}.",
                        location=f"{a.course.code} Course Deliverable",
                        is_completed=is_done,
                        is_overdue=is_late,
                    )
                )

        # -------------------------------------------------------------
        # 4. Course Quizzes (Availability Window & Deadline)
        # -------------------------------------------------------------
        if event_type_filter in (None, "ALL", "QUIZ"):
            quiz_qs = Quiz.objects.filter(
                course__in=scoped_courses,
                status=QuizStatus.PUBLISHED,
                is_active=True,
            ).select_related("course")

            completed_quiz_ids = set()
            if getattr(user, "is_student_role", False):
                completed_quiz_ids = set(
                    QuizAttempt.objects.filter(
                        student=user,
                        quiz__in=quiz_qs,
                        status__in=[AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED],
                    ).values_list("quiz_id", flat=True)
                )

            for q in quiz_qs:
                is_done = q.id in completed_quiz_ids
                is_late = (q.available_to < now) and not is_done

                # Event at quiz deadline (available_to)
                items.append(
                    CalendarItem(
                        item_id=f"quiz_{q.id}",
                        title=f"{q.course.code}: {q.title}",
                        category="QUIZ",
                        category_label="Quiz Due / Window Close",
                        badge_class="badge-academic-danger" if is_late else "badge-academic-info",
                        icon="fa-clock",
                        start_date=q.available_to,
                        end_date=None,
                        course_id=q.course.id,
                        course_code=q.course.code,
                        course_title=q.course.title,
                        url=reverse("quizzes:quiz_detail", kwargs={"pk": q.id}) if not getattr(user, "is_parent_role", False) else None,
                        description=f"Quiz deadline ({q.duration_minutes}m sitting limit, {q.total_marks} marks).",
                        location=f"{q.course.code} Assessment",
                        is_completed=is_done,
                        is_overdue=is_late,
                    )
                )

        # Sort chronologically
        items.sort(key=lambda x: x.start_date)
        return items

    @classmethod
    def build_month_grid(
        cls,
        year: int,
        month: int,
        items: List[CalendarItem] = None,
        events: List[CalendarItem] = None,
    ) -> List[List[Dict[str, Any]]]:
        """Generate a 2D calendar matrix (weeks x days) populated with events.

        Accepts either ``items`` or ``events`` as the calendar item list for
        backward compatibility. ``items`` takes precedence when both are supplied.
        Cell dictionaries expose the key ``items`` (and legacy ``events``) for
        template access.
        """
        # Normalise: accept either kwarg name
        resolved: List[CalendarItem] = items if items is not None else (events or [])

        cal = calendar.Calendar(firstweekday=calendar.MONDAY)
        month_days = cal.monthdatescalendar(year, month)

        grid: List[List[Dict[str, Any]]] = []

        for week in month_days:
            week_row = []
            for d in week:
                # Find all events occurring on this date
                day_events = [
                    ev for ev in resolved
                    if ev.start_date.date() == d
                    or (ev.end_date and ev.start_date.date() <= d <= ev.end_date.date())
                ]
                week_row.append({
                    "date": d,
                    "day_number": d.day,
                    "is_current_month": (d.month == month),
                    "is_today": (d == timezone.now().date()),
                    "items": day_events,        # primary key used in templates & tests
                    "events": day_events,       # legacy alias for existing templates
                    "event_count": len(day_events),
                })
            grid.append(week_row)

        return grid
