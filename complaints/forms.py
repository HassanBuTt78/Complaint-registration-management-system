"""Complaint forms: submission, editing, staff actions and filtering."""

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from accounts.models import Department, Role, User

from .models import (
    ALLOWED_TRANSITIONS,
    Complaint,
    ComplaintCategory,
    ComplaintRemark,
    ComplaintStatus,
)
from .validators import validate_attachment

BOOTSTRAP_INPUT = {"class": "form-control"}
BOOTSTRAP_SELECT = {"class": "form-select"}


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A ``FileField`` that cleans and validates a list of uploads."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"class": "form-control"}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if not data:
            if self.required and not initial:
                raise ValidationError(self.error_messages["required"], code="required")
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        cleaned = []
        for item in data:
            value = single_clean(item, initial)
            if value:
                validate_attachment(value)
                cleaned.append(value)
        if len(cleaned) > 5:
            raise ValidationError(_("You may attach at most 5 files per complaint."))
        return cleaned


class ComplaintForm(forms.ModelForm):
    """
    Student-facing submission / edit form (FR-3, FR-4, FR-5; Algorithm 3).
    """

    attachments = MultipleFileField(
        label=_("Upload attachment (PDF, JPG, PNG)"),
        required=False,
        help_text=_(
            "Optional. Up to 5 files, %(size)d MB each. PDF, JPG and PNG only."
        )
        % {"size": settings.MAX_UPLOAD_SIZE_MB},
    )

    class Meta:
        model = Complaint
        fields = ["subject", "category", "department", "description", "is_anonymous"]
        labels = {
            "subject": _("Complaint subject"),
            "department": _("Department"),
            "description": _("Detailed description"),
            "is_anonymous": _(
                "Submit anonymously (your identity will be hidden from the HOD)"
            ),
        }
        widgets = {
            "subject": forms.TextInput(
                attrs={
                    **BOOTSTRAP_INPUT,
                    "placeholder": "Enter a brief subject for your complaint",
                    "maxlength": 200,
                    "required": True,
                }
            ),
            "category": forms.Select(attrs={**BOOTSTRAP_SELECT, "id": "id_category"}),
            "department": forms.Select(
                attrs={**BOOTSTRAP_SELECT, "id": "id_department"}
            ),
            "description": forms.Textarea(
                attrs={
                    **BOOTSTRAP_INPUT,
                    "rows": 6,
                    "placeholder": "Please describe your issue in detail",
                    "required": True,
                }
            ),
            "is_anonymous": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.student = kwargs.pop("student", None)
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].empty_label = "--Select--"
        self.fields["category"].choices = ComplaintCategory.choices

    def clean_subject(self):
        subject = (self.cleaned_data.get("subject") or "").strip()
        if len(subject) < 5:
            raise ValidationError(
                _("Please provide a subject of at least 5 characters.")
            )
        return subject

    def clean_description(self):
        description = (self.cleaned_data.get("description") or "").strip()
        if len(description) < 20:
            raise ValidationError(
                _("Please describe the issue in at least 20 characters.")
            )
        return description

    def save(self, commit=True):
        complaint = super().save(commit=False)
        if self.student is not None and complaint.student_id is None:
            complaint.student = self.student
        if commit:
            complaint.save()
        return complaint


class StatusUpdateForm(forms.Form):
    """HOD/Admin status change, constrained by the state machine (FR-8)."""

    status = forms.ChoiceField(
        label=_("New status"), choices=(), widget=forms.Select(attrs=BOOTSTRAP_SELECT)
    )
    note = forms.CharField(
        label=_("Note (optional)"),
        required=False,
        widget=forms.Textarea(attrs={**BOOTSTRAP_INPUT, "rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        self.complaint = kwargs.pop("complaint")
        super().__init__(*args, **kwargs)
        labels = dict(ComplaintStatus.choices)
        allowed = ALLOWED_TRANSITIONS.get(self.complaint.status, set())
        self.fields["status"].choices = [
            (value, labels[value]) for value in sorted(allowed)
        ]
        if not allowed:
            self.fields["status"].widget.attrs["disabled"] = True

    def clean_status(self):
        status = self.cleaned_data["status"]
        if not self.complaint.can_transition_to(status):
            raise ValidationError(
                _("'%(new)s' is not a valid next status for this complaint.")
                % {"new": dict(ComplaintStatus.choices).get(status, status)}
            )
        return status


class AssignComplaintForm(forms.Form):
    """Assign a complaint to a staff member (UC10)."""

    assigned_to = forms.ModelChoiceField(
        label=_("Assign to"),
        queryset=User.objects.none(),
        widget=forms.Select(attrs=BOOTSTRAP_SELECT),
    )
    note = forms.CharField(
        label=_("Assignment note (optional)"),
        required=False,
        widget=forms.Textarea(attrs={**BOOTSTRAP_INPUT, "rows": 2}),
    )

    def __init__(self, *args, **kwargs):
        self.complaint = kwargs.pop("complaint")
        super().__init__(*args, **kwargs)
        self.fields["assigned_to"].queryset = User.objects.filter(
            is_active=True,
            role__in=[Role.HOD, Role.ADMIN],
            department_id=self.complaint.department_id,
        ) | User.objects.filter(is_active=True, role=Role.ADMIN)
        self.fields["assigned_to"].queryset = self.fields[
            "assigned_to"
        ].queryset.distinct().order_by("full_name")


class RemarkForm(forms.ModelForm):
    """Add a remark / progress note (UC12)."""

    class Meta:
        model = ComplaintRemark
        fields = ["text", "is_internal"]
        labels = {"text": _("Remark"), "is_internal": _("Internal note (hidden from the complainant)")}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    **BOOTSTRAP_INPUT,
                    "rows": 3,
                    "placeholder": "Add a progress note or reply",
                }
            ),
            "is_internal": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # Students cannot write internal notes.
        if self.user is not None and self.user.is_student:
            del self.fields["is_internal"]

    def clean_text(self):
        text = (self.cleaned_data.get("text") or "").strip()
        if len(text) < 3:
            raise ValidationError(_("Remark is too short."))
        return text


class ComplaintFilterForm(forms.Form):
    """Filter / search bar shared by the HOD and Admin dashboards (UC13)."""

    q = forms.CharField(
        label=_("Search"),
        required=False,
        widget=forms.TextInput(
            attrs={
                **BOOTSTRAP_INPUT,
                "placeholder": "Keyword or complaint reference",
            }
        ),
    )
    status = forms.ChoiceField(
        label=_("Status"),
        required=False,
        choices=[("", "All statuses")] + list(ComplaintStatus.choices),
        widget=forms.Select(attrs=BOOTSTRAP_SELECT),
    )
    category = forms.ChoiceField(
        label=_("Category"),
        required=False,
        choices=[("", "All categories")] + list(ComplaintCategory.choices),
        widget=forms.Select(attrs=BOOTSTRAP_SELECT),
    )
    department = forms.ModelChoiceField(
        label=_("Department"),
        required=False,
        queryset=Department.objects.all(),
        empty_label="All departments",
        widget=forms.Select(attrs=BOOTSTRAP_SELECT),
    )
    date_from = forms.DateField(
        label=_("From"),
        required=False,
        widget=forms.DateInput(attrs={**BOOTSTRAP_INPUT, "type": "date"}),
    )
    date_to = forms.DateField(
        label=_("To"),
        required=False,
        widget=forms.DateInput(attrs={**BOOTSTRAP_INPUT, "type": "date"}),
    )
    sort = forms.ChoiceField(
        label=_("Sort by"),
        required=False,
        choices=[
            ("-created_at", "Newest first"),
            ("created_at", "Oldest first"),
            ("status", "Status"),
            ("department__name", "Department"),
        ],
        widget=forms.Select(attrs=BOOTSTRAP_SELECT),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        # An HOD is locked to their own department - the field is removed entirely
        # so it cannot be tampered with via query string.
        if user is not None and not user.is_admin_role:
            del self.fields["department"]

    def clean(self):
        cleaned = super().clean()
        date_from, date_to = cleaned.get("date_from"), cleaned.get("date_to")
        if date_from and date_to and date_from > date_to:
            self.add_error("date_to", _("'To' date must not precede the 'From' date."))
        return cleaned
