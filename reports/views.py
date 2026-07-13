# Force reload dev server to register templatetags
from datetime import timedelta

from django.db.models import Count, Max, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from crm.models import Customer
from pos.models import Expense, Payment
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
            "label": "VIP Customers",
            "description": "3+ recorded orders",
            "count": segment_counts["vip"],
            "percent": percentage(segment_counts["vip"]),
            "tone": "cyan",
        },
        {
            "label": "Loyal",
            "description": "1–2 recorded orders",
            "count": segment_counts["loyal"],
            "percent": percentage(segment_counts["loyal"]),
            "tone": "surface",
        },
        {
            "label": "At-Risk",
            "description": "No recorded orders yet",
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
        for _ in range(i):
            target_month_date = (target_month_date - timedelta(days=1)).replace(day=1)
            
        month_start = timezone.make_aware(datetime.datetime(target_month_date.year, target_month_date.month, 1))
        if target_month_date.month == 12:
            next_month = timezone.make_aware(datetime.datetime(target_month_date.year + 1, 1, 1))
        else:
            next_month = timezone.make_aware(datetime.datetime(target_month_date.year, target_month_date.month + 1, 1))
            
        month_end = next_month - timedelta(seconds=1)
        
        m_income = Payment.objects.filter(paid_at__range=(month_start, month_end)).aggregate(s=Sum("amount"))["s"] or 0
        m_expense = Expense.objects.filter(date__range=(month_start.date(), month_end.date())).aggregate(s=Sum("amount"))["s"] or 0
        
        months_labels.append(target_month_date.strftime("%b"))
        income_data.append(float(m_income))
        expense_data.append(float(m_expense))

    # Build customer list with relative times and actions
    def get_relative_time(dt):
        if not dt:
            return "Never"
        now = timezone.now()
        diff = now - dt
        if diff.days == 0:
            return "Today"
        elif diff.days == 1:
            return "Yesterday"
        elif diff.days < 7:
            return f"{diff.days} days ago"
        elif diff.days < 30:
            return f"{diff.days // 7} weeks ago"
        else:
            return dt.strftime("%Y-%m-%d")

    customer_list = []
    for c in customers.order_by("-total_spend"):
        segment = "VIP" if c.order_count >= 3 else ("Loyal" if c.order_count >= 1 else "At-Risk")
        if segment == "VIP":
            action = "Offer exclusive early access"
        elif segment == "Loyal":
            action = "Send standard newsletter"
        else:
            action = "Trigger win-back email sequence"
            
        customer_list.append({
            "pk": c.pk,
            "name": c.name,
            "segment": segment,
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
