# Academic LMS

Academic LMS is a role based learning and academic management application for administrators, lecturers, students, and parents or guardians. It brings course records, learning resources, quizzes, an academic calendar, and a deterministic workload planner into one Django project.

This README describes the code currently in this repository. Some registered Django apps and documents are scaffolding or plans; they are identified as such below rather than described as finished features.

## Problem and objectives

The project provides a shared place to manage academic course structures and learning activities while limiting access to a user's role, course allocations, enrollments, and explicit parent-student links. The planner summarizes upcoming assignment and quiz work using visible rules; it does not use an AI service.

## Implemented features

- Email-based sign-in, role-specific dashboards, profile editing, and password change/reset views.
- Admin-managed users, role profiles, parent-student relationships, departments, programs, academic years, semesters, courses, allocations, and enrollments.
- Academic events and a calendar with month, week, and list views, plus role-scoped course events.
- Course modules and learning resources, including file and external-link validation, access checks, and downloads.
- Quizzes with question authoring, timed attempts, automatic objective-question grading, short-answer review, and result views.
- A deterministic workload planner that prioritizes assignment and quiz deadlines, identifies close deadline clusters, and produces a seven-day plan when a student sets study availability.
- Django Admin registrations for accounts, academics, courseware, quizzes, and related records. The Admin uses an isolated brown-and-cream stylesheet.
- Automated Django tests and GitHub Actions workflows for system checks, migration consistency, tests, and Pylint.

Assignment and submission data models are present and used by dashboard/planner queries. The current URL configuration does not expose a complete student assignment-submission workflow. The registered `attendance`, `discussions`, `gradebook`, `notifications`, and `reporting` apps are placeholders; attendance tracking, forums, GPA/transcripts, notification delivery, and report exports are not implemented.

## Roles and access

| Role | Current access |
| --- | --- |
| Administrator | Staff/superuser access to Django Admin and institutional dashboard. Admin registrations cover users, role profiles, relationship links, academic structure, courseware, quizzes, questions, attempts, and answers. |
| Lecturer | Courseware and quiz authoring/grading for courses allocated to the lecturer; lecturer dashboard and course workload summaries. |
| Student | Own profile and dashboard, resources for enrolled courses, published quizzes and own results, and own workload preferences/plan. Enrollment records are managed through the Admin; there is no self-service enrollment route. |
| Parent | Read-only information for students explicitly linked to the parent account, including permitted course resources, published quiz results, deadlines, and workload summaries. |

These are application-level checks in views and permission helpers as well as Django Admin's staff/permission checks. A parent link is required for student-specific observer access.

## Technology and supported versions

- Python: GitHub Actions runs Python 3.11, 3.12, and 3.13. This checkout was also exercised locally with Python 3.14.7; that version is not in the CI matrix.
- Django: `>=5.2,<5.3`.
- Database: SQLite in `config.settings.development`; PostgreSQL configuration in `config.settings.production`.
- UI: Django templates, Bootstrap 5.3, Font Awesome 6.5, vanilla JavaScript, and project CSS. Admin-only styles are in `static/css/admin.css`.
- Other runtime dependencies are declared in `requirements/base.txt`; CI uses the hash-locked `requirements/ci.txt` generated from `requirements/ci.in`.
- Production-only packages, including Gunicorn and the PostgreSQL adapter, are in `requirements/prod.txt`.

The base requirements are version ranges rather than a complete lockfile. CI dependencies are pinned and hash-checked.

## Architecture and project layout

```text
academic_lms/
├── apps/
│   ├── accounts/       # Custom user, profiles, authentication, role access
│   ├── academics/      # Departments, programs, years, semesters, courses
│   ├── assessments/    # Assignment and submission models; quiz model facade
│   ├── core/           # Landing page, academic events, calendar
│   ├── courseware/     # Modules, learning resources, upload validation
│   ├── quizzes/        # Quiz models, authoring, attempts, grading, results
│   ├── planner/        # Study budget and workload planning service
│   ├── attendance/     # Placeholder app
│   ├── discussions/    # Placeholder app
│   ├── gradebook/      # Placeholder app
│   ├── notifications/ # Placeholder app
│   └── reporting/      # Placeholder app
├── config/settings/    # Shared, development, and production settings
├── requirements/       # Runtime, development, production, and CI inputs
├── static/             # CSS and JavaScript
├── templates/          # Shared, role, feature, and Admin templates
├── docs/               # Requirements, architecture, role matrix, roadmap
├── manage.py
└── README.md
```

The request path is configured in `config/urls.py`, which mounts account, courseware, quiz, planner, and core URLs. `assessments` models are currently consumed by dashboards and the planner; they do not have their own URL module.

## Prerequisites

- Python 3.11 or newer; CI coverage is specifically 3.11–3.13.
- Git.
- For production database configuration, PostgreSQL and the adapter from `requirements/prod.txt`.

## Local setup

From the `academic_lms` directory, in PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env` for local use. Generate a unique Django key with:

```powershell
.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Put the generated value in your ignored `.env` file. Do not commit `.env` or use the example placeholder in a deployment. The development settings use SQLite at `db.sqlite3`; the `DB_*` and `DATABASE_URL` variables are for the production settings.

Initialize and run the application:

```powershell
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

The application is served at `http://127.0.0.1:8000/`. Sign-in is at `/accounts/login/`, the Admin at `/admin/`, and the design-system showcase at `/dev-showcase/`.

## Environment variables

`config/settings/base.py` reads `SECRET_KEY`, `DEBUG`, `ENVIRONMENT`, `ALLOWED_HOSTS`, `TIME_ZONE`, `COURSEWARE_MAX_UPLOAD_SIZE`, and `LOG_LEVEL`. Development also reads `DEFAULT_FROM_EMAIL`. Production reads database settings (`DATABASE_URL` or `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`), email settings, and the HTTPS/security flags shown in `.env.example`.

`ENVIRONMENT` defaults to `development`; `config.settings.production` fixes it to `production`. `DEBUG` defaults to true in development and false in production. Production settings reject a missing, short, or known development `SECRET_KEY`. Set a unique key of at least 50 characters, a real `ALLOWED_HOSTS` list, production database/email values, and HTTPS cookie/redirect/HSTS settings appropriate to the hosting environment.

## Database and migrations

Development uses SQLite, configured directly in `config/settings/development.py`. Production settings configure PostgreSQL from `DATABASE_URL` or the individual `DB_*` values. PostgreSQL deployment has not been exercised as part of this repository's local verification.

Use `.venv\Scripts\python.exe manage.py migrate` to apply migrations. Check for uncommitted model changes without creating a migration using:

```powershell
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Existing migrations are part of the application history and should not be removed to perform cleanup.

## Development demo data

The development-only command is:

```powershell
.venv\Scripts\python.exe manage.py seed_demo_data
```

It creates or reconciles generic numbered identities such as `student1` / `student1@example.com`, `lecturer1` / `lecturer1@example.com`, `parent1` / `parent1@example.com`, and `admin1` / `admin1@example.com`. The email is the sign-in identifier. Newly created accounts use the development-only password `password`; existing account passwords are preserved unless `--force` is supplied. Do not expose seeded accounts publicly or reuse this password outside local development. The command is blocked when `DEBUG` is false or the environment is production. Reconciliation preserves existing profile/link records while clearing demo contact details.

## Django Admin

Open `/admin/` and sign in with an active staff account. Access to the Admin requires Django staff status and is further restricted by each model's configured permissions. The Admin has its own brown-and-cream theme in `templates/admin/base_site.html` and `static/css/admin.css`; this stylesheet is not loaded by public pages.

## Tests and CI

Run the Django test suite and project checks from this directory:

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test
```

The GitHub Actions Django workflow installs `requirements/ci.txt` and runs those three checks on Python 3.11, 3.12, and 3.13. The Pylint workflow uses the same CI dependencies and analyzes Python source outside migrations and virtual environments. A local run in this checkout completed 162 tests successfully on Python 3.14.7; this is a local result, not a claim about GitHub Actions.

## Deployment notes

`config.settings.production` provides PostgreSQL configuration and WhiteNoise compressed static-file storage. `requirements/prod.txt` includes Gunicorn and the PostgreSQL driver. No hosting provider, production URL, or end-to-end deployment is defined or verified here. Configure a unique secret, `DEBUG=False`, allowed host names, PostgreSQL, email delivery, HTTPS, and secure cookie/HSTS settings before deploying. Collect static assets with `.venv\Scripts\python.exe manage.py collectstatic` as part of the deployment process.

## Security notes

- Password authentication is handled by Django's password hashing and validators.
- View-level permissions scope lecturer access by course allocation, student access by enrollment, and parent access by explicit relationships.
- Courseware files and URLs pass through validators; uploaded media is stored outside source control.
- Keep `.env`, production secrets, local databases, uploaded media, and generated static output out of Git.
- Development settings and seeded demo credentials are not suitable for public deployment.
- Review production host, database, email, HTTPS, and secret settings for the target environment; a successful local check is not a deployment security audit.

## Known limitations and future work

Attendance, discussions, gradebook, notifications, and reporting apps are currently placeholders. Assignment/submission records exist without a complete web submission workflow. Student self-service enrollment is not implemented. External fonts and Bootstrap/Font Awesome are loaded from third-party CDNs. `docs/` contains project planning and architecture material; where it describes future work, treat that as a specification rather than evidence that the feature is implemented.
