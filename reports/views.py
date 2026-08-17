# Force reload dev server to register templatetags
from datetime import timedelta

from django.db.models import Count, F, Max, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _, ngettext

from ai_mart_grading.models import Assessment
from crm.models import Customer
from pos.models import Expense, Order, OrderItem, Payment
from resell_pricing_engine.models import PriceValuation, PromoContent
from staff.decorators import role_required
from staff.models import StaffProfile

# ຈຳນວນວັນຍ້ອນຫຼັງຂອງແຕ່ລະໄລຍະ (Scope 2.1 — ລາຍງານ ວັນ/ທິດ/ເດືອນ/ປີ)
PERIODS = {
    "day": (_("Today"), 1),
    "week": (_("7 days"), 7),
    "month": (_("30 days"), 30),
    "year": (_("1 year"), 365),
}


@role_required(StaffProfile.Role.MANAGER)
def service_usage(request):
    """ສະຖິຕິການໃຊ້ບໍລິການ ແລະ ການປະເມີນຂອງ AI (Scope 2.5) — ຜູ້ຈັດການເທົ່ານັ້ນ"""
    period = request.GET.get("period", "month")
    if period not in PERIODS:
        period = "month"
    label, days = PERIODS[period]
    start = timezone.localdate() - timedelta(days=days - 1)

    # ນັບຈາກລາຍການໃນບິນ ບໍ່ນັບບິນທີ່ຍົກເລີກ — ບິນທີ່ຍົກເລີກບໍ່ແມ່ນການໃຊ້ບໍລິການຈິງ
    service_rows = list(
        OrderItem.objects.filter(
            order__created_at__date__gte=start,
            service_type__isnull=False,
        )
        .exclude(order__status=Order.Status.CANCELLED)
        .values("service_type__name", "service_type__category")
        .annotate(
            times_used=Sum("quantity"),
            orders_count=Count("order", distinct=True),
            revenue=Sum(F("quantity") * F("unit_price")),
        )
        .order_by("-times_used")
    )

    busiest = service_rows[0]["times_used"] if service_rows else 0
    for row in service_rows:
        row["share_percent"] = (
            int((row["times_used"] / busiest) * 100) if busiest else 0
        )

    assessments = Assessment.objects.filter(created_at__date__gte=start)
    grade_rows = list(
        assessments.exclude(overall_grade="")
        .values("overall_grade")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return render(
        request,
        "reports/service_usage.html",
        {
            "active_nav": "service_usage",
            "period": period,
            "period_label": label,
            "periods": PERIODS,
            "service_rows": service_rows,
            "total_services_used": sum(r["times_used"] for r in service_rows),
            "total_service_revenue": sum(r["revenue"] or 0 for r in service_rows),
            "assessment_count": assessments.count(),
            "grade_rows": grade_rows,
            "valuation_count": PriceValuation.objects.filter(
                created_at__date__gte=start
            ).count(),
            "promo_count": PromoContent.objects.filter(
                created_at__date__gte=start
            ).count(),
        },
    )


@role_required(StaffProfile.Role.MANAGER)
def income_expense(request):
    """ລາຍງານລາຍຮັບ-ລາຍຈ່າຍ (Scope 2.5 — Reports) — ຜູ້ຈັດການເທົ່ານັ້ນ"""
    period = request.GET.get("period", "month")
    if period not in PERIODS:
        period = "month"
    label, days = PERIODS[period]
    start = timezone.localdate() - timedelta(days=days - 1)

    payments = Payment.objects.filter(paid_at__date__gte=start)
    expenses = Expense.objects.filter(date__gte=start)

    income_total = payments.aggregate(s=Sum("amount"))["s"] or 0
    expense_total = expenses.aggregate(s=Sum("amount"))["s"] or 0

    # ລວມຍອດແຍກຕາມວັນ
    rows = {}
    for entry in (
        payments.annotate(d=TruncDate("paid_at"))
        .values("d")
        .annotate(total=Sum("amount"))
    ):
        rows.setdefault(entry["d"], {"income": 0, "expense": 0})
        rows[entry["d"]]["income"] = entry["total"]
    for entry in expenses.values("date").annotate(total=Sum("amount")):
        rows.setdefault(entry["date"], {"income": 0, "expense": 0})
        rows[entry["date"]]["expense"] = entry["total"]

    daily_rows = [
        {
            "date": d,
            "income": v["income"],
            "expense": v["expense"],
            "net": v["income"] - v["expense"],
        }
        for d, v in sorted(rows.items(), reverse=True)
    ]
    max_cashflow = max(
        [row["income"] for row in daily_rows] + [row["expense"] for row in daily_rows] + [0]
    )
    for row in daily_rows:
        row["income_height"] = int((row["income"] / max_cashflow) * 100) if max_cashflow else 0
        row["expense_height"] = (
            int((row["expense"] / max_cashflow) * 100) if max_cashflow else 0
        )

    customers = Customer.objects.annotate(
        order_count=Count("orders", distinct=True),
        last_order=Max("orders__created_at"),
        total_spend=Sum("orders__payments__amount"),
    )
    total_customers = customers.count()
    segment_counts = {"vip": 0, "loyal": 0, "at_risk": 0}
    for customer in customers:
        if customer.order_count >= 3:
            segment_counts["vip"] += 1
        elif customer.order_count >= 1:
            segment_counts["loyal"] += 1
        else:
            segment_counts["at_risk"] += 1

    def percentage(value):
        return round((value / total_customers) * 100) if total_customers else 0

    rfm_segments = [
        {
            "label": _("VIP customers"),
            "description": _("3+ recorded orders"),
            "count": segment_counts["vip"],
            "percent": percentage(segment_counts["vip"]),
            "tone": "cyan",
        },
        {
            "label": _("Loyal customers"),
            "description": _("1–2 recorded orders"),
            "count": segment_counts["loyal"],
            "percent": percentage(segment_counts["loyal"]),
            "tone": "surface",
        },
        {
            "label": _("At-risk customers"),
            "description": _("No recorded orders yet"),
            "count": segment_counts["at_risk"],
            "percent": percentage(segment_counts["at_risk"]),
            "tone": "alert",
        },
    ]

    # Calculate last 6 months data for Chart.js
    import datetime
    months_labels = []
    income_data = []
    expense_data = []
    today = timezone.localdate()
    
    for i in range(5, -1, -1):
        first_of_this_month = today.replace(day=1)
        target_month_date = first_of_this_month
        for step in range(i):
            target_month_date = (target_month_date - timedelta(days=1)).replace(day=1)
            
        month_start = timezone.make_aware(datetime.datetime(target_month_date.year, target_month_date.month, 1))
        if target_month_date.month == 12:
            next_month = timezone.make_aware(datetime.datetime(target_month_date.year + 1, 1, 1))
        else:
            next_month = timezone.make_aware(datetime.datetime(target_month_date.year, target_month_date.month + 1, 1))
            
        month_end = next_month - timedelta(seconds=1)
        
        m_income = Payment.objects.filter(paid_at__range=(month_start, month_end)).aggregate(s=Sum("amount"))["s"] or 0
        m_expense = Expense.objects.filter(date__range=(month_start.date(), month_end.date())).aggregate(s=Sum("amount"))["s"] or 0
        
        months_labels.append(date_format(target_month_date, "M"))
        income_data.append(float(m_income))
        expense_data.append(float(m_expense))

    # Build customer list with relative times and actions
    def get_relative_time(dt):
        if not dt:
            return _("Never")
        now = timezone.now()
        diff = now - dt
        if diff.days == 0:
            return _("Today")
        elif diff.days == 1:
            return _("Yesterday")
        elif diff.days < 7:
            return ngettext(
                "%(count)d day ago", "%(count)d days ago", diff.days
            ) % {"count": diff.days}
        elif diff.days < 30:
            weeks = diff.days // 7
            return ngettext(
                "%(count)d week ago", "%(count)d weeks ago", weeks
            ) % {"count": weeks}
        else:
            return dt.strftime("%Y-%m-%d")

    customer_list = []
    for c in customers.order_by("-total_spend"):
        segment = "VIP" if c.order_count >= 3 else ("Loyal" if c.order_count >= 1 else "At-Risk")
        if segment == "VIP":
            segment_label = _("VIP")
            action = _("Offer exclusive early access")
        elif segment == "Loyal":
            segment_label = _("Loyal")
            action = _("Send standard newsletter")
        else:
            segment_label = _("At-risk")
            action = _("Trigger win-back email sequence")
            
        customer_list.append({
            "pk": c.pk,
            "name": c.name,
            "segment": segment,
            "segment_label": segment_label,
            "last_order": get_relative_time(c.last_order),
            "total_spend": float(c.total_spend or 0),
            "action": action
        })

    context = {
        "active_nav": "reports",
        "period": period,
        "period_label": label,
        "periods": PERIODS,
        "start": start,
        "income_total": income_total,
        "expense_total": expense_total,
        "net_total": income_total - expense_total,
        "daily_rows": daily_rows,
        "rfm_segments": rfm_segments,
        "total_customers": total_customers,
        "chart_labels": months_labels,
        "chart_income": income_data,
        "chart_expense": expense_data,
        "customer_list": customer_list,
    }
    return render(request, "reports/income_expense.html", context)
