"""
Database-backed file storage.

Serverless platforms (Vercel, and any similar function runtime) give each
invocation a read-only filesystem apart from an ephemeral ``/tmp``. Writing
uploads to ``MEDIA_ROOT`` therefore silently loses them, which would break FR-4.

Storing attachment bytes in the database keeps FR-4 fully working with no extra
service, no object-storage account and no cost. That is the right trade here:
the SRS caps uploads at 5 MB and 5 files per complaint, so volumes stay small.

The backend is a drop-in ``Storage`` implementation, so ``FileField`` and the
existing ``complaints:attachment`` download view work unchanged.
"""

from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, Storage
from django.db import models
from django.utils import timezone
from django.utils.deconstruct import deconstructible


class StoredFile(models.Model):
    """Raw bytes of one uploaded file, keyed by its storage path."""

    name = models.CharField(max_length=255, unique=True, db_index=True)
    content = models.BinaryField()
    size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        # Declared explicitly because this model lives outside ``models.py``.
        app_label = "complaints"
        ordering = ["-created_at", "-id"]
        verbose_name = "stored file"
        verbose_name_plural = "stored files"

    def __str__(self):
        return self.name


@deconstructible
class DatabaseStorage(Storage):
    """
    A ``Storage`` that persists file content in the :class:`StoredFile` table.

    ``deconstructible`` matters: ``FileField(storage=...)`` is serialised into
    migrations, so the class must be reconstructible by reference.
    """

    def _open(self, name, mode="rb"):
        if "w" in mode:
            raise ValueError("DatabaseStorage files are read-only once written.")
        record = StoredFile.objects.filter(name=name).first()
        if record is None:
            raise FileNotFoundError(f"No stored file named {name!r}.")
        return ContentFile(bytes(record.content), name=name)

    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        StoredFile.objects.update_or_create(
            name=name,
            defaults={
                "content": data,
                "size": len(data),
                "content_type": getattr(content, "content_type", "") or "",
            },
        )
        return name

    def exists(self, name):
        return StoredFile.objects.filter(name=name).exists()

    def delete(self, name):
        StoredFile.objects.filter(name=name).delete()

    def size(self, name):
        record = StoredFile.objects.filter(name=name).only("size").first()
        if record is None:
            raise FileNotFoundError(f"No stored file named {name!r}.")
        return record.size

    def get_created_time(self, name):
        record = StoredFile.objects.filter(name=name).only("created_at").first()
        if record is None:
            raise FileNotFoundError(f"No stored file named {name!r}.")
        return record.created_at

    get_modified_time = get_created_time
    get_accessed_time = get_created_time

    def url(self, name):
        """
        Attachments are only ever reached through the permission-checked
        ``complaints:attachment`` view, never by a direct media URL. Refusing
        here makes any accidental use of ``.url`` fail loudly rather than leak a
        path that would 404 in production.
        """
        raise NotImplementedError(
            "Attachments are served via the 'complaints:attachment' view, "
            "which enforces access control. Do not link to storage URLs."
        )

    def listdir(self, path):
        prefix = path if path.endswith("/") or not path else f"{path}/"
        names = StoredFile.objects.filter(name__startswith=prefix).values_list(
            "name", flat=True
        )
        return [], [name[len(prefix) :] for name in names]


@deconstructible
class AttachmentStorage(Storage):
    """
    The backend actually attached to ``ComplaintAttachment.file``.

    It resolves to :class:`DatabaseStorage` or ``FileSystemStorage`` **per
    operation**, reading ``USE_DATABASE_FILE_STORAGE`` each time.

    Deciding per operation rather than once is deliberate. Django evaluates a
    callable passed as ``FileField(storage=...)`` a single time, when the model
    class is imported - which happens before settings can be adjusted, makes the
    choice untestable via ``override_settings``, and would bake whichever value
    happened to be present at import into the process for its whole lifetime.
    Delegating keeps one code path correct on local disk and on Vercel.
    """

    def _backend(self):
        from django.conf import settings

        if getattr(settings, "USE_DATABASE_FILE_STORAGE", False):
            return DatabaseStorage()
        return FileSystemStorage()

    def _open(self, name, mode="rb"):
        return self._backend()._open(name, mode)

    def _save(self, name, content):
        return self._backend()._save(name, content)

    def exists(self, name):
        return self._backend().exists(name)

    def delete(self, name):
        return self._backend().delete(name)

    def size(self, name):
        return self._backend().size(name)

    def url(self, name):
        return self._backend().url(name)

    def listdir(self, path):
        return self._backend().listdir(path)

    def get_created_time(self, name):
        return self._backend().get_created_time(name)

    def get_modified_time(self, name):
        return self._backend().get_modified_time(name)

    def get_accessed_time(self, name):
        return self._backend().get_accessed_time(name)


def select_attachment_storage():
    """Backwards-compatible helper returning the currently active backend."""
    return AttachmentStorage()._backend()
