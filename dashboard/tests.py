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
        self.order = Order.objects.create(customer=self.customer)
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
