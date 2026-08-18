from django.test import TestCase
from django.urls import reverse

from asset_intake.models import Asset
from crm.models import Customer

from .models import MemberCard, PointTransaction


class PointBalanceTest(TestCase):
    def setUp(self):
        customer = Customer.objects.create(name="ທົດສອບ", phone="02087654321")
        self.card = MemberCard.objects.create(customer=customer)

    def test_card_number_generated(self):
        self.assertTrue(self.card.card_number.startswith("HK-"))

    def test_points_accumulate(self):
        PointTransaction.objects.create(card=self.card, points=50, reason="ໃຊ້ບໍລິການ")
        PointTransaction.objects.create(card=self.card, points=-20, reason="ແລກສ່ວນຫຼຸດ")
        self.card.refresh_from_db()
        self.assertEqual(self.card.points_balance, 30)


class CustomerPortalTest(TestCase):
    """ໜ້າ public — ເຂົ້າຜ່ານ token + ຢືນຢັນເບີໂທທີ່ລົງທະບຽນກ່ອນ"""

    def setUp(self):
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="020 1111 2222")
        self.asset = Asset.objects.create(
            customer=self.customer, brand="Nike", model_name="Air Max"
        )
        self.track_url = reverse(
            "digital_member:track", args=[self.asset.public_token]
        )

    def _verify(self, phone="02011112222"):
        return self.client.post(self.track_url, {"phone": phone})

    def test_gate_shown_before_verification(self):
        resp = self.client.get(self.track_url)
        self.assertEqual(resp.status_code, 200)
        # ຍັງບໍ່ຢືນຢັນ — ເຫັນແຕ່ຟອມ ບໍ່ເຫັນລາຍລະອຽດເກີບ
        self.assertContains(resp, "ຢືນຢັນຕົວຕົນ")
        self.assertNotContains(resp, "Air Max")

    def test_wrong_phone_rejected(self):
        resp = self._verify(phone="02099998888")
        self.assertContains(resp, "ບໍ່ກົງ")
        resp = self.client.get(self.track_url)
        self.assertNotContains(resp, "Air Max")

    def test_correct_phone_unlocks_tracking(self):
        resp = self._verify()
        self.assertEqual(resp.status_code, 302)
        resp = self.client.get(self.track_url)
        self.assertContains(resp, self.asset.ticket_number)
        self.assertContains(resp, "Nike")

    def test_phone_format_flexible(self):
        # ຕື່ມແບບ +856 ກໍຜ່ານ ເພາະທຽບ 8 ໂຕທ້າຍ
        resp = self._verify(phone="+856 20 1111 2222")
        self.assertEqual(resp.status_code, 302)

    def test_wrong_token_404(self):
        url = reverse("digital_member:track", args=["wrong-token-123"])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_track_shows_member_points(self):
        card = MemberCard.objects.create(customer=self.customer)
        PointTransaction.objects.create(card=card, points=70, reason="ໃຊ້ບໍລິການ")
        self._verify()
        resp = self.client.get(self.track_url)
        self.assertContains(resp, "70")
        self.assertContains(resp, card.card_number)

    def test_member_card_page(self):
        card = MemberCard.objects.create(customer=self.customer)
        url = reverse("digital_member:member_card", args=[card.card_number])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, card.card_number)

    def test_inactive_card_404(self):
        card = MemberCard.objects.create(customer=self.customer, is_active=False)
        url = reverse("digital_member:member_card", args=[card.card_number])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_member_card_page_shows_the_same_figures_as_the_crm_card(self):
        """ບັດຝັ່ງລູກຄ້າ ຕ້ອງບອກຕົວເລກຊຸດດຽວກັນກັບບັດທີ່ພະນັກງານເຫັນໃນ CRM"""
        from pos.models import Order

        card = MemberCard.objects.create(customer=self.customer, stamps_count=12)
        for _ in range(3):
            Order.objects.create(customer=self.customer, status=Order.Status.PAID)
        Order.objects.create(customer=self.customer, status=Order.Status.OPEN)

        resp = self.client.get(
            reverse("digital_member:member_card", args=[card.card_number])
        )

        self.assertEqual(resp.status_code, 200)
        # ນັບສະເພາະບິນທີ່ຊຳລະແລ້ວ ຄືກັນກັບ crm.views
        self.assertEqual(resp.context["visit_count"], 3)
        self.assertEqual(resp.context["card"].stamps_count, 12)
        self.assertEqual(resp.context["card"].current_stamps, 2)
        self.assertEqual(resp.context["card"].rewards_available, 1)
        # ໜ້າຕາບັດແບບດຽວກັບ modal ຂອງ CRM: ໂລໂກ້ + ຕີນບັດ + ລິ້ງດາວໂຫຼດຮູບ
        self.assertContains(resp, "WWW.HUGKERB.LA")
        self.assertContains(resp, "Shoe Spa · Member")
        self.assertContains(
            resp,
            reverse("digital_member:member_card_image", args=[card.card_number]),
        )

    def test_portal_pages_hide_the_scrollbar(self):
        card = MemberCard.objects.create(customer=self.customer)
        resp = self.client.get(
            reverse("digital_member:member_card", args=[card.card_number])
        )
        # ຍັງເລື່ອນໄດ້ ແຕ່ບໍ່ສະແດງແຖບ scroll
        self.assertContains(resp, "scrollbar-width: none")
        self.assertContains(resp, "::-webkit-scrollbar")


class LookupTest(TestCase):
    """ໜ້າຄົ້ນຫາດ້ວຍເລກໃບຮັບເຄື່ອງ + ເບີໂທ (ບໍ່ຕ້ອງສະແກນ QR)"""

    def setUp(self):
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02011112222")
        self.asset = Asset.objects.create(customer=self.customer, brand="Nike")
        self.url = reverse("digital_member:lookup")

    def test_lookup_page_renders(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ເລກໃບຮັບເຄື່ອງ")

    def test_lookup_success_redirects_to_track(self):
        resp = self.client.post(
            self.url,
            {"ticket_number": self.asset.ticket_number, "phone": "020 1111 2222"},
        )
        self.assertRedirects(
            resp,
            reverse("digital_member:track", args=[self.asset.public_token]),
        )
        # ຫຼັງ lookup ສຳເລັດ ຖືວ່າຢືນຢັນແລ້ວ — ເຫັນລາຍລະອຽດເລີຍ
        resp = self.client.get(
            reverse("digital_member:track", args=[self.asset.public_token])
        )
        self.assertContains(resp, "Nike")

    def test_lookup_wrong_phone_fails(self):
        resp = self.client.post(
            self.url,
            {"ticket_number": self.asset.ticket_number, "phone": "02000000000"},
        )
        self.assertContains(resp, "ບໍ່ພົບຂໍ້ມູນ ຫຼື ເບີໂທບໍ່ກົງ")

    def test_lookup_unknown_ticket_fails(self):
        resp = self.client.post(
            self.url, {"ticket_number": "TK-NOPE", "phone": "02011112222"}
        )
        self.assertContains(resp, "ບໍ່ພົບຂໍ້ມູນ ຫຼື ເບີໂທບໍ່ກົງ")


class MemberCardImageTest(TestCase):
    """ຮູບບັດສະສົມ Stamp ທີ່ສົ່ງໃຫ້ລູກຄ້າທາງ WhatsApp"""

    def setUp(self):
        self.customer = Customer.objects.create(name="ທ້າວ ທົດສອບ", phone="02077778888")
        self.card = MemberCard.objects.create(customer=self.customer, stamps_count=3)

    def test_card_image_returns_png_without_login(self):
        response = self.client.get(
            reverse("digital_member:member_card_image", args=[self.card.card_number])
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")
        self.assertTrue(response.content.startswith(b"\x89PNG"))

    def test_card_image_is_not_cached(self):
        response = self.client.get(
            reverse("digital_member:member_card_image", args=[self.card.card_number])
        )
        self.assertEqual(response["Cache-Control"], "no-store")

    def test_inactive_card_image_is_hidden(self):
        self.card.is_active = False
        self.card.save(update_fields=["is_active"])
        response = self.client.get(
            reverse("digital_member:member_card_image", args=[self.card.card_number])
        )
        self.assertEqual(response.status_code, 404)

    def test_unknown_card_number_returns_404(self):
        response = self.client.get(
            reverse("digital_member:member_card_image", args=["HK-DOESNOTEXIST"])
        )
        self.assertEqual(response.status_code, 404)

    def test_whatsapp_message_includes_card_image_link(self):
        from notifications.services import build_stamp_card_message, member_card_image_url

        message = build_stamp_card_message(self.customer, self.card, visit_count=3)
        self.assertIn(member_card_image_url(self.card), message)
        self.assertIn("3/10", message)
        self.assertIn("👟👟👟", message)
