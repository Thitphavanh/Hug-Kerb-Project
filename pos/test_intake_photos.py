"""ເທັສການແນບຮູບ "ກ່ອນເຮັດ" ຕອນເປີດບິນຢູ່ໜ້າ POS (Scope 2.3)

ຄູ່ເກີບຍັງບໍ່ທັນມີຕອນພະນັກງານເລືອກຮູບ — ໄຟລ໌ຈຶ່ງໄປພ້ອມກັບຟອມ
ແລ້ວເຊີບເວີຄ່ອຍຜູກໃສ່ຄູ່ທີ່ຫາກໍສ້າງ. ນີ້ຄືຈຸດທີ່ພັງງ່າຍສຸດ.
"""

import io
import shutil
import tempfile
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from asset_intake.models import Asset, Brand
from media_backup.models import MediaFile

from .models import ServiceType


def photo(name="before.jpg", color="gray"):
    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(buf, "JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), "image/jpeg")


class PosIntakePhotoTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media = tempfile.mkdtemp(prefix="hugkerb-pos-photo-")
        cls._override = override_settings(MEDIA_ROOT=cls._media)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="pos-photo", password="test-pass-123"
        )
        self.client.force_login(self.user)
        Brand.objects.get_or_create(name="Nike", defaults={"sort_order": 0})
        self.service = ServiceType.objects.create(
            name="Basic Clean", price=Decimal("90000.00"), is_active=True
        )

    def _post(self, **extra):
        data = {
            "customer_name": "ນາງ ມະນີ",
            "customer_phone": "02055551212",
            "item_indices": "0",
            "brand_0": "Nike",
            "model_name_0": "Air Force 1",
            "color_0": "Black",
            "size_0": "43",
            "service_0": str(self.service.pk),
        }
        data.update(extra)
        return self.client.post(reverse("pos:create"), data)

    def test_the_form_accepts_photos_and_attaches_them_to_the_new_pair(self):
        """ຮູບແບບຫຼັກ — ຖ່າຍຮູບຕອນເປີດບິນ ແລ້ວຕິດຢູ່ກັບຄູ່ເກີບເລີຍ"""
        self._post(photos_0=photo())

        asset = Asset.objects.get(model_name="Air Force 1")
        self.assertEqual(asset.media_files.count(), 1)

    def test_photos_are_filed_as_before_service_evidence(self):
        self._post(photos_0=photo())

        media = MediaFile.objects.get(asset__model_name="Air Force 1")
        self.assertEqual(media.stage, MediaFile.Stage.BEFORE)
        self.assertEqual(media.media_type, MediaFile.MediaType.IMAGE)

    def test_opening_a_bill_without_photos_still_works(self):
        """ຮ້ານຮີບ ບໍ່ທັນຖ່າຍຮູບ — ຕ້ອງເປີດບິນໄດ້ຢູ່ ບໍ່ແມ່ນບລັອກໄວ້"""
        response = self._post()

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Asset.objects.filter(model_name="Air Force 1").exists())

    def test_each_pair_keeps_its_own_photos(self):
        """ສອງຄູ່ໃນບິນດຽວ ຮູບຕ້ອງບໍ່ໄປປົນກັນ — ບໍ່ດັ່ງນັ້ນຫຼັກຖານໃຊ້ບໍ່ໄດ້"""
        self._post(
            item_indices="0,1",
            brand_1="Nike",
            model_name_1="Dunk Low",
            color_1="White",
            size_1="42",
            service_1=str(self.service.pk),
            photos_0=photo("a.jpg", "gray"),
            photos_1=photo("b.jpg", "white"),
        )

        first = Asset.objects.get(model_name="Air Force 1")
        second = Asset.objects.get(model_name="Dunk Low")
        self.assertEqual(first.media_files.count(), 1)
        self.assertEqual(second.media_files.count(), 1)

    @override_settings(MAX_UPLOAD_IMAGE_MB=1)
    def test_an_oversized_photo_is_refused_but_the_bill_is_still_opened(self):
        """ຮູບໃຫຍ່ເກີນຕ້ອງບໍ່ເຮັດໃຫ້ເສຍບິນທັງໃບ — ບອກແລ້ວໃຫ້ອັບໃໝ່ພາຍຫຼັງ"""
        big = SimpleUploadedFile("huge.jpg", b"\xff\xd8\xff" + b"x" * (2 * 1024 * 1024), "image/jpeg")

        response = self._post(photos_0=big)

        asset = Asset.objects.get(model_name="Air Force 1")
        self.assertEqual(asset.media_files.count(), 0)
        self.assertEqual(response.status_code, 302)

    def test_the_page_offers_a_photo_field_for_the_first_item(self):
        html = self.client.get(reverse("pos:create")).content.decode()

        self.assertIn('enctype="multipart/form-data"', html)
        self.assertIn('name="photos_0"', html)


class PhotoAngleSlotTest(PosIntakePhotoTest):
    """ຮູບຕ້ອງລົງຖືກມຸມ — ບໍ່ດັ່ງນັ້ນ AI ປະເມີນຜິດ ແລະ ຫຼັກຖານໃຊ້ອ້າງບໍ່ໄດ້"""

    def test_each_photo_is_filed_under_the_angle_it_was_taken_for(self):
        self._post(
            photos_0_front=photo("f.jpg"),
            photos_0_outsole=photo("o.jpg"),
            photos_0_laces=photo("l.jpg"),
        )

        asset = Asset.objects.get(model_name="Air Force 1")
        angles = dict(asset.media_files.values_list("capture_angle", "file"))
        self.assertEqual(
            set(angles),
            {
                MediaFile.CaptureAngle.FRONT,
                MediaFile.CaptureAngle.OUTSOLE,
                MediaFile.CaptureAngle.LACES,
            },
        )

    def test_every_slot_the_page_offers_is_accepted_by_the_server(self):
        """ກັນຊ່ອງໃນໜ້າຈໍກັບຊ່ອງທີ່ເຊີບເວີຮັບ ຫຼົງກັນ"""
        from media_backup.services import INTAKE_PHOTO_SLOTS

        extra = {
            f"photos_0_{angle}": photo(f"{angle}.jpg")
            for angle, _label in INTAKE_PHOTO_SLOTS
        }
        self._post(**extra)

        asset = Asset.objects.get(model_name="Air Force 1")
        self.assertEqual(asset.media_files.count(), len(INTAKE_PHOTO_SLOTS))
        stored = set(asset.media_files.values_list("capture_angle", flat=True))
        self.assertEqual(stored, {angle for angle, _ in INTAKE_PHOTO_SLOTS})

    def test_unlabelled_extra_photos_are_still_kept(self):
        self._post(photos_0=[photo("x1.jpg"), photo("x2.jpg")])

        asset = Asset.objects.get(model_name="Air Force 1")
        self.assertEqual(asset.media_files.count(), 2)
        self.assertEqual(
            set(asset.media_files.values_list("capture_angle", flat=True)), {""}
        )

    def test_angle_photos_and_extra_photos_can_be_sent_together(self):
        self._post(photos_0_front=photo("f.jpg"), photos_0=photo("x.jpg"))

        asset = Asset.objects.get(model_name="Air Force 1")
        self.assertEqual(asset.media_files.count(), 2)

    def test_the_page_shows_a_named_box_for_every_slot(self):
        from media_backup.services import INTAKE_PHOTO_SLOTS

        html = self.client.get(reverse("pos:create")).content.decode()

        for angle, _label in INTAKE_PHOTO_SLOTS:
            self.assertIn(f'name="photos_0_{angle}"', html)


class PhotoSlotLanguageTest(PosIntakePhotoTest):
    """ປ້າຍຊື່ຊ່ອງເປັນຄ່າຄົງທີ່ລະດັບ module — ຖ້າໃຊ້ gettext ທຳມະດາ ມັນຈະຖືກແປ
    ຕອນ import ແລ້ວຄ້າງເປັນພາສານັ້ນຕະຫຼອດ. ເທັສນີ້ກັນບັກນັ້ນກັບມາ."""

    def _labels_in(self, language):
        import re

        self.client.post(
            reverse("set_language"),
            {"language": language, "next": reverse("pos:create")},
        )
        html = self.client.get(reverse("pos:create")).content.decode()
        return re.findall(r'<span class="name">([^<]+)</span>', html)

    def test_slot_labels_are_lao_in_lao(self):
        labels = self._labels_in("lo")

        self.assertIn("ຮູບດ້ານໜ້າ", labels)
        self.assertIn("ຮູບພື້ນເຫຼືອງ (Oxidation)", labels)

    def test_slot_labels_are_english_in_english(self):
        labels = self._labels_in("en")

        self.assertIn("Front", labels)
        self.assertIn("Sole yellowing", labels)

    def test_switching_language_actually_changes_the_labels(self):
        lao = self._labels_in("lo")
        english = self._labels_in("en")

        self.assertNotEqual(lao[:9], english[:9])
