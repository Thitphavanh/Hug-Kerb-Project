"""ໜ້າລາຍງານພະນັກງານ ແລະ ຄອມມິດຊັນ (ຜູ້ຈັດການເທົ່ານັ້ນ)"""

from decimal import Decimal

from django.shortcuts import render
from django.utils import timezone

from asset_intake.models import Asset

from .decorators import role_required
from .models import StaffProfile


def _parse_month(request):
    """ອ່ານ ?month=YYYY-MM — ຄ່າຜິດຮູບແບບໃຫ້ໃຊ້ເດືອນປັດຈຸບັນ"""
    today = timezone.localdate()
    month_str = request.GET.get("month", "")
    try:
        year, month = map(int, month_str.split("-"))
        if not 1 <= month <= 12:
            raise ValueError
        return year, month
    except (ValueError, AttributeError):
        return today.year, today.month


@role_required(StaffProfile.Role.MANAGER)
def commission_report(request):
    year, month = _parse_month(request)

    # ວຽກທີ່ສົ່ງມອບແລ້ວໃນເດືອນນີ້ ແລະ ມີຊ່າງຮັບຜິດຊອບ
    assets = (
        Asset.objects.filter(
            status=Asset.Status.RETURNED,
            completed_at__year=year,
            completed_at__month=month,
            assigned_to__isnull=False,
        )
        .select_related("assigned_to", "customer")
        .prefetch_related("order_items")
    )

    by_tech = {}
    for asset in assets:
        job_value = sum(
            (item.subtotal for item in asset.order_items.all()), start=Decimal("0")
        )
        row = by_tech.setdefault(
            asset.assigned_to_id,
            {"user": asset.assigned_to, "jobs": [], "base_total": Decimal("0")},
        )
        row["jobs"].append({"asset": asset, "value": job_value})
        row["base_total"] += job_value

    profiles = {
        p.user_id: p for p in StaffProfile.objects.filter(user_id__in=by_tech.keys())
    }
    rows = []
    grand_commission = Decimal("0")
    for user_id, row in by_tech.items():
        profile = profiles.get(user_id)
        rate = profile.commission_rate if profile else Decimal("0")
        commission = (row["base_total"] * rate / 100).quantize(Decimal("0.01"))
        grand_commission += commission
        rows.append(
            {
                "user": row["user"],
                "profile": profile,
                "job_count": len(row["jobs"]),
                "jobs": row["jobs"],
                "base_total": row["base_total"],
                "rate": rate,
                "commission": commission,
            }
        )
    rows.sort(key=lambda r: r["commission"], reverse=True)

    context = {
        "active_nav": "staff",
        "rows": rows,
        "grand_commission": grand_commission,
        "month_value": f"{year:04d}-{month:02d}",
        "staff_members": StaffProfile.objects.select_related("user"),
    }
    return render(request, "staff/commission_report.html", context)
