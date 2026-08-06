"""
Template helpers.

Django templates cannot pass arguments to model methods, so identity masking is
exposed as filters that always route through the model's single source of truth
(``Complaint.complainant_display`` / ``identity_visible_to``).
"""

from django import template

register = template.Library()


@register.filter
def complainant_for(complaint, user):
    """Complainant name as ``user`` is entitled to see it (FR-5)."""
    return complaint.complainant_display(user)


@register.filter
def complainant_id_for(complaint, user):
    """Complainant institutional ID as ``user`` is entitled to see it."""
    return complaint.complainant_identifier(user)


@register.filter
def identity_visible(complaint, user):
    return complaint.identity_visible_to(user)


@register.filter
def status_count(counts, status_value):
    """Look up a status tally from the dict built by the dashboard views."""
    try:
        return counts.get(status_value, 0)
    except AttributeError:
        return 0


@register.simple_tag
def querystring_replace(request, **kwargs):
    """Rebuild the current query string with ``kwargs`` overridden."""
    params = request.GET.copy()
    for key, value in kwargs.items():
        if value in (None, ""):
            params.pop(key, None)
        else:
            params[key] = value
    params.pop("page", None)
    encoded = params.urlencode()
    return f"?{encoded}" if encoded else "?"
