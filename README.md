# Role-Based Student Learning and Academic Management System

A robust, full-stack Django web application designed for higher education institutions to manage academic programs, role-based user workflows, student course registrations, grading, assessments, and automated reporting.

---

## 🌟 Key Features & Role-Based Workflows

### 👑 Administrator
- **Analytics & Dashboard**: Real-time institution statistics including student/lecturer counts, course numbers, and allocation breakdowns.
- **User Management**: Add, update, and manage student and lecturer profiles with automated credential generation.
- **Academic Hierarchy**: Configure programs, academic sessions/years, and semesters. Set active semesters globally.
- **Course Allocation**: Allocate courses to designated lecturers.
- **News & Announcements**: Post announcements, bulletins, and events visible to all users.

### 👨‍🏫 Lecturer
- **Assigned Courses**: View assigned courses, course materials, and student rosters.
- **Course Content Management**: Upload course documentation, syllabi, and lecture video links.
- **Continuous Assessment & Grading**: Submit scores for assignments, midterms, attendance, and final examinations.
- **Automated Calculations**: System calculates total score, GPA point, grade letter, and status (Pass/Fail).
- **PDF Result Sheets**: Generate and download printable official semester result sheets.
- **Quizzes & Marking**: Create multi-choice/true-false quizzes, view student submissions, and mark essay responses.

### 🎓 Student
- **Course Registration**: Add and drop courses for the active academic semester.
- **Course Access**: Access lecture notes, resources, and video lectures.
- **Quizzes**: Attempt time-limited quizzes with category tracking and instant feedback.
- **Grades & Assessment**: View semester-wise assessment scores and cumulative grade point averages (CGPA).
- **Registration Form PDF**: Generate and download official signed student course registration slips.

---

## 🏗️ Architecture & Apps Structure

| App | Purpose |
| :--- | :--- |
| `accounts` | Custom `User` model, role-based permissions (`@admin_required`, `@lecturer_required`, `@student_required`), authentication, and profiles. |
| `core` | Sessions, semesters, academic programs, and site-wide news/announcements. |
| `course` | Course catalogs, uploads, course allocation, and material management. |
| `result` | Continuous assessments, grading calculations, and ReportLab PDF document generators. |
| `quiz` | Quiz management, sittings, multiple-choice questions, and score tracking. |
| `payments` | Optional invoice and tuition payment processing module. |
| `search` | Global search engine for courses and academic records. |

---

## 🛠️ Technology Stack

- **Backend**: Python 3.8+ / 3.10+, Django 4.2+
- **Frontend**: HTML5, Bootstrap 5.3, FontAwesome 6.5, jQuery
- **Document Engine**: ReportLab Platypus (PDF generation)
- **Database**: SQLite (development) / PostgreSQL (production ready)
- **Authentication**: Role-based access control with custom session security decorators

---

## 🚀 Getting Started

### 1. Prerequisites
Ensure Python 3.8+ or Python 3.10+ is installed on your system.

### 2. Environment Setup
```bash
# Clone the repository
git clone https://github.com/Simarpreet2005/student-learning-and-academic-management-system.git
cd student-learning-and-academic-management-system

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory:
```env
SECRET_KEY=your-secure-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
```

### 4. Database Initialization
```bash
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
python manage.py collectstatic --no-input
```

### 5. Run the Application
```bash
python manage.py runserver
```
Visit `http://127.0.0.1:8000/` in your browser.

---

## 📄 License & Attribution

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
Initial open-source foundation adapted from SkyLearn / django_quiz.