from django import template

register = template.Library()

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
