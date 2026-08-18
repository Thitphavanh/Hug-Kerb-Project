"""ເທັສການກວດໄຟລ໌ຫຼັກຖານກ່ອນເກັບ (Scope 2.3)

ເທັສພວກນີ້ຂຽນໄຟລ໌ຈິງລົງ disk ຈຶ່ງຕ້ອງຊີ້ MEDIA_ROOT ໄປໂຟນເດີຊົ່ວຄາວ
ບໍ່ດັ່ງນັ້ນຮູບຂີ້ເຫຍື້ອຈາກເທັສຈະໄປປົນກັບຫຼັກຖານຈິງຂອງຮ້ານ.
"""

import hashlib
import shutil
import tempfile
from io import StringIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from asset_intake.models import Asset
from crm.models import Customer

from .backends import BackupError, LocalDirectoryBackend, get_backup_backend
from .models import BackupRun, MediaFile
from .services import pending_backup_queryset, run_backup, store_uploads
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


class ChecksumAndProvenanceTest(TempMediaTestCase):
    """ຫຼັກຖານຕ້ອງສືບກັບໄປຫາຄົນອັບໂຫຼດໄດ້ ແລະ ພິສູດໄດ້ວ່າບໍ່ຖືກແກ້"""

    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="evidence-staff", password="test-pass-123"
        )
        self.customer = Customer.objects.create(name="ນາງ ຈັນ", phone="02055554444")
        self.asset = Asset.objects.create(customer=self.customer, brand="Nike")

    def test_upload_records_who_uploaded_it_with_a_checksum_and_size(self):
        saved, _errors = store_uploads(
            asset=self.asset,
            files=[fake_upload("front.jpg", "image/jpeg")],
            uploaded_by=self.staff,
        )

        media = saved[0]
        self.assertEqual(media.uploaded_by, self.staff)
        self.assertEqual(len(media.checksum), 64)
        self.assertGreater(media.size_bytes, 0)
        self.assertFalse(media.is_backed_up)

    def test_the_checksum_matches_the_bytes_that_landed_on_disk(self):
        """ຄິດ checksum ແລ້ວຕ້ອງ seek ກັບ ບໍ່ດັ່ງນັ້ນໄຟລ໌ທີ່ບັນທຶກຈະຫວ່າງ"""
        payload = b"x" * 4096
        upload = SimpleUploadedFile("proof.jpg", payload, "image/jpeg")

        saved, _errors = store_uploads(asset=self.asset, files=[upload])

        media = saved[0]
        self.assertEqual(media.file.size, len(payload))
        self.assertEqual(media.checksum, hashlib.sha256(payload).hexdigest())


class BackupBackendResolutionTest(SimpleTestCase):
    def test_backup_is_off_by_default(self):
        with override_settings(MEDIA_BACKUP_BACKEND="none"):
            self.assertIsNone(get_backup_backend())

    def test_local_backend_without_a_directory_is_a_clear_error(self):
        with override_settings(MEDIA_BACKUP_BACKEND="local", MEDIA_BACKUP_DIR=""):
            with self.assertRaises(BackupError) as caught:
                get_backup_backend()

        self.assertIn("MEDIA_BACKUP_DIR", caught.exception.message)

    def test_an_unknown_backend_name_is_refused(self):
        with override_settings(MEDIA_BACKUP_BACKEND="dropbox"):
            with self.assertRaises(BackupError):
                get_backup_backend()


class RunBackupTest(TempMediaTestCase):
    """ຫົວໃຈຂອງ Scope 2.3 — ຫຼັກຖານຕ້ອງມີສຳເນົາທີ່ສອງ"""

    def setUp(self):
        self.backup_dir = tempfile.mkdtemp(prefix="hugkerb-test-backup-")
        self.addCleanup(shutil.rmtree, self.backup_dir, ignore_errors=True)
        self.customer = Customer.objects.create(name="ນາງ ນ້ອຍ", phone="02055556666")
        self.asset = Asset.objects.create(customer=self.customer, brand="Adidas")

    def _backend(self):
        return LocalDirectoryBackend(self.backup_dir)

    def _upload(self, name="front.jpg"):
        saved, _errors = store_uploads(
            asset=self.asset, files=[fake_upload(name, "image/jpeg")]
        )
        return saved[0]

    def test_an_unbacked_file_is_copied_and_marked(self):
        media = self._upload()

        run = run_backup(backend=self._backend())

        media.refresh_from_db()
        self.assertEqual(run.status, BackupRun.Status.SUCCESS)
        self.assertEqual(run.files_copied, 1)
        self.assertTrue(media.is_backed_up)
        self.assertTrue(Path(media.backup_ref).exists())
        self.assertEqual(
            Path(media.backup_ref).read_bytes(), media.file.read()
        )

    def test_running_twice_does_not_copy_the_same_file_again(self):
        """ຕັ້ງເປັນ cron ລາຍວັນໄດ້ ໂດຍບໍ່ຕ້ອງກັງວົນເລື່ອງຮອບທັບກັນ"""
        self._upload()

        run_backup(backend=self._backend())
        second = run_backup(backend=self._backend())

        self.assertEqual(second.files_copied, 0)
        self.assertEqual(second.status, BackupRun.Status.SUCCESS)

    def test_a_new_upload_after_a_backup_is_picked_up_by_the_next_run(self):
        self._upload("front.jpg")
        run_backup(backend=self._backend())

        self._upload("heel.jpg")
        second = run_backup(backend=self._backend())

        self.assertEqual(second.files_copied, 1)
        self.assertEqual(MediaFile.objects.filter(backed_up_at__isnull=True).count(), 0)

    def test_one_missing_file_does_not_stop_the_rest_from_being_backed_up(self):
        """ໄຟລ໌ຫາຍໜຶ່ງອັນຕ້ອງບໍ່ກັນບໍ່ໃຫ້ຫຼັກຖານທີ່ເຫຼືອຖືກສຳຮອງ"""
        broken = self._upload("missing.jpg")
        good = self._upload("good.jpg")
        Path(broken.file.path).unlink()

        run = run_backup(backend=self._backend())

        broken.refresh_from_db()
        good.refresh_from_db()
        self.assertEqual(run.status, BackupRun.Status.PARTIAL)
        self.assertEqual(run.files_copied, 1)
        self.assertEqual(run.files_failed, 1)
        self.assertIn("missing.jpg", run.detail)
        self.assertTrue(good.is_backed_up)
        self.assertFalse(broken.is_backed_up)

    def test_backup_without_a_configured_destination_is_refused(self):
        self._upload()

        with override_settings(MEDIA_BACKUP_BACKEND="none"):
            with self.assertRaises(BackupError):
                run_backup()

    def test_the_limit_leaves_the_remaining_files_for_the_next_run(self):
        """ສຳຮອງຄັ້ງທຳອິດທີ່ມີໄຟລ໌ຫຼາຍ — ແບ່ງແລ່ນເປັນຮອບໆໄດ້"""
        for name in ("a.jpg", "b.jpg", "c.jpg"):
            self._upload(name)

        run = run_backup(limit=2, backend=self._backend())

        self.assertEqual(run.files_copied, 2)
        self.assertEqual(pending_backup_queryset().count(), 1)


class BackupCommandTest(TempMediaTestCase):
    def setUp(self):
        self.backup_dir = tempfile.mkdtemp(prefix="hugkerb-test-cmd-")
        self.addCleanup(shutil.rmtree, self.backup_dir, ignore_errors=True)
        customer = Customer.objects.create(name="ນາງ ດາລາ", phone="02055557777")
        self.asset = Asset.objects.create(customer=customer, brand="Puma")

    def test_the_command_reports_the_pending_count_without_copying(self):
        store_uploads(asset=self.asset, files=[fake_upload("front.jpg", "image/jpeg")])
        output = StringIO()

        with override_settings(MEDIA_BACKUP_BACKEND="none"):
            call_command("backup_media", "--status", stdout=output)

        self.assertIn("1", output.getvalue())
        self.assertFalse(BackupRun.objects.exists())

    def test_the_command_refuses_to_run_when_no_destination_is_configured(self):
        store_uploads(asset=self.asset, files=[fake_upload("front.jpg", "image/jpeg")])

        with override_settings(MEDIA_BACKUP_BACKEND="none"):
            with self.assertRaises(CommandError):
                call_command("backup_media", stdout=StringIO())

    def test_the_command_copies_pending_files(self):
        store_uploads(asset=self.asset, files=[fake_upload("front.jpg", "image/jpeg")])
        output = StringIO()

        with override_settings(
            MEDIA_BACKUP_BACKEND="local", MEDIA_BACKUP_DIR=self.backup_dir
        ):
            call_command("backup_media", stdout=output)

        run = BackupRun.objects.get()
        self.assertEqual(run.status, BackupRun.Status.SUCCESS)
        self.assertEqual(run.files_copied, 1)
        self.assertEqual(pending_backup_queryset().count(), 0)


class DashboardBackupAlertTest(TempMediaTestCase):
    """ການສຳຮອງທີ່ລົ້ມແບບງຽບໆເປັນອັນຕະລາຍທີ່ສຸດ — ຕ້ອງໂຜ່ຢູ່ໜ້າທຳອິດ"""

    def setUp(self):
        user = get_user_model().objects.create_user(
            username="dashboard-staff", password="test-pass-123"
        )
        self.client.force_login(user)
        customer = Customer.objects.create(name="ນາງ ສີ", phone="02055559999")
        self.asset = Asset.objects.create(customer=customer, brand="Nike")
        self.url = reverse("dashboard:index")

    def test_no_alert_when_backup_is_switched_off(self):
        with override_settings(MEDIA_BACKUP_BACKEND="none"):
            response = self.client.get(self.url)

        self.assertIsNone(response.context["backup_alert"])

    def test_configured_but_never_run_raises_an_alert(self):
        with override_settings(
            MEDIA_BACKUP_BACKEND="local", MEDIA_BACKUP_DIR="/tmp/hugkerb-backup"
        ):
            response = self.client.get(self.url)

        self.assertIsNotNone(response.context["backup_alert"])

    def test_a_failed_run_raises_an_alert(self):
        BackupRun.objects.create(
            destination="local:/mnt/backup", status=BackupRun.Status.FAILED
        )

        with override_settings(
            MEDIA_BACKUP_BACKEND="local", MEDIA_BACKUP_DIR="/tmp/hugkerb-backup"
        ):
            response = self.client.get(self.url)

        self.assertIsNotNone(response.context["backup_alert"])

    def test_a_clean_run_raises_no_alert(self):
        BackupRun.objects.create(
            destination="local:/mnt/backup", status=BackupRun.Status.SUCCESS
        )

        with override_settings(
            MEDIA_BACKUP_BACKEND="local", MEDIA_BACKUP_DIR="/tmp/hugkerb-backup"
        ):
            response = self.client.get(self.url)

        self.assertIsNone(response.context["backup_alert"])
