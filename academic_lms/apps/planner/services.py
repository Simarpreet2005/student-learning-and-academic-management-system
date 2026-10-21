"""Rule-based, deterministic academic workload planning engine.

Zero AI, zero LLMs, zero non-deterministic APIs.
All calculations are transparent, mathematical, and testable with fixed reference times.

Key capabilities:
1. Collects pending and completed deliverables (Assignments, Quizzes) across student's enrolled courses.
2. Clearly distinguishes actual deadlines and durations from estimates; never invents missing data.
3. Identifies overlapping deadline clusters within rolling 48-hour windows.
4. Ranks tasks by urgency, proximity, cluster density, and effort into reproducible priority tiers.
5. Categorizes workload as Balanced, Moderate, Heavy, or Conflict using documented mathematical thresholds.
6. Builds a deterministic 7-day study schedule when student has configured weekly study availability.
   If availability is not configured, provides the prioritized task list without guessing free time.
7. Excludes completed submissions/attempts from active workload and over-capacity calculations.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from django.utils import timezone

from apps.accounts.models import Role, User
from apps.academics.models import Course, EnrollmentStatus, StudentEnrollment
from apps.assessments.models import Assignment, AssignmentSubmission
from apps.planner.models import StudentStudyBudget
from apps.quizzes.models import AttemptStatus, Quiz, QuizAttempt, QuizStatus


@dataclass
class PlannerTask:
    """Normalized in-memory representation of an academic task (Assignment or Quiz)."""

    task_id: str                      # e.g. "assignment_12", "quiz_5"
    source_id: int                    # Database primary key
    task_type: str                    # "ASSIGNMENT" or "QUIZ"
    title: str
    course_id: int
    course_code: str
    course_title: str
    course_credits: int

    # Actual Dates & Durations (Never estimated)
    deadline: Optional[datetime]      # Assignment due_date or Quiz available_to
    start_date: Optional[datetime]    # Assignment created_at or Quiz available_from
    actual_duration_minutes: Optional[int]  # Quiz duration_minutes; None for assignment

    # Estimated Effort (Lecturer-entered; None if unestimated)
    estimated_effort_hours: Optional[float]

    # Completion & Status Flags
    is_completed: bool
    completion_status: str            # "PENDING", "SUBMITTED", "GRADED", "EXPIRED", "ATTEMPTS_EXHAUSTED"
    is_overdue: bool
    days_remaining: Optional[float]   # Positive = future, Negative = past
    hours_remaining: Optional[float]

    # Calculated Priority & Cluster Metadata
    priority_score: int = 0           # Deterministic integer score (0-120)
    priority_level: str = "LOW"       # CRITICAL, HIGH, MEDIUM, LOW, OVERDUE, COMPLETED, UNSCHEDULED
    priority_explanation: str = ""    # Plain-English justification of priority ranking
    is_in_cluster: bool = False
    cluster_id: Optional[str] = None
    cluster_severity: Optional[str] = None

    @property
    def has_estimated_effort(self) -> bool:
        return self.estimated_effort_hours is not None

    @property
    def has_actual_duration(self) -> bool:
        return self.actual_duration_minutes is not None

    @property
    def effective_effort_hours(self) -> Optional[float]:
        """Return known effort if estimated; for quizzes with duration, return duration in hours if effort is not entered."""
        if self.estimated_effort_hours is not None:
            return float(self.estimated_effort_hours)
        if self.actual_duration_minutes is not None:
            return round(self.actual_duration_minutes / 60.0, 2)
        return None


@dataclass
class DeadlineCluster:
    """A detected group of pending deliverables due within 48 hours of each other."""

    cluster_id: str
    task_ids: List[str]
    task_titles: List[str]
    start_time: datetime
    end_time: datetime
    span_hours: float
    task_count: int
    severity: str                     # "CRITICAL" (>=4), "HEAVY" (3), "MODERATE" (2)
    description: str


@dataclass
class StudyScheduleSession:
    """A planned study block allocated to a specific task on a specific day."""

    task_id: str
    task_title: str
    course_code: str
    allocated_hours: float
    session_type: str                 # "ESTIMATED_EFFORT", "QUIZ_SITTING", "RECOMMENDED_REVIEW"
    notes: str


@dataclass
class StudyScheduleDay:
    """A day in the 7-day study schedule."""

    date: date
    weekday_name: str
    available_hours: float
    allocated_hours: float
    sessions: List[StudyScheduleSession] = field(default_factory=list)

    @property
    def remaining_hours(self) -> float:
        return max(0.0, round(self.available_hours - self.allocated_hours, 1))

    @property
    def is_fully_booked(self) -> bool:
        return self.allocated_hours >= self.available_hours and self.available_hours > 0


@dataclass
class StudySchedule:
    """Complete 7-day suggested pacing schedule."""

    days: List[StudyScheduleDay]
    total_available_hours: float
    total_allocated_hours: float
    has_deficit: bool
    deficit_hours: float
    notes: List[str] = field(default_factory=list)


@dataclass
class WorkloadSummary:
    """Complete workload analysis for a student at a given reference time."""

    student_id: int
    student_name: str
    student_email: str
    reference_time: datetime

    # Preference State
    is_configured: bool               # True if StudentStudyBudget exists
    available_weekly_hours: Optional[float]

    # Overall Workload Classification
    workload_level: str               # "BALANCED", "MODERATE", "HEAVY", "CONFLICT"
    workload_label: str
    workload_badge_class: str         # UI styling token
    workload_description: str
    utilization_percentage: Optional[float]  # Effort required vs available hours (None if unconfigured)

    # Metrics
    total_pending_tasks: int
    total_completed_tasks: int
    total_overdue_tasks: int
    tasks_next_7_days: int
    total_known_effort_hours: float
    tasks_with_unestimated_effort: int
    tasks_with_actual_durations: int

    # Deliverables & Insights
    clusters: List[DeadlineCluster]
    prioritized_tasks: List[PlannerTask]
    completed_tasks: List[PlannerTask]
    schedule: Optional[StudySchedule]


class WorkloadPlannerService:
    """Deterministic, rule-based academic workload calculation service."""

    # Cluster detection window in hours
    CLUSTER_WINDOW_HOURS = 48

    # Workload classification ratio thresholds (when study hours are configured)
    THRESHOLD_BALANCED_RATIO = 0.40   # Effort <= 40% of available study time
    THRESHOLD_MODERATE_RATIO = 0.85   # 40% < Effort <= 85% of available study time
    THRESHOLD_HEAVY_RATIO = 1.25      # 85% < Effort <= 125% of available study time
    # Above 1.25 is CONFLICT

    @classmethod
    def get_student_workload(
        cls,
        student: User,
        reference_time: Optional[datetime] = None,
    ) -> WorkloadSummary:
        """Calculate the complete deterministic workload plan for a student."""
        now = reference_time or timezone.now()

        # 1. Fetch study budget preference if configured
        budget: Optional[StudentStudyBudget] = None
        try:
            budget = student.study_budget
        except (StudentStudyBudget.DoesNotExist, AttributeError):
            budget = None

        # 2. Collect all tasks across student's enrolled courses
        all_tasks = cls.collect_student_tasks(student, reference_time=now)

        # 3. Detect deadline clusters across pending, non-overdue tasks
        clusters = cls.detect_deadline_clusters(all_tasks, window_hours=cls.CLUSTER_WINDOW_HOURS)

        # 4. Rank tasks by priority and assign explanations
        prioritized_tasks, completed_tasks = cls.calculate_task_priorities(
            all_tasks,
            clusters,
            reference_time=now,
        )

        # 5. Classify workload level
        (
            workload_level,
            workload_label,
            badge_class,
            workload_desc,
            utilization_pct,
        ) = cls.classify_workload(
            prioritized_tasks,
            budget,
            clusters,
            reference_time=now,
            horizon_days=7,
        )

        # 6. Generate 7-day study schedule if budget is configured
        schedule = cls.generate_study_schedule(
            prioritized_tasks,
            budget,
            reference_time=now,
        )

        # 7. Compute aggregate metric counters
        pending_tasks = [t for t in prioritized_tasks if not t.is_completed]
        overdue_tasks = [t for t in pending_tasks if t.is_overdue]
        next_7_days_tasks = [
            t for t in pending_tasks
            if not t.is_overdue and t.days_remaining is not None and t.days_remaining <= 7.0
        ]

        total_known_effort = 0.0
        unestimated_count = 0
        actual_duration_count = 0

        for t in next_7_days_tasks:
            eff = t.effective_effort_hours
            if eff is not None:
                total_known_effort += eff
            else:
                unestimated_count += 1
            if t.has_actual_duration:
                actual_duration_count += 1

        total_known_effort = round(total_known_effort, 1)

        available_weekly = (
            float(budget.target_weekly_hours) if budget is not None else None
        )

        return WorkloadSummary(
            student_id=student.id,
            student_name=student.get_full_name,
            student_email=student.email,
            reference_time=now,
            is_configured=(budget is not None),
            available_weekly_hours=available_weekly,
            workload_level=workload_level,
            workload_label=workload_label,
            workload_badge_class=badge_class,
            workload_description=workload_desc,
            utilization_percentage=utilization_pct,
            total_pending_tasks=len(pending_tasks),
            total_completed_tasks=len(completed_tasks),
            total_overdue_tasks=len(overdue_tasks),
            tasks_next_7_days=len(next_7_days_tasks),
            total_known_effort_hours=total_known_effort,
            tasks_with_unestimated_effort=unestimated_count,
            tasks_with_actual_durations=actual_duration_count,
            clusters=clusters,
            prioritized_tasks=prioritized_tasks,
            completed_tasks=completed_tasks,
            schedule=schedule,
        )

    @classmethod
    def collect_student_tasks(
        cls,
        student: User,
        reference_time: Optional[datetime] = None,
    ) -> List[PlannerTask]:
        """Extract all Assignment and Quiz deliverables for the student's active enrollments."""
        now = reference_time or timezone.now()

        # Find active course registrations
        enrollments = StudentEnrollment.objects.filter(
            student=student,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        ).select_related("course")

        enrolled_courses = [e.course for e in enrollments]
        if not enrolled_courses:
            return []

        tasks: List[PlannerTask] = []

        # -------------------------------------------------------------
        # A. Collect Assignments
        # -------------------------------------------------------------
        assignments = Assignment.objects.filter(
            course__in=enrolled_courses,
            is_published=True,
            is_active=True,
        ).select_related("course")

        for a in assignments:
            # Check if student has submitted
            sub = AssignmentSubmission.objects.filter(
                assignment=a,
                student=student,
                is_active=True,
            ).first()

            is_completed = sub is not None and sub.status in [
                AssignmentSubmission.SubmissionStatus.SUBMITTED,
                AssignmentSubmission.SubmissionStatus.GRADED,
            ]
            completion_status = sub.status if sub else "PENDING"

            # Check deadline proximity
            deadline = a.due_date
            is_overdue = False
            days_rem = None
            hours_rem = None

            if deadline:
                delta_sec = (deadline - now).total_seconds()
                days_rem = round(delta_sec / 86400.0, 2)
                hours_rem = round(delta_sec / 3600.0, 1)
                if delta_sec < 0 and not is_completed:
                    is_overdue = True

            effort = float(a.estimated_effort_hours) if a.estimated_effort_hours is not None else None

            tasks.append(
                PlannerTask(
                    task_id=f"assignment_{a.id}",
                    source_id=a.id,
                    task_type="ASSIGNMENT",
                    title=a.title,
                    course_id=a.course.id,
                    course_code=a.course.code,
                    course_title=a.course.title,
                    course_credits=getattr(a.course, "credits", 3),
                    deadline=deadline,
                    start_date=a.created_at,
                    actual_duration_minutes=None,
                    estimated_effort_hours=effort,
                    is_completed=is_completed,
                    completion_status=completion_status,
                    is_overdue=is_overdue,
                    days_remaining=days_rem,
                    hours_remaining=hours_rem,
                )
            )

        # -------------------------------------------------------------
        # B. Collect Quizzes
        # -------------------------------------------------------------
        quizzes = Quiz.objects.filter(
            course__in=enrolled_courses,
            status=QuizStatus.PUBLISHED,
            is_active=True,
        ).select_related("course")

        for q in quizzes:
            # Check student attempt history
            attempts = QuizAttempt.objects.filter(quiz=q, student=student)
            finished_attempt = attempts.filter(
                status__in=[AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED]
            ).first()

            is_completed = finished_attempt is not None
            if is_completed:
                completion_status = finished_attempt.status
            elif attempts.count() >= q.max_attempts:
                is_completed = True
                completion_status = "ATTEMPTS_EXHAUSTED"
            else:
                completion_status = "PENDING"

            deadline = q.available_to
            is_overdue = False
            days_rem = None
            hours_rem = None

            if deadline:
                delta_sec = (deadline - now).total_seconds()
                days_rem = round(delta_sec / 86400.0, 2)
                hours_rem = round(delta_sec / 3600.0, 1)
                if delta_sec < 0 and not is_completed:
                    is_overdue = True

            effort = float(q.estimated_effort_hours) if q.estimated_effort_hours is not None else None

            tasks.append(
                PlannerTask(
                    task_id=f"quiz_{q.id}",
                    source_id=q.id,
                    task_type="QUIZ",
                    title=q.title,
                    course_id=q.course.id,
                    course_code=q.course.code,
                    course_title=q.course.title,
                    course_credits=getattr(q.course, "credits", 3),
                    deadline=deadline,
                    start_date=q.available_from,
                    actual_duration_minutes=q.duration_minutes,
                    estimated_effort_hours=effort,
                    is_completed=is_completed,
                    completion_status=completion_status,
                    is_overdue=is_overdue,
                    days_remaining=days_rem,
                    hours_remaining=hours_rem,
                )
            )

        return tasks

    @classmethod
    def detect_deadline_clusters(
        cls,
        tasks: List[PlannerTask],
        window_hours: int = 48,
    ) -> List[DeadlineCluster]:
        """Detect clusters of 2 or more pending deliverables due within window_hours of each other."""
        # Only pending, non-overdue tasks with defined deadlines can cluster
        valid_tasks = [
            t for t in tasks
            if not t.is_completed and not t.is_overdue and t.deadline is not None
        ]

        if len(valid_tasks) < 2:
            return []

        # Sort chronologically by deadline
        sorted_tasks = sorted(valid_tasks, key=lambda t: t.deadline)
        clusters: List[DeadlineCluster] = []
        cluster_counter = 1

        window_delta = timedelta(hours=window_hours)
        used_task_ids = set()

        for i in range(len(sorted_tasks)):
            current = sorted_tasks[i]
            if current.task_id in used_task_ids:
                continue

            # Group all upcoming tasks within window_delta of current.deadline
            grouped = [current]
            for j in range(i + 1, len(sorted_tasks)):
                candidate = sorted_tasks[j]
                if candidate.deadline - current.deadline <= window_delta:
                    grouped.append(candidate)

            if len(grouped) >= 2:
                for t in grouped:
                    used_task_ids.add(t.task_id)

                start_time = grouped[0].deadline
                end_time = grouped[-1].deadline
                span_hours = round((end_time - start_time).total_seconds() / 3600.0, 1)

                task_count = len(grouped)
                if task_count >= 4:
                    severity = "CRITICAL"
                elif task_count == 3:
                    severity = "HEAVY"
                else:
                    severity = "MODERATE"

                c_id = f"cluster_{cluster_counter}"
                cluster_counter += 1

                for t in grouped:
                    t.is_in_cluster = True
                    t.cluster_id = c_id
                    t.cluster_severity = severity

                titles_str = ", ".join([f"{t.course_code}: {t.title}" for t in grouped])
                desc = (
                    f"{task_count} deliverables due within {span_hours}h "
                    f"({start_time.strftime('%b %d, %H:%M')} – {end_time.strftime('%b %d, %H:%M')})"
                )

                clusters.append(
                    DeadlineCluster(
                        cluster_id=c_id,
                        task_ids=[t.task_id for t in grouped],
                        task_titles=[t.title for t in grouped],
                        start_time=start_time,
                        end_time=end_time,
                        span_hours=span_hours,
                        task_count=task_count,
                        severity=severity,
                        description=desc,
                    )
                )

        return clusters

    @classmethod
    def calculate_task_priorities(
        cls,
        tasks: List[PlannerTask],
        clusters: List[DeadlineCluster],
        reference_time: datetime,
    ) -> Tuple[List[PlannerTask], List[PlannerTask]]:
        """Compute deterministic priority scores and transparent justifications for all tasks."""
        pending: List[PlannerTask] = []
        completed: List[PlannerTask] = []

        for t in tasks:
            if t.is_completed:
                t.priority_score = 0
                t.priority_level = "COMPLETED"
                t.priority_explanation = (
                    f"Completed ({t.completion_status.replace('_', ' ').title()}). "
                    f"Excluded from active study workload."
                )
                completed.append(t)
                continue

            if t.is_overdue:
                t.priority_score = 110
                t.priority_level = "OVERDUE"
                days_past = abs(t.days_remaining) if t.days_remaining is not None else 0.0
                t.priority_explanation = (
                    f"Deadline passed {days_past:.1f} days ago. "
                    f"Immediate attention required: late submission or expired sitting."
                )
                pending.append(t)
                continue

            if t.deadline is None:
                t.priority_score = 10
                t.priority_level = "UNSCHEDULED"
                t.priority_explanation = (
                    "No fixed deadline published by instructor. Work at a steady self-directed pace."
                )
                pending.append(t)
                continue

            # Deterministic scoring for pending tasks with deadlines
            score = 0
            explanation_parts: List[str] = []

            # 1. Proximity component
            days = t.days_remaining
            if days <= 1.0:
                score += 85
                explanation_parts.append(f"Due in {t.hours_remaining:.0f} hours (Critical Proximity)")
            elif days <= 3.0:
                score += 65
                explanation_parts.append(f"Due in {days:.1f} days (Immediate Window)")
            elif days <= 7.0:
                score += 45
                explanation_parts.append(f"Due in {days:.1f} days (Upcoming Week)")
            else:
                score += 20
                explanation_parts.append(f"Due in {days:.1f} days (Long-Range)")

            # 2. Cluster impact
            if t.is_in_cluster:
                if t.cluster_severity == "CRITICAL":
                    score += 20
                    explanation_parts.append("In critical 4+ task deadline conflict")
                elif t.cluster_severity == "HEAVY":
                    score += 15
                    explanation_parts.append("In 3-task overlapping deadline cluster")
                else:
                    score += 10
                    explanation_parts.append("Overlaps with another deliverable within 48h")

            # 3. Known effort / duration weight
            eff = t.effective_effort_hours
            if eff is not None:
                if eff >= 6.0:
                    score += 10
                    explanation_parts.append(f"High required effort: {eff}h")
                elif eff >= 3.0:
                    score += 5
                    explanation_parts.append(f"Moderate effort: {eff}h")
                elif eff < 1.0 and t.task_type == "QUIZ":
                    explanation_parts.append(f"Quiz sitting duration: {t.actual_duration_minutes} min")
            else:
                explanation_parts.append("Effort unestimated by lecturer")

            # 4. Course credit minor tie-breaker (max +6)
            credit_boost = min(t.course_credits, 6)
            score += credit_boost

            # Map total score to priority tier
            if score >= 85:
                level = "CRITICAL"
            elif score >= 65:
                level = "HIGH"
            elif score >= 45:
                level = "MEDIUM"
            else:
                level = "LOW"

            t.priority_score = score
            t.priority_level = level
            t.priority_explanation = "; ".join(explanation_parts) + "."
            pending.append(t)

        # Sort pending tasks deterministically:
        # Highest score first -> Earliest deadline -> Course code -> Title
        far_future = reference_time + timedelta(days=3650)
        pending.sort(
            key=lambda item: (
                -item.priority_score,
                item.deadline if item.deadline else far_future,
                item.course_code,
                item.title,
            )
        )

        # Completed tasks sorted by deadline descending
        completed.sort(
            key=lambda item: (
                item.deadline if item.deadline else reference_time,
                item.course_code,
            ),
            reverse=True,
        )

        return pending, completed

    @classmethod
    def classify_workload(
        cls,
        pending_tasks: List[PlannerTask],
        budget: Optional[StudentStudyBudget],
        clusters: List[DeadlineCluster],
        reference_time: datetime,
        horizon_days: int = 7,
    ) -> Tuple[str, str, str, str, Optional[float]]:
        """Classify workload as BALANCED, MODERATE, HEAVY, or CONFLICT using deterministic rules."""
        # Active tasks due within planning horizon
        horizon_tasks = [
            t for t in pending_tasks
            if not t.is_overdue and t.days_remaining is not None and t.days_remaining <= horizon_days
        ]

        task_count = len(horizon_tasks)
        max_cluster_size = max([c.task_count for c in clusters], default=0)

        # -------------------------------------------------------------
        # Branch A: Student has configured study availability
        # -------------------------------------------------------------
        if budget is not None:
            weekly_available = float(budget.target_weekly_hours)
            total_known_effort = sum(
                [t.effective_effort_hours for t in horizon_tasks if t.effective_effort_hours is not None]
            )

            if weekly_available > 0:
                ratio = round(total_known_effort / weekly_available, 2)
                utilization_pct = round(ratio * 100.0, 1)
            else:
                ratio = 999.0
                utilization_pct = 999.0

            # Rule 1: CONFLICT
            if (
                ratio > cls.THRESHOLD_HEAVY_RATIO  # > 1.25 (exceeds budget by >25%)
                or max_cluster_size >= 4
                or (max_cluster_size >= 3 and ratio > 1.0)
            ):
                return (
                    "CONFLICT",
                    "Conflict",
                    "badge-academic-danger",
                    (
                        f"Workload Conflict: Required effort ({total_known_effort}h) exceeds "
                        f"available study budget ({weekly_available}h) by "
                        f"{max(0.0, round(total_known_effort - weekly_available, 1))}h "
                        f"({utilization_pct}% capacity), or {max_cluster_size} overlapping deadlines clash."
                    ),
                    utilization_pct,
                )

            # Rule 2: HEAVY
            if (
                ratio > cls.THRESHOLD_MODERATE_RATIO  # 0.85 < ratio <= 1.25
                or max_cluster_size == 3
                or task_count >= 4
            ):
                return (
                    "HEAVY",
                    "Heavy",
                    "badge-academic-warning",
                    (
                        f"Heavy Workload: {task_count} deliverables due in next {horizon_days} days "
                        f"utilizing {utilization_pct}% of available study capacity "
                        f"({total_known_effort}h of {weekly_available}h). Early pacing recommended."
                    ),
                    utilization_pct,
                )

            # Rule 3: MODERATE
            if (
                ratio > cls.THRESHOLD_BALANCED_RATIO  # 0.40 < ratio <= 0.85
                or max_cluster_size == 2
                or task_count in (2, 3)
            ):
                return (
                    "MODERATE",
                    "Moderate",
                    "badge-academic-info",
                    (
                        f"Moderate Workload: {task_count} upcoming tasks scheduled at "
                        f"{utilization_pct}% capacity ({total_known_effort}h of {weekly_available}h). "
                        f"Pacing is on track."
                    ),
                    utilization_pct,
                )

            # Rule 4: BALANCED
            return (
                "BALANCED",
                "Balanced",
                "badge-academic-success",
                (
                    f"Balanced Workload: {task_count} task(s) scheduled. "
                    f"Ample available study time ({utilization_pct}% capacity utilization; "
                    f"{weekly_available - total_known_effort:.1f}h surplus)."
                ),
                utilization_pct,
            )

        # -------------------------------------------------------------
        # Branch B: Student has NOT configured study availability
        # We do NOT guess or invent free time.
        # Categorization is based deterministically on task counts & cluster density.
        # -------------------------------------------------------------
        if task_count >= 5 or max_cluster_size >= 4:
            return (
                "CONFLICT",
                "Conflict",
                "badge-academic-danger",
                (
                    f"Schedule Conflict: High deliverable density ({task_count} tasks due within "
                    f"{horizon_days} days, with an overlapping cluster of {max_cluster_size} tasks). "
                    f"Configure your weekly study hours to compute personal time utilization."
                ),
                None,
            )

        if task_count in (3, 4) or max_cluster_size == 3:
            return (
                "HEAVY",
                "Heavy",
                "badge-academic-warning",
                (
                    f"Heavy Workload: {task_count} deliverables due within {horizon_days} days. "
                    f"Configure your weekly study hours to receive a day-by-day study schedule."
                ),
                None,
            )

        if task_count == 2 or max_cluster_size == 2:
            return (
                "MODERATE",
                "Moderate",
                "badge-academic-info",
                (
                    f"Moderate Workload: {task_count} upcoming deliverables scheduled. "
                    f"Configure study availability for customized pacing recommendations."
                ),
                None,
            )

        return (
            "BALANCED",
            "Balanced",
            "badge-academic-success",
            (
                f"Balanced Workload: {task_count} pending deliverable(s) due within {horizon_days} days "
                f"with no overlapping clusters detected."
            ),
            None,
        )

    @classmethod
    def generate_study_schedule(
        cls,
        pending_tasks: List[PlannerTask],
        budget: Optional[StudentStudyBudget],
        reference_time: datetime,
    ) -> Optional[StudySchedule]:
        """Build a deterministic 7-day study allocation calendar.

        Returns None if the student has not configured their weekly study budget,
        strictly respecting the requirement not to assume or invent free time.
        """
        if budget is None:
            return None

        # Filter active tasks with defined deadlines
        valid_tasks = [
            t for t in pending_tasks
            if not t.is_completed and not t.is_overdue and t.deadline is not None
        ]

        # Remaining effort tracking per task
        task_remaining_hours: Dict[str, float] = {}
        for t in valid_tasks:
            eff = t.effective_effort_hours
            task_remaining_hours[t.task_id] = eff if eff is not None else 2.0

        days: List[StudyScheduleDay] = []
        total_avail = 0.0
        total_alloc = 0.0

        weekday_names = [
            "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
        ]

        # Build 7-day projection starting from reference_time.date()
        start_date = reference_time.date()

        for day_offset in range(7):
            cur_date = start_date + timedelta(days=day_offset)
            weekday_idx = cur_date.weekday()  # 0 = Monday ... 6 = Sunday
            avail_hours = float(budget.get_hours_for_weekday(weekday_idx))
            total_avail += avail_hours

            day_obj = StudyScheduleDay(
                date=cur_date,
                weekday_name=weekday_names[weekday_idx],
                available_hours=avail_hours,
                allocated_hours=0.0,
            )

            # Allocate daily study blocks to highest priority tasks due on or after cur_date
            remaining_daily = avail_hours

            for t in valid_tasks:
                if remaining_daily <= 0.0:
                    break

                # Task must not be due before the start of this day
                if t.deadline.date() < cur_date:
                    continue

                needed = task_remaining_hours.get(t.task_id, 0.0)
                if needed <= 0.0:
                    continue

                # Allocate up to available time or 2.0h max block
                block = min(remaining_daily, needed, 2.0)
                block = round(block, 1)

                if block <= 0.0:
                    continue

                # Session labeling
                if t.has_estimated_effort:
                    sess_type = "ESTIMATED_EFFORT"
                    note = f"Pacing toward estimated {t.estimated_effort_hours}h effort"
                elif t.task_type == "QUIZ":
                    sess_type = "QUIZ_SITTING"
                    note = f"Quiz preparation ({t.actual_duration_minutes}m duration)"
                else:
                    sess_type = "RECOMMENDED_REVIEW"
                    note = "Recommended study block (effort unestimated by lecturer)"

                day_obj.sessions.append(
                    StudyScheduleSession(
                        task_id=t.task_id,
                        task_title=t.title,
                        course_code=t.course_code,
                        allocated_hours=block,
                        session_type=sess_type,
                        notes=note,
                    )
                )

                day_obj.allocated_hours = round(day_obj.allocated_hours + block, 1)
                remaining_daily = round(remaining_daily - block, 1)
                task_remaining_hours[t.task_id] = round(needed - block, 1)
                total_alloc = round(total_alloc + block, 1)

            days.append(day_obj)

        # Detect time deficit
        total_required_effort = sum(
            [t.effective_effort_hours for t in valid_tasks if t.effective_effort_hours is not None]
        )
        has_deficit = total_required_effort > total_avail
        deficit_hours = max(0.0, round(total_required_effort - total_avail, 1))

        notes: List[str] = []
        if has_deficit:
            notes.append(
                f"Deficit Alert: Required effort across active tasks ({total_required_effort:.1f}h) "
                f"exceeds your available 7-day study budget ({total_avail:.1f}h) by {deficit_hours:.1f}h. "
                f"Consider adjusting daily availability or prioritizing the highest-urgency tasks."
            )
        else:
            notes.append(
                f"Pacing Confirmed: All scheduled study blocks fit within your {total_avail:.1f}h "
                f"weekly study budget with {total_avail - total_alloc:.1f}h buffer."
            )

        return StudySchedule(
            days=days,
            total_available_hours=round(total_avail, 1),
            total_allocated_hours=round(total_alloc, 1),
            has_deficit=has_deficit,
            deficit_hours=deficit_hours,
            notes=notes,
        )

    @classmethod
    def get_course_workload(
        cls,
        course: Course,
        reference_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Aggregate course-level deliverable clusters and submission statistics for lecturers.

        Strictly does NOT expose any individual student's private study budget or preferences.
        """
        now = reference_time or timezone.now()

        # Enrolled students count
        enrollment_count = StudentEnrollment.objects.filter(
            course=course,
            status=EnrollmentStatus.ENROLLED,
            is_active=True,
        ).count()

        # Collect course assignments
        assignments = Assignment.objects.filter(
            course=course,
            is_active=True,
        ).order_by("due_date")

        # Collect course quizzes
        quizzes = Quiz.objects.filter(
            course=course,
            is_active=True,
        ).order_by("available_to")

        deliverables: List[Dict[str, Any]] = []

        for a in assignments:
            submissions_count = AssignmentSubmission.objects.filter(
                assignment=a,
                is_active=True,
            ).count()

            is_overdue = (a.due_date < now) if a.due_date else False

            deliverables.append({
                "type": "ASSIGNMENT",
                "id": a.id,
                "title": a.title,
                "due_date": a.due_date,
                "estimated_effort_hours": a.estimated_effort_hours,
                "is_published": a.is_published,
                "submissions_count": submissions_count,
                "pending_count": max(0, enrollment_count - submissions_count),
                "is_overdue": is_overdue,
            })

        for q in quizzes:
            attempts_count = QuizAttempt.objects.filter(
                quiz=q,
                status__in=[AttemptStatus.SUBMITTED, AttemptStatus.COMPLETED],
            ).values("student_id").distinct().count()

            is_overdue = (q.available_to < now) if q.available_to else False

            deliverables.append({
                "type": "QUIZ",
                "id": q.id,
                "title": q.title,
                "due_date": q.available_to,
                "duration_minutes": q.duration_minutes,
                "estimated_effort_hours": q.estimated_effort_hours,
                "is_published": q.is_published,
                "submissions_count": attempts_count,
                "pending_count": max(0, enrollment_count - attempts_count),
                "is_overdue": is_overdue,
            })

        # Detect internal deliverable clashes within this course
        deliverables.sort(key=lambda d: d["due_date"] if d["due_date"] else now + timedelta(days=365))
        internal_clusters = []

        window_delta = timedelta(hours=cls.CLUSTER_WINDOW_HOURS)
        for i in range(len(deliverables)):
            d1 = deliverables[i]
            if not d1["due_date"] or d1["is_overdue"]:
                continue
            grouped = [d1]
            for j in range(i + 1, len(deliverables)):
                d2 = deliverables[j]
                if d2["due_date"] and (d2["due_date"] - d1["due_date"] <= window_delta):
                    grouped.append(d2)
            if len(grouped) >= 2:
                internal_clusters.append({
                    "count": len(grouped),
                    "titles": [g["title"] for g in grouped],
                    "span_hours": round(
                        (grouped[-1]["due_date"] - grouped[0]["due_date"]).total_seconds() / 3600.0, 1
                    ),
                })

        return {
            "course": course,
            "enrollment_count": enrollment_count,
            "deliverables": deliverables,
            "deliverable_count": len(deliverables),
            "internal_clusters": internal_clusters,
            "reference_time": now,
        }
