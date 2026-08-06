"""Authentication views: registration, login, logout, profile (FR-1, FR-2)."""

from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from .forms import PortalLoginForm, ProfileForm, StudentSignUpForm
from .models import AuditAction, AuditLog


class PortalLoginView(LoginView):
    """Login screen with audit logging and django-axes lockout protection."""

    template_name = "registration/login.html"
    authentication_form = PortalLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)  # expire at browser close
        AuditLog.record(
            actor=self.request.user,
            action=AuditAction.LOGIN_SUCCESS,
            target=self.request.user.email,
            request=self.request,
        )
        messages.success(
            self.request, f"Welcome back, {self.request.user.get_short_name()}."
        )
        return response

    def form_invalid(self, form):
        AuditLog.record(
            action=AuditAction.LOGIN_FAILED,
            target=(form.data.get("username") or "")[:255],
            detail="Invalid credentials supplied.",
            request=self.request,
        )
        messages.error(self.request, "Invalid credentials. Please try again.")
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse("dashboards:home")


@require_http_methods(["GET", "POST"])
def signup(request):
    """Public student registration (FR-1, Algorithm 1)."""
    if request.user.is_authenticated:
        return redirect("dashboards:home")

    if request.method == "POST":
        form = StudentSignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            AuditLog.record(
                actor=user,
                action=AuditAction.REGISTER,
                target=user.email,
                detail="Student self-registration.",
                request=request,
            )
            messages.success(
                request,
                "Registration complete. You can now sign in with your credentials.",
            )
            return redirect("accounts:login")
        messages.error(request, "Please correct the highlighted errors and try again.")
    else:
        form = StudentSignUpForm()

    return render(request, "registration/signup.html", {"form": form})


@require_http_methods(["POST", "GET"])
def logout_view(request):
    if request.user.is_authenticated:
        AuditLog.record(
            actor=request.user,
            action=AuditAction.LOGOUT,
            target=request.user.email,
            request=request,
        )
    auth_logout(request)
    messages.info(request, "You have been signed out.")
    return redirect("accounts:login")


@login_required
def profile(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
        messages.error(request, "Please correct the errors below.")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


def register_success_redirect(request):  # pragma: no cover - convenience alias
    return redirect("accounts:login")


__all__ = [
    "PortalLoginView",
    "signup",
    "logout_view",
    "profile",
    "auth_login",
]
