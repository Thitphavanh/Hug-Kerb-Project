from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Customer


class DuplicatePhoneTests(TestCase):
    """ເບີໂທແມ່ນ unique field — submit ຊ້ຳຕ້ອງສະແດງ error ທີ່ເຂົ້າໃຈໄດ້
    ບໍ່ແມ່ນ crash ດ້ວຍ IntegrityError (500 server error)."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="crm-tester", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.existing = Customer.objects.create(
            name="ນາງ ມາລີ", phone="02055551111"
        )

    def test_create_with_duplicate_phone_is_blocked_not_merged(self):
        """ຊື່ຕ່າງກັນແຕ່ເບີໂທຄືກັນ ຕ້ອງຖືກ block ຢ່າງດຽວ — ຫ້າມ redirect ໄປສະແດງ
        customer ຄົນເກົ່າແທນ ເພາະອາດເຮັດໃຫ້ພະນັກງານແກ້ໄຂຂໍ້ມູນຄົນຜິດໂດຍບໍ່ຮູ້ຕົວ."""
        response = self.client.post(
            reverse("crm:index"),
            {
                "name": "ທ້າວ ສົມສັກ",
                "phone": self.existing.phone,
                "email": "",
                "tier": "basic",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("crm:index"))
        self.assertEqual(Customer.objects.filter(phone=self.existing.phone).count(), 1)
        self.assertFalse(Customer.objects.filter(name="ທ້າວ ສົມສັກ").exists())

    def test_edit_to_duplicate_phone_shows_error_instead_of_crashing(self):
        other = Customer.objects.create(name="ທ້າວ ບຸນມີ", phone="02055552222")
        response = self.client.post(
            reverse("crm:edit_customer", args=[other.pk]),
            {
                "name": "ທ້າວ ບຸນມີ",
                "phone": self.existing.phone,
                "email": "",
                "tier": "basic",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"/crm/?customer={other.pk}")
        other.refresh_from_db()
        self.assertEqual(other.phone, "02055552222")

    def test_edit_keeping_own_phone_still_works(self):
        response = self.client.post(
            reverse("crm:edit_customer", args=[self.existing.pk]),
            {
                "name": "ນາງ ມາລີ ອັບເດດ",
                "phone": self.existing.phone,
                "email": "",
                "tier": "basic",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.existing.refresh_from_db()
        self.assertEqual(self.existing.name, "ນາງ ມາລີ ອັບເດດ")
