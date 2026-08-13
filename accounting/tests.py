from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from pos.models import Expense, Order, Payment

from .models import AccountCategory, Budget, CashBook, CashHandover
from .services import totals_by_currency, unified_transactions


class AccountingTestCase(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="manager", email="manager@example.com", password="test-pass-123"
        )
        self.income_category = AccountCategory.objects.create(
            name="ລາຍຮັບທົດສອບ", transaction_type="IN"
        )
        self.expense_category = AccountCategory.objects.create(
            name="ລາຍຈ່າຍທົດສອບ", transaction_type="OUT"
        )
        self.today = timezone.localdate()

    def login(self):
        self.client.force_login(self.user)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("accounting:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_totals_merge_pos_and_manual_without_mixing_currencies(self):
        order = Order.objects.create(status=Order.Status.PAID, created_by=self.user)
        payment = Payment.objects.create(
            order=order, amount=Decimal("500000"), currency="LAK", method="cash"
        )
        Payment.objects.filter(pk=payment.pk).update(
            paid_at=timezone.make_aware(datetime.combine(self.today, datetime.min.time()))
        )
        Expense.objects.create(
            date=self.today,
            category=Expense.Category.SUPPLIES,
            description="ນ້ຳຢາ",
            amount=Decimal("100000"),
            currency="LAK",
        )
        CashBook.objects.create(
            date=self.today,
            description="ລາຍຮັບອື່ນ",
            transaction_type="IN",
            category=self.income_category,
            amount=Decimal("500"),
            currency="THB",
            created_by=self.user,
        )
        CashBook.objects.create(
            date=self.today,
            description="draft excluded",
            transaction_type="OUT",
            category=self.expense_category,
            amount=Decimal("999"),
            currency="THB",
            status=CashBook.Status.DRAFT,
        )

        totals = totals_by_currency(self.today, self.today)
        self.assertEqual(totals["LAK"]["income"], Decimal("500000"))
        self.assertEqual(totals["LAK"]["expense"], Decimal("100000"))
        self.assertEqual(totals["LAK"]["balance"], Decimal("400000"))
        self.assertEqual(totals["THB"]["income"], Decimal("500"))
        self.assertEqual(totals["THB"]["expense"], Decimal("0"))

        sources = {row["source"] for row in unified_transactions(self.today, self.today)}
        self.assertEqual(sources, {"pos", "pos_expense", "manual"})

    def test_create_edit_and_delete_manual_transaction(self):
        self.login()
        create_response = self.client.post(
            reverse("accounting:transaction_create"),
            {
                "date": self.today,
                "time": "09:30",
                "transaction_type": "OUT",
                "category": self.expense_category.pk,
                "description": "ຄ່າສົ່ງ",
                "amount": "150000",
                "currency": "LAK",
                "payment_method": "cash",
                "reference": "TEST-1",
                "status": "confirmed",
                "note": "",
            },
        )
        self.assertEqual(create_response.status_code, 302)
        entry = CashBook.objects.get(reference="TEST-1")
        self.assertEqual(entry.created_by, self.user)

        edit_response = self.client.post(
            reverse("accounting:transaction_edit", args=[entry.pk]),
            {
                "date": self.today,
                "time": "09:45",
                "transaction_type": "OUT",
                "category": self.expense_category.pk,
                "description": "ຄ່າສົ່ງແກ້ໄຂ",
                "amount": "175000",
                "currency": "LAK",
                "payment_method": "transfer",
                "reference": "TEST-1",
                "status": "confirmed",
                "note": "updated",
            },
        )
        self.assertEqual(edit_response.status_code, 302)
        entry.refresh_from_db()
        self.assertEqual(entry.amount, Decimal("175000"))
        self.assertEqual(entry.updated_by, self.user)

        delete_response = self.client.post(
            reverse("accounting:transaction_delete", args=[entry.pk])
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(CashBook.objects.filter(pk=entry.pk).exists())

    def test_form_rejects_category_with_wrong_transaction_type(self):
        self.login()
        response = self.client.post(
            reverse("accounting:transaction_create"),
            {
                "date": self.today,
                "time": "10:00",
                "transaction_type": "IN",
                "category": self.expense_category.pk,
                "description": "invalid category",
                "amount": "100",
                "currency": "LAK",
                "payment_method": "cash",
                "status": "confirmed",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ໝວດບໍ່ກົງກັບປະເພດລາຍການ")
        self.assertFalse(CashBook.objects.filter(description="invalid category").exists())

    def test_dashboard_report_csv_and_handover_render(self):
        self.login()
        CashBook.objects.create(
            date=self.today,
            description="test income",
            transaction_type="IN",
            category=self.income_category,
            amount=Decimal("200000"),
            currency="LAK",
            payment_method="cash",
        )
        dashboard = self.client.get(reverse("accounting:dashboard"), {"date": self.today})
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "test income")

        report = self.client.get(reverse("accounting:report"))
        self.assertEqual(report.status_code, 200)
        self.assertContains(report, "ລາຍລະອຽດກະແສເງິນ")

        export = self.client.get(reverse("accounting:export_csv"))
        self.assertEqual(export.status_code, 200)
        self.assertIn("text/csv", export["Content-Type"])
        self.assertIn("ລາຍຮັບ", export.content.decode("utf-8-sig"))

        handover = self.client.post(
            reverse("accounting:cash_handover"),
            {
                "date": self.today,
                "currency": "LAK",
                "opening_balance": "50000",
                "counted_amount": "250000",
                "received_by": "Owner",
                "note": "",
            },
        )
        self.assertEqual(handover.status_code, 302)
        saved = CashHandover.objects.get(date=self.today, currency="LAK")
        self.assertEqual(saved.expected_amount, Decimal("250000"))
        self.assertEqual(saved.difference, Decimal("0"))

    def test_manager_can_configure_categories_and_budgets_without_admin(self):
        self.login()
        settings_page = self.client.get(reverse("accounting:settings"))
        self.assertEqual(settings_page.status_code, 200)
        self.assertContains(settings_page, "ໝວດບັນຊີ ແລະ ງົບປະມານ")

        category_response = self.client.post(
            reverse("accounting:settings"),
            {
                "action": "add_category",
                "category-name": "ຄ່າປະກັນໄພ",
                "category-transaction_type": "OUT",
                "category-color": "#123456",
            },
        )
        self.assertEqual(category_response.status_code, 302)
        category = AccountCategory.objects.get(name="ຄ່າປະກັນໄພ")

        budget_response = self.client.post(
            reverse("accounting:settings"),
            {
                "action": "save_budget",
                "budget-month": self.today.strftime("%Y-%m"),
                "budget-category": category.pk,
                "budget-currency": "LAK",
                "budget-amount": "900000",
            },
        )
        self.assertEqual(budget_response.status_code, 302)
        budget = Budget.objects.get(category=category, currency="LAK")
        self.assertEqual(budget.month.day, 1)
        self.assertEqual(budget.amount, Decimal("900000"))

        toggle_response = self.client.post(
            reverse("accounting:category_toggle", args=[category.pk])
        )
        self.assertEqual(toggle_response.status_code, 302)
        category.refresh_from_db()
        self.assertFalse(category.is_active)

        delete_response = self.client.post(
            reverse("accounting:budget_delete", args=[budget.pk])
        )
        self.assertEqual(delete_response.status_code, 302)
        self.assertFalse(Budget.objects.filter(pk=budget.pk).exists())

    def test_accounting_form_and_kanban_switch_between_english_and_lao(self):
        self.login()
        accounting_url = reverse("accounting:transaction_create")
        kanban_url = reverse("asset_intake:kanban")

        self.client.post(
            reverse("set_language"), {"language": "en", "next": accounting_url}
        )
        english_form = self.client.get(accounting_url)
        self.assertContains(english_form, "Add accounting transaction")
        self.assertContains(english_form, "Transaction details")
        self.assertContains(english_form, "Payment method")
        self.assertContains(english_form, "Save transaction")
        self.assertContains(english_form, "Kanban Tracking")
        self.assertContains(english_form, "Accounting")

        english_kanban = self.client.get(kanban_url)
        self.assertContains(english_kanban, "Kanban Job Tracking")
        self.assertContains(english_kanban, "All work")
        self.assertContains(english_kanban, "Repair &amp; restoration")

        self.client.post(
            reverse("set_language"), {"language": "lo", "next": accounting_url}
        )
        lao_form = self.client.get(accounting_url)
        self.assertContains(lao_form, "ເພີ່ມລາຍການບັນຊີ")
        self.assertContains(lao_form, "ຊ່ອງທາງຊຳລະ")
        self.assertContains(lao_form, "ບັນທຶກລາຍການ")
        self.assertContains(lao_form, "ຕິດຕາມການເຮັດວຽກ")
        self.assertContains(lao_form, "ບັນຊີລາຍຮັບ–ລາຍຈ່າຍ")

        lao_kanban = self.client.get(kanban_url)
        self.assertContains(lao_kanban, "ກະດານຕິດຕາມການເຮັດວຽກ")
        self.assertContains(lao_kanban, "ວຽກທັງໝົດ")
        self.assertContains(lao_kanban, "ສ້ອມແປງ / ບູລະນະ")

    def test_accounting_dashboard_switches_all_primary_labels(self):
        CashBook.objects.create(
            date=self.today,
            description="Bilingual dashboard entry",
            transaction_type="IN",
            category=self.income_category,
            amount=Decimal("250000"),
            currency="LAK",
            payment_method="cash",
            status=CashBook.Status.CONFIRMED,
        )
        self.login()
        dashboard_url = reverse("accounting:dashboard")

        self.client.post(
            reverse("set_language"), {"language": "en", "next": dashboard_url}
        )
        english = self.client.get(dashboard_url)
        self.assertContains(english, "Income and expense accounting")
        self.assertContains(english, "Add transaction")
        self.assertContains(english, "All currencies")
        self.assertContains(english, "Daily transactions")
        self.assertContains(english, "Manual")
        self.assertContains(english, "Cash")
        self.assertContains(english, "Budget control")
        self.assertContains(english, "Daily ledger")
        self.assertContains(english, "Cash handover")
        self.assertContains(english, "Categories & budgets")

        self.client.post(
            reverse("set_language"), {"language": "lo", "next": dashboard_url}
        )
        lao = self.client.get(dashboard_url)
        self.assertContains(lao, "ບັນຊີລາຍຮັບ–ລາຍຈ່າຍ")
        self.assertContains(lao, "ເພີ່ມລາຍການ")
        self.assertContains(lao, "ທຸກສະກຸນ")
        self.assertContains(lao, "ລາຍການປະຈຳວັນ")
        self.assertContains(lao, "ປ້ອນເອງ")
        self.assertContains(lao, "ເງິນສົດ")
        self.assertContains(lao, "ຄວບຄຸມງົບ")
        self.assertContains(lao, "ບັນຊີປະຈຳວັນ")
        self.assertContains(lao, "ສົ່ງມອບເງິນ")
        self.assertContains(lao, "ໝວດ ແລະ ງົບປະມານ")

    def test_report_handover_and_settings_switch_between_english_and_lao(self):
        self.login()
        report_url = reverse("accounting:report")
        handover_url = reverse("accounting:cash_handover")
        settings_url = reverse("accounting:settings")

        self.client.post(
            reverse("set_language"), {"language": "en", "next": report_url}
        )
        english_report = self.client.get(report_url)
        self.assertContains(english_report, "Financial report")
        self.assertContains(english_report, "Start date")
        self.assertContains(english_report, "Cashflow breakdown")

        english_handover = self.client.get(handover_url)
        self.assertContains(english_handover, "Cash handover and reconciliation")
        self.assertContains(english_handover, "Opening balance")
        self.assertContains(english_handover, "Confirm handover")

        english_settings = self.client.get(settings_url)
        self.assertContains(english_settings, "Accounting categories and budgets")
        self.assertContains(english_settings, "Add a new category")
        self.assertContains(english_settings, "Set monthly budget")
        self.assertContains(english_settings, "Budget amount")

        self.client.post(
            reverse("set_language"), {"language": "lo", "next": report_url}
        )
        lao_report = self.client.get(report_url)
        self.assertContains(lao_report, "ລາຍງານການເງິນ")
        self.assertContains(lao_report, "ຈາກວັນທີ")
        self.assertContains(lao_report, "ລາຍລະອຽດກະແສເງິນ")

        lao_handover = self.client.get(handover_url)
        self.assertContains(lao_handover, "ສົ່ງມອບ ແລະ ກວດນັບເງິນ")
        self.assertContains(lao_handover, "ເງິນທອນຕົ້ນມື້")
        self.assertContains(lao_handover, "ຢືນຢັນການສົ່ງມອບ")

        lao_settings = self.client.get(settings_url)
        self.assertContains(lao_settings, "ໝວດບັນຊີ ແລະ ງົບປະມານ")
        self.assertContains(lao_settings, "ເພີ່ມໝວດໃໝ່")
        self.assertContains(lao_settings, "ຕັ້ງງົບລາຍເດືອນ")
        self.assertContains(lao_settings, "ງົບປະມານ")

    def test_financial_summaries_use_the_primary_theme(self):
        self.login()

        monthly = self.client.get(
            reverse("accounting:monthly_summary_financial"),
            {"month": "07", "year": "2026", "currency": "LAK"},
        )
        self.assertEqual(monthly.status_code, 200)
        self.assertContains(monthly, "financial-summary-shell")
        self.assertContains(monthly, "summary-hero")
        self.assertContains(monthly, "summary-primary-action")
        self.assertContains(monthly, "summary-preview-stage")
        self.assertContains(monthly, "07/2026")

        yearly = self.client.get(
            reverse("accounting:yearly_summary_financial"),
            {"year": "2026", "currency": "LAK"},
        )
        self.assertEqual(yearly.status_code, 200)
        self.assertContains(yearly, "financial-summary-shell")
        self.assertContains(yearly, "summary-hero")
        self.assertContains(yearly, "summary-primary-action")
        self.assertContains(yearly, "summary-preview-stage")
        self.assertContains(yearly, "Yearly Summary Financial")
