import re
from collections import defaultdict
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext as _

from pos.models import Expense, Payment

from .labels import localized_category_name
from .models import CashBook


CURRENCIES = ("LAK", "THB", "USD")
ZERO = Decimal("0")

# ໃບແຈ້ງຍອດແຍກຕາມ "ກະເປົ໋າ" ທີ່ເງິນຢູ່ ບໍ່ແມ່ນຕາມຊ່ອງທາງດິບ:
# ສະແກນ QR ເງິນເຂົ້າບັນຊີທະນາຄານ ຈຶ່ງນັບຮ່ວມກັບເງິນໂອນ.
PAYMENT_GROUPS = {
    "cash": (CashBook.PaymentMethod.CASH,),
    "bank": (CashBook.PaymentMethod.TRANSFER, CashBook.PaymentMethod.QR),
    "other": (CashBook.PaymentMethod.OTHER,),
}
STATEMENT_GROUPS = ("cash", "bank", "other")


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


def pl_bucket(row):
    """ແຖວນີ້ລົງທາງໃດໃນລາຍງານກຳໄລ-ຂາດທຶນ → (bucket, ຈຳນວນທີ່ມີເຄື່ອງໝາຍ)

    ກົດດຽວທີ່ທຸກລາຍງານກຳໄລ-ຂາດທຶນຕ້ອງໃຊ້ຮ່ວມກັນ:
    ຄືນເງິນລູກຄ້າ = ຫັກອອກຈາກ *ລາຍຮັບ* ບໍ່ແມ່ນເພີ່ມເປັນ *ລາຍຈ່າຍ*
    (ຖ້ານັບເປັນລາຍຈ່າຍ ຍອດສຸດທິຈະຖືກ ແຕ່ຍອດຂາຍ ແລະ ຍອດຈ່າຍຈະບວມທັງສອງຝັ່ງ)
    """
    if row.get("refund"):
        return "income", -row["amount"]
    if row["type"] == "IN":
        return "income", row["amount"]
    return "expense", row["amount"]


def operational_rows(rows):
    """ສະເພາະແຖວທີ່ນັບເຂົ້າກຳໄລ-ຂາດທຶນ: ຢືນຢັນແລ້ວ ແລະ ບໍ່ແມ່ນການຍ້າຍເງິນພາຍໃນ"""
    return [
        row for row in rows if row["status"] == "confirmed" and not row["internal"]
    ]


def exclude_internal_transfers(queryset):
    """ຕັດການຍ້າຍເງິນລະຫວ່າງກະເປົ໋າຂອງຮ້ານເອງອອກ (ເຊັ່ນ ເງິນສົດ → ບັນຊີທະນາຄານ)

    ນີ້ຄື gate ອັນດຽວທີ່ທຸກລາຍງານກຳໄລ-ຂາດທຶນຕ້ອງຜ່ານ. ຖ້າບໍ່ຕັດ ເງິນກ້ອນດຽວ
    ຈະຖືກນັບເປັນລາຍຈ່າຍຕອນອອກຈາກກຳປັ່ນ ແລະ ນັບເປັນລາຍຮັບຕອນເຂົ້າບັນຊີ
    ເຮັດໃຫ້ທັງລາຍຮັບ ແລະ ລາຍຈ່າຍ ບວມຂຶ້ນທັງສອງຝັ່ງ.
    ໃບແຈ້ງຍອດ (statement) ບໍ່ໃຊ້ helper ນີ້ — ຢູ່ນັ້ນເງິນຍ້າຍຈິງ ຈຶ່ງຕ້ອງເຫັນ.
    """
    return queryset.exclude(category__is_internal_transfer=True)


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
    # ແຖວທີ່ຖືກ void ບໍ່ນັບເປັນລາຍຮັບ — ຄືບໍ່ເຄີຍເກີດຂຶ້ນ
    # ແລະ ການຍ້າຍເງິນເຂົ້າບັນຊີຕົນເອງບໍ່ແມ່ນລາຍຮັບ/ລາຍຈ່າຍ
    manual = exclude_internal_transfers(confirmed_cashbook())
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
                "internal": item.category.is_internal_transfer,
                "refund": False,
                "raw_method": item.payment_method,
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
                # ຄືນເງິນຕ້ອງມີປ້າຍຂອງໂຕເອງ — ຂຶ້ນ "ລາຍຮັບຈາກ POS" ໃນຖັນເງິນອອກ
                # ເຮັດໃຫ້ຄົນອ່ານລາຍງານເຂົ້າໃຈຜິດ
                "category": _("POS refund") if is_refund else _("POS income"),
                "category_color": "#fb7185" if is_refund else "#22d3ee",
                "amount": item.amount,
                "currency": item.currency,
                "method": _payment_method_label(item.method),
                "reference": item.order.order_number,
                "source": "pos",
                "source_label": "POS",
                "status": "confirmed",
                "status_label": _("Confirmed"),
                "internal": False,
                # ທຸງບອກລາຍງານກຳໄລ-ຂາດທຶນວ່າແຖວນີ້ຕ້ອງຫັກອອກຈາກລາຍຮັບ
                # ສ່ວນໃບແຈ້ງຍອດຍັງໃຊ້ type=OUT ຢູ່ ເພາະເງິນອອກຈາກກຳປັ່ນຈິງ
                "refund": is_refund,
                "raw_method": item.method,
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
                "internal": False,
                "refund": False,
                "raw_method": CashBook.PaymentMethod.CASH,
                "object": item,
            }
        )
    rows.sort(key=lambda row: row["sort_at"], reverse=True)
    return rows[:limit] if limit else rows


def payment_group(raw_method):
    """ຈັດຊ່ອງທາງຊຳລະເຂົ້າ "ກະເປົ໋າ" ທີ່ເງິນໄປນອນຢູ່ຈິງ"""
    for group, methods in PAYMENT_GROUPS.items():
        if raw_method in methods:
            return group
    return "other"


def payment_group_label(group):
    return {
        "cash": _("Cash"),
        "bank": _("Bank account"),
        "other": _("Other channels"),
    }.get(group, group)


def statement_rows(start_date, end_date, currency, group=None):
    """ແຖວສຳລັບໃບແຈ້ງຍອດ ຮຽງເກົ່າ → ໃໝ່

    ຕ່າງຈາກລາຍງານກຳໄລ-ຂາດທຶນຢູ່ຈຸດດຽວ: ບໍ່ຕັດການຍ້າຍເງິນພາຍໃນອອກ ເພາະ
    ໃນໃບແຈ້ງຍອດ ເງິນຍ້າຍອອກຈາກກຳປັ່ນຈິງ ແລະ ເຂົ້າບັນຊີຈິງ ຕ້ອງເຫັນທັງສອງຝັ່ງ.
    """
    rows = [
        row
        for row in unified_transactions(start_date, end_date, currency=currency)
        if row["status"] == "confirmed"
        and (group is None or payment_group(row["raw_method"]) == group)
    ]
    rows.sort(key=lambda row: row["sort_at"])
    return rows


def statement_opening_balance(start_date, currency, group):
    """ຍອດຍົກມາ — ຜົນລວມທຸກລາຍການກ່ອນວັນທີເລີ່ມງວດ"""
    if not start_date or group is None:
        return ZERO
    balance = ZERO
    for row in statement_rows(None, start_date - timedelta(days=1), currency, group):
        balance += row["amount"] if row["type"] == "IN" else -row["amount"]
    return balance


def totals_by_payment_group(rows):
    """{'IN': {'cash': …, 'bank': …, 'other': …}, 'OUT': {…}} ຈາກແຖວທີ່ສົ່ງມາ"""
    totals = {
        "IN": {group: ZERO for group in STATEMENT_GROUPS},
        "OUT": {group: ZERO for group in STATEMENT_GROUPS},
    }
    for row in rows:
        totals[row["type"]][payment_group(row["raw_method"])] += row["amount"]
    return totals


def normalize_category_key(name):
    """ຫຍໍ້ຊື່ໝວດທີ່ໝາຍຄວາມຄືກັນໃຫ້ເປັນ key ດຽວ

    ໝວດທີ່ມີປ້າຍພາສາອັງກິດໃນວົງເລັບທ້າຍຊື່ ຈະຖືກລວມຕາມປ້າຍນັ້ນ ເຮັດໃຫ້
    ການສະກົດຕ່າງກັນເລັກນ້ອຍບໍ່ແຍກເປັນສອງແຖວໃນລາຍງານ.
    """
    text = str(name or "").strip()
    if not text:
        return "∅"
    match = re.search(r"\(([^)]+)\)\s*$", text)
    return (match.group(1) if match else text).strip().lower()


def group_by_category(rows, transaction_type, currency, default_other=None):
    """ລວມຍອດຕາມໝວດ → [{'description', 'amount'}] ຮຽງຈາກຫຼາຍໄປໜ້ອຍ

    ໃຊ້ກົດດຽວກັບ pl_bucket(): ຄືນເງິນຂຶ້ນເປັນແຖວ *ຕິດລົບ* ໃນຝັ່ງລາຍຮັບ
    ບໍ່ແມ່ນແຖວບວກໃນຝັ່ງລາຍຈ່າຍ — ຜົນລວມຈຶ່ງກົງກັບການ໌ດຍອດລວມສະເໝີ
    """
    default_other = default_other or _("Other")
    bucket_wanted = "income" if transaction_type == "IN" else "expense"
    merged = {}
    order = []
    for row in rows:
        if row["currency"] != currency or row["status"] != "confirmed":
            continue
        bucket, amount = pl_bucket(row)
        if bucket != bucket_wanted:
            continue
        name = row["category"] or default_other
        key = normalize_category_key(name)
        if key not in merged:
            merged[key] = {"description": name, "amount": ZERO}
            order.append(key)
        merged[key]["amount"] += amount
    result = [merged[key] for key in order]
    result.sort(key=lambda item: -item["amount"])
    return result


def group_by_category_and_payment(rows, default_other=None):
    """ຄືກັບ group_by_category ແຕ່ແຍກຍອດແຕ່ລະໝວດອອກເປັນ ເງິນສົດ / ບັນຊີ / ອື່ນໆ"""
    default_other = default_other or _("Other")
    merged = {}
    order = []
    for row in rows:
        name = row["category"] or default_other
        key = normalize_category_key(name)
        if key not in merged:
            merged[key] = {"description": name} | {
                group: ZERO for group in STATEMENT_GROUPS
            }
            order.append(key)
        merged[key][payment_group(row["raw_method"])] += row["amount"]
    result = []
    for key in order:
        item = merged[key]
        item["amount"] = sum(item[group] for group in STATEMENT_GROUPS)
        result.append(item)
    result.sort(key=lambda item: -item["amount"])
    return result


def grouped_report(start_date, end_date, grouping="daily"):
    rows = operational_rows(unified_transactions(start_date, end_date))
    grouped = defaultdict(lambda: {"income": ZERO, "expense": ZERO})
    for row in rows:
        date = row["date"]
        if grouping == "monthly":
            period = date.replace(day=1)
        elif grouping == "yearly":
            period = date.replace(month=1, day=1)
        else:
            period = date
        key = (period, row["currency"])
        bucket, amount = pl_bucket(row)
        grouped[key][bucket] += amount

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
