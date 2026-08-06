"""Complaint views: submission, tracking, staff actions, secure file serving."""

import mimetypes

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from accounts.mixins import deny, role_required
from accounts.models import Department, Role

from .categorizer import suggest_category, suggest_department
from .forms import (
    AssignComplaintForm,
    ComplaintForm,
    RemarkForm,
    StatusUpdateForm,
)
from .models import (
    Complaint,
    ComplaintAttachment,
    ComplaintStatus,
    InvalidTransition,
)
from .services import (
    add_remark,
    assign_complaint,
    change_status,
    create_complaint,
    get_complaint_for,
    update_complaint,
)


def _upload_context():
    """Client-side mirror of the server's upload limits (FR-4)."""
    return {
        "max_upload_bytes": settings.MAX_UPLOAD_SIZE,
        "max_upload_mb": settings.MAX_UPLOAD_SIZE_MB,
        "allowed_extensions": ",".join(settings.ALLOWED_UPLOAD_EXTENSIONS),
    }


@role_required(Role.STUDENT)
def complaint_create(request):
    """FR-3 / Algorithm 3: submit a new complaint."""
    if request.method == "POST":
        form = ComplaintForm(request.POST, request.FILES, student=request.user)
        if form.is_valid():
            complaint = create_complaint(
                complaint=form.save(commit=False),
                student=request.user,
                attachments=form.cleaned_data.get("attachments"),
                request=request,
            )
            messages.success(
                request,
                f"Complaint {complaint.reference} submitted successfully. "
                "A confirmation email is on its way.",
            )
            return redirect("complaints:detail", pk=complaint.pk)
        messages.error(request, "Please correct the errors below and resubmit.")
    else:
        form = ComplaintForm(student=request.user, initial={"department": request.user.department_id})

    return render(
        request,
        "complaints/complaint_form.html",
        {"form": form, "mode": "create", **_upload_context()},
    )


@role_required(Role.STUDENT)
def complaint_edit(request, pk):
    """UC5: edit a complaint while it is still in the Submitted state."""
    complaint = get_object_or_404(
        Complaint.objects.visible_to(request.user).with_related(), pk=pk
    )
    if not complaint.can_be_edited_by(request.user):
        deny(
            request,
            "Complaint can no longer be edited (it has already been assigned).",
        )

    if request.method == "POST":
        form = ComplaintForm(
            request.POST, request.FILES, instance=complaint, student=request.user
        )
        if form.is_valid():
            update_complaint(
                complaint=form.save(commit=False),
                actor=request.user,
                attachments=form.cleaned_data.get("attachments"),
                request=request,
            )
            messages.success(request, "Complaint updated.")
            return redirect("complaints:detail", pk=complaint.pk)
        messages.error(request, "Please correct the errors below.")
    else:
        form = ComplaintForm(instance=complaint, student=request.user)

    return render(
        request,
        "complaints/complaint_form.html",
        {"form": form, "mode": "edit", "complaint": complaint, **_upload_context()},
    )


def complaint_detail(request, pk):
    """
    FR-6: complaint detail with the full status timeline.

    ``get_complaint_for`` applies queryset-level RBAC, so an out-of-scope
    complaint is indistinguishable from a non-existent one.
    """
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    complaint = get_complaint_for(request.user, pk)
    if complaint is None:
        if Complaint.objects.filter(pk=pk).exists():
            deny(request, f"Attempted to open complaint #{pk} outside their scope.")
        raise Http404("Complaint not found.")

    can_manage = complaint.can_be_managed_by(request.user)
    context = {
        "complaint": complaint,
        "timeline": complaint.timeline(request.user),
        "attachments": complaint.attachments.all(),
        "can_manage": can_manage,
        "can_edit": complaint.can_be_edited_by(request.user),
        "can_cancel": complaint.can_be_cancelled_by(request.user),
        "identity_visible": complaint.identity_visible_to(request.user),
        "can_unmask": complaint.can_unmask(request.user),
        "complainant_name": complaint.complainant_display(request.user),
        "complainant_id": complaint.complainant_identifier(request.user),
        "remark_form": RemarkForm(user=request.user),
        "status_form": StatusUpdateForm(complaint=complaint) if can_manage else None,
        "assign_form": AssignComplaintForm(complaint=complaint) if can_manage else None,
    }
    return render(request, "complaints/complaint_detail.html", context)


@require_POST
@role_required(Role.STUDENT)
def complaint_cancel(request, pk):
    complaint = get_object_or_404(Complaint.objects.visible_to(request.user), pk=pk)
    if not complaint.can_be_cancelled_by(request.user):
        deny(request, "Complaint can no longer be cancelled.")
    try:
        change_status(
            complaint=complaint,
            new_status=ComplaintStatus.CANCELLED,
            actor=request.user,
            note="Cancelled by the complainant.",
            request=request,
        )
        messages.success(request, f"Complaint {complaint.reference} cancelled.")
    except InvalidTransition as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("complaints:detail", pk=complaint.pk)


@require_POST
@role_required(Role.HOD, Role.ADMIN)
def complaint_status_update(request, pk):
    """FR-8: HOD/Admin status change, validated by the state machine."""
    complaint = get_object_or_404(
        Complaint.objects.visible_to(request.user).with_related(), pk=pk
    )
    if not complaint.can_be_managed_by(request.user):
        deny(request, "Complaint belongs to another department.")

    form = StatusUpdateForm(request.POST, complaint=complaint)
    if form.is_valid():
        try:
            change_status(
                complaint=complaint,
                new_status=form.cleaned_data["status"],
                actor=request.user,
                note=form.cleaned_data.get("note", ""),
                request=request,
            )
            messages.success(
                request, f"Status updated to {complaint.get_status_display()}."
            )
        except InvalidTransition as exc:
            messages.error(request, "; ".join(exc.messages))
    else:
        messages.error(
            request,
            "Invalid status update: "
            + "; ".join(
                f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()
            ),
        )
    return redirect("complaints:detail", pk=complaint.pk)


@require_POST
@role_required(Role.HOD, Role.ADMIN)
def complaint_assign(request, pk):
    """UC10: assign a complaint to a staff member."""
    complaint = get_object_or_404(
        Complaint.objects.visible_to(request.user).with_related(), pk=pk
    )
    if not complaint.can_be_managed_by(request.user):
        deny(request, "Complaint belongs to another department.")

    form = AssignComplaintForm(request.POST, complaint=complaint)
    if form.is_valid():
        assign_complaint(
            complaint=complaint,
            assignee=form.cleaned_data["assigned_to"],
            actor=request.user,
            note=form.cleaned_data.get("note", ""),
            request=request,
        )
        messages.success(
            request,
            f"Complaint assigned to {form.cleaned_data['assigned_to'].get_full_name()}.",
        )
    else:
        messages.error(request, "Could not assign the complaint. Check the selection.")
    return redirect("complaints:detail", pk=complaint.pk)


@require_POST
def complaint_add_remark(request, pk):
    """UC12: add a remark. Students may reply; staff may add internal notes."""
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    complaint = get_complaint_for(request.user, pk)
    if complaint is None:
        raise Http404("Complaint not found.")

    form = RemarkForm(request.POST, user=request.user)
    if form.is_valid():
        add_remark(
            complaint=complaint,
            author=request.user,
            text=form.cleaned_data["text"],
            is_internal=bool(form.cleaned_data.get("is_internal")),
            request=request,
        )
        messages.success(request, "Remark added.")
    else:
        messages.error(request, "Remark could not be saved. Please check your input.")
    return redirect("complaints:detail", pk=complaint.pk)


def attachment_download(request, pk):
    """
    Serve an attachment only to users entitled to the parent complaint.

    Media files are never exposed through a public static route, so this view is
    the only way to reach them.
    """
    if not request.user.is_authenticated:
        raise PermissionDenied("Authentication required.")

    attachment = get_object_or_404(
        ComplaintAttachment.objects.select_related("complaint"), pk=pk
    )
    if not Complaint.objects.visible_to(request.user).filter(
        pk=attachment.complaint_id
    ).exists():
        deny(request, f"Attempted to download attachment #{pk} outside their scope.")

    try:
        handle = attachment.file.open("rb")
    except (FileNotFoundError, ValueError):
        raise Http404("The stored file is no longer available.")

    content_type = attachment.content_type or (
        mimetypes.guess_type(attachment.file.name)[0] or "application/octet-stream"
    )
    response = FileResponse(
        handle,
        content_type=content_type,
        as_attachment=True,
        filename=attachment.original_name or "attachment",
    )
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_GET
@role_required(Role.STUDENT, Role.HOD, Role.ADMIN)
def categorize_suggest(request):
    """
    Bonus: rule-based category/department suggestion for the submission form.

    Returns JSON consumed by ``static/js/complaint-form.js``.
    """
    text = f"{request.GET.get('subject', '')} {request.GET.get('description', '')}"
    category, confidence = suggest_category(text)
    department = suggest_department(text, Department.objects.filter(is_active=True))
    return JsonResponse(
        {
            "category": category,
            "confidence": confidence,
            "department_id": department.pk if department else None,
            "department_name": department.name if department else None,
        }
    )
