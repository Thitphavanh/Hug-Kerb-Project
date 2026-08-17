"""ເທັສການກວດໄຟລ໌ຫຼັກຖານກ່ອນເກັບ (Scope 2.3)

ເທັສພວກນີ້ຂຽນໄຟລ໌ຈິງລົງ disk ຈຶ່ງຕ້ອງຊີ້ MEDIA_ROOT ໄປໂຟນເດີຊົ່ວຄາວ
ບໍ່ດັ່ງນັ້ນຮູບຂີ້ເຫຍື້ອຈາກເທັສຈະໄປປົນກັບຫຼັກຖານຈິງຂອງຮ້ານ.
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from asset_intake.models import Asset
from crm.models import Customer

from .models import MediaFile
from .services import store_uploads
from .validators import UploadRejected, classify_upload, validate_receipt

ONE_MB = 1024 * 1024


def fake_upload(name, content_type, megabytes=0.01):
    return SimpleUploadedFile(name, b"x" * int(ONE_MB * megabytes), content_type)


class UploadValidationTest(TestCase):
    def test_a_normal_photo_is_accepted(self):
        photo = fake_upload("front.jpg", "image/jpeg")
        self.assertEqual(classify_upload(photo), MediaFile.MediaType.IMAGE)

    def test_a_normal_video_is_accepted(self):
        clip = fake_upload("defect.mp4", "video/mp4", megabytes=2)
        self.assertEqual(classify_upload(clip), MediaFile.MediaType.VIDEO)

    def test_an_oversized_video_is_refused_with_the_limit_in_the_message(self):
        """ຫົວໃຈຂອງຟີເຈີ — ຄລິບຍາວຄລິບດຽວຕ້ອງບໍ່ເຮັດໃຫ້ດິສເຕັມ"""
        with override_settings(MAX_UPLOAD_VIDEO_MB=5):
            clip = fake_upload("long.mp4", "video/mp4", megabytes=6)
            with self.assertRaises(UploadRejected) as caught:
                classify_upload(clip)

        self.assertIn("5", caught.exception.message)

    def test_an_oversized_photo_is_refused(self):
        with override_settings(MAX_UPLOAD_IMAGE_MB=2):
            photo = fake_upload("huge.png", "image/png", megabytes=3)
            with self.assertRaises(UploadRejected):
                classify_upload(photo)

    def test_an_executable_disguised_by_extension_is_refused(self):
        payload = fake_upload("invoice.pdf", "application/pdf")
        with self.assertRaises(UploadRejected):
            classify_upload(payload)

    def test_contents_that_contradict_the_extension_are_refused(self):
        """ປ່ຽນນາມສະກຸນເປັນ .jpg ແຕ່ຂ້າງໃນບໍ່ແມ່ນຮູບ"""
        disguised = fake_upload("payload.jpg", "application/zip")
        with self.assertRaises(UploadRejected):
            classify_upload(disguised)


class TempMediaTestCase(TestCase):
    """ຂຽນໄຟລ໌ລົງໂຟນເດີຊົ່ວຄາວ ແລ້ວລຶບຖິ້ມຫຼັງເທັສຈົບ"""

    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.mkdtemp(prefix="hugkerb-test-media-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_dir, ignore_errors=True)


class ReceiptAttachmentValidationTest(TestCase):
    """ໄຟລ໌ແນບໃນລາຍການບັນຊີ — ອີກທາງໜຶ່ງທີ່ໄຟລ໌ເຂົ້າ disk ໄດ້"""

    def test_a_receipt_photo_is_accepted(self):
        self.assertIsNotNone(validate_receipt(fake_upload("bill.jpg", "image/jpeg")))

    def test_a_pdf_receipt_is_accepted(self):
        self.assertIsNotNone(validate_receipt(fake_upload("bill.pdf", "application/pdf")))

    def test_a_video_is_refused_as_a_receipt(self):
        with self.assertRaises(UploadRejected):
            validate_receipt(fake_upload("clip.mp4", "video/mp4"))

    def test_an_oversized_receipt_is_refused(self):
        with override_settings(MAX_UPLOAD_IMAGE_MB=2):
            with self.assertRaises(UploadRejected):
                validate_receipt(fake_upload("huge.jpg", "image/jpeg", megabytes=3))

    def test_the_accounting_form_rejects_an_oversized_attachment(self):
        """ກວດຜ່ານຟອມຈິງ — attrs accept ໃນ browser ຂ້າມໄດ້ ຈຶ່ງຕ້ອງກັນຝັ່ງເຊີບເວີ"""
        from accounting.forms import CashBookForm

        with override_settings(MAX_UPLOAD_IMAGE_MB=1):
            form = CashBookForm(
                data={},
                files={"attachment": fake_upload("huge.jpg", "image/jpeg", megabytes=2)},
            )
            form.is_valid()

        self.assertIn("attachment", form.errors)


class StoreUploadsTest(TempMediaTestCase):
    def setUp(self):
        self.customer = Customer.objects.create(name="ນາງ ພອນ", phone="02055551111")
        self.asset = Asset.objects.create(customer=self.customer, brand="Nike")

    def test_a_bad_file_is_skipped_but_the_good_ones_still_save(self):
        """ພະນັກງານເລືອກຮູບເທື່ອລະຫຼາຍໃບ ບໍ່ຄວນເສຍທັງຊຸດຍ້ອນໃບດຽວ"""
        with override_settings(MAX_UPLOAD_IMAGE_MB=2):
            saved, errors = store_uploads(
                asset=self.asset,
                files=[
                    fake_upload("good-1.jpg", "image/jpeg"),
                    fake_upload("too-big.jpg", "image/jpeg", megabytes=3),
                    fake_upload("good-2.jpg", "image/jpeg"),
                ],
            )

        self.assertEqual(len(saved), 2)
        self.assertEqual(len(errors), 1)
        self.assertIn("too-big.jpg", errors[0])
        self.assertEqual(MediaFile.objects.filter(asset=self.asset).count(), 2)

    def test_video_files_are_stored_as_video_not_image(self):
        saved, _errors = store_uploads(
            asset=self.asset, files=[fake_upload("clip.mov", "video/quicktime")]
        )

        self.assertEqual(saved[0].media_type, MediaFile.MediaType.VIDEO)

    def test_selecting_too_many_files_stores_only_the_allowed_number(self):
        with override_settings(MAX_UPLOAD_FILES_PER_REQUEST=3):
            saved, errors = store_uploads(
                asset=self.asset,
                files=[fake_upload(f"p{i}.jpg", "image/jpeg") for i in range(6)],
            )

        self.assertEqual(len(saved), 3)
        self.assertEqual(len(errors), 1)


class IntakeUploadViewTest(TempMediaTestCase):
    """ກວດວ່າໜ້າຈິງເອີ້ນຜ່ານຕົວກວດ ບໍ່ມີທາງລັດຂ້າມ"""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="intake-upload", password="test-pass-123"
        )
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(name="ນາງ ດາວ", phone="02055552222")
        self.asset = Asset.objects.create(customer=self.customer, brand="Adidas")

    @override_settings(MAX_UPLOAD_VIDEO_MB=1)
    def test_uploading_an_oversized_video_saves_nothing_and_explains_why(self):
        response = self.client.post(
            reverse("asset_intake:detail", args=[self.asset.pk]),
            {
                "upload_stage": MediaFile.Stage.BEFORE,
                "photos": fake_upload("long.mp4", "video/mp4", megabytes=2),
            },
            follow=True,
        )

        self.assertEqual(MediaFile.objects.filter(asset=self.asset).count(), 0)
        shown = [str(m) for m in response.context["messages"]]
        self.assertTrue(
            any("long.mp4" in text for text in shown),
            f"ຄວນບອກຊື່ໄຟລ໌ທີ່ຕົກ ແຕ່ໄດ້: {shown}",
        )
