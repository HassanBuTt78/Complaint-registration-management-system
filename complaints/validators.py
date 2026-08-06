"""Upload validation for complaint attachments (FR-4)."""

import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: Magic-number prefixes for the three formats the SRS permits.
_MAGIC_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "jpg": [b"\xff\xd8\xff"],
    "jpeg": [b"\xff\xd8\xff"],
    "png": [b"\x89PNG\r\n\x1a\n"],
}


def validate_attachment(uploaded_file):
    """
    Reject anything that is not a genuine PDF/JPG/PNG within the size limit.

    Three independent checks are applied: extension, declared content type and
    the file's own magic number, so renaming ``payload.exe`` to ``proof.pdf``
    does not get through.
    """
    if uploaded_file is None:
        return uploaded_file

    max_size = settings.MAX_UPLOAD_SIZE
    size = getattr(uploaded_file, "size", 0) or 0
    if size == 0:
        raise ValidationError(_("The uploaded file is empty."))
    if size > max_size:
        raise ValidationError(
            _("File is too large (%(size).1f MB). Maximum allowed size is %(max)d MB.")
            % {"size": size / (1024 * 1024), "max": settings.MAX_UPLOAD_SIZE_MB}
        )

    name = getattr(uploaded_file, "name", "") or ""
    ext = os.path.splitext(name)[1].lower().lstrip(".")
    allowed = settings.ALLOWED_UPLOAD_EXTENSIONS
    if ext not in allowed:
        raise ValidationError(
            _("Unsupported file type '.%(ext)s'. Allowed formats: %(allowed)s.")
            % {"ext": ext or "unknown", "allowed": ", ".join(a.upper() for a in allowed)}
        )

    content_type = (getattr(uploaded_file, "content_type", "") or "").lower()
    if content_type and content_type not in settings.ALLOWED_UPLOAD_CONTENT_TYPES:
        raise ValidationError(
            _("Unsupported content type '%(ct)s'. Allowed formats: PDF, JPG, PNG.")
            % {"ct": content_type}
        )

    signatures = _MAGIC_SIGNATURES.get(ext, [])
    if signatures:
        try:
            uploaded_file.seek(0)
            header = uploaded_file.read(16)
        finally:
            uploaded_file.seek(0)
        if not any(header.startswith(sig) for sig in signatures):
            raise ValidationError(
                _("The file content does not match a valid %(ext)s file.")
                % {"ext": ext.upper()}
            )

    return uploaded_file
