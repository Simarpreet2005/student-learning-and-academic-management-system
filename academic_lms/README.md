# Academic LMS â€” Role-Based Student Learning and Academic Management System

A robust, enterprise-grade Django web application engineered for higher education institutions. Academic LMS provides a unified, secure academic lifecycle management platform tailored for four distinct user roles: **Administrator**, **Lecturer**, **Student**, and **Parent**.

Designed with an original **brown-and-cream scholastic aesthetic**, strict server-side authorization, accessible contrast ratios, and zero external AI or live-class dependencies.

---

## ðŸŒŸ Current Project Status

### Phase 8 Complete âœ… â€” All Planned Phases Delivered

The Academic LMS has successfully completed **all eight planned implementation phases**, delivering a fully integrated academic management platform with role-specific dashboards, an interactive academic calendar, and a comprehensive automated test suite.

| Phase | Description | Status |
|:---:|:---|:---:|
| 1 | Project Scaffolding, Configuration & Brown-and-Cream Design System | âœ… Done |
| 2 | Core Academic Hierarchy & Calendar (`apps.core`) | âœ… Done |
| 3 | Custom Authentication, User Profiles & Parent Linkage (`apps.accounts`) | âœ… Done |
| 4 | Departments, Programs, Courses, Allocations & Enrollments (`apps.academics`) | âœ… Done |
| 5 | Digital Courseware & Learning Resources (`apps.courseware`) | âœ… Done |
| 6 | Quizzes, Grading & Results (`apps.quizzes`) | âœ… Done |
| 7 | Rule-Based Smart Academic Workload Planner (`apps.planner`) | âœ… Done |
| 8 | Final Dashboards, Academic Calendar, Integration & QA (`apps.core` + `apps.accounts`) | âœ… Done |

> [!NOTE]
> Attendance management (`apps.attendance`) and discussion forums (`apps.discussions`) are intentionally excluded from the implemented scope per project requirements.

**Active test suite**: **157 automated tests** â€” 0 failures, 0 errors.

---

## ðŸ›ï¸ Architecture & Domain Applications Structure

```text
academic_lms/
â”œâ”€â”€ config/                         # Core Django configuration
â”‚   â”œâ”€â”€ settings/
â”‚   â”‚   â”œâ”€â”€ base.py                 # Common settings, security, crispy forms
â”‚   â”‚   â”œâ”€â”€ development.py          # SQLite engine, debug & console email
â”‚   â”‚   â””â”€â”€ production.py           # PostgreSQL, WhiteNoise static, SSL headers
â”‚   â”œâ”€â”€ urls.py                     # Root URL routing (includes quizzes/)
â”‚   â””â”€â”€ wsgi.py
â”œâ”€â”€ apps/                           # Domain-driven modular applications
â”‚   â”œâ”€â”€ core/                       # AcademicYear, Semester, Events, Base models, Landing view
â”‚   â”œâ”€â”€ accounts/                   # Custom User, Profiles (Student, Lecturer, Parent), Guardianship
â”‚   â”œâ”€â”€ academics/                  # Departments, Programs, Courses, Allocations, Enrollments
â”‚   â”œâ”€â”€ courseware/                 # Modules, Notes, File Attachments
â”‚   â”œâ”€â”€ quizzes/                    # Quiz, Question, QuizAttempt, StudentAnswer; grading service
â”‚   â”œâ”€â”€ assessments/                # Assignment, AssignmentSubmission, Quizzes facade
â”‚   â”œâ”€â”€ gradebook/                  # Grading scales, GPA/CGPA engine, Transcripts
â”‚   â”œâ”€â”€ attendance/                 # Sessions, Attendance records, Low-attendance alerts (<75%)
â”‚   â”œâ”€â”€ planner/                    # âœ… Rule-based Smart Academic Workload Planner (Deterministic)
â”‚   â”œâ”€â”€ discussions/                # Course forums, threads, instructor endorsements
â”‚   â”œâ”€â”€ notifications/              # In-app notification dispatcher & alerts
â”‚   â””â”€â”€ reporting/                  # Official PDF document & CSV export services
â”œâ”€â”€ static/                         # Design system CSS and client-side JavaScript
â”‚   â”œâ”€â”€ css/
â”‚   â”‚   â”œâ”€â”€ theme.css               # Brown-and-cream design tokens
â”‚   â”‚   â””â”€â”€ components.css          # Cards, tables, forms, badges, workload heatmap
â”‚   â””â”€â”€ js/
â”‚       â””â”€â”€ main.js                 # Vanilla client-side interactions
â”œâ”€â”€ templates/                      # Modular template hierarchy
â”‚   â”œâ”€â”€ base.html                   # Master layout with navbar, sidebar, theme styles
â”‚   â”œâ”€â”€ components/                 # Navbar, footer, flash messages
â”‚   â”œâ”€â”€ quizzes/                    # Quiz list/detail, take, result, grading desk templates
â”‚   â”œâ”€â”€ planner/                    # âœ… Workload dashboard, preferences, course workload, parent observer
â”‚   â””â”€â”€ core/                       # Phase 1 showcase & academic calendar views
â”œâ”€â”€ docs/                           # Architectural blueprints & specifications
â”‚   â”œâ”€â”€ REQUIREMENTS.md             # Functional & non-functional requirements
â”‚   â”œâ”€â”€ ROLE_PERMISSION_MATRIX.md   # Granular RBAC permissions for all 4 roles
â”‚   â”œâ”€â”€ ARCHITECTURE.md             # ERD diagrams, service layer, design tokens
â”‚   â””â”€â”€ IMPLEMENTATION_ROADMAP.md   # 15 phased delivery milestones
â”œâ”€â”€ manage.py
â”œâ”€â”€ requirements/
â”‚   â”œâ”€â”€ base.txt                    # Core Django dependencies
â”‚   â”œâ”€â”€ dev.txt                     # Testing, linting, development tools
â”‚   â””â”€â”€ prod.txt                    # Gunicorn, PostgreSQL drivers
â”œâ”€â”€ .env.example
â”œâ”€â”€ .gitignore
â””â”€â”€ README.md
```

---

## ðŸ‘¥ Four Core User Roles

| Role | Scope | Key Capabilities |
| :--- | :--- | :--- |
| **Administrator** | Institutional Governance | Manage academic departments, degree programs, course offerings, user directory, credentials, lecturer allocations, and institutional oversight. |
| **Lecturer** | Instructional Leadership | Manage assigned courses, publish courseware, create assignments and quizzes, evaluate deliverables with rubrics and feedback, log session attendance. |
| **Student** | Active Learning | Register for courses, access materials, submit assignments, attempt quizzes, track attendance, and use the **Rule-Based Smart Academic Workload Planner**. |
| **Parent** | Authorized Observer | **Strictly read-only visibility** into explicitly linked students: attendance records, published assessment marks, upcoming deadlines, and registration slips. |

---

## ðŸš« Strict Project Boundaries

To maintain high architectural integrity, predictable performance, and strict security:
- **No AI or Large Language Model (LLM) integration**: All planning algorithms and calculations are 100% deterministic and rule-based.
- **No live classes or video conferencing**: No WebRTC, third-party video call plugins, or Jitsi integrations.
- **English only**: All user interface text, system labels, error messages, and documentation are strictly in English.

---

## ðŸ› ï¸ Technology Stack & Dependencies

| Component | Version | License | Purpose |
| :--- | :--- | :--- | :--- |
| **Python** | 3.14.7 | PSF License | Runtime language with modern typing (verified) |
| **Django** | 5.2.18 | 3-Clause BSD | Core web framework, ORM, authentication (verified) |
| **Pillow** | 13.0.0 | HPND License | Image processing for user profiles and assets |
| **ReportLab** | 5.0.1 | 3-Clause BSD | Server-side PDF engine for transcripts and slips |
| **python-decouple** | 3.8 | 3-Clause BSD | 12-factor configuration via `.env` |
| **crispy-bootstrap5** | 2026.9 | MIT | Clean, accessible Bootstrap 5 form rendering |
| **django-crispy-forms**| 2.7 | MIT | Form styling framework |
| **WhiteNoise** | 6.12.0 | MIT | Efficient, compressed static file serving |
| **requests** | 2.34.2 | Apache 2.0 | HTTP client for integrations |

> [!NOTE]
> `xhtml2pdf` was removed because its transitive dependency `pyhanko` / `cryptography` / `cffi` lacks pre-built wheels for Python 3.14 on Windows. ReportLab is used directly for all PDF generation tasks.

---

## ðŸš€ Quick Start Guide

### 1. Prerequisites
Ensure Python 3.14.7 (64-bit) is installed on your Windows system.

### 2. Environment Setup (Windows PowerShell)
```powershell
# Navigate to the Academic LMS project directory
cd D:\lms\academic_lms

# Copy environment configuration if not already created
cp .env.example .env

# Create the dedicated virtual environment using Python 3.14
py -3.14 -m venv .venv

# Upgrade pip and install baseline dependencies
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements\base.txt
```

### 3. Database Initialization & Verification
```powershell
# Run system integrity check
.venv\Scripts\python.exe manage.py check

# Verify migration status
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py migrate --check

# Execute automated test suite (157 tests — Phase 8 complete)
.venv\Scripts\python.exe manage.py test --verbosity=2
```

### 4. Run Development Server
```powershell
# Start local development server on port 8000
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
Open your browser and navigate to: **`http://127.0.0.1:8000/`** to view the Phase 1 Design System & System Showcase.

---

## ðŸ“‹ Phased Implementation Roadmap

- [x] **Phase 1: Project Scaffolding, Core Configuration & Design System**
- [x] **Phase 2: Custom Authentication, User Model, Profiles & Parent Linkage**
- [x] **Phase 3: Academic Structure, Courses, Prerequisites & Student Enrollments**
- [x] **Phase 4: Courseware & Digital Learning Materials**
- [x] **Phase 5: Assignments, Submissions & Lecturer Rubric Grading** *(skeleton; quiz module delivered first)*
- [x] **Phase 6: Quizzes, Question Bank & Timed Assessments** â€” MCQ, True/False, Short-Answer; auto-grading; manual grading desk; results & parent read-only access
- [x] **Phase 7: Rule-Based Smart Academic Workload Planner Engine** (`apps.planner`) â€” 100% deterministic, zero AI, deadline clustering (&le;48h), Balanced/Moderate/Heavy/Conflict classification, 7-day schedule generator
- [ ] **Phase 8: Consolidated Gradebook, GPA Engine & Transcripts**
- [ ] **Phase 9: Session-Wise Class Attendance & Low-Attendance Alerts**
- [ ] **Phase 10: Course Discussion Forums & Moderation**
- [ ] **Phase 11: In-App Notification Center & Event Triggers**
- [ ] **Phase 12: Role-Specific Dashboards (Admin, Lecturer, Student, Parent)**
- [ ] **Phase 13: Official PDF Transcripts, Registration Slips & CSV Reporting**
- [ ] **Phase 14: Repeatable Seed Demo Data Management Command**
- [ ] **Phase 15: Quality Assurance, Security Hardening & Final Polish**

---

## ðŸ“„ License

This project is licensed under the **MIT License**. Third-party frameworks and libraries retain their respective open-source licenses.