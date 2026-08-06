"""
Role-specific dashboards, user management, analytics and exports.

Covers FR-6 (tracking), FR-7 (department scoping), FR-10 (user management),
FR-11 (reports) and UC16-UC21.
"""

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.forms import AdminUserForm, DepartmentForm
from accounts.mixins import deny, role_required
from accounts.models import AuditAction, AuditLog, Department, Role, User
from complaints.forms import ComplaintFilterForm
from complaints.models import (
    Complaint,
    ComplaintCategory,
    ComplaintStatus,
    TERMINAL_STATUSES,
)
from complaints.services import apply_filters, unmask_complaint
from notifications.models import Notification

from .exports import complaints_to_csv, complaints_to_pdf

PAGE_SIZE = 15


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def home(request):
    """Route each role to its own dashboard."""
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    if request.user.is_admin_role:
        return redirect("dashboards:admin")
    if request.user.is_hod:
        return redirect("dashboards:hod")
    return redirect("dashboards:student")


def _status_counts(queryset):
    """Counts keyed by status value, zero-filled for every known status."""
    raw = dict(
        queryset.values_list("status").annotate(total=Count("id")).values_list(
            "status", "total"
        )
    )
    return {value: raw.get(value, 0) for value, _label in ComplaintStatus.choices}


def _paginate(request, queryset):
    paginator = Paginator(queryset, PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))


def _querystring_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return f"&{encoded}" if encoded else ""


# ---------------------------------------------------------------------------
# Student dashboard (FR-6)
# ---------------------------------------------------------------------------
@role_required(Role.STUDENT)
def student_dashboard(request):
    base = Complaint.objects.visible_to(request.user).with_related()
    form = ComplaintFilterForm(request.GET or None, user=request.user)
    filtered = base
    if form.is_valid():
        filtered = apply_filters(base, cleaned_data=form.cleaned_data, user=request.user)

    counts = _status_counts(base)
    open_count = sum(
        count for status, count in counts.items() if status not in TERMINAL_STATUSES
    )
    return render(
        request,
        "dashboards/student.html",
        {
            "filter_form": form,
            "page_obj": _paginate(request, filtered),
            "total": base.count(),
            "open_count": open_count,
            "resolved_count": counts.get(ComplaintStatus.RESOLVED, 0)
            + counts.get(ComplaintStatus.CLOSED, 0),
            "counts": counts,
            "status_choices": ComplaintStatus.choices,
            "querystring": _querystring_without_page(request),
        },
    )


# ---------------------------------------------------------------------------
# HOD dashboard (FR-7, UC9/UC13/UC14)
# ---------------------------------------------------------------------------
@role_required(Role.HOD)
def hod_dashboard(request):
    if request.user.department_id is None:
        deny(request, "HOD account has no department assigned.")

    base = Complaint.objects.visible_to(request.user).with_related()
    form = ComplaintFilterForm(request.GET or None, user=request.user)
    filtered = base
    if form.is_valid():
        filtered = apply_filters(base, cleaned_data=form.cleaned_data, user=request.user)

    counts = _status_counts(base)
    unassigned = base.filter(assigned_to__isnull=True).count()
    return render(
        request,
        "dashboards/hod.html",
        {
            "filter_form": form,
            "page_obj": _paginate(request, filtered),
            "department": request.user.department,
            "total": base.count(),
            "counts": counts,
            "unassigned": unassigned,
            "anonymous_count": base.filter(is_anonymous=True).count(),
            "status_choices": ComplaintStatus.choices,
            "querystring": _querystring_without_page(request),
        },
    )


# ---------------------------------------------------------------------------
# Admin dashboard (FR-10, UC16-UC21)
# ---------------------------------------------------------------------------
@role_required(Role.ADMIN)
def admin_dashboard(request):
    base = Complaint.objects.visible_to(request.user).with_related()
    form = ComplaintFilterForm(request.GET or None, user=request.user)
    filtered = base
    if form.is_valid():
        filtered = apply_filters(base, cleaned_data=form.cleaned_data, user=request.user)

    counts = _status_counts(base)
    return render(
        request,
        "dashboards/admin.html",
        {
            "filter_form": form,
            "page_obj": _paginate(request, filtered),
            "total": base.count(),
            "counts": counts,
            "department_count": Department.objects.filter(is_active=True).count(),
            "user_count": User.objects.filter(is_active=True).count(),
            "anonymous_count": base.filter(is_anonymous=True).count(),
            "status_choices": ComplaintStatus.choices,
            "querystring": _querystring_without_page(request),
        },
    )


# ---------------------------------------------------------------------------
# Analytics (FR-11, UC19)
# ---------------------------------------------------------------------------
@role_required(Role.HOD, Role.ADMIN)
def analytics(request):
    base = Complaint.objects.visible_to(request.user)

    per_department = list(
        base.values("department__name").annotate(total=Count("id")).order_by("-total")
    )
    per_status = [
        {
            "status": label,
            "total": base.filter(status=value).count(),
        }
        for value, label in ComplaintStatus.choices
    ]
    per_category = [
        {
            "category": label,
            "total": base.filter(category=value).count(),
        }
        for value, label in ComplaintCategory.choices
    ]

    resolution = base.filter(resolved_at__isnull=False).annotate(
        duration=ExpressionWrapper(
            F("resolved_at") - F("created_at"), output_field=DurationField()
        )
    ).aggregate(avg=Avg("duration"))["avg"]
    avg_resolution_hours = (
        round(resolution.total_seconds() / 3600, 1) if resolution else 0.0
    )

    twelve_months_ago = timezone.now() - timezone.timedelta(days=365)
    monthly = list(
        base.filter(created_at__gte=twelve_months_ago)
        .annotate(month=TruncMonth("created_at"))
        .values("month")
        .annotate(total=Count("id"))
        .order_by("month")
    )
    monthly_trend = [
        {"label": row["month"].strftime("%b %Y") if row["month"] else "-", "total": row["total"]}
        for row in monthly
    ]

    resolved_total = base.filter(
        status__in=[ComplaintStatus.RESOLVED, ComplaintStatus.CLOSED]
    ).count()
    total = base.count()

    return render(
        request,
        "dashboards/analytics.html",
        {
            "total": total,
            "resolved_total": resolved_total,
            "resolution_rate": round(resolved_total / total * 100, 1) if total else 0.0,
            "avg_resolution_hours": avg_resolution_hours,
            "per_department": per_department,
            "per_status": per_status,
            "per_category": per_category,
            "monthly_trend": monthly_trend,
            "scope": request.user.department.name
            if request.user.is_hod
            else "All departments",
        },
    )


# ---------------------------------------------------------------------------
# Reports & exports (FR-11)
# ---------------------------------------------------------------------------
@role_required(Role.HOD, Role.ADMIN)
def reports(request):
    base = Complaint.objects.visible_to(request.user).with_related()
    form = ComplaintFilterForm(request.GET or None, user=request.user)
    filtered = base
    if form.is_valid():
        filtered = apply_filters(base, cleaned_data=form.cleaned_data, user=request.user)

    export = request.GET.get("export")
    if export in {"csv", "pdf"}:
        rows = list(filtered[:5000])
        if not rows:
            messages.warning(
                request, "No complaints match the selected filters - nothing to export."
            )
            return redirect(f"{reverse('dashboards:reports')}")
        AuditLog.record(
            actor=request.user,
            action=AuditAction.REPORT_EXPORTED,
            target=export.upper(),
            detail=f"{len(rows)} record(s) exported.",
            request=request,
        )
        if export == "csv":
            return complaints_to_csv(rows, viewer=request.user)
        return complaints_to_pdf(rows, viewer=request.user)

    summary = {
        "total": filtered.count(),
        "by_status": _status_counts(filtered),
        "by_category": {
            label: filtered.filter(category=value).count()
            for value, label in ComplaintCategory.choices
        },
    }
    return render(
        request,
        "dashboards/reports.html",
        {
            "filter_form": form,
            "page_obj": _paginate(request, filtered),
            "summary": summary,
            "querystring": _querystring_without_page(request),
        },
    )


# ---------------------------------------------------------------------------
# Unmasking (FR-5, UC18) - Admin only
# ---------------------------------------------------------------------------
@role_required(Role.ADMIN)
def unmask(request, pk):
    complaint = get_object_or_404(Complaint.objects.with_related(), pk=pk)
    if not complaint.is_anonymous:
        messages.info(request, "This complaint was not submitted anonymously.")
        return redirect("complaints:detail", pk=complaint.pk)

    if request.method == "POST":
        reason = (request.POST.get("reason") or "").strip()
        if len(reason) < 5:
            messages.error(
                request, "Please state a reason (at least 5 characters) for unmasking."
            )
        else:
            student = unmask_complaint(
                complaint=complaint, actor=request.user, reason=reason, request=request
            )
            messages.warning(
                request,
                f"Identity revealed: {student.get_full_name()} "
                f"({student.identifier or 'no ID'}) - {student.email}. "
                "This action has been recorded in the audit log.",
            )
            return redirect("complaints:detail", pk=complaint.pk)

    return render(request, "dashboards/unmask_confirm.html", {"complaint": complaint})


# ---------------------------------------------------------------------------
# User management (FR-10, UC17)
# ---------------------------------------------------------------------------
@role_required(Role.ADMIN)
def user_list(request):
    users = User.objects.select_related("department").all()
    query = (request.GET.get("q") or "").strip()
    role = request.GET.get("role") or ""
    if query:
        users = users.filter(
            Q(full_name__icontains=query)
            | Q(email__icontains=query)
            | Q(identifier__icontains=query)
        )
    if role in Role.values:
        users = users.filter(role=role)
    return render(
        request,
        "dashboards/user_list.html",
        {
            "page_obj": _paginate(request, users),
            "q": query,
            "role": role,
            "roles": Role.choices,
            "querystring": _querystring_without_page(request),
        },
    )


@role_required(Role.ADMIN)
def user_create(request):
    if request.method == "POST":
        form = AdminUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            AuditLog.record(
                actor=request.user,
                action=AuditAction.USER_CREATED,
                target=user.email,
                detail=f"role={user.role}",
                request=request,
            )
            messages.success(request, f"User {user.get_full_name()} created.")
            return redirect("dashboards:user_list")
        messages.error(request, "Please correct the errors below.")
    else:
        form = AdminUserForm()
    return render(
        request, "dashboards/user_form.html", {"form": form, "mode": "create"}
    )


@role_required(Role.ADMIN)
def user_edit(request, pk):
    target = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        form = AdminUserForm(request.POST, instance=target)
        if form.is_valid():
            user = form.save()
            AuditLog.record(
                actor=request.user,
                action=AuditAction.USER_UPDATED,
                target=user.email,
                detail=f"role={user.role} active={user.is_active}",
                request=request,
            )
            messages.success(request, f"User {user.get_full_name()} updated.")
            return redirect("dashboards:user_list")
        messages.error(request, "Please correct the errors below.")
    else:
        form = AdminUserForm(instance=target)
    return render(
        request,
        "dashboards/user_form.html",
        {"form": form, "mode": "edit", "target": target},
    )


@require_POST
@role_required(Role.ADMIN)
def user_toggle_active(request, pk):
    """Deactivate / reactivate an account (never a hard delete - audit integrity)."""
    target = get_object_or_404(User, pk=pk)
    if target.pk == request.user.pk:
        messages.error(request, "You cannot deactivate your own account.")
        return redirect("dashboards:user_list")

    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])
    AuditLog.record(
        actor=request.user,
        action=AuditAction.USER_ACTIVATED
        if target.is_active
        else AuditAction.USER_DEACTIVATED,
        target=target.email,
        request=request,
    )
    messages.success(
        request,
        f"{target.get_full_name()} has been "
        f"{'reactivated' if target.is_active else 'deactivated'}.",
    )
    return redirect("dashboards:user_list")


# ---------------------------------------------------------------------------
# Departments (UC21 - system configuration)
# ---------------------------------------------------------------------------
@role_required(Role.ADMIN)
def department_list(request):
    departments = Department.objects.annotate(
        complaint_count=Count("complaints"), member_count=Count("members", distinct=True)
    )
    form = DepartmentForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        department = form.save()
        AuditLog.record(
            actor=request.user,
            action=AuditAction.USER_UPDATED,
            target=f"Department:{department.name}",
            detail="Department created/updated.",
            request=request,
        )
        messages.success(request, f"Department '{department.name}' saved.")
        return redirect("dashboards:departments")
    return render(
        request,
        "dashboards/department_list.html",
        {"departments": departments, "form": form},
    )


# ---------------------------------------------------------------------------
# Activity log (UC20)
# ---------------------------------------------------------------------------
@role_required(Role.ADMIN)
def activity_log(request):
    entries = AuditLog.objects.select_related("actor").all()
    action = request.GET.get("action") or ""
    query = (request.GET.get("q") or "").strip()
    if action:
        entries = entries.filter(action=action)
    if query:
        entries = entries.filter(
            Q(actor_label__icontains=query)
            | Q(target__icontains=query)
            | Q(detail__icontains=query)
        )
    return render(
        request,
        "dashboards/activity_log.html",
        {
            "page_obj": _paginate(request, entries),
            "actions": AuditAction.choices,
            "action": action,
            "q": query,
            "notifications": Notification.objects.all()[:10],
            "querystring": _querystring_without_page(request),
        },
    )
