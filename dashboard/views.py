from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from asset_intake.models import Asset
from digital_member.models import MemberCard
from inventory.models import Supply
from pos.models import Expense, Order, Payment
from resell_pricing_engine.models import PriceValuation


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
    }
    return render(request, "dashboard/index.html", context)
