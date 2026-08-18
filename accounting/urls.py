from django.urls import path

from . import views

app_name = "accounting"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("transactions/add/", views.transaction_create, name="transaction_create"),
    path("transactions/<int:pk>/edit/", views.transaction_edit, name="transaction_edit"),
    path("transactions/<int:pk>/delete/", views.transaction_delete, name="transaction_delete"),
    path("categories/<int:pk>/", views.category_detail, name="category_detail"),
    path("report/", views.report, name="report"),
    path("report/export/", views.export_report, name="export_report"),
    # ຊື່ເກົ່າ — ລິ້ງ/ບຸກມາກທີ່ບັນທຶກໄວ້ແລ້ວຍັງໃຊ້ໄດ້
    path("report/export/csv/", views.export_report, name="export_csv"),
    path("export/daily/", views.export_daily_transactions, name="export_daily_transactions"),
    path("payment-method-report/", views.payment_method_report, name="payment_method_report"),
    path("cash-handover/", views.cash_handover, name="cash_handover"),
    path("cash-handover/yearly/", views.yearly_cash_handover, name="yearly_cash_handover"),
    path("monthly-summary-financial/", views.monthly_summary_financial, name="monthly_summary_financial"),
    path("yearly-summary-financial/", views.yearly_summary_financial, name="yearly_summary_financial"),
    path("category-detail-print/", views.category_detail_print, name="category_detail_print"),
    path("settings/", views.settings_view, name="settings"),
    path("settings/categories/<int:pk>/toggle/", views.category_toggle, name="category_toggle"),
    path("settings/budgets/<int:pk>/delete/", views.budget_delete, name="budget_delete"),
]
