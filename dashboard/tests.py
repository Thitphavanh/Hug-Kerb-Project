from django.contrib.auth import get_user_model
from django.urls import reverse
from django.contrib.auth.models import User
from django.test import TestCase

from asset_intake.models import Asset
from crm.models import Customer
from pos.models import Expense, Order, OrderItem, Payment
from staff.models import StaffProfile


class DashboardSmokeTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("staff", password="test1234")
        # ໜ້າ Reports ຈຳກັດສະເພາະຜູ້ຈັດການ
        StaffProfile.objects.create(user=self.user, role=StaffProfile.Role.MANAGER)
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02012345678")
        self.asset = Asset.objects.create(
            customer=self.customer, brand="Nike", model_name="Air Force 1", size="42"
        )
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)

        OrderItem.objects.create(
            order=self.order, description="ຊັກເກີບ", quantity=2, unit_price=150
        )
        Payment.objects.create(order=self.order, amount=300)
        Expense.objects.create(description="ນ້ຳຢາຊັກເກີບ", amount=100)

    def test_order_total(self):
        self.assertEqual(self.order.total, 300)

    def test_dashboard_requires_login(self):
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 302)

    def test_dashboard_shows_stats(self):
        self.client.force_login(self.user)
        response = self.client.get("/dashboard/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["revenue_today"], 300)
        self.assertEqual(response.context["expense_month"], 100)
        self.assertEqual(response.context["net_month"], 200)
        self.assertEqual(response.context["active_assets"], 1)

    def test_reports_totals(self):
        self.client.force_login(self.user)
        response = self.client.get("/reports/?period=month")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["income_total"], 300)
        self.assertEqual(response.context["expense_total"], 100)
        self.assertEqual(response.context["net_total"], 200)


class AppShellLayoutTest(TestCase):
    """ກ່ອງເນື້ອຫາໃນ base.html ຕ້ອງເປັນ containing block ສະເໝີ

    ເຄີຍພັງມາແລ້ວ: input ທີ່ໃສ່ .sr-only (Tailwind ຕັ້ງເປັນ position:absolute)
    ບໍ່ມີ ancestor ທີ່ positioned ຈຶ່ງໄປອ້າງອີງໜ້າເອກະສານແທນ ຫຼຸດອອກຈາກ
    <main> ທີ່ scroll ເອງ ແລ້ວດັນ <html> ໃຫ້ສູງກວ່າຈໍ — ເກີດຊ່ອງຫວ່າງຂາວ
    ໃຫຍ່ຢູ່ລຸ່ມແອັບ ແລະ scrollbar ຊ້ອນກັນສອງອັນ (ເຫັນຢູ່ໜ້າ /pos/create/).
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="shell-mgr", email="shell@example.com", password="test-pass-123"
        )
        self.client.force_login(self.user)

    def test_content_wrapper_is_a_positioned_containing_block(self):
        response = self.client.get(reverse("pos:create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "relative max-w-container-max")

    def test_pages_using_sr_only_inputs_still_get_the_wrapper(self):
        """ທຸກໜ້າທີ່ໃຊ້ .sr-only ຕ້ອງໄດ້ກ່ອງ relative ນຳ ບໍ່ດັ່ງນັ້ນຈະລົ້ນຄືເກົ່າ"""
        for url in (
            reverse("pos:create"),
            reverse("asset_intake:create"),
            reverse("asset_intake:storage"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                body = response.content.decode()
                if "sr-only" in body:
                    self.assertIn("relative max-w-container-max", body)
