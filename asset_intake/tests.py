import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from ai_mart_grading.models import Assessment, AssessmentItem, ChecklistItem
from crm.models import Customer
from media_backup.models import MediaFile
from pos.models import ServiceType

from .models import Asset, AssetService
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


class AssetServiceWorkflowTest(TestCase):
    """ຄອບຄຸມ 3 ກໍລະນີຈິງ: ມາຊັກຢ່າງດຽວ / ມາສ້ອມຢ່າງດຽວ / ເຮັດທັງ 2"""

    def setUp(self):
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02033334444")
        self.wash = ServiceType.objects.create(
            name="Deep Clean",
            category=ServiceType.Category.PRIMARY,
            work_type=ServiceType.WorkType.WASH,
            price=150000,
        )
        self.repair = ServiceType.objects.create(
            name="Sole Restoration",
            category=ServiceType.Category.ADD_ON,
            work_type=ServiceType.WorkType.REPAIR,
            price=300000,
        )

    def _asset(self):
        return Asset.objects.create(customer=self.customer, brand="Nike")

    def test_wash_only_pair_never_enters_repair_state(self):
        asset = self._asset()
        service = AssetService.objects.create(asset=asset, service_type=self.wash)

        service.status = AssetService.Status.IN_PROGRESS
        service.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.CLEANING)

        service.status = AssetService.Status.DONE
        service.save()
        asset.refresh_from_db()
        # ຊັກແລ້ວ = ພ້ອມຮັບເລີຍ ບໍ່ຕ້ອງຜ່ານ "ກຳລັງສ້ອມແປງ"
        self.assertEqual(asset.status, Asset.Status.READY)

    def test_repair_only_pair_never_enters_cleaning_state(self):
        asset = self._asset()
        service = AssetService.objects.create(asset=asset, service_type=self.repair)

        service.status = AssetService.Status.IN_PROGRESS
        service.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.REPAIRING)

        service.status = AssetService.Status.DONE
        service.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.READY)

    def test_pair_with_both_services_is_ready_only_after_both_are_done(self):
        asset = self._asset()
        wash = AssetService.objects.create(asset=asset, service_type=self.wash)
        repair = AssetService.objects.create(asset=asset, service_type=self.repair)

        wash.status = AssetService.Status.DONE
        wash.save()
        asset.refresh_from_db()
        # ຊັກແລ້ວ ແຕ່ຍັງເຫຼືອສ້ອມ → ຍັງບໍ່ພ້ອມຮັບ
        self.assertNotEqual(asset.status, Asset.Status.READY)

        repair.status = AssetService.Status.DONE
        repair.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.READY)

    def test_repair_in_progress_wins_over_wash_for_pair_status(self):
        asset = self._asset()
        AssetService.objects.create(
            asset=asset,
            service_type=self.wash,
            status=AssetService.Status.IN_PROGRESS,
        )
        repair = AssetService.objects.create(
            asset=asset,
            service_type=self.repair,
            status=AssetService.Status.IN_PROGRESS,
        )
        repair.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.REPAIRING)

    def test_skipped_service_does_not_block_ready(self):
        asset = self._asset()
        wash = AssetService.objects.create(asset=asset, service_type=self.wash)
        repair = AssetService.objects.create(asset=asset, service_type=self.repair)

        wash.status = AssetService.Status.DONE
        wash.save()
        repair.status = AssetService.Status.SKIPPED
        repair.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.READY)

    def test_delivered_pair_is_not_reopened_by_rollup(self):
        asset = self._asset()
        service = AssetService.objects.create(asset=asset, service_type=self.wash)
        asset.status = Asset.Status.RETURNED
        asset.save()

        service.status = AssetService.Status.IN_PROGRESS
        service.save()
        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.RETURNED)

    def test_timestamps_recorded_per_service(self):
        asset = self._asset()
        service = AssetService.objects.create(asset=asset, service_type=self.wash)
        self.assertIsNone(service.started_at)

        service.status = AssetService.Status.IN_PROGRESS
        service.save()
        self.assertIsNotNone(service.started_at)
        self.assertIsNone(service.finished_at)

        service.status = AssetService.Status.DONE
        service.save()
        self.assertIsNotNone(service.finished_at)

    def test_order_item_creates_matching_asset_service(self):
        from pos.models import Order, OrderItem

        asset = self._asset()
        order = Order.objects.create(customer=self.customer)
        OrderItem.objects.create(
            order=order, service_type=self.repair, asset=asset, unit_price=300000
        )

        service = AssetService.objects.get(asset=asset, service_type=self.repair)
        self.assertEqual(service.work_type, ServiceType.WorkType.REPAIR)
        self.assertEqual(service.name, "Sole Restoration")
        self.assertEqual(service.status, AssetService.Status.PENDING)


class KanbanBoardTest(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("staff", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02055556666")
        self.wash = ServiceType.objects.create(
            name="Deep Clean",
            work_type=ServiceType.WorkType.WASH,
            price=150000,
        )
        self.repair = ServiceType.objects.create(
            name="Sole Restoration",
            work_type=ServiceType.WorkType.REPAIR,
            price=300000,
        )

    def test_board_splits_services_into_work_type_lanes(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(asset=asset, service_type=self.wash)
        AssetService.objects.create(asset=asset, service_type=self.repair)

        response = self.client.get(reverse("asset_intake:kanban"))
        lane_ids = [lane["id"] for lane in response.context["lanes"]]
        self.assertEqual(sorted(lane_ids), ["repair", "wash"])
        # ຄູ່ດຽວ ແຕ່ອອກເປັນ 2 card ຄົນລະແຖວ
        cards = [
            item
            for lane in response.context["lanes"]
            for column in lane["columns"]
            for item in column["items"]
        ]
        self.assertEqual(len(cards), 2)

    def test_work_type_filter_shows_only_that_lane(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(asset=asset, service_type=self.wash)
        AssetService.objects.create(asset=asset, service_type=self.repair)

        response = self.client.get(reverse("asset_intake:kanban"), {"work_type": "wash"})
        lane_ids = [lane["id"] for lane in response.context["lanes"]]
        self.assertEqual(lane_ids, ["wash"])

    def test_drag_updates_service_and_rolls_up_pair_status(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        service = AssetService.objects.create(asset=asset, service_type=self.repair)

        response = self.client.post(
            reverse("asset_intake:kanban_update"),
            data={"service_id": service.pk, "status": "in_progress"},
            content_type="application/json",
        )
        self.assertTrue(response.json()["success"])
        service.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(service.status, AssetService.Status.IN_PROGRESS)
        self.assertEqual(asset.status, Asset.Status.REPAIRING)

    def test_delivered_pairs_are_hidden_from_board(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(asset=asset, service_type=self.wash)
        asset.status = Asset.Status.RETURNED
        asset.save()

        response = self.client.get(reverse("asset_intake:kanban"))
        self.assertEqual(response.context["lanes"], [])


class AssetStatusConsistencyTest(TestCase):
    """ກັນບໍ່ໃຫ້ Asset.status ຫຼົງອອກຈາກສະຖານະວຽກອີກ"""

    def setUp(self):
        self.customer = Customer.objects.create(name="ທົດສອບ", phone="02012345678")
        self.wash = ServiceType.objects.create(
            name="Deep Clean", work_type=ServiceType.WorkType.WASH, price=150000
        )
        self.assess = ServiceType.objects.create(
            name="AI Report", work_type=ServiceType.WorkType.ASSESS, price=0
        )

    def test_resync_fixes_legacy_status_without_matching_work(self):
        """ຄູ່ເກົ່າທີ່ເປັນ 'ກຳລັງຊັກ' ແຕ່ມີແຕ່ວຽກປະເມີນທີ່ຍັງລໍຖ້າ → ຕ້ອງກັບເປັນ 'ຮັບເຂົ້າ'"""
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(asset=asset, service_type=self.assess)
        # ຈຳລອງຂໍ້ມູນເກົ່າ: ຕັ້ງກົງໆ ບໍ່ຜ່ານ rollup
        Asset.objects.filter(pk=asset.pk).update(status=Asset.Status.CLEANING)

        call_command("resync_asset_status", stdout=StringIO())

        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.RECEIVED)

    def test_resync_is_idempotent(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(
            asset=asset,
            service_type=self.wash,
            status=AssetService.Status.IN_PROGRESS,
        )
        call_command("resync_asset_status", stdout=StringIO())
        asset.refresh_from_db()
        first = asset.status

        call_command("resync_asset_status", stdout=StringIO())
        asset.refresh_from_db()
        self.assertEqual(asset.status, first)

    def test_resync_does_not_notify_customer(self):
        """ການແກ້ຂໍ້ມູນຍ້ອນຫຼັງ ບໍ່ຄວນສົ່ງຂໍ້ຄວາມລົບກວນລູກຄ້າ"""
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(asset=asset, service_type=self.assess)
        Asset.objects.filter(pk=asset.pk).update(status=Asset.Status.CLEANING)

        with patch("notifications.services.notify_status_change") as notify:
            call_command("resync_asset_status", stdout=StringIO())

        notify.assert_not_called()

    def test_resync_leaves_delivered_pairs_alone(self):
        asset = Asset.objects.create(customer=self.customer, brand="Nike")
        AssetService.objects.create(asset=asset, service_type=self.wash)
        Asset.objects.filter(pk=asset.pk).update(status=Asset.Status.RETURNED)

        call_command("resync_asset_status", stdout=StringIO())

        asset.refresh_from_db()
        self.assertEqual(asset.status, Asset.Status.RETURNED)


class TicketNumberCollisionTest(TestCase):
    """ເລກໃບຮັບເຄື່ອງຕ້ອງບໍ່ຊ້ຳ ເມື່ອຮັບເກີບຫຼາຍຄູ່ພ້ອມກັນ (POS ຫຼາຍລາຍການ)"""

    def test_bulk_intake_in_same_second_does_not_collide(self):
        customer = Customer.objects.create(name="ທົດສອບ", phone="02099998888")
        assets = [
            Asset.objects.create(customer=customer, brand="Nike") for _ in range(60)
        ]
        numbers = {a.ticket_number for a in assets}
        self.assertEqual(len(numbers), 60)

    def test_ticket_number_fits_the_column(self):
        from .models import generate_ticket_number

        max_length = Asset._meta.get_field("ticket_number").max_length
        self.assertLessEqual(len(generate_ticket_number()), max_length)


class IntakeHandoverGateTest(TestCase):
    """ປຸ່ມ "ສົ່ງມອບແລ້ວ" ໜ້າລາຍລະອຽດ ຕ້ອງຜ່ານ gate ຍອດຄ້າງຄືກັບໜ້າ POS

    ກ່ອນນີ້ມັນຕັ້ງ status=returned ໂດຍກົງ → ເກີບອອກຈາກຮ້ານໄດ້ ທັ້ງທີ່ຍັງບໍ່ໄດ້ຮັບເງິນ
    ແລະ ບໍ່ມີບັນທຶກວ່າໃຜມາຮັບ / ໃຜເປັນຜູ້ມອບ
    """

    def setUp(self):
        from decimal import Decimal

        from pos.models import Order, OrderItem, Payment
        from pos.services import record_payment

        from .models import StorageSlot

        self.Order = Order
        self.Payment = Payment
        self.record_payment = record_payment
        self.Decimal = Decimal

        self.user = get_user_model().objects.create_user("desk", password="pw12345678")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ນາງ ພອນ", phone="02055556666")
        self.slot = StorageSlot.objects.create(zone="A", cabinet=1, position=7)
        self.asset = Asset.objects.create(
            customer=self.customer,
            brand="Nike",
            model_name="Dunk Low",
            status=Asset.Status.READY,
            storage_slot=self.slot,
        )
        self.order = Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=self.order,
            asset=self.asset,
            description="ຊັກເກີບ",
            quantity=1,
            unit_price=Decimal("150000.00"),
        )

    def _press_delivered(self, received_to="ນາງ ພອນ"):
        return self.client.post(
            reverse("asset_intake:detail", args=[self.asset.pk]),
            {"status": "returned", "received_to": received_to},
            follow=True,
        )

    def test_unpaid_pair_cannot_be_marked_delivered(self):
        response = self._press_delivered()
        self.asset.refresh_from_db()

        self.assertEqual(self.asset.status, Asset.Status.READY)
        self.assertIsNotNone(self.asset.storage_slot)
        text = " ".join(str(m) for m in response.context["messages"])
        self.assertIn(self.order.order_number, text)

    def test_paid_pair_is_delivered_and_records_custody(self):
        self.record_payment(
            order=self.order,
            amount=self.Decimal("150000"),
            method=self.Payment.Method.CASH,
            user=self.user,
        )

        self._press_delivered()
        self.asset.refresh_from_db()

        self.assertEqual(self.asset.status, Asset.Status.RETURNED)
        self.assertEqual(self.asset.returned_to, "ນາງ ພອນ")
        self.assertEqual(self.asset.returned_by, self.user)
        self.assertIsNotNone(self.asset.completed_at)
        self.assertIsNone(self.asset.storage_slot)

    def test_every_bill_holding_the_pair_must_be_settled(self):
        """ຄູ່ດຽວອາດຢູ່ 2 ບິນ (ຊັກບິນນຶ່ງ ມາສ້ອມເພີ່ມອີກບິນ) — ຕ້ອງຄົບທັງສອງ"""
        from pos.models import OrderItem

        self.record_payment(
            order=self.order,
            amount=self.Decimal("150000"),
            method=self.Payment.Method.CASH,
            user=self.user,
        )
        second = self.Order.objects.create(customer=self.customer, vat_rate=0)
        OrderItem.objects.create(
            order=second,
            asset=self.asset,
            description="ສ້ອມພື້ນ",
            quantity=1,
            unit_price=self.Decimal("80000.00"),
        )

        self._press_delivered()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.READY)

        self.record_payment(
            order=second,
            amount=self.Decimal("80000"),
            method=self.Payment.Method.CASH,
            user=self.user,
        )
        self._press_delivered()
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.RETURNED)

    def test_pair_without_any_bill_can_still_be_delivered(self):
        """ຮັບເຂົ້າຜ່ານໜ້າ intake ໂດຍກົງ ຍັງບໍ່ມີບິນ — ບໍ່ຄວນລັອກໄວ້"""
        loose = Asset.objects.create(
            customer=self.customer, brand="Vans", status=Asset.Status.READY
        )

        self.client.post(
            reverse("asset_intake:detail", args=[loose.pk]),
            {"status": "returned", "received_to": "ນາງ ພອນ"},
            follow=True,
        )
        loose.refresh_from_db()

        self.assertEqual(loose.status, Asset.Status.RETURNED)
        self.assertEqual(loose.returned_by, self.user)

    def test_other_statuses_still_update_normally(self):
        self.client.post(
            reverse("asset_intake:detail", args=[self.asset.pk]),
            {"status": "cleaning"},
        )
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.status, Asset.Status.CLEANING)


class IntakeDetailTemplateTest(TestCase):
    """{# ... #} ຮອງຮັບແຖວດຽວ — ຂຽນຫຼາຍແຖວມັນຈະ render ອອກໜ້າຈໍໃຫ້ລູກຄ້າເຫັນ"""

    def setUp(self):
        self.user = get_user_model().objects.create_user("desk", password="pw12345678")
        self.client.force_login(self.user)
        self.asset = Asset.objects.create(
            customer=Customer.objects.create(name="ທ້າວ ບຸນ", phone="02055557777"),
            brand="Nike",
        )

    def test_developer_comments_do_not_leak_onto_the_page(self):
        response = self.client.get(reverse("asset_intake:detail", args=[self.asset.pk]))
        body = response.content.decode()
        self.assertNotIn("responsive", body)
        self.assertNotIn("{#", body)
