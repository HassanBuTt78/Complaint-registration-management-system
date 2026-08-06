"""Authentication and user-management forms (FR-1, FR-2, FR-10)."""

from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import Department, Role

User = get_user_model()

BOOTSTRAP_INPUT = {"class": "form-control"}
BOOTSTRAP_SELECT = {"class": "form-select"}


class StudentSignUpForm(forms.ModelForm):
    """
    Public registration (FR-1).

    Only *Student* accounts can be created here; HOD and Admin accounts are
    provisioned by the Principal through the Admin dashboard (FR-10).
    """

    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={**BOOTSTRAP_INPUT, "autocomplete": "new-password"}
        ),
        help_text=_("At least 8 characters; not entirely numeric or too common."),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={**BOOTSTRAP_INPUT, "autocomplete": "new-password"}
        ),
    )
    accept_terms = forms.BooleanField(
        label=_("I confirm the information provided is accurate"),
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    class Meta:
        model = User
        fields = ["full_name", "email", "identifier", "phone", "department"]
        labels = {
            "identifier": _("Student ID / Roll number"),
            "department": _("Your department"),
        }
        widgets = {
            "full_name": forms.TextInput(
                attrs={**BOOTSTRAP_INPUT, "placeholder": "Enter your full name"}
            ),
            "email": forms.EmailInput(
                attrs={**BOOTSTRAP_INPUT, "placeholder": "you@example.com"}
            ),
            "identifier": forms.TextInput(
                attrs={**BOOTSTRAP_INPUT, "placeholder": "e.g. BSIT-22-084600"}
            ),
            "phone": forms.TextInput(
                attrs={**BOOTSTRAP_INPUT, "placeholder": "03xx-xxxxxxx"}
            ),
            "department": forms.Select(attrs=BOOTSTRAP_SELECT),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].required = True
        self.fields["identifier"].required = True
        self.fields["phone"].required = False

    def clean_email(self):
        email = (self.cleaned_data["email"] or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError(_("An account with this email already exists."))
        return email

    def clean_identifier(self):
        identifier = (self.cleaned_data.get("identifier") or "").strip()
        if not identifier:
            raise ValidationError(_("Your student ID is required."))
        if User.objects.filter(identifier__iexact=identifier).exists():
            raise ValidationError(_("This student ID is already registered."))
        return identifier

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("The two password fields did not match."))
        if p1:
            temp = User(
                email=cleaned.get("email") or "",
                full_name=cleaned.get("full_name") or "",
            )
            try:
                password_validation.validate_password(p1, temp)
            except ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = Role.STUDENT
        user.username = user.email
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class PortalLoginForm(AuthenticationForm):
    """Login accepting an email or an institutional ID (FR-2)."""

    username = forms.CharField(
        label=_("Email or ID"),
        widget=forms.TextInput(
            attrs={
                **BOOTSTRAP_INPUT,
                "autofocus": True,
                "placeholder": "Enter your email or ID",
                "autocomplete": "username",
            }
        ),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                **BOOTSTRAP_INPUT,
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
            }
        ),
    )
    remember_me = forms.BooleanField(
        label=_("Remember me"),
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )

    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": _(
            "Invalid credentials. Please check your email/ID and password."
        ),
        "inactive": _("This account has been deactivated. Contact the administrator."),
    }


class AdminUserForm(forms.ModelForm):
    """Admin-side create/update of any user, including role assignment (FR-10)."""

    password1 = forms.CharField(
        label=_("Password"),
        strip=False,
        required=False,
        widget=forms.PasswordInput(attrs={**BOOTSTRAP_INPUT, "autocomplete": "off"}),
        help_text=_("Leave blank when editing to keep the existing password."),
    )
    password2 = forms.CharField(
        label=_("Confirm password"),
        strip=False,
        required=False,
        widget=forms.PasswordInput(attrs={**BOOTSTRAP_INPUT, "autocomplete": "off"}),
    )

    class Meta:
        model = User
        fields = [
            "full_name",
            "email",
            "identifier",
            "phone",
            "role",
            "department",
            "is_active",
        ]
        widgets = {
            "full_name": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "email": forms.EmailInput(attrs=BOOTSTRAP_INPUT),
            "identifier": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "phone": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "role": forms.Select(attrs=BOOTSTRAP_SELECT),
            "department": forms.Select(attrs=BOOTSTRAP_SELECT),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.filter(is_active=True)
        self.fields["department"].required = False
        self.fields["identifier"].required = False
        if self.instance.pk is None:
            self.fields["password1"].required = True
            self.fields["password2"].required = True

    def clean_email(self):
        email = (self.cleaned_data["email"] or "").strip().lower()
        qs = User.objects.filter(email__iexact=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_("An account with this email already exists."))
        return email

    def clean_identifier(self):
        identifier = (self.cleaned_data.get("identifier") or "").strip()
        if not identifier:
            return None
        qs = User.objects.filter(identifier__iexact=identifier)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError(_("This ID is already assigned to another user."))
        return identifier

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        department = cleaned.get("department")

        # Invalid role/department combinations are blocked (FR-10 business rule).
        if role == Role.HOD and not department:
            self.add_error(
                "department", _("A Head of Department must be given a department.")
            )
        if role == Role.ADMIN and department:
            cleaned["department"] = None

        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 or p2:
            if p1 != p2:
                self.add_error("password2", _("The two password fields did not match."))
            else:
                try:
                    password_validation.validate_password(p1, self.instance)
                except ValidationError as exc:
                    self.add_error("password1", exc)
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        if user.role == Role.ADMIN:
            user.department = None
        if commit:
            user.save()
        return user


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ["name", "code", "description", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "code": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "description": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_code(self):
        return (self.cleaned_data["code"] or "").strip().upper()


class ProfileForm(forms.ModelForm):
    """Self-service profile update for any signed-in user."""

    class Meta:
        model = User
        fields = ["full_name", "phone"]
        widgets = {
            "full_name": forms.TextInput(attrs=BOOTSTRAP_INPUT),
            "phone": forms.TextInput(attrs=BOOTSTRAP_INPUT),
        }
