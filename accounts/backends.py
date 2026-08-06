"""Authentication backend allowing login by email *or* institutional ID."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrIdentifierBackend(ModelBackend):
    """
    Authenticate against ``email`` or ``identifier``.

    The login screen offers Student ID / Staff ID / Email depending on the
    selected role, so both keys must resolve to the same account (FR-2).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        login_value = username or kwargs.get("email") or kwargs.get(User.USERNAME_FIELD)
        if not login_value or not password:
            return None

        login_value = login_value.strip()
        try:
            user = User.objects.get(
                Q(email__iexact=login_value) | Q(identifier__iexact=login_value)
            )
        except User.DoesNotExist:
            # Run the default hasher anyway to keep timing uniform.
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:  # pragma: no cover - unique columns
            user = (
                User.objects.filter(
                    Q(email__iexact=login_value) | Q(identifier__iexact=login_value)
                )
                .order_by("id")
                .first()
            )
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
