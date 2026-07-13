from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

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
