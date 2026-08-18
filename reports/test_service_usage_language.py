from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.models import Customer
from pos.models import Order, OrderItem, ServiceType


class ServiceUsageLanguageTests(TestCase):
    """ໜ້າສະຖິຕິບໍລິການຕ້ອງອອກຄົບທັງລາວ ແລະ ອັງກິດ

    ເຄີຍພັງມາແລ້ວຍ້ອນຄຳແປຖືກໝາຍເປັນ fuzzy — gettext ຈະຂ້າມ fuzzy ແລ້ວຕົກ
    ກັບໄປອັງກິດ ເຮັດໃຫ້ໜ້າອອກເຄິ່ງລາວເຄິ່ງອັງກິດ ທັງໆທີ່ .po ມີຄຳແປຢູ່.
    """

    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="mgr", email="mgr@example.com", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.url = reverse("reports:service_usage")

        # ຕ້ອງມີຂໍ້ມູນ ບໍ່ດັ່ງນັ້ນຕາຕະລາງຈະບໍ່ render ແລ້ວຫົວຖັນຈະບໍ່ຖືກເທັສ
        customer = Customer.objects.create(name="ນາງ ແກ້ວ", phone="02055554444")
        service = ServiceType.objects.create(
            name="Deep Clean", price=Decimal("150000.00")
        )
        order = Order.objects.create(
            customer=customer, vat_rate=0, status=Order.Status.PAID
        )
        OrderItem.objects.create(
            order=order, service_type=service, quantity=2, unit_price=Decimal("150000.00")
        )

    def _switch(self, code):
        self.client.post(reverse("set_language"), {"language": code, "next": self.url})
        return self.client.get(self.url)

    def test_page_is_fully_lao_in_lao_mode(self):
        page = self._switch("lo")
        self.assertEqual(page.status_code, 200)
        for text in [
            "ການໃຊ້ບໍລິການ",
            "ບໍລິການທີ່ສົ່ງມອບ",
            "ລາຍຮັບຈາກບໍລິການ",
            "ການປະເມີນດ້ວຍ AI",
            "ການປະເມີນລາຄາດ້ວຍ AI",
            "ບໍລິການທີ່ໃຊ້ຫຼາຍທີ່ສຸດ",
            "ການເຄື່ອນໄຫວຂອງ AI",
            "ເກຣດສະພາບເກີບທີ່ AI ປະເມີນໃຫ້",
            "ໂພສໂປຣໂມທີ່ AI ສ້າງ",
            "ມື້ນີ້",
            "30 ວັນ",
        ]:
            self.assertContains(page, text)

    def test_page_is_fully_english_in_english_mode(self):
        page = self._switch("en")
        self.assertEqual(page.status_code, 200)
        for text in [
            "Service usage",
            "Services delivered",
            "Service revenue",
            "AI assessments",
            "Most used services",
            "AI activity",
            "Condition grades the AI returned",
            "Promo posts generated",
            "Today",
            "30 days",
        ]:
            self.assertContains(page, text)

    def test_table_headers_follow_the_language(self):
        lao = self._switch("lo")
        self.assertContains(lao, "ຈຳນວນຄັ້ງ")
        self.assertContains(lao, "ຈຳນວນບິນ")

        english = self._switch("en")
        self.assertContains(english, ">Times<")
        self.assertContains(english, ">Bills<")
