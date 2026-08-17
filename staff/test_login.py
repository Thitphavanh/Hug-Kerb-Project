"""ເທັສໜ້າເຂົ້າສູ່ລະບົບຂອງຮ້ານ

ຫົວໃຈ: ພະນັກງານທີ່ຮ້ານສ້າງເອງຜ່ານໜ້າ "ເພີ່ມພະນັກງານ" ບໍ່ມີ is_staff
ຈຶ່ງເຂົ້າໜ້າ login ຂອງ Django admin ບໍ່ໄດ້ — ຕ້ອງມີໜ້າ login ຂອງຮ້ານເອງ.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import StaffProfile


class ShopLoginTest(TestCase):
    def setUp(self):
        self.password = "shop-pass-123"
        self.user = get_user_model().objects.create_user(
            username="somchai", password=self.password
        )
        StaffProfile.objects.create(
            user=self.user,
            role=StaffProfile.Role.TECHNICIAN,
            commission_rate=Decimal("0"),
        )

    def test_a_technician_without_admin_access_can_sign_in(self):
        """ນີ້ຄືບັກທີ່ແກ້ — ກ່ອນນີ້ຊ່າງຊັກເກີບເຂົ້າລະບົບບໍ່ໄດ້ເລີຍ"""
        self.assertFalse(self.user.is_staff, "ພະນັກງານຮ້ານບໍ່ຄວນຕ້ອງມີສິດ admin")

        response = self.client.post(
            reverse("login"),
            {"username": "somchai", "password": self.password},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_signing_in_lands_on_the_shop_dashboard_not_the_django_admin(self):
        response = self.client.post(
            reverse("login"),
            {"username": "somchai", "password": self.password},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], reverse("dashboard:index"))

    def test_a_wrong_password_is_refused(self):
        response = self.client.post(
            reverse("login"), {"username": "somchai", "password": "wrong"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_protected_page_sends_a_signed_out_visitor_to_the_shop_login(self):
        response = self.client.get(reverse("pos:create"))

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            response.url.startswith(reverse("login")),
            f"ຄວນໄປໜ້າ login ຂອງຮ້ານ ແຕ່ໄປ {response.url}",
        )

    def test_the_login_page_carries_the_shop_branding(self):
        response = self.client.get(reverse("login"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hug ເກີບ")
        self.assertNotContains(response, "Django site admin")

    def test_signing_out_ends_the_session(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("logout"))

        self.assertEqual(response.status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
