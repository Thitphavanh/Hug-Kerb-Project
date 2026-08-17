"""ເທັສໜ້າສະຖິຕິການໃຊ້ບໍລິການ ແລະ AI (Scope 2.5)"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ai_mart_grading.models import Assessment
from asset_intake.models import Asset
from crm.models import Customer
from pos.models import Order, OrderItem, ServiceType
from staff.models import StaffProfile


class ServiceUsageReportTest(TestCase):
    def setUp(self):
        self.manager = get_user_model().objects.create_user(
            username="manager-usage", password="test-pass-123"
        )
        StaffProfile.objects.create(
            user=self.manager,
            role=StaffProfile.Role.MANAGER,
            commission_rate=Decimal("0"),
        )
        self.client.force_login(self.manager)

        self.customer = Customer.objects.create(name="ນາງ ແກ້ວ", phone="02055553333")
        self.deep_clean = ServiceType.objects.create(
            name="Deep Clean", price=Decimal("150000.00")
        )
        self.repair = ServiceType.objects.create(
            name="Sole Restoration", price=Decimal("300000.00")
        )

    def _order_with(self, service, quantity, price, status=Order.Status.PAID):
        order = Order.objects.create(
            customer=self.customer, vat_rate=0, status=status
        )
        OrderItem.objects.create(
            order=order,
            service_type=service,
            quantity=quantity,
            unit_price=Decimal(price),
        )
        return order

    def test_services_are_ranked_by_how_often_they_are_delivered(self):
        self._order_with(self.deep_clean, 3, "150000.00")
        self._order_with(self.repair, 1, "300000.00")

        response = self.client.get(reverse("reports:service_usage"))
        rows = response.context["service_rows"]

        self.assertEqual(rows[0]["service_type__name"], "Deep Clean")
        self.assertEqual(rows[0]["times_used"], 3)
        self.assertEqual(rows[1]["service_type__name"], "Sole Restoration")

    def test_revenue_per_service_multiplies_quantity_by_price(self):
        self._order_with(self.deep_clean, 2, "150000.00")

        response = self.client.get(reverse("reports:service_usage"))
        row = response.context["service_rows"][0]

        self.assertEqual(row["revenue"], Decimal("300000.00"))

    def test_cancelled_bills_do_not_count_as_service_usage(self):
        """ບິນທີ່ຍົກເລີກບໍ່ແມ່ນການໃຊ້ບໍລິການຈິງ ຈຶ່ງບໍ່ຄວນນັບ"""
        self._order_with(self.deep_clean, 5, "150000.00", status=Order.Status.CANCELLED)

        response = self.client.get(reverse("reports:service_usage"))

        self.assertEqual(response.context["service_rows"], [])
        self.assertEqual(response.context["total_services_used"], 0)

    def test_ai_assessments_are_counted_and_grouped_by_grade(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        Assessment.objects.create(asset=asset, overall_grade="A")
        Assessment.objects.create(asset=asset, overall_grade="A")
        Assessment.objects.create(asset=asset, overall_grade="C")

        response = self.client.get(reverse("reports:service_usage"))

        self.assertEqual(response.context["assessment_count"], 3)
        grades = {r["overall_grade"]: r["count"] for r in response.context["grade_rows"]}
        self.assertEqual(grades, {"A": 2, "C": 1})

    def test_an_invalid_period_falls_back_instead_of_erroring(self):
        response = self.client.get(reverse("reports:service_usage"), {"period": "junk"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["period"], "month")

    def test_a_technician_cannot_open_the_report(self):
        technician = get_user_model().objects.create_user(
            username="tech-usage", password="test-pass-123"
        )
        StaffProfile.objects.create(
            user=technician,
            role=StaffProfile.Role.TECHNICIAN,
            commission_rate=Decimal("0"),
        )
        self.client.force_login(technician)

        response = self.client.get(reverse("reports:service_usage"))

        self.assertNotEqual(response.status_code, 200)

    def test_the_page_renders_the_service_names_for_the_shop_to_read(self):
        self._order_with(self.deep_clean, 1, "150000.00")

        response = self.client.get(reverse("reports:service_usage"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Deep Clean")
