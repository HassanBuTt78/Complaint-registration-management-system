from django.contrib import admin

from .models import (
    Complaint,
    ComplaintAttachment,
    ComplaintRemark,
    ComplaintStatusHistory,
)


class AttachmentInline(admin.TabularInline):
    model = ComplaintAttachment
    extra = 0
    readonly_fields = ("original_name", "content_type", "size_bytes", "uploaded_at")


class RemarkInline(admin.TabularInline):
    model = ComplaintRemark
    extra = 0
    readonly_fields = ("created_at",)


class StatusHistoryInline(admin.TabularInline):
    model = ComplaintStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "changed_at")
    can_delete = False


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "subject",
        "category",
        "department",
        "status",
        "is_anonymous",
        "created_at",
    )
    list_filter = ("status", "category", "department", "is_anonymous")
    search_fields = ("reference", "subject", "description")
    readonly_fields = ("reference", "created_at", "updated_at", "resolved_at", "closed_at")
    inlines = [AttachmentInline, RemarkInline, StatusHistoryInline]
    date_hierarchy = "created_at"
