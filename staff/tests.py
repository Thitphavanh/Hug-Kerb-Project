from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from asset_intake.models import Asset
from crm.models import Customer
from pos.models import Order, OrderItem

from .models import StaffProfile

User = get_user_model()


class CommissionReportTest(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("manager1", password="x")
        StaffProfile.objects.create(
            user=self.manager, role=StaffProfile.Role.MANAGER
        )
        self.tech = User.objects.create_user("tech1", password="x")
        StaffProfile.objects.create(
            user=self.tech,
            role=StaffProfile.Role.TECHNICIAN,
            commission_rate=Decimal("10"),
        )
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02011112222")
        self.url = reverse("staff:commissions")

    def _completed_asset(self, price):
        asset = Asset.objects.create(
            customer=self.customer, brand="Nike", assigned_to=self.tech
        )
        order = Order.objects.create(customer=self.customer)
        OrderItem.objects.create(
            order=order, asset=asset, description="ຊັກເກີບ", quantity=1, unit_price=price
        )
        asset.status = Asset.Status.RETURNED
        asset.save(update_fields=["status", "updated_at"])
        return asset

    def test_technician_cannot_access(self):
        self.client.force_login(self.tech)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 403)

    def test_manager_sees_commission(self):
        self._completed_asset(Decimal("200"))
        self._completed_asset(Decimal("300"))
        self.client.force_login(self.manager)
        month = timezone.localdate().strftime("%Y-%m")
        resp = self.client.get(self.url, {"month": month})
        self.assertEqual(resp.status_code, 200)
        rows = resp.context["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["base_total"], Decimal("500"))
        # 10% ຂອງ 500 = 50
        self.assertEqual(rows[0]["commission"], Decimal("50.00"))

    def test_invalid_month_falls_back(self):
        self.client.force_login(self.manager)
        resp = self.client.get(self.url, {"month": "not-a-month"})
        self.assertEqual(resp.status_code, 200)

    def test_commission_report_switches_between_english_and_lao(self):
        self.client.force_login(self.manager)

        self.client.post(
            reverse("set_language"), {"language": "en", "next": self.url}
        )
        english = self.client.get(self.url)
        self.assertContains(english, "Staff and commissions")
        self.assertContains(english, "Completed jobs")
        self.assertContains(english, "Staff directory")
        self.assertContains(english, "Technician")

        self.client.post(
            reverse("set_language"), {"language": "lo", "next": self.url}
        )
        lao = self.client.get(self.url)
        self.assertContains(lao, "ພະນັກງານ ແລະ ຄອມມິດຊັນ")
        self.assertContains(lao, "ວຽກສຳເລັດ")
        self.assertContains(lao, "ລາຍຊື່ພະນັກງານ")
        self.assertContains(lao, "ຊ່າງ")
