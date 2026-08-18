import json
from datetime import datetime, timedelta
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
        # ໜ້າ login ຂອງຮ້ານ ບໍ່ແມ່ນຂອງ admin — ພະນັກງານຮ້ານບໍ່ມີສິດ admin
        self.assertIn(reverse("login"), response.url)

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

    def _seed_statement_month(self):
        """ໜຶ່ງເດືອນທີ່ມີ ລາຍຮັບສົດ, ລາຍຈ່າຍໂອນ ແລະ ການຍ້າຍເງິນພາຍໃນຄູ່ໜຶ່ງ"""
        transfer_category = AccountCategory.objects.create(
            name="ຍ້າຍເງິນເຂົ້າບັນຊີ", transaction_type="OUT", is_internal_transfer=True
        )
        transfer_in_category = AccountCategory.objects.create(
            name="ຍ້າຍເງິນເຂົ້າບັນຊີ", transaction_type="IN", is_internal_transfer=True
        )
        first = self.today.replace(day=1)
        CashBook.objects.create(
            date=first,
            description="ຮັບເງິນສົດ",
            transaction_type="IN",
            category=self.income_category,
            amount=Decimal("1000000"),
            currency="LAK",
            payment_method=CashBook.PaymentMethod.CASH,
            created_by=self.user,
        )
        CashBook.objects.create(
            date=first,
            description="ຈ່າຍຄ່ານ້ຳຢາ ໂອນ",
            transaction_type="OUT",
            category=self.expense_category,
            amount=Decimal("200000"),
            currency="LAK",
            payment_method=CashBook.PaymentMethod.TRANSFER,
            created_by=self.user,
        )
        # ຍ້າຍເງິນສົດ 300,000 ເຂົ້າບັນຊີ = 2 ແຖວ ຜູກກັນ
        CashBook.objects.create(
            date=first,
            description="ຕັດເງິນສົດອອກຈາກກຳປັ່ນ",
            transaction_type="OUT",
            category=transfer_category,
            amount=Decimal("300000"),
            currency="LAK",
            payment_method=CashBook.PaymentMethod.CASH,
            created_by=self.user,
        )
        CashBook.objects.create(
            date=first,
            description="ເຂົ້າບັນຊີທະນາຄານ",
            transaction_type="IN",
            category=transfer_in_category,
            amount=Decimal("300000"),
            currency="LAK",
            payment_method=CashBook.PaymentMethod.TRANSFER,
            created_by=self.user,
        )
        return first

    def test_payment_method_report_keeps_internal_transfers_out_of_profit_totals(self):
        self.login()
        first = self._seed_statement_month()

        response = self.client.get(
            reverse("accounting:payment_method_report"),
            {"month": f"{first.month:02d}", "year": str(first.year), "currency": "LAK"},
        )
        self.assertEqual(response.status_code, 200)
        totals = response.context["full_totals"]
        # ການຍ້າຍເງິນບໍ່ບວມທັງລາຍຮັບ ແລະ ລາຍຈ່າຍ
        self.assertEqual(totals["IN"]["cash"], Decimal("1000000"))
        self.assertEqual(totals["IN"]["bank"], Decimal("0"))
        self.assertEqual(totals["OUT"]["cash"], Decimal("0"))
        self.assertEqual(totals["OUT"]["bank"], Decimal("200000"))
        self.assertEqual(response.context["internal_moved"], Decimal("300000"))
        # ແຕ່ໃນລາຍລະອຽດ ຍັງເຫັນທັງ 4 ແຖວ ເພາະເງິນຍ້າຍຈິງ
        self.assertEqual(len(response.context["items"]), 4)

    def test_cash_statement_runs_a_balance_and_shows_the_transfer_out(self):
        self.login()
        first = self._seed_statement_month()

        response = self.client.get(
            reverse("accounting:payment_method_report"),
            {
                "month": f"{first.month:02d}",
                "year": str(first.year),
                "currency": "LAK",
                "report_type": "cash",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["opening_balance"], Decimal("0"))
        # ຮັບສົດ 1,000,000 ແລ້ວຍ້າຍອອກ 300,000 → ເຫຼືອ 700,000 ໃນກຳປັ່ນ
        self.assertEqual(response.context["closing_balance"], Decimal("700000"))
        self.assertEqual(response.context["total_credit"], Decimal("1000000"))
        self.assertEqual(response.context["total_debit"], Decimal("300000"))
        self.assertEqual(response.context["credit_count"], 1)
        self.assertEqual(response.context["debit_count"], 1)

    def test_bank_statement_counts_qr_with_transfers(self):
        self.login()
        first = self._seed_statement_month()
        CashBook.objects.create(
            date=first,
            description="ຮັບເງິນຜ່ານ QR",
            transaction_type="IN",
            category=self.income_category,
            amount=Decimal("50000"),
            currency="LAK",
            payment_method=CashBook.PaymentMethod.QR,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("accounting:payment_method_report"),
            {
                "month": f"{first.month:02d}",
                "year": str(first.year),
                "currency": "LAK",
                "report_type": "bank",
            },
        )
        self.assertEqual(response.status_code, 200)
        # QR ນັບເປັນລາຍຮັບບັນຊີ; ຍ້າຍເງິນເຂົ້າ 300,000 ບໍ່ນັບເປັນລາຍຮັບ
        self.assertEqual(response.context["full_totals"]["IN"]["bank"], Decimal("50000"))
        # ໃບແຈ້ງຍອດ: +300,000 (ຍ້າຍເຂົ້າ) +50,000 (QR) −200,000 (ຈ່າຍໂອນ)
        self.assertEqual(response.context["closing_balance"], Decimal("150000"))

    def test_statement_opening_balance_carries_from_earlier_months(self):
        self.login()
        first = self.today.replace(day=1)
        CashBook.objects.create(
            date=first - timedelta(days=10),
            description="ຮັບເງິນສົດເດືອນກ່ອນ",
            transaction_type="IN",
            category=self.income_category,
            amount=Decimal("400000"),
            currency="LAK",
            payment_method=CashBook.PaymentMethod.CASH,
            created_by=self.user,
        )

        response = self.client.get(
            reverse("accounting:payment_method_report"),
            {
                "month": f"{first.month:02d}",
                "year": str(first.year),
                "currency": "LAK",
                "report_type": "cash",
            },
        )
        self.assertEqual(response.context["opening_balance"], Decimal("400000"))
        self.assertEqual(response.context["closing_balance"], Decimal("400000"))

    def test_legacy_payment_report_links_land_on_the_merged_statement(self):
        self.login()
        response = self.client.get(
            reverse("accounting:payment_method_report"), {"report_type": "out_transfer"}
        )
        self.assertEqual(response.context["report_type"], "bank")

    def test_report_exports_csv_and_pdf(self):
        self.login()
        self._seed_statement_month()

        csv_response = self.client.get(
            reverse("accounting:export_report"), {"format": "csv"}
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertIn("text/csv", csv_response["Content-Type"])
        self.assertIn(".csv", csv_response["Content-Disposition"])

        pdf_response = self.client.get(
            reverse("accounting:export_report"), {"format": "pdf"}
        )
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response["Content-Type"], "application/pdf")
        self.assertTrue(pdf_response.content.startswith(b"%PDF"))

    def test_report_exports_excel_and_word_when_the_packages_are_available(self):
        self.login()
        self._seed_statement_month()

        for export_format, extension in (("excel", ".xlsx"), ("word", ".docx")):
            with self.subTest(export_format=export_format):
                response = self.client.get(
                    reverse("accounting:export_report"), {"format": export_format}
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(extension, response["Content-Disposition"])
                # ທັງສອງເປັນ zip container ຂອງ Office Open XML
                self.assertTrue(response.content.startswith(b"PK"))

    def test_daily_export_can_be_filtered_to_one_payment_channel(self):
        self.login()
        first = self._seed_statement_month()

        response = self.client.get(
            reverse("accounting:export_daily_transactions"),
            {"date": first.isoformat(), "payment": "bank"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response["Content-Disposition"])

    def test_category_detail_print_lists_every_bank_movement(self):
        self.login()
        first = self._seed_statement_month()

        response = self.client.get(
            reverse("accounting:category_detail_print"),
            {
                "key": "bank_expense",
                "month": f"{first.month:02d}",
                "year": str(first.year),
                "currency": "LAK",
            },
        )
        self.assertEqual(response.status_code, 200)
        # ລາຍຈ່າຍທີ່ຈ່າຍດ້ວຍການໂອນ ບໍ່ວ່າຈະຢູ່ໝວດໃດ
        self.assertEqual(response.context["total"], Decimal("200000"))
        self.assertFalse(response.context["show_balance"])


class ProfitAndLossConsistencyTests(TestCase):
    """ລັອກໄວ້ວ່າ dashboard · ໜ້າລາຍງານ · ໃບສະຫຼຸບເດືອນ/ປີ ຕ້ອງໃຫ້ຕົວເລກດຽວກັນ

    ສາມໜ້ານີ້ເຄີຍຄິດຄົນລະແບບ: ໃບສະຫຼຸບບໍ່ຕັດການຍ້າຍເງິນພາຍໃນ ແລະ
    ໜ້າລາຍງານນັບຄືນເງິນເປັນລາຍຈ່າຍ ເຮັດໃຫ້ຍອດຂາຍບວມທັງທີ່ຍອດສຸດທິຖືກ.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="pl-manager", email="pl@example.com", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()

        self.sales = AccountCategory.objects.create(
            name="ຂາຍໜ້າຮ້ານ (Shop sales)", transaction_type="IN"
        )
        self.rent = AccountCategory.objects.create(
            name="ຄ່າເຊົ່າ (Rent)", transaction_type="OUT"
        )
        # ຄູ່ຍ້າຍເງິນ: ອອກຈາກກຳປັ່ນ → ເຂົ້າບັນຊີທະນາຄານ (ບໍ່ແມ່ນລາຍຮັບ/ລາຍຈ່າຍ)
        self.transfer_in = AccountCategory.objects.create(
            name="ຝາກເຂົ້າບັນຊີ (Deposit in)",
            transaction_type="IN",
            is_internal_transfer=True,
        )
        self.transfer_out = AccountCategory.objects.create(
            name="ຖອນຈາກກຳປັ່ນ (Deposit out)",
            transaction_type="OUT",
            is_internal_transfer=True,
        )

        def entry(category, transaction_type, amount, method="cash"):
            CashBook.objects.create(
                date=self.today,
                description=category.name,
                transaction_type=transaction_type,
                category=category,
                amount=Decimal(amount),
                currency="LAK",
                payment_method=method,
                created_by=self.user,
            )

        entry(self.sales, "IN", "1000000")
        entry(self.rent, "OUT", "300000", "transfer")
        entry(self.transfer_out, "OUT", "500000")
        entry(self.transfer_in, "IN", "500000", "transfer")

        # POS: ຮັບເງິນ 200,000 ແລ້ວຄືນໃຫ້ລູກຄ້າ 50,000
        order = Order.objects.create(status=Order.Status.PAID, created_by=self.user)
        paid_at = timezone.make_aware(
            datetime.combine(self.today, datetime.min.time()) + timedelta(hours=9)
        )
        for kind, amount in (
            (Payment.Kind.PAYMENT, "200000"),
            (Payment.Kind.REFUND, "50000"),
        ):
            payment = Payment.objects.create(
                order=order,
                kind=kind,
                amount=Decimal(amount),
                base_amount=Decimal(amount),
                currency="LAK",
                method="cash",
            )
            Payment.objects.filter(pk=payment.pk).update(paid_at=paid_at)

        # ຄວາມຈິງທີ່ທຸກໜ້າຕ້ອງລາຍງານ
        self.expected_income = Decimal("1150000")   # 1,000,000 + 200,000 − 50,000
        self.expected_expense = Decimal("300000")   # ຄ່າເຊົ່າ (ຍ້າຍເງິນບໍ່ນັບ)

    def _report_totals(self):
        response = self.client.get(
            reverse("accounting:report"),
            {"start": self.today.isoformat(), "end": self.today.isoformat()},
        )
        self.assertEqual(response.status_code, 200)
        rows = [row for row in response.context["rows"] if row["currency"] == "LAK"]
        self.assertEqual(len(rows), 1)
        return rows[0], response.context["totals"]["LAK"]

    def test_dashboard_totals_net_refunds_and_skip_internal_transfers(self):
        totals = totals_by_currency(self.today, self.today)["LAK"]
        self.assertEqual(totals["income"], self.expected_income)
        self.assertEqual(totals["expense"], self.expected_expense)

    def test_report_table_and_summary_cards_agree_on_the_same_page(self):
        row, cards = self._report_totals()
        self.assertEqual(row["income"], self.expected_income)
        self.assertEqual(row["expense"], self.expected_expense)
        # ຕາຕະລາງ ແລະ ການ໌ດຢູ່ໜ້າດຽວກັນ ຫ້າມຂັດກັນ
        self.assertEqual(row["income"], cards["income"])
        self.assertEqual(row["expense"], cards["expense"])

    def test_monthly_and_yearly_summary_match_the_dashboard(self):
        for view_name, params in (
            ("accounting:monthly_summary_financial",
             {"month": f"{self.today.month:02d}", "year": str(self.today.year)}),
            ("accounting:yearly_summary_financial", {"year": str(self.today.year)}),
        ):
            with self.subTest(view=view_name):
                response = self.client.get(reverse(view_name), params)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    Decimal(str(response.context["default_cash_lak"])),
                    self.expected_income,
                )
                report = json.loads(response.context["report_json"])["LAK"]
                income = sum(Decimal(str(row["amount"])) for row in report["income"])
                expense = sum(Decimal(str(row["amount"])) for row in report["expense"])
                self.assertEqual(income, self.expected_income)
                self.assertEqual(expense, self.expected_expense)

    def test_internal_transfer_never_appears_as_income_or_expense(self):
        response = self.client.get(
            reverse("accounting:monthly_summary_financial"),
            {"month": f"{self.today.month:02d}", "year": str(self.today.year)},
        )
        report = json.loads(response.context["report_json"])["LAK"]
        names = [row["description"] for row in report["income"] + report["expense"]]
        self.assertNotIn(self.transfer_in.name, names)
        self.assertNotIn(self.transfer_out.name, names)

    def test_refund_is_a_negative_income_line_labelled_as_a_refund(self):
        response = self.client.get(
            reverse("accounting:monthly_summary_financial"),
            {"month": f"{self.today.month:02d}", "year": str(self.today.year)},
        )
        report = json.loads(response.context["report_json"])["LAK"]
        refunds = [
            row for row in report["income"] if Decimal(str(row["amount"])) < 0
        ]
        self.assertEqual(len(refunds), 1)
        self.assertEqual(Decimal(str(refunds[0]["amount"])), Decimal("-50000"))
        # ປ້າຍຕ້ອງບອກວ່າເປັນການຄືນເງິນ ບໍ່ແມ່ນ "ລາຍຮັບຈາກ POS"
        self.assertNotIn("income", refunds[0]["description"].lower())
        self.assertEqual(
            [row["description"] for row in report["expense"]].count(
                refunds[0]["description"]
            ),
            0,
        )


class YearlyCashHandoverTests(TestCase):
    """ໃບສົ່ງມອບເງິນປະຈຳປີ — ລວມການສົ່ງມອບລາຍວັນທັງປີ ແລະ ຊີ້ວັນທີ່ຍອດບໍ່ກົງ"""

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="handover-manager", email="ho@example.com", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.year = timezone.localdate().year

    def _handover(self, month, day, expected, counted, currency="LAK"):
        return CashHandover.objects.create(
            date=datetime(self.year, month, day).date(),
            currency=currency,
            expected_amount=Decimal(expected),
            counted_amount=Decimal(counted),
            handed_by=self.user,
            received_by="ເຈົ້າຂອງຮ້ານ",
        )

    def test_year_totals_add_up_and_flag_the_days_that_did_not_balance(self):
        self._handover(1, 5, "500000", "500000")
        self._handover(1, 6, "300000", "280000")   # ຂາດ 20,000
        self._handover(3, 10, "700000", "710000")  # ເກີນ 10,000

        response = self.client.get(
            reverse("accounting:yearly_cash_handover"), {"year": str(self.year)}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year_expected"], Decimal("1500000"))
        self.assertEqual(response.context["year_counted"], Decimal("1490000"))
        self.assertEqual(response.context["year_difference"], Decimal("-10000"))
        self.assertEqual(response.context["recorded_days"], 3)
        self.assertEqual(len(response.context["mismatches"]), 2)

        months = {row["month"]: row for row in response.context["months"]}
        self.assertEqual(len(response.context["months"]), 12)
        self.assertEqual(months[1]["counted"], Decimal("780000"))
        self.assertEqual(months[1]["mismatch_days"], 1)
        self.assertEqual(months[3]["difference"], Decimal("10000"))
        self.assertEqual(months[2]["days"], 0)

    def test_other_years_and_currencies_stay_out_of_the_sheet(self):
        self._handover(2, 2, "100000", "100000")
        self._handover(2, 3, "900", "900", currency="THB")
        CashHandover.objects.create(
            date=datetime(self.year - 1, 2, 2).date(),
            currency="LAK",
            expected_amount=Decimal("999999"),
            counted_amount=Decimal("999999"),
            handed_by=self.user,
            received_by="ປີກ່ອນ",
        )

        response = self.client.get(
            reverse("accounting:yearly_cash_handover"),
            {"year": str(self.year), "currency": "LAK"},
        )

        self.assertEqual(response.context["year_expected"], Decimal("100000"))
        self.assertEqual(response.context["recorded_days"], 1)

    def test_daily_handover_page_links_to_the_yearly_sheet(self):
        response = self.client.get(reverse("accounting:cash_handover"))
        self.assertContains(response, reverse("accounting:yearly_cash_handover"))
