import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_mart_grading.models import Assessment, AssessmentItem, ChecklistItem
from crm.models import Customer
from media_backup.models import MediaFile
from pos.models import ServiceType

from .models import Asset
from .views import build_care_price_recommendation


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
        self.assertContains(english, "Save draft")

        self.client.post(reverse("set_language"), {"language": "lo", "next": url})
        lao = self.client.get(url)
        self.assertContains(
            lao, "ລະບົບກວດສອບ ແລະ ປະເມີນລາຄາ AI (AI Smart Grading)"
        )
        self.assertContains(lao, "ຂໍ້ມູນຮັບເຄື່ອງ")
        self.assertContains(lao, "ຄວາມສະອາດ ແລະ ຮອຍເປື້ອນຂອງໜ້າເກີບ")
        self.assertContains(lao, "ຮັບເຂົ້າ")
        self.assertContains(lao, "ບັນທຶກຮ່າງ")

    def test_buyback_panel_only_shows_for_buyback_service(self):
        """ຜົນການປະເມີນລາຄາຮັບຊື້ ຄວນສະແດງສະເພາະອໍເດີທີ່ມີບໍລິການຮັບຊື້ເກີບມືສອງແທ້ໆ
        — ບໍ່ແມ່ນທຸກອໍເດີທີ່ຜ່ານ AI checklist (ຄືກັນກັບອໍເດີຊັກເກີບທຳມະດາ)."""
        from pos.models import Order, OrderItem, ServiceType

        ChecklistItem.objects.create(
            name="ຮອຍເປື້ອນ/ຄວາມສະອາດຂອງໜ້າເກີບ",
            category=ChecklistItem.Category.UPPER,
        )
        self.client.force_login(self.user)
        url = reverse("asset_intake:detail", args=[self.asset.pk])

        # ອໍເດີຊັກເກີບທຳມະດາ (ບໍ່ມີບໍລິການຮັບຊື້) — ບໍ່ຄວນເຫັນ panel ລາຄາຮັບຊື້
        cleaning_service = ServiceType.objects.create(
            name="Deep Clean Service", category=ServiceType.Category.PRIMARY, price=150000
        )
        order = Order.objects.create(customer=self.customer, created_by=self.user)
        OrderItem.objects.create(
            order=order, service_type=cleaning_service, asset=self.asset,
            description="Deep clean", quantity=1, unit_price=150000,
        )
        resp = self.client.get(url)
        self.assertNotContains(resp, "ຜົນການປະເມີນລາຄາຮັບຊື້ເກີບມືສອງ")

        # ເພີ່ມບໍລິການຮັບຊື້ເກີບມືສອງເຂົ້າອໍເດີດຽວກັນ — ຕອນນີ້ຄວນເຫັນທັງ checklist
        # (ໂຄງລ່າງຮ່ວມ) ແລະ panel ລາຄາຮັບຊື້
        buyback_service = ServiceType.objects.create(
            name="Buy-back Evaluation", category=ServiceType.Category.BUYBACK, price=0
        )
        OrderItem.objects.create(
            order=order, service_type=buyback_service, asset=self.asset,
            description="Buy-back", quantity=1, unit_price=0,
        )
        resp2 = self.client.get(url)
        self.assertContains(resp2, "ຜົນການປະເມີນ AI")
        self.assertContains(resp2, "ຜົນການປະເມີນລາຄາຮັບຊື້ເກີບມືສອງ")

    def test_buyback_photo_checklist_locks_ai_until_required_angles_complete(self):
        from pos.models import Order, OrderItem, ServiceType

        self.client.force_login(self.user)
        self.client.post(
            reverse("set_language"),
            {
                "language": "en",
                "next": reverse("asset_intake:detail", args=[self.asset.pk]),
            },
        )
        service = ServiceType.objects.create(
            name="Buy-back Evaluation",
            category=ServiceType.Category.BUYBACK,
            price=0,
        )
        order = Order.objects.create(customer=self.customer, created_by=self.user)
        OrderItem.objects.create(
            order=order,
            service_type=service,
            asset=self.asset,
            description="Buy-back",
            unit_price=0,
        )
        url = reverse("asset_intake:detail", args=[self.asset.pk])

        incomplete = self.client.get(url)
        self.assertContains(incomplete, "Buy-back photo checklist")
        self.assertContains(incomplete, "0/5")
        self.assertContains(incomplete, "Complete required photos first")
        self.assertContains(incomplete, "Complete photos and AI assessment first")

        required_angles = [
            MediaFile.CaptureAngle.FRONT,
            MediaFile.CaptureAngle.HEEL,
            MediaFile.CaptureAngle.SIDE,
            MediaFile.CaptureAngle.OUTSOLE,
            MediaFile.CaptureAngle.SIZE_LABEL,
        ]
        for angle in required_angles:
            MediaFile.objects.create(
                asset=self.asset,
                stage=MediaFile.Stage.BEFORE,
                media_type=MediaFile.MediaType.IMAGE,
                capture_angle=angle,
                file=f"assets/test-{angle}.jpg",
            )
        Assessment.objects.create(
            asset=self.asset,
            status=Assessment.Status.DONE,
            overall_grade="B",
        )

        complete = self.client.get(url)
        self.assertContains(complete, "5/5")
        self.assertNotContains(complete, "Complete required photos first")
        self.assertContains(complete, "Run valuation")

    def test_photo_upload_saves_selected_buyback_angle(self):
        self.client.force_login(self.user)
        url = reverse("asset_intake:detail", args=[self.asset.pk])

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                response = self.client.post(
                    url,
                    {
                        "upload_stage": MediaFile.Stage.BEFORE,
                        "capture_angle": MediaFile.CaptureAngle.FRONT,
                        "photos": SimpleUploadedFile(
                            "front.jpg",
                            b"test-image-content",
                            content_type="image/jpeg",
                        ),
                    },
                )

        self.assertEqual(response.status_code, 302)
        media = MediaFile.objects.get(asset=self.asset)
        self.assertEqual(media.capture_angle, MediaFile.CaptureAngle.FRONT)


class CarePriceRecommendationTest(TestCase):
    def setUp(self):
        ServiceType.objects.all().delete()
        self.basic = ServiceType.objects.create(
            name="Basic Clean Service",
            category=ServiceType.Category.PRIMARY,
            price=90000,
        )
        self.deep = ServiceType.objects.create(
            name="Deep Clean Service",
            category=ServiceType.Category.PRIMARY,
            price=150000,
        )
        self.premium = ServiceType.objects.create(
            name="Premium Spa + Deodorize",
            category=ServiceType.Category.PRIMARY,
            price=220000,
        )
        self.customer = Customer.objects.create(
            name="Care price customer",
            phone="02099990000",
        )
        self.asset = Asset.objects.create(
            customer=self.customer,
            brand="Jordan",
            model_name="Jordan 1 Low",
        )
        self.user = get_user_model().objects.create_user(
            "care-price-staff",
            password="x",
        )
        self.cleanliness = ChecklistItem.objects.create(
            name="ຮອຍເປື້ອນ/ຄວາມສະອາດຂອງໜ້າເກີບ",
            category=ChecklistItem.Category.UPPER,
            max_score=10,
        )

    def _assessment_with_score(self, score, status=Assessment.Status.DONE):
        assessment = Assessment.objects.create(
            asset=self.asset,
            status=status,
            overall_grade="B",
        )
        AssessmentItem.objects.create(
            assessment=assessment,
            checklist_item=self.cleanliness,
            score=score,
        )
        return assessment

    def test_cleanliness_score_selects_configured_price_tier(self):
        cases = (
            (9, "light", self.basic, 90000),
            (6, "moderate", self.deep, 150000),
            (3, "heavy", self.premium, 220000),
        )
        for score, level, service, price in cases:
            with self.subTest(score=score):
                result = build_care_price_recommendation(
                    self._assessment_with_score(score)
                )
                self.assertEqual(result["dirt_level"], level)
                self.assertEqual(result["service"], service)
                self.assertEqual(result["price"], price)

    def test_detail_displays_price_immediately_after_completed_assessment(self):
        self._assessment_with_score(6)
        self.client.force_login(self.user)
        self.client.post(
            reverse("set_language"),
            {
                "language": "en",
                "next": reverse("asset_intake:detail", args=[self.asset.pk]),
            },
        )

        response = self.client.get(
            reverse("asset_intake:detail", args=[self.asset.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["care_price_recommendation"]["service"],
            self.deep,
        )
        self.assertContains(response, "AI cleaning price estimate")
        self.assertContains(response, "Deep Clean Service")
        self.assertContains(response, "150,000")
        self.assertContains(response, "Configured shop price")

    def test_failed_assessment_does_not_show_price_estimate(self):
        failed = self._assessment_with_score(6, status=Assessment.Status.FAILED)
        self.assertIsNone(build_care_price_recommendation(failed))

        self.client.force_login(self.user)
        response = self.client.get(
            reverse("asset_intake:detail", args=[self.asset.pk])
        )
        self.assertIsNone(response.context["care_price_recommendation"])
        self.assertNotContains(response, "AI cleaning price estimate")

    def test_recommendation_uses_latest_shop_price(self):
        self.premium.price = 275000
        self.premium.save(update_fields=["price"])

        result = build_care_price_recommendation(
            self._assessment_with_score(2)
        )

        self.assertEqual(result["service"], self.premium)
        self.assertEqual(result["price"], 275000)
