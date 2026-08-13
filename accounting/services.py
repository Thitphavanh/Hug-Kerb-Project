from collections import defaultdict
from datetime import datetime, time
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from pos.models import Expense, Payment

from .labels import localized_category_name
from .models import CashBook


CURRENCIES = ("LAK", "THB", "USD")
ZERO = Decimal("0")


def _payment_method_label(value):
    return {
        "cash": _("Cash"),
        "transfer": _("Bank transfer"),
        "qr": _("QR payment"),
        "other": _("Other"),
    }.get(value, value)


def _status_label(value):
    return {
        "confirmed": _("Confirmed"),
        "draft": _("Draft"),
        "void": _("Void"),
    }.get(value, value)


def _legacy_expense_category(value):
    return {
        "supplies": _("Supplies and cleaning products"),
        "rent": _("Rent"),
        "utility": _("Utilities"),
        "salary": _("Salaries and wages"),
        "marketing": _("Marketing and advertising"),
        "other": _("Other expenses"),
    }.get(value, value)


def confirmed_cashbook():
    return CashBook.objects.filter(status=CashBook.Status.CONFIRMED)


def _aware_bounds(start_date=None, end_date=None):
    start_dt = None
    end_dt = None
    if start_date:
        start_dt = timezone.make_aware(datetime.combine(start_date, time.min))
    if end_date:
        end_dt = timezone.make_aware(datetime.combine(end_date, time.max))
    return start_dt, end_dt


def totals_by_currency(start_date=None, end_date=None, payment_method=None):
    """Return separate totals per currency; currencies are never converted implicitly."""
    result = {
        currency: {"income": ZERO, "expense": ZERO, "balance": ZERO}
        for currency in CURRENCIES
    }
    manual = confirmed_cashbook()
    # ແຖວທີ່ຖືກ void ບໍ່ນັບເປັນລາຍຮັບ — ຄືບໍ່ເຄີຍເກີດຂຶ້ນ
    payments = Payment.objects.live()
    expenses = Expense.objects.all()

    if start_date:
        manual = manual.filter(date__gte=start_date)
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        manual = manual.filter(date__lte=end_date)
        expenses = expenses.filter(date__lte=end_date)

    start_dt, end_dt = _aware_bounds(start_date, end_date)
    if start_dt:
        payments = payments.filter(paid_at__gte=start_dt)
    if end_dt:
        payments = payments.filter(paid_at__lte=end_dt)

    if payment_method:
        manual = manual.filter(payment_method=payment_method)
        payments = payments.filter(method=payment_method)
        # The legacy POS Expense model has no payment method. Shop expenses are
        # treated as cash for handover until that source gains a method field.
        if payment_method != CashBook.PaymentMethod.CASH:
            expenses = expenses.none()

    for row in manual.values("currency", "transaction_type").annotate(total=Sum("amount")):
        bucket = "income" if row["transaction_type"] == "IN" else "expense"
        result[row["currency"]][bucket] += row["total"] or ZERO
    # ຮັບເງິນ = ລາຍຮັບ, ຄືນເງິນ = ຫັກອອກຈາກລາຍຮັບ (ບໍ່ແມ່ນລາຍຈ່າຍ)
    for row in payments.values("currency", "kind").annotate(total=Sum("amount")):
        total = row["total"] or ZERO
        if row["kind"] == Payment.Kind.REFUND:
            result[row["currency"]]["income"] -= total
        else:
            result[row["currency"]]["income"] += total
    for row in expenses.values("currency").annotate(total=Sum("amount")):
        result[row["currency"]]["expense"] += row["total"] or ZERO

    for values in result.values():
        values["balance"] = values["income"] - values["expense"]
    return result


def unified_transactions(
    start_date=None,
    end_date=None,
    currency="",
    transaction_type="",
    query="",
    category_id="",
    limit=None,
):
    """Merge editable ledger entries with read-only POS income and expenses."""
    manual = CashBook.objects.select_related("category", "created_by")
    payments = Payment.objects.live().select_related("order", "order__customer")
    expenses = Expense.objects.all()

    if start_date:
        manual = manual.filter(date__gte=start_date)
        expenses = expenses.filter(date__gte=start_date)
    if end_date:
        manual = manual.filter(date__lte=end_date)
        expenses = expenses.filter(date__lte=end_date)
    start_dt, end_dt = _aware_bounds(start_date, end_date)
    if start_dt:
        payments = payments.filter(paid_at__gte=start_dt)
    if end_dt:
        payments = payments.filter(paid_at__lte=end_dt)

    if currency:
        manual = manual.filter(currency=currency)
        payments = payments.filter(currency=currency)
        expenses = expenses.filter(currency=currency)
    if transaction_type == "IN":
        manual = manual.filter(transaction_type="IN")
        payments = payments.filter(kind=Payment.Kind.PAYMENT)
        expenses = expenses.none()
    elif transaction_type == "OUT":
        manual = manual.filter(transaction_type="OUT")
        # ຄືນເງິນເປັນເງິນອອກ ຈຶ່ງຍັງຕ້ອງສະແດງໃນລາຍການ "ລາຍຈ່າຍ"
        payments = payments.filter(kind=Payment.Kind.REFUND)
    if category_id:
        manual = manual.filter(category_id=category_id)
        payments = payments.none()
        expenses = expenses.none()
    if query:
        manual = manual.filter(
            Q(description__icontains=query)
            | Q(reference__icontains=query)
            | Q(note__icontains=query)
        )
        payments = payments.filter(
            Q(order__order_number__icontains=query)
            | Q(order__customer__name__icontains=query)
            | Q(note__icontains=query)
        )
        expenses = expenses.filter(description__icontains=query)

    rows = []
    for item in manual:
        rows.append(
            {
                "sort_at": timezone.make_aware(datetime.combine(item.date, item.time)),
                "date": item.date,
                "time": item.time,
                "type": item.transaction_type,
                "type_label": _("Income") if item.transaction_type == "IN" else _("Expense"),
                "description": item.description,
                "category": localized_category_name(item.category),
                "category_color": item.category.color,
                "amount": item.amount,
                "currency": item.currency,
                "method": _payment_method_label(item.payment_method),
                "reference": item.reference,
                "source": "manual",
                "source_label": _("Manual"),
                "status": item.status,
                "status_label": _status_label(item.status),
                "object": item,
            }
        )
    for item in payments:
        local_paid_at = timezone.localtime(item.paid_at)
        customer = item.order.customer.name if item.order.customer else _("Walk-in customer")
        is_refund = item.kind == Payment.Kind.REFUND
        rows.append(
            {
                "sort_at": local_paid_at,
                "date": local_paid_at.date(),
                "time": local_paid_at.time(),
                "type": "OUT" if is_refund else "IN",
                "type_label": _("Refund") if is_refund else _("Income"),
                "description": (
                    _("Refund for %(order)s — %(customer)s")
                    if is_refund
                    else _("Payment for %(order)s — %(customer)s")
                ) % {
                    "order": item.order.order_number,
                    "customer": customer,
                },
                "category": _("POS income"),
                "category_color": "#22d3ee",
                "amount": item.amount,
                "currency": item.currency,
                "method": _payment_method_label(item.method),
                "reference": item.order.order_number,
                "source": "pos",
                "source_label": "POS",
                "status": "confirmed",
                "status_label": _("Confirmed"),
                "object": item,
            }
        )
    for item in expenses:
        rows.append(
            {
                "sort_at": timezone.make_aware(datetime.combine(item.date, time.min)),
                "date": item.date,
                "time": None,
                "type": "OUT",
                "type_label": _("Expense"),
                "description": item.description,
                "category": _legacy_expense_category(item.category),
                "category_color": "#fb7185",
                "amount": item.amount,
                "currency": item.currency,
                "method": _("Cash"),
                "reference": f"EXP-{item.pk}",
                "source": "pos_expense",
                "source_label": _("POS expense"),
                "status": "confirmed",
                "status_label": _("Confirmed"),
                "object": item,
            }
        )
    rows.sort(key=lambda row: row["sort_at"], reverse=True)
    return rows[:limit] if limit else rows


def grouped_report(start_date, end_date, grouping="daily"):
    rows = unified_transactions(start_date, end_date)
    grouped = defaultdict(lambda: {"income": ZERO, "expense": ZERO})
    for row in rows:
        if row["status"] != "confirmed":
            continue
        date = row["date"]
        if grouping == "monthly":
            period = date.replace(day=1)
        elif grouping == "yearly":
            period = date.replace(month=1, day=1)
        else:
            period = date
        key = (period, row["currency"])
        bucket = "income" if row["type"] == "IN" else "expense"
        grouped[key][bucket] += row["amount"]

    result = []
    for (period, currency), values in sorted(grouped.items(), reverse=True):
        result.append(
            {
                "period": period,
                "currency": currency,
                "income": values["income"],
                "expense": values["expense"],
                "balance": values["income"] - values["expense"],
            }
        )
    return result
