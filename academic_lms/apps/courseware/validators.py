"""Validators and safe upload path generator for Learning Resources."""
import os
import re
import uuid
import urllib.parse
from django.conf import settings
from django.core.exceptions import ValidationError


def resource_upload_path(instance, filename: str) -> str:
    """Generate safe, collision-free storage path for uploaded learning resources.

    Mitigates path traversal by discarding user-provided path fragments and
    generating a UUID-based filename while preserving the sanitized lowercase extension.
    """
    _, ext = os.path.splitext(filename)
    safe_ext = ext.lower().strip()
    safe_filename = f"{uuid.uuid4().hex}{safe_ext}"

    course_slug = "general"
    if instance and getattr(instance, "course_id", None) and hasattr(instance, "course") and instance.course:
        course_slug = re.sub(r"[^a-zA-Z0-9_-]", "", instance.course.code.lower())

    return os.path.join("courseware", course_slug, safe_filename).replace("\\", "/")


def validate_resource_file(file):
    """Validate uploaded resource file extension and maximum file size."""
    if not file:
        return

    # 1. Filename & Extension inspection
    filename = getattr(file, "name", "")
    _, ext = os.path.splitext(filename)
    clean_ext = ext.lower().strip()

    dangerous = getattr(
        settings,
        "DANGEROUS_EXTENSIONS",
        [".exe", ".bat", ".cmd", ".sh", ".py", ".js", ".vbs", ".msi", ".php", ".phtml", ".html", ".htm", ".dll", ".com", ".scr", ".jar", ".ps1"],
    )
    if clean_ext in dangerous:
        raise ValidationError(
            f"The file extension '{clean_ext}' is prohibited for security reasons."
        )

    allowed = getattr(
        settings,
        "COURSEWARE_ALLOWED_EXTENSIONS",
        [".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".odt", ".odp", ".ods", ".txt", ".rtf", ".zip"],
    )
    if clean_ext not in allowed:
        allowed_list = ", ".join(allowed)
        raise ValidationError(
            f"File extension '{clean_ext}' is not supported. Permitted extensions: {allowed_list}."
        )

    # 2. File size enforcement
    max_size = getattr(settings, "COURSEWARE_MAX_UPLOAD_SIZE", 20 * 1024 * 1024)
    if file.size > max_size:
        file_mb = file.size / (1024 * 1024)
        max_mb = max_size / (1024 * 1024)
        raise ValidationError(
            f"File size ({file_mb:.1f} MB) exceeds maximum allowed limit of {max_mb:.0f} MB."
        )


def validate_resource_url(url: str):
    """Validate that external URLs use allowed safe schemes (http / https)."""
    if not url:
        return

    raw_lower = url.lower().strip()
    # Explicitly block unsafe URI schemes
    if raw_lower.startswith(("javascript:", "data:", "vbscript:", "file:", "about:")):
        raise ValidationError("Unsafe URL scheme detected. Only http:// and https:// URLs are permitted.")

    try:
        parsed = urllib.parse.urlparse(url.strip())
    except Exception as exc:
        raise ValidationError(f"Invalid URL structure: {exc}") from exc

    if parsed.scheme.lower() not in ("http", "https"):
        raise ValidationError("Only web links starting with 'http://' or 'https://' are permitted.")

    if not parsed.netloc:
        raise ValidationError("Invalid URL: missing domain/hostname.")
