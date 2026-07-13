from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from crm.models import Customer


class ReportsTranslationTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="report-manager", password="test-pass-123"
        )
        Customer.objects.create(name="Report customer", phone="02055551111")
        self.client.force_login(self.user)
        self.url = reverse("reports:income_expense")

    def test_report_switches_between_english_and_lao(self):
        self.client.post(
            reverse("set_language"), {"language": "en", "next": self.url}
        )
        english = self.client.get(self.url)
        self.assertContains(english, "Financial overview")
        self.assertContains(english, "Total revenue")
        self.assertContains(english, "Customer segments")
        self.assertContains(english, "Trigger win-back email sequence")

        self.client.post(
            reverse("set_language"), {"language": "lo", "next": self.url}
        )
        lao = self.client.get(self.url)
        self.assertContains(lao, "ພາບລວມການເງິນ")
        self.assertContains(lao, "ລາຍຮັບລວມ")
        self.assertContains(lao, "ກຸ່ມລູກຄ້າ")
        self.assertContains(lao, "ກະຕຸ້ນອີເມວເພື່ອດຶງລູກຄ້າກັບຄືນ")
