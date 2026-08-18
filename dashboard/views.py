from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.utils import timezone
from django.utils.translation import gettext as _

from asset_intake.models import Asset
from digital_member.models import MemberCard
from inventory.models import Supply
from pos.models import Expense, Order, Payment
from resell_pricing_engine.models import PriceValuation
from crm.models import Customer


@login_required
def index(request):
    """ໜ້າຈໍສະຫຼູບຜົນປະກອບການ (Scope 2.5 — Dashboard)"""
    today = timezone.localdate()
    month_start = today.replace(day=1)

    revenue_today = (
        Payment.objects.filter(paid_at__date=today).aggregate(s=Sum("amount"))["s"] or 0
    )
    revenue_month = (
        Payment.objects.filter(paid_at__date__gte=month_start).aggregate(s=Sum("amount"))["s"]
        or 0
    )
    expense_month = (
        Expense.objects.filter(date__gte=month_start).aggregate(s=Sum("amount"))["s"] or 0
    )

    chart_rows = []
    max_chart_value = 0
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        income = (
            Payment.objects.filter(paid_at__date=day).aggregate(s=Sum("amount"))["s"] or 0
        )
        pricing_estimate = (
            PriceValuation.objects.filter(created_at__date=day).aggregate(
                s=Sum("suggested_price")
            )["s"]
            or 0
        )
        max_chart_value = max(max_chart_value, income, pricing_estimate)
        chart_rows.append(
            {
                "date": day,
                "income": income,
                "pricing_estimate": pricing_estimate,
            }
        )

    for row in chart_rows:
        row["income_height"] = int((row["income"] / max_chart_value) * 100) if max_chart_value else 0
        row["pricing_height"] = (
            int((row["pricing_estimate"] / max_chart_value) * 100)
            if max_chart_value
            else 0
        )

    context = {
        "active_nav": "dashboard",
        "revenue_today": revenue_today,
        "revenue_month": revenue_month,
        "expense_month": expense_month,
        "net_month": revenue_month - expense_month,
        "active_assets": Asset.objects.exclude(status=Asset.Status.RETURNED).count(),
        "member_count": MemberCard.objects.filter(is_active=True).count(),
        "low_stock_supplies": [
            s for s in Supply.objects.filter(is_active=True) if s.is_low_stock
        ],
        "recent_orders": Order.objects.select_related("customer")[:10],
        "recent_assets": Asset.objects.select_related("customer")[:10],
        "chart_rows": chart_rows,
        **_backup_health(),
    }
    return render(request, "dashboard/index.html", context)


def _backup_health():
    """ສະພາບການສຳຮອງຫຼັກຖານ — ເຕືອນສະເພາະຕອນມີບັນຫາຈິງ

    ການສຳຮອງທີ່ລົ້ມແບບງຽບໆເປັນອັນຕະລາຍທີ່ສຸດ: ຮ້ານຈະຮູ້ຕໍ່ເມື່ອຕ້ອງກູ້ຫຼັກຖານ
    ແລ້ວມັນບໍ່ມີ. ຈຶ່ງເອົາຂຶ້ນມາໄວ້ໜ້າທຳອິດທີ່ພະນັກງານເປີດທຸກເຊົ້າ.
    """
    from django.conf import settings

    from media_backup.models import BackupRun
    from media_backup.services import pending_backup_queryset

    if (getattr(settings, "MEDIA_BACKUP_BACKEND", "none") or "none").lower() in (
        "",
        "none",
        "off",
    ):
        return {"backup_alert": None}

    last_run = BackupRun.objects.first()
    if last_run is None:
        return {
            "backup_alert": _("Evidence backup has never run yet."),
            "backup_pending": pending_backup_queryset().count(),
        }

    if last_run.status in (BackupRun.Status.FAILED, BackupRun.Status.PARTIAL):
        return {
            "backup_alert": _("The last evidence backup did not finish cleanly."),
            "backup_pending": pending_backup_queryset().count(),
            "backup_last_run": last_run,
        }

    return {"backup_alert": None, "backup_last_run": last_run}


@login_required
def global_search(request):
    import re
    q = request.GET.get("q", "").strip()
    if not q:
        return redirect("dashboard:index")

    # If q is a URL, extract the relevant identifiers
    if q.lower().startswith(("http://", "https://")):
        # A. QR customer portal tracking URL: .../portal/t/<token>/
        m = re.search(r"/t/([A-Za-z0-9_-]+)/?", q)
        if m:
            asset = Asset.objects.filter(public_token=m.group(1)).first()
            if asset:
                return redirect("asset_intake:detail", pk=asset.pk)
                
        # B. QR customer portal card URL: .../portal/card/<card_number>/
        m = re.search(r"/card/([A-Za-z0-9_-]+)/?", q)
        if m:
            card = MemberCard.objects.select_related("customer").filter(card_number__iexact=m.group(1)).first()
            if card and card.customer:
                return redirect(f"{reverse('crm:index')}?q={card.customer.name}")

        # C. General ID/PK in URL: e.g. .../intake/12/
        m = re.search(r"/(\d+)/?(?:[?#].*)?$", q)
        if m:
            asset = Asset.objects.filter(pk=int(m.group(1))).first()
            if asset:
                return redirect("asset_intake:detail", pk=asset.pk)

    # 1. Search Asset by Ticket Number (e.g., TK...) or exact token
    asset = Asset.objects.filter(Q(ticket_number__iexact=q) | Q(public_token__iexact=q)).first()
    if asset:
        return redirect("asset_intake:detail", pk=asset.pk)

    # 2. Search Order by Order Number (e.g., ORD...)
    order = Order.objects.filter(order_number__iexact=q).first()
    if order:
        return redirect("pos:quotation", pk=order.pk)

    # 3. Partial searches
    asset_partial = Asset.objects.filter(ticket_number__icontains=q).first()
    if asset_partial:
        return redirect("asset_intake:detail", pk=asset_partial.pk)

    order_partial = Order.objects.filter(order_number__icontains=q).first()
    if order_partial:
        return redirect("pos:quotation", pk=order_partial.pk)

    # 4. Search Customer (by name, phone, or email, or exact card number)
    card = MemberCard.objects.select_related("customer").filter(card_number__iexact=q).first()
    if card and card.customer:
        return redirect(f"{reverse('crm:index')}?q={card.customer.name}")

    customer = Customer.objects.filter(
        Q(name__icontains=q) | Q(phone__icontains=q) | Q(email__icontains=q)
    ).first()
    if customer:
        return redirect(f"{reverse('crm:index')}?q={q}")

    messages.warning(request, f"ไม่พบข้อมูลสำหรับ: '{q}'")
    return redirect("dashboard:index")
