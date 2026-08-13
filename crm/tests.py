from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from digital_member.models import MemberCard
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


class StampLoyaltyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="crm-tester-stamp", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທ້າວ ສົມຊາຍ", phone="02099998888")
        self.card = MemberCard.objects.create(customer=self.customer)

    def test_add_stamp_increments_count(self):
        response = self.client.post(reverse("crm:add_stamp", args=[self.customer.pk]), {"count": 1})
        self.assertEqual(response.status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.stamps_count, 1)
        self.assertEqual(self.card.current_stamps, 1)
        self.assertEqual(self.card.rewards_available, 0)

    def test_collecting_10_stamps_unlocks_discount_reward(self):
        for _ in range(10):
            self.client.post(reverse("crm:add_stamp", args=[self.customer.pk]), {"count": 1})
        self.card.refresh_from_db()
        self.assertEqual(self.card.stamps_count, 10)
        self.assertEqual(self.card.current_stamps, 10)
        self.assertEqual(self.card.rewards_earned, 1)
        self.assertEqual(self.card.rewards_available, 1)

    def test_redeem_discount_claims_reward(self):
        self.card.stamps_count = 10
        self.card.save()

        response = self.client.post(reverse("crm:redeem_discount", args=[self.customer.pk]))
        self.assertEqual(response.status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.stamps_redeemed, 1)
        self.assertEqual(self.card.rewards_available, 0)
        self.assertEqual(self.card.current_stamps, 0)

    def test_reset_stamps(self):
        self.card.stamps_count = 5
        self.card.save()

        response = self.client.post(reverse("crm:reset_stamps", args=[self.customer.pk]))
        self.assertEqual(response.status_code, 302)
        self.card.refresh_from_db()
        self.assertEqual(self.card.stamps_count, 0)
        self.assertEqual(self.card.stamps_redeemed, 0)



class StampReviewModalTest(TestCase):
    """ປຸ່ມ "ກວດ Stamp" ຕ້ອງເປີດ modal ອ່ານຢ່າງດຽວ — ບໍ່ປະທັບ Stamp ໂດຍການກົດເສີຍໆ"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="crm-stamp-modal", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02011119999")
        self.card = MemberCard.objects.create(customer=self.customer, stamps_count=3)

    def test_modal_renders_with_card_details(self):
        response = self.client.get(reverse("crm:index"), {"customer": self.customer.pk})
        self.assertContains(response, 'id="stampReviewModal"')
        self.assertContains(response, "openStampReview()")

    def test_main_button_does_not_post_stamps(self):
        response = self.client.get(reverse("crm:index"), {"customer": self.customer.pk})
        # ປຸ່ມຫຼັກເປັນ type=button ເປີດ modal — ບໍ່ແມ່ນ form submit
        self.assertContains(response, 'onclick="openStampReview()"')
        self.card.refresh_from_db()
        self.assertEqual(self.card.stamps_count, 3)

    def test_add_stamp_rejects_zero_count(self):
        self.client.post(
            reverse("crm:add_stamp", args=[self.customer.pk]), {"count": 0}
        )
        self.card.refresh_from_db()
        self.assertEqual(self.card.stamps_count, 3)
