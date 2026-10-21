"""Management command to populate development demo accounts for Academic LMS.

Strictly idempotent and restricted to development environments.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import (
    User,
    Role,
    StudentProfile,
    LecturerProfile,
    ParentProfile,
    ParentStudentRelationship,
    RelationshipType,
)


class Command(BaseCommand):
    help = "Seed development demo accounts for Admin, Lecturer, Student, and Parent roles."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force seeding even if demo users already exist (will update passwords and profile data).",
        )

    def handle(self, *args, **options):
        # Production safeguard: Strictly refuse execution if DEBUG is False
        if not getattr(settings, "DEBUG", False):
            raise CommandError(
                "Refusing to seed demo accounts: DEBUG is set to False. "
                "This command is strictly disabled in production environments."
            )

        # Environment check safeguard
        env_mode = getattr(settings, "ENVIRONMENT", "development")
        if env_mode.lower() in ["prod", "production"]:
            raise CommandError(
                f"Refusing to seed demo accounts: ENVIRONMENT is '{env_mode}'. "
                "Demo seeding is prohibited on production systems."
            )

        self.stdout.write(self.style.MIGRATE_HEADING("Seeding Academic LMS demo accounts..."))

        demo_password = "password"

        # 1. Administrator Account
        admin_user, created = User.objects.get_or_create(
            email="admin@gmail.com",
            defaults={
                "username": "admin123",
                "first_name": "System",
                "last_name": "Administrator",
                "role": Role.ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        admin_user.username = "admin123"
        admin_user.first_name = "System"
        admin_user.last_name = "Administrator"
        admin_user.role = Role.ADMIN
        admin_user.is_staff = True
        admin_user.is_superuser = True
        admin_user.is_active = True
        admin_user.set_password(demo_password)
        admin_user.save()
        status_admin = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"  [{status_admin}] Admin: admin@gmail.com (admin123)"))

        # 2. Lecturer Account
        lecturer_user, created = User.objects.get_or_create(
            email="lecturer@gmail.com",
            defaults={
                "username": "lecturer123",
                "first_name": "Arthur",
                "last_name": "Pendelton",
                "role": Role.LECTURER,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        lecturer_user.username = "lecturer123"
        lecturer_user.first_name = "Arthur"
        lecturer_user.last_name = "Pendelton"
        lecturer_user.role = Role.LECTURER
        lecturer_user.is_staff = False
        lecturer_user.is_superuser = False
        lecturer_user.is_active = True
        lecturer_user.set_password(demo_password)
        lecturer_user.save()

        lecturer_profile, _ = LecturerProfile.objects.get_or_create(
            user=lecturer_user,
            defaults={
                "employee_id": "LEC-2026-001",
                "department": "Computer Science & Engineering",
                "office_location": "Science Hall Room 304",
                "phone": "+1 (555) 234-5678",
            },
        )
        lecturer_profile.employee_id = "LEC-2026-001"
        lecturer_profile.department = "Computer Science & Engineering"
        lecturer_profile.office_location = "Science Hall Room 304"
        lecturer_profile.phone = "+1 (555) 234-5678"
        lecturer_profile.save()
        status_lec = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"  [{status_lec}] Lecturer: lecturer@gmail.com (lecturer123)"))

        # 3. Student Account
        student_user, created = User.objects.get_or_create(
            email="student@gmail.com",
            defaults={
                "username": "student123",
                "first_name": "Julian",
                "last_name": "Mercer",
                "role": Role.STUDENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        student_user.username = "student123"
        student_user.first_name = "Julian"
        student_user.last_name = "Mercer"
        student_user.role = Role.STUDENT
        student_user.is_staff = False
        student_user.is_superuser = False
        student_user.is_active = True
        student_user.set_password(demo_password)
        student_user.save()

        student_profile, _ = StudentProfile.objects.get_or_create(
            user=student_user,
            defaults={
                "student_id": "STD-2026-0001",
                "program": "B.Sc. Software Engineering",
                "current_semester": "Fall 2026",
                "phone": "+1 (555) 345-6789",
                "emergency_contact": "Eleanor Mercer (Mother) +1 (555) 456-7890",
            },
        )
        student_profile.student_id = "STD-2026-0001"
        student_profile.program = "B.Sc. Software Engineering"
        student_profile.current_semester = "Fall 2026"
        student_profile.phone = "+1 (555) 345-6789"
        student_profile.emergency_contact = "Eleanor Mercer (Mother) +1 (555) 456-7890"
        student_profile.save()
        status_std = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"  [{status_std}] Student: student@gmail.com (student123)"))

        # 4. Parent Account
        parent_user, created = User.objects.get_or_create(
            email="parent@gmail.com",
            defaults={
                "username": "parent123",
                "first_name": "Eleanor",
                "last_name": "Mercer",
                "role": Role.PARENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )
        parent_user.username = "parent123"
        parent_user.first_name = "Eleanor"
        parent_user.last_name = "Mercer"
        parent_user.role = Role.PARENT
        parent_user.is_staff = False
        parent_user.is_superuser = False
        parent_user.is_active = True
        parent_user.set_password(demo_password)
        parent_user.save()

        parent_profile, _ = ParentProfile.objects.get_or_create(
            user=parent_user,
            defaults={
                "phone": "+1 (555) 456-7890",
                "address": "42 Elm Crest Avenue, Campus Town",
            },
        )
        parent_profile.phone = "+1 (555) 456-7890"
        parent_profile.address = "42 Elm Crest Avenue, Campus Town"
        parent_profile.save()
        status_par = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"  [{status_par}] Parent: parent@gmail.com (parent123)"))

        # 5. Parent-Student Relationship Linkage
        rel, rel_created = ParentStudentRelationship.objects.get_or_create(
            parent=parent_user,
            student=student_user,
            defaults={"relationship_type": RelationshipType.MOTHER},
        )
        rel.relationship_type = RelationshipType.MOTHER
        rel.save()
        status_rel = "Created" if rel_created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"  [{status_rel}] Linked Parent ({parent_user.email}) -> Student ({student_user.email}) as Mother"
            )
        )

        self.stdout.write(
            self.style.SUCCESS(
                "\nDemo accounts seeded successfully! All accounts configured with predictable development passwords."
            )
        )
