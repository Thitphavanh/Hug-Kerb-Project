import csv
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from staff.decorators import role_required
from staff.models import StaffProfile

from .forms import AccountCategoryForm, BudgetForm, CashBookForm, CashHandoverForm
from .labels import localized_category_name
from .models import AccountCategory, Budget, CashBook, CashHandover
from .services import CURRENCIES, grouped_report, totals_by_currency, unified_transactions


manager_required = role_required(StaffProfile.Role.MANAGER)


def _parse_date(value, fallback):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


@manager_required
def dashboard(request):
    today = timezone.localdate()
    selected_date = _parse_date(request.GET.get("date"), today)
    currency = request.GET.get("currency", "")
    transaction_type = request.GET.get("type", "")
    category_id = request.GET.get("category", "")
    query = request.GET.get("q", "").strip()

    daily_totals = totals_by_currency(selected_date, selected_date)
    all_totals = totals_by_currency()
    transactions = unified_transactions(
        selected_date,
        selected_date,
        currency,
        transaction_type,
        query,
        category_id,
    )

    month_start = selected_date.replace(day=1)
    monthly_totals = totals_by_currency(month_start, selected_date)
    budget_rows = []
    for budget in Budget.objects.select_related("category").filter(month=month_start):
        actual = (
            CashBook.objects.filter(
                status=CashBook.Status.CONFIRMED,
                transaction_type="OUT",
                category=budget.category,
                currency=budget.currency,
                date__range=(month_start, selected_date),
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        percent = min(100, round((actual / budget.amount) * 100)) if budget.amount else 0
        budget_rows.append(
            {
                "budget": budget,
                "category_name": localized_category_name(budget.category),
                "actual": actual,
                "remaining": budget.amount - actual,
                "percent": percent,
            }
        )

    categories = [
        {"pk": category.pk, "name": localized_category_name(category)}
        for category in AccountCategory.objects.filter(is_active=True)
    ]

    return render(
        request,
        "accounting/dashboard.html",
        {
            "active_nav": "accounting",
            "selected_date": selected_date,
            "transactions": transactions,
            "daily_totals": daily_totals,
            "all_totals": all_totals,
            "monthly_totals": monthly_totals,
            "currencies": CURRENCIES,
            "categories": categories,
            "filters": {
                "currency": currency,
                "type": transaction_type,
                "category": str(category_id),
                "q": query,
            },
            "budget_rows": budget_rows,
        },
    )


@manager_required
def transaction_create(request):
    form = CashBookForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        transaction = form.save(commit=False)
        transaction.created_by = request.user
        transaction.updated_by = request.user
        transaction.save()
        messages.success(request, _("Transaction saved successfully."))
        return redirect(f"{reverse('accounting:dashboard')}?date={transaction.date}")
    return render(
        request,
        "accounting/transaction_form.html",
        {"form": form, "active_nav": "accounting", "page_title": _("Add accounting transaction")},
    )


@manager_required
def transaction_edit(request, pk):
    transaction = get_object_or_404(CashBook, pk=pk)
    form = CashBookForm(request.POST or None, request.FILES or None, instance=transaction)
    if form.is_valid():
        transaction = form.save(commit=False)
        transaction.updated_by = request.user
        transaction.save()
        messages.success(request, _("Transaction updated successfully."))
        return redirect(f"{reverse('accounting:dashboard')}?date={transaction.date}")
    return render(
        request,
        "accounting/transaction_form.html",
        {"form": form, "transaction": transaction, "active_nav": "accounting", "page_title": _("Edit accounting transaction")},
    )


@manager_required
@require_POST
def transaction_delete(request, pk):
    transaction = get_object_or_404(CashBook, pk=pk)
    view_date = transaction.date
    transaction.delete()
    messages.success(request, _("Transaction deleted successfully."))
    return redirect(f"{reverse('accounting:dashboard')}?date={view_date}")


def _report_filters(request):
    today = timezone.localdate()
    default_start = today.replace(day=1)
    start_date = _parse_date(request.GET.get("start"), default_start)
    end_date = _parse_date(request.GET.get("end"), today)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    grouping = request.GET.get("group", "daily")
    if grouping not in {"daily", "monthly", "yearly"}:
        grouping = "daily"
    return start_date, end_date, grouping


@manager_required
def report(request):
    start_date, end_date, grouping = _report_filters(request)
    rows = grouped_report(start_date, end_date, grouping)
    totals = totals_by_currency(start_date, end_date)
    max_amount = max(
        [row["income"] for row in rows] + [row["expense"] for row in rows] + [Decimal("0")]
    )
    for row in rows:
        row["income_percent"] = round((row["income"] / max_amount) * 100) if max_amount else 0
        row["expense_percent"] = round((row["expense"] / max_amount) * 100) if max_amount else 0
    return render(
        request,
        "accounting/report.html",
        {
            "active_nav": "accounting",
            "start_date": start_date,
            "end_date": end_date,
            "grouping": grouping,
            "rows": rows,
            "totals": totals,
        },
    )


@manager_required
def export_csv(request):
    start_date, end_date, grouping = _report_filters(request)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="hug-kerb-accounting-{start_date}-{end_date}.csv"'
    )
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow([_("Period"), _("Currency"), _("Income"), _("Expense"), _("Net")])
    for row in grouped_report(start_date, end_date, grouping):
        writer.writerow(
            [row["period"], row["currency"], row["income"], row["expense"], row["balance"]]
        )
    return response


@manager_required
def category_detail(request, pk):
    category = get_object_or_404(AccountCategory, pk=pk)
    today = timezone.localdate()
    start_date = _parse_date(request.GET.get("start"), today.replace(day=1))
    end_date = _parse_date(request.GET.get("end"), today)
    transactions = CashBook.objects.filter(
        category=category, date__range=(start_date, end_date)
    ).select_related("created_by")
    total = transactions.filter(status=CashBook.Status.CONFIRMED).aggregate(total=Sum("amount"))["total"] or 0
    return render(
        request,
        "accounting/category_detail.html",
        {
            "active_nav": "accounting",
            "category": category,
            "transactions": transactions,
            "total": total,
            "start_date": start_date,
            "end_date": end_date,
        },
    )


@manager_required
def cash_handover(request):
    today = timezone.localdate()
    selected_date = _parse_date(request.GET.get("date") or request.POST.get("date"), today)
    selected_currency = request.GET.get("currency") or request.POST.get("currency") or "LAK"
    existing = CashHandover.objects.filter(
        date=selected_date, currency=selected_currency
    ).first()
    form = CashHandoverForm(
        request.POST or None,
        instance=existing,
        initial={"date": selected_date, "currency": selected_currency},
    )
    cash_totals = totals_by_currency(
        selected_date, selected_date, payment_method=CashBook.PaymentMethod.CASH
    )
    if form.is_valid():
        handover = form.save(commit=False)
        opening = handover.opening_balance or Decimal("0")
        handover.expected_amount = opening + cash_totals[handover.currency]["balance"]
        handover.handed_by = request.user
        handover.save()
        messages.success(request, _("Handover saved successfully."))
        return redirect(
            f"{reverse('accounting:cash_handover')}?date={handover.date}&currency={handover.currency}"
        )
    history = CashHandover.objects.select_related("handed_by")[:30]
    return render(
        request,
        "accounting/cash_handover.html",
        {
            "active_nav": "accounting",
            "form": form,
            "existing": existing,
            "cash_totals": cash_totals,
            "selected_date": selected_date,
            "selected_currency": selected_currency,
            "history": history,
            "currencies": CURRENCIES,
        },
    )


@manager_required
def settings_view(request):
    today = timezone.localdate()
    category_form = AccountCategoryForm(prefix="category")
    budget_form = BudgetForm(
        prefix="budget", initial={"month": today.replace(day=1)}
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add_category":
            category_form = AccountCategoryForm(request.POST, prefix="category")
            if category_form.is_valid():
                category_form.save()
                messages.success(request, _("Category added successfully."))
                return redirect("accounting:settings")
        elif action == "save_budget":
            budget_form = BudgetForm(request.POST, prefix="budget")
            if budget_form.is_valid():
                data = budget_form.cleaned_data
                Budget.objects.update_or_create(
                    month=data["month"].replace(day=1),
                    category=data["category"],
                    currency=data["currency"],
                    defaults={"amount": data["amount"]},
                )
                messages.success(request, _("Budget saved successfully."))
                return redirect("accounting:settings")

    return render(
        request,
        "accounting/settings.html",
        {
            "active_nav": "accounting",
            "category_form": category_form,
            "budget_form": budget_form,
            "income_categories": [
                {
                    "pk": category.pk,
                    "name": localized_category_name(category),
                    "color": category.color,
                    "is_active": category.is_active,
                }
                for category in AccountCategory.objects.filter(transaction_type="IN")
            ],
            "expense_categories": [
                {
                    "pk": category.pk,
                    "name": localized_category_name(category),
                    "color": category.color,
                    "is_active": category.is_active,
                }
                for category in AccountCategory.objects.filter(transaction_type="OUT")
            ],
            "budgets": [
                {
                    "pk": budget.pk,
                    "month": budget.month,
                    "category_name": localized_category_name(budget.category),
                    "currency": budget.currency,
                    "amount": budget.amount,
                }
                for budget in Budget.objects.select_related("category")[:36]
            ],
        },
    )


@manager_required
@require_POST
def category_toggle(request, pk):
    category = get_object_or_404(AccountCategory, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    messages.success(request, _("Category status updated successfully."))
    return redirect("accounting:settings")


@manager_required
@require_POST
def budget_delete(request, pk):
    get_object_or_404(Budget, pk=pk).delete()
    messages.success(request, _("Budget deleted successfully."))
    return redirect("accounting:settings")


def _get_accounting_cycle_dates(month_val, year_val, today):
    """
    Returns (current_month, current_year, start_date, end_date) for the standard
    calendar month: 1st day to the last day of the month.
    """
    import calendar
    import datetime
    m = int(month_val) if (month_val and str(month_val).isdigit()) else None
    y = int(str(year_val).replace(',', '').strip()) if (year_val and str(year_val).replace(',', '').strip().isdigit()) else None
    
    if m is None or y is None:
        m = today.month
        y = today.year

    start_date = datetime.date(y, m, 1)
    _, num_days = calendar.monthrange(y, m)
    end_date = datetime.date(y, m, num_days)
    return m, y, start_date, end_date


def _normalize_category_key(cat):
    """
    Merge categories that mean the same thing so variant Lao spellings collapse
    into a single P&L line. Categories sharing the same English label inside
    trailing parentheses map to the same key.
    """
    import re
    cat_str = str(cat)
    if not cat_str:
        return '∅'
    m = re.search(r'\(([^)]+)\)\s*$', cat_str)
    if m:
        return m.group(1).strip().lower()
    return cat_str.strip().lower()


def _group_by_category(transactions, transaction_type, currency_code, default_other="ອື່ນໆ"):
    """
    Group a list of unified transaction dicts by (normalized) category and sum the amounts.
    Returns [{'description': <label>, 'amount': float}, ...] sorted by amount descending.
    """
    from collections import defaultdict
    filtered = [
        t for t in transactions
        if t["type"] == transaction_type and t["currency"] == currency_code and t["status"] == "confirmed"
    ]
    
    merged = {}
    order = []
    for t in filtered:
        cat = t["category"] or default_other
        key = _normalize_category_key(cat)
        amt = float(t["amount"] or 0)
        if key in merged:
            merged[key]['amount'] += amt
        else:
            merged[key] = {'description': cat, 'amount': amt}
            order.append(key)
            
    result = [merged[k] for k in order]
    result.sort(key=lambda x: -x['amount'])
    return result


@manager_required
def monthly_summary_financial(request):
    """
    Generate the Monthly Financial Summary (ໃບສະຫຼຸບການເງິນປະຈຳເດືອນ).
    Auto-populates data from unified transactions (including POS) for LAK, THB, and USD.
    """
    import json
    import datetime
    today = timezone.localdate()
    
    month_str = request.GET.get('month')
    year_str = request.GET.get('year')
    run_count = request.GET.get('run_count', '1')
    date_str = request.GET.get('date')
    currency = request.GET.get('currency', 'ALL')
    
    current_month, current_year, start_date, end_date = _get_accounting_cycle_dates(
        month_str, year_str, today
    )
    voucher_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else today
    
    # Fetch unified transactions for the period
    transactions = unified_transactions(start_date, end_date)
    
    # Calculate incomes
    cash_in_lak = sum(t["amount"] for t in transactions if t["type"] == "IN" and t["currency"] == "LAK" and t["status"] == "confirmed")
    cash_in_thb = sum(t["amount"] for t in transactions if t["type"] == "IN" and t["currency"] == "THB" and t["status"] == "confirmed")
    cash_in_usd = sum(t["amount"] for t in transactions if t["type"] == "IN" and t["currency"] == "USD" and t["status"] == "confirmed")
    
    # Build list of items for manual adjustment sheet editor
    default_items = []
    for t in transactions:
        if t["type"] == "OUT" and t["status"] == "confirmed":
            default_items.append({
                'description': t["description"],
                'currency': t["currency"],
                'amount': float(t["amount"])
            })
            
    # Group by category per currency
    report_data = {}
    for cur in ('LAK', 'THB', 'USD'):
        report_data[cur] = {
            'income': _group_by_category(transactions, 'IN', cur),
            'expense': _group_by_category(transactions, 'OUT', cur),
        }
        
    context = {
        'active_nav': 'accounting',
        'selected_month': f"{current_month:02d}",
        'selected_year': str(current_year),
        'run_count': run_count,
        'voucher_date': voucher_date.strftime('%Y-%m-%d'),
        'voucher_date_formatted': voucher_date.strftime('%d-%m-%Y'),
        'default_cash_lak': float(cash_in_lak),
        'default_cash_thb': float(cash_in_thb),
        'default_cash_usd': float(cash_in_usd),
        'default_items_json': json.dumps(default_items),
        'report_json': json.dumps(report_data, ensure_ascii=False),
        'selected_currency': currency,
        'back_url': '/accounting/report/',
    }
    return render(request, 'accounting/monthly_summary_financial.html', context)


@manager_required
def yearly_summary_financial(request):
    """
    Generate the Yearly Financial Summary (ໃບສະຫຼຸບການເງິນປະຈຳປີ).
    Auto-populates data from unified transactions grouped by category and currency for the selected year.
    """
    import json
    import datetime
    today = timezone.localdate()
    
    year_str = request.GET.get('year')
    run_count = request.GET.get('run_count', '1')
    date_str = request.GET.get('date')
    currency = request.GET.get('currency', 'ALL')
    
    current_year = int(year_str) if (year_str and year_str.isdigit()) else today.year
    voucher_date = datetime.datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else today
    
    start_date = datetime.date(current_year, 1, 1)
    end_date = datetime.date(current_year, 12, 31)
    
    # Fetch unified transactions for the entire year
    transactions = unified_transactions(start_date, end_date)
    
    # Calculate incomes
    cash_in_lak = sum(t["amount"] for t in transactions if t["type"] == "IN" and t["currency"] == "LAK" and t["status"] == "confirmed")
    cash_in_thb = sum(t["amount"] for t in transactions if t["type"] == "IN" and t["currency"] == "THB" and t["status"] == "confirmed")
    cash_in_usd = sum(t["amount"] for t in transactions if t["type"] == "IN" and t["currency"] == "USD" and t["status"] == "confirmed")
    
    # Retrieve expenses grouped by category and currency
    # Using python grouping from unified transactions
    from collections import defaultdict
    expense_groups = defaultdict(float)
    for t in transactions:
        if t["type"] == "OUT" and t["status"] == "confirmed":
            key = (t["category"], t["currency"])
            expense_groups[key] += float(t["amount"])
            
    default_items = []
    for (category_name, cur), total_amount in sorted(expense_groups.items(), key=lambda x: -x[1]):
        default_items.append({
            'description': category_name or 'ລາຍຈ່າຍອື່ນໆ (Other Expenses)',
            'currency': cur,
            'amount': total_amount
        })
        
    if not default_items:
        default_items.append({
            'description': 'ລາຍຈ່າຍອື່ນໆ (Other Expenses)',
            'currency': 'LAK',
            'amount': 0.0
        })
        
    # Group by category per currency for P&L structure
    report_data = {}
    for cur in ('LAK', 'THB', 'USD'):
        report_data[cur] = {
            'income': _group_by_category(transactions, 'IN', cur),
            'expense': _group_by_category(transactions, 'OUT', cur),
        }
        
    context = {
        'active_nav': 'accounting',
        'selected_year': str(current_year),
        'run_count': run_count,
        'voucher_date': voucher_date.strftime('%Y-%m-%d'),
        'voucher_date_formatted': voucher_date.strftime('%d-%m-%Y'),
        'default_cash_lak': float(cash_in_lak),
        'default_cash_thb': float(cash_in_thb),
        'default_cash_usd': float(cash_in_usd),
        'default_items_json': json.dumps(default_items),
        'report_json': json.dumps(report_data, ensure_ascii=False),
        'selected_currency': currency,
        'back_url': '/accounting/report/',
    }
    return render(request, 'accounting/yearly_summary_financial.html', context)


@manager_required
def category_detail_print(request):
    """
    Printable line-by-line breakdown of a single category for a month.
    Supports key='office' (ຄ່າໃຊ້ຈ່າຍຫ້ອງການ), key='other' (ລາຍຈ່າຍອື່ນໆ),
    key='other_income' (ລາຍຮັບອື່ນໆ), and key='office_income' (ເງິນບໍລິຫານຫ້ອງການ).
    """
    import datetime
    today = timezone.localdate()
    
    key = request.GET.get('key', 'office')
    currency = request.GET.get('currency', 'LAK')
    if currency not in ('LAK', 'THB', 'USD'):
        currency = 'LAK'
        
    month_str = request.GET.get('month')
    year_str = request.GET.get('year')
    current_month, current_year, start_date, end_date = _get_accounting_cycle_dates(
        month_str, year_str, today
    )
    
    # Fetch unified transactions
    transactions = unified_transactions(start_date, end_date, currency=currency)
    
    # Filter by category matching the key
    if key == 'other_income':
        match_fn = lambda c: 'ລາຍຮັບອື່ນ' in c or 'other income' in c.lower()
        title_lo = 'ລາຍຮັບອື່ນໆ (Other Income)'
        title_en = 'Other Income'
        transaction_type = 'IN'
    elif key == 'office_income':
        match_fn = lambda c: 'ບໍລິຫານ' in c or 'office administration' in c.lower()
        title_lo = 'ເງິນບໍລິຫານຫ້ອງການ (Office Administration)'
        title_en = 'Office Administration Income'
        transaction_type = 'IN'
    elif key == 'other':
        match_fn = lambda c: 'ອື່ນໆ' in c or 'other expenses' in c.lower()
        title_lo = 'ລາຍຈ່າຍອື່ນໆ (Other Expenses)'
        title_en = 'Other Expenses'
        transaction_type = 'OUT'
    else:
        key = 'office'
        match_fn = lambda c: 'ຫ້ອງການ' in c or 'office expenses' in c.lower()
        title_lo = 'ຄ່າໃຊ້ຈ່າຍຫ້ອງການ'
        title_en = 'Office Expenses'
        transaction_type = 'OUT'
        
    items = []
    total = 0.0
    for t in transactions:
        if t["type"] == transaction_type and t["status"] == "confirmed" and match_fn(t["category"]):
            items.append({
                'date': t["date"],
                'description': t["description"],
                'category': t["category"] or '-',
                'amount': float(t["amount"]),
            })
            total += float(t["amount"])
            
    # Sort items by date
    items.sort(key=lambda x: x['date'])
    
    context = {
        'key': key,
        'title_lo': title_lo,
        'title_en': title_en,
        'items': items,
        'total': total,
        'currency': currency,
        'selected_month': f"{current_month:02d}",
        'selected_year': str(current_year),
        'today': today,
    }
    return render(request, 'accounting/category_detail_print.html', context)
