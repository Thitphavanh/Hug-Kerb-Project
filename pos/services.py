"""ຕັກກະການຮັບເງິນ ແລະ ການສົ່ງມອບເຄື່ອງ (POS Scope 2.1)

ເຫດຜົນທີ່ແຍກອອກມາຈາກ views.py:
ການຮັບເງິນຖືກເອີ້ນຈາກຫຼາຍທາງ (ໜ້າຄິດເງິນ, ປຸ່ມດ່ວນໃນໃບບິນ, ອະນາຄົດ: API)
ຕັກກະ ledger + idempotency + ການປະທັບ Stamp ຈຶ່ງຕ້ອງຢູ່ບ່ອນດຽວ ບໍ່ໃຫ້ຊ້ຳກັນ.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import BASE_CURRENCY, ZERO, Order, Payment


def resolve_fx_rate(currency, submitted=None):
    """ອັດຕາແລກປ່ຽນ 1 ໜ່ວຍຂອງ currency → ສະກຸນຫຼັກ

    ລຳດັບຄວາມສຳຄັນ: ຄ່າທີ່ພະນັກງານປ້ອນ → ຄ່າໃນ settings → 1
    ສະກຸນຫຼັກເອງແມ່ນ 1 ສະເໝີ ບໍ່ໃຫ້ໃຜ override
    """
    if currency == BASE_CURRENCY:
        return Decimal("1")

    if submitted not in (None, ""):
        try:
            rate = Decimal(str(submitted))
        except (InvalidOperation, TypeError):
            raise ValidationError(_("The exchange rate is not a valid number."))
        if rate <= ZERO:
            raise ValidationError(_("The exchange rate must be greater than zero."))
        return rate

    configured = getattr(settings, "POS_FX_RATES", {}) or {}
    if currency in configured:
        return Decimal(str(configured[currency]))

    raise ValidationError(
        _("No exchange rate is set for %(currency)s. Enter the rate to continue.")
        % {"currency": currency}
    )


def _as_decimal(value, field_label):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(
            _("%(field)s is not a valid number.") % {"field": field_label}
        )


@transaction.atomic
def record_payment(
    *,
    order,
    amount,
    method,
    currency=None,
    tendered=None,
    fx_rate=None,
    kind=Payment.Kind.PAYMENT,
    user=None,
    idempotency_key=None,
    note="",
):
    """ບັນທຶກ 1 ແຖວໃນ ledger ແລ້ວຄິດສະຖານະບິນຄືນໃໝ່

    ຄືນຄ່າ (payment, created) — created=False ໝາຍວ່າ idempotency_key ຊ້ຳ
    ຈຶ່ງສົ່ງແຖວເກົ່າຄືນໃຫ້ ບໍ່ໄດ້ຮັບເງິນເພີ່ມ.
    """
    if idempotency_key:
        existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
        if existing is not None:
            if existing.order_id != order.pk:
                raise ValidationError(
                    _("This payment reference is already used by another order.")
                )
            return existing, False

    # ລັອກແຖວອໍເດີໄວ້ ກັນສອງເຄື່ອງຮັບເງິນບິນດຽວກັນພ້ອມກັນ.
    # prefetch ສະເພາະ items — payments ຕ້ອງອ່ານສົດທຸກຄັ້ງ ເພາະເຮົາຈະເພີ່ມແຖວໃໝ່
    # ຢູ່ກາງທາງ, cache ເກົ່າຈະເຮັດໃຫ້ຄິດຍອດຄ້າງຜິດ
    locked = Order.objects.select_for_update().prefetch_related("items").get(pk=order.pk)

    if locked.status == Order.Status.CANCELLED:
        raise ValidationError(_("This order was cancelled and cannot take payment."))

    currency = currency or BASE_CURRENCY
    amount = _as_decimal(amount, _("Amount")).quantize(Decimal("0.01"))
    if amount <= ZERO:
        raise ValidationError(_("The amount must be greater than zero."))

    rate = resolve_fx_rate(currency, fx_rate)
    base_amount = (amount * rate).quantize(Decimal("0.01"))

    if kind == Payment.Kind.PAYMENT:
        balance = locked.balance_due
        if balance <= ZERO:
            raise ValidationError(_("This order is already fully paid."))
        if base_amount > balance:
            raise ValidationError(
                _(
                    "The amount is larger than the balance due (%(balance)s). "
                    "Enter what the customer hands over in the tendered field instead."
                )
                % {"balance": balance}
            )
    else:
        already_paid = locked.amount_paid
        if base_amount > already_paid:
            raise ValidationError(
                _("You cannot refund more than the %(paid)s already received.")
                % {"paid": already_paid}
            )

    # ເງິນທອນ ຄິດເປັນສະກຸນທີ່ຮັບມາ ບໍ່ແມ່ນສະກຸນຫຼັກ — ພະນັກງານທອນເປັນເງິນນັ້ນ
    change_amount = ZERO
    if tendered not in (None, ""):
        tendered = _as_decimal(tendered, _("Tendered amount")).quantize(Decimal("0.01"))
        if tendered < amount:
            raise ValidationError(
                _("The tendered amount is less than the amount being paid.")
            )
        change_amount = tendered - amount
    else:
        tendered = None

    was_settled_before = locked.settled_at is not None

    payment = Payment.objects.create(
        order=locked,
        kind=kind,
        amount=amount,
        currency=currency,
        method=method,
        tendered_amount=tendered,
        change_amount=change_amount,
        fx_rate=rate,
        base_amount=base_amount,
        received_by=user,
        idempotency_key=idempotency_key or None,
        note=note,
    )

    locked.sync_status()

    # ປະທັບ Stamp ຕອນຂ້າມເສັ້ນເປັນ "ຊຳລະຄົບ" ຄັ້ງທຳອິດເທົ່ານັ້ນ
    if not was_settled_before and locked.settled_at is not None:
        award_visit_stamp(locked)

    order.refresh_from_db()
    return payment, True


@transaction.atomic
def void_payment(*, payment, user=None, reason=""):
    """ຍົກເລີກແຖວການຊຳລະ (ກ່ອນປິດຮອບ) — ບໍ່ລຶບແຖວ ພຽງແຕ່ໝາຍວ່າບໍ່ມີຜົນ"""
    if payment.voided_at is not None:
        return payment

    payment.voided_at = timezone.now()
    payment.voided_by = user
    payment.void_reason = reason
    payment.save(update_fields=["voided_at", "voided_by", "void_reason"])

    order = (
        Order.objects.select_for_update()
        .prefetch_related("items")
        .get(pk=payment.order_id)
    )
    order.sync_status()
    return payment


def award_visit_stamp(order):
    """1 ບິນທີ່ຊຳລະຄົບ = ມາໃຊ້ບໍລິການ 1 ຄັ້ງ = 1 Stamp

    ເອີ້ນສະເພາະຕອນຂ້າມເສັ້ນເປັນ PAID ຄັ້ງທຳອິດ — ຜູ້ເອີ້ນເປັນຜູ້ຄຸມ idempotency
    """
    if not order.customer_id:
        return None

    from digital_member.models import MemberCard, StampTransaction

    card, _created = MemberCard.objects.get_or_create(customer=order.customer)
    card.stamps_count += 1
    card.save(update_fields=["stamps_count"])
    StampTransaction.objects.create(
        card=card,
        action=StampTransaction.Action.ADD,
        count=1,
        note=f"ຊຳລະບິນ {order.order_number}",
    )
    return card


@transaction.atomic
def hand_over_asset(*, order, asset, user=None, received_to=""):
    """ສົ່ງມອບເກີບ 1 ຄູ່ຄືນລູກຄ້າ — ຖືກ gate ດ້ວຍຍອດຄ້າງຊຳລະ

    ນີ້ຄືຈຸດຕັດອັນດຽວລະຫວ່າງເສັ້ນທາງ "ເງິນ" ກັບເສັ້ນທາງ "ເຄື່ອງ"
    """
    from asset_intake.models import Asset

    locked = (
        Order.objects.select_for_update()
        .prefetch_related("items", "payments")
        .get(pk=order.pk)
    )

    if locked.balance_due > ZERO:
        raise ValidationError(
            _("Cannot hand over: %(balance)s is still due on this order.")
            % {"balance": locked.balance_due}
        )

    if asset.pk not in {a.pk for a in locked.assets()}:
        raise ValidationError(_("This item does not belong to this order."))

    if asset.status == Asset.Status.RETURNED:
        return asset

    asset.status = Asset.Status.RETURNED
    asset.completed_at = timezone.now()
    asset.returned_to = received_to[:120]
    asset.returned_by = user
    # ຄືນບ່ອນເກັບໃຫ້ວ່າງ — ເກີບອອກຈາກຮ້ານແລ້ວ ບໍ່ຄວນຍຶດຊ່ອງໄວ້
    asset.storage_slot = None
    asset.save(
        update_fields=[
            "status",
            "completed_at",
            "returned_to",
            "returned_by",
            "storage_slot",
            "updated_at",
        ]
    )
    return asset
