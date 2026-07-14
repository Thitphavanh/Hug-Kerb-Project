from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from ai_mart_grading.models import ChecklistItem
from crm.models import Customer

from .models import Asset


class AssetTokenTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02011112222")

    def test_public_token_generated_and_unique(self):
        a1 = Asset.objects.create(customer=self.customer, brand="Nike")
        a2 = Asset.objects.create(customer=self.customer, brand="Adidas")
        self.assertTrue(a1.public_token)
        self.assertNotEqual(a1.public_token, a2.public_token)

    def test_completed_at_set_on_returned(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        self.assertIsNone(asset.completed_at)
        asset.status = Asset.Status.RETURNED
        asset.save(update_fields=["status", "updated_at"])
        asset.refresh_from_db()
        self.assertIsNotNone(asset.completed_at)


class TagAndTicketViewTest(TestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02011112222")
        self.asset = Asset.objects.create(customer=self.customer, brand="Nike")
        self.user = get_user_model().objects.create_user("staff1", password="x")

    def test_tag_label_requires_login(self):
        url = reverse("asset_intake:tag_label", args=[self.asset.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)  # redirect ໄປ login

    def test_tag_label_renders_qr(self):
        self.client.force_login(self.user)
        url = reverse("asset_intake:tag_label", args=[self.asset.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data:image/png;base64,")
        self.assertContains(resp, self.asset.ticket_number)

    def test_ticket_view_has_portal_qr(self):
        self.client.force_login(self.user)
        url = reverse("asset_intake:ticket_view", args=[self.asset.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "data:image/png;base64,")
        # ຄຳແນະນຳວິທີເຂົ້າແບບບໍ່ສະແກນ QR: /portal/ + ເລກ TK + ເບີໂທ
        self.assertContains(resp, "/portal/")
        self.assertContains(resp, self.asset.ticket_number)

    def test_social_image_redirects_without_photos(self):
        self.client.force_login(self.user)
        url = reverse("asset_intake:social_image", args=[self.asset.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)

    def test_intake_list_switches_between_english_and_lao(self):
        self.client.force_login(self.user)
        url = reverse("asset_intake:list")

        self.client.post(reverse("set_language"), {"language": "en", "next": url})
        english = self.client.get(url)
        self.assertContains(english, "AI inspection and valuation system")
        self.assertContains(english, "New intake")
        self.assertContains(english, "Ticket number")
        self.assertContains(english, "Received")

        self.client.post(reverse("set_language"), {"language": "lo", "next": url})
        lao = self.client.get(url)
        self.assertContains(lao, "ລະບົບກວດສອບ ແລະ ປະເມີນລາຄາ AI")
        self.assertContains(lao, "ຮັບເຄື່ອງໃໝ່")
        self.assertContains(lao, "ເລກໃບຮັບ")
        self.assertContains(lao, "ຮັບເຂົ້າ")

    def test_intake_detail_switches_between_english_and_lao(self):
        ChecklistItem.objects.create(
            name="ຮອຍເປື້ອນ/ຄວາມສະອາດຂອງໜ້າເກີບ",
            category=ChecklistItem.Category.UPPER,
        )
        self.client.force_login(self.user)
        url = reverse("asset_intake:detail", args=[self.asset.pk])

        self.client.post(reverse("set_language"), {"language": "en", "next": url})
        english = self.client.get(url)
        self.assertContains(
            english, "AI inspection and price estimation (AI Smart Grading)"
        )
        self.assertContains(english, "Asset intake")
        self.assertContains(english, "Upper cleanliness and stains")
        self.assertContains(english, "Received")
        self.assertContains(english, "Run valuation")
        self.assertContains(english, "Save draft")

        self.client.post(reverse("set_language"), {"language": "lo", "next": url})
        lao = self.client.get(url)
        self.assertContains(
            lao, "ລະບົບກວດສອບ ແລະ ປະເມີນລາຄາ AI (AI Smart Grading)"
        )
        self.assertContains(lao, "ຂໍ້ມູນຮັບເຄື່ອງ")
        self.assertContains(lao, "ຄວາມສະອາດ ແລະ ຮອຍເປື້ອນຂອງໜ້າເກີບ")
        self.assertContains(lao, "ຮັບເຂົ້າ")
        self.assertContains(lao, "ເລີ່ມປະເມີນລາຄາ")
        self.assertContains(lao, "ບັນທຶກຮ່າງ")
