from django import template
from django.utils.translation import gettext

register = template.Library()

SERVICE_NAME_MSGIDS = (
    "AI Condition Report",
    "Color Touch-up",
    "Deep Clean Service",
    "Premium Spa + Deodorize",
    "Sole Restoration",
)

@register.filter(name='money')
def money(value):
    if value is None or value == "":
        return "0"
    try:
        val = float(value)
        if val.is_integer():
            return f"{int(val):,}"
        else:
            # Check if decimal part is 0 (e.g. 150000.0)
            if (val * 100) % 100 == 0:
                return f"{int(val):,}"
            return f"{val:,.2f}"
    except (ValueError, TypeError):
        return value


@register.filter(name="service_name")
def service_name(value):
    """Translate known database-backed service names in the active language."""
    text = getattr(value, "name", value)
    if not text:
        return ""
    text = str(text)
    return gettext(text) if text in SERVICE_NAME_MSGIDS else text


@register.filter(name="service_description")
def service_description(value):
    """Translate a known service-name prefix while preserving item details."""
    if not value:
        return ""
    text = str(value)
    for msgid in SERVICE_NAME_MSGIDS:
        if text == msgid or text.startswith(f"{msgid} "):
            return f"{gettext(msgid)}{text[len(msgid):]}"
    return text
