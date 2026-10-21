"""Create generic, privacy-safe demo accounts for development environments."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import (
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
    RelationshipType,
    Role,
    StudentProfile,
    User,
)


DEMO_ACCOUNTS = (
    {
        "key": "admin",
        "role": Role.ADMIN,
        "username": "admin1",
        "legacy_username": "admin123",
        "email": "admin1@example.com",
        "label": "Administrator 1",
    },
    {
        "key": "lecturer",
        "role": Role.LECTURER,
        "username": "lecturer1",
        "legacy_username": "lecturer123",
        "email": "lecturer1@example.com",
        "label": "Lecturer 1",
    },
    {
        "key": "student",
        "role": Role.STUDENT,
        "username": "student1",
        "legacy_username": "student123",
        "email": "student1@example.com",
        "label": "Student 1",
    },
    {
        "key": "parent",
        "role": Role.PARENT,
        "username": "parent1",
        "legacy_username": "parent123",
        "email": "parent1@example.com",
        "label": "Parent 1",
    },
)


class Command(BaseCommand):
    help = "Seed generic development demo accounts for the four application roles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reset passwords for existing demo accounts to the development password.",
        )

    def handle(self, *args, **options):
        if not getattr(settings, "DEBUG", False):
            raise CommandError("Refusing to seed demo accounts while DEBUG is disabled.")
        environment = getattr(settings, "ENVIRONMENT", "development")
        if environment.lower() in {"prod", "production"}:
            raise CommandError("Refusing to seed demo accounts in a production environment.")

        with transaction.atomic():
            users = {}
            created_users = set()
            for account in DEMO_ACCOUNTS:
                user, created = self._get_or_create_demo_user(account)
                if user.role != account["role"]:
                    raise CommandError(
                        f"Cannot reconcile {account['key']} demo account: "
                        "matching account has a different role."
                    )
                user.username = account["username"]
                user.email = account["email"]
                user.first_name = account["label"]
                user.last_name = ""
                user.role = account["role"]
                user.is_staff = account["role"] == Role.ADMIN
                user.is_superuser = account["role"] == Role.ADMIN
                user.is_active = True
                if created or options["force"]:
                    user.set_password("password")
                user.save()
                users[account["key"]] = user
                if created:
                    created_users.add(account["key"])

            lecturer_profile, _ = LecturerProfile.objects.get_or_create(
                user=users["lecturer"],
                defaults={
                    "employee_id": "LEC-DEMO-001",
                    "department": "Computer Science",
                    "office_location": "",
                    "phone": "",
                },
            )
            lecturer_profile.phone = ""
            lecturer_profile.save(update_fields=["phone", "updated_at"])

            student_profile, _ = StudentProfile.objects.get_or_create(
                user=users["student"],
                defaults={
                    "student_id": "STD-DEMO-001",
                    "program": "Software Engineering",
                    "current_semester": "",
                    "phone": "",
                    "emergency_contact": "",
                },
            )
            student_profile.phone = ""
            student_profile.emergency_contact = ""
            student_profile.date_of_birth = None
            student_profile.save(
                update_fields=["phone", "emergency_contact", "date_of_birth", "updated_at"]
            )

            parent_profile, _ = ParentProfile.objects.get_or_create(user=users["parent"])
            parent_profile.phone = ""
            parent_profile.address = ""
            parent_profile.save(update_fields=["phone", "address", "updated_at"])

            ParentStudentRelationship.objects.get_or_create(
                parent=users["parent"],
                student=users["student"],
                defaults={"relationship_type": RelationshipType.GUARDIAN},
            )

        self.stdout.write(
            self.style.SUCCESS(
                "Demo accounts are ready: "
                + ", ".join(
                    f"{account['label']} ({'created' if account['key'] in created_users else 'updated'})"
                    for account in DEMO_ACCOUNTS
                )
            )
        )

    @staticmethod
    def _get_or_create_demo_user(account):
        candidates = User.objects.filter(
            Q(username=account["legacy_username"])
            | Q(username=account["username"])
            | Q(email=account["email"])
        ).distinct()
        matches = list(candidates)
        if len(matches) > 1:
            raise CommandError(
                f"Cannot safely reconcile {account['key']} demo account: "
                "multiple matching accounts exist."
            )
        if matches:
            return matches[0], False
        return User.objects.create_user(
            username=account["username"],
            email=account["email"],
            password="password",
            role=account["role"],
            first_name=account["label"],
        ), True
