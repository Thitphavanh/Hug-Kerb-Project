"""ເທັສການສ້າງຮູບ Before/After ສຳລັບໂພສ (Scope 2.3)

ຈຸດສຳຄັນ: ຮູບທີ່ອັບຄ້າງ (ເນັດຫຼຸດກາງທາງ) ຜ່ານການກວດຕອນອັບໂຫຼດໄດ້ ເພາະຫົວໄຟລ໌
ຍັງດີ ແຕ່ເປີດບໍ່ໄດ້ຕອນມາປະກອບ — ຕ້ອງບອກພະນັກງານ ບໍ່ແມ່ນຂຶ້ນໜ້າ 500.
"""

import io
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from crm.models import Customer
from media_backup.models import MediaFile

from .models import Asset


def png_bytes(color="navy", size=(600, 600)):
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class SocialImageTest(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.mkdtemp(prefix="hugkerb-social-test-")
        cls._override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="social-test", password="test-pass-123"
        )
        self.client.force_login(self.user)
        customer = Customer.objects.create(name="ນາງ ມະນີ", phone="02055554444")
        self.asset = Asset.objects.create(customer=customer, brand="Nike")

    def _add_photo(self, stage, data):
        return MediaFile.objects.create(
            asset=self.asset,
            file=SimpleUploadedFile(f"{stage}.png", data, "image/png"),
            stage=stage,
            media_type=MediaFile.MediaType.IMAGE,
        )

    def _url(self):
        return reverse("asset_intake:social_image", args=[self.asset.pk])

    def test_it_builds_the_image_when_both_photos_are_good(self):
        self._add_photo(MediaFile.Stage.BEFORE, png_bytes("gray"))
        self._add_photo(MediaFile.Stage.AFTER, png_bytes("white"))

        response = self.client.get(self._url())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_it_asks_for_photos_when_one_stage_is_missing(self):
        self._add_photo(MediaFile.Stage.BEFORE, png_bytes())

        response = self.client.get(self._url(), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTrue([str(m) for m in response.context["messages"]])

    def test_a_truncated_upload_reports_the_problem_instead_of_a_server_error(self):
        """ຫົວໃຈ — ເນັດຫຼຸດຕອນອັບຮູບ ບໍ່ຄວນເຮັດໃຫ້ໜ້າພັງ 500

        ຕ້ອງບັງຄັບ LOAD_TRUNCATED_IMAGES=False ເອງ ເພາະ weasyprint ຕັ້ງເປັນ True
        ໃຫ້ທັງໂປຣເຊັສຕອນຖືກ import — ຜົນຄືໜ້ານີ້ຈະ 500 ຫຼື ບໍ່ ຂຶ້ນກັບວ່າ
        ມີໃຜສ້າງ PDF ໃນ worker ນັ້ນກ່ອນແລ້ວບໍ່. ເທັສຈຶ່ງຕ້ອງລັອກຄ່ານີ້ໄວ້.
        """
        from PIL import ImageFile

        good = png_bytes("white")
        self._add_photo(MediaFile.Stage.BEFORE, good[: len(good) // 2])
        self._add_photo(MediaFile.Stage.AFTER, good)

        previous = ImageFile.LOAD_TRUNCATED_IMAGES
        ImageFile.LOAD_TRUNCATED_IMAGES = False
        try:
            response = self.client.get(self._url(), follow=True)
        finally:
            ImageFile.LOAD_TRUNCATED_IMAGES = previous

        # ບໍ່ຜູກກັບຄຳໃດຄຳໜຶ່ງ — ຂໍ້ຄວາມນີ້ຖືກແປ ຈຶ່ງປ່ຽນຕາມພາສາຂອງຜູ້ໃຊ້
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response["Content-Type"], "image/png")
        shown = [str(m) for m in response.context["messages"]]
        self.assertTrue(shown, "ຄວນມີຂໍ້ຄວາມບອກພະນັກງານ ບໍ່ແມ່ນປ່ອຍໃຫ້ໜ້າພັງ")
