"""ປາຍທາງສຳຮອງໄຟລ໌ຫຼັກຖານ (Scope 2.3 — Cloud Storage ຕາມສັນຍາຂໍ້ 3)

ຫຼັກຖານຮູບກ່ອນ-ຫຼັງບໍລິການເປັນສິ່ງດຽວທີ່ຮ້ານໃຊ້ຢືນຢັນກັບລູກຄ້າເມື່ອມີຂໍ້ຂັດແຍ່ງ.
ຖ້າມີສຳເນົາດຽວຢູ່ disk ເຄື່ອງ ແລ້ວ disk ເສຍ = ຫຼັກຖານຫາຍໝົດ ກູ້ບໍ່ໄດ້.

ອອກແບບເປັນ 2 ປາຍທາງ ເພື່ອບໍ່ໃຫ້ການສຳຮອງຕິດຄ້າງລໍການຕັດສິນໃຈເລື່ອງ cloud:

  local  — ສຳເນົາໄປໂຟນເດີອື່ນ (external drive ຫຼື network share ທີ່ mount ໄວ້)
           ໃຊ້ໄດ້ທັນທີ ບໍ່ຕ້ອງມີບັນຊີ ບໍ່ມີຄ່າໃຊ້ຈ່າຍລາຍເດືອນ
  s3     — S3 / Cloudflare R2 / Backblaze B2 ເມື່ອຮ້ານພ້ອມຈ່າຍ ~250 ບາດ/ເດືອນ

ສອງອັນນີ້ໃຊ້ໜ້າຕາດຽວກັນ ຈຶ່ງຍ້າຍໄປມາໄດ້ໂດຍປ່ຽນແຕ່ .env ບໍ່ຕ້ອງແກ້ໂຄ້ດ.
"""

import shutil
from pathlib import Path

from django.conf import settings


class BackupError(Exception):
    """ສຳຮອງບໍ່ສຳເລັດ — .message ເອົາໄປສະແດງ/ບັນທຶກໄດ້ເລີຍ"""

    def __init__(self, message):
        super().__init__(message)
        self.message = message


class BaseBackupBackend:
    name = "base"

    def describe(self):
        raise NotImplementedError

    def store(self, *, key, fileobj):
        """ຂຽນ fileobj ໄປປາຍທາງພາຍໃຕ້ key ແລ້ວຄືນ reference ທີ່ຊີ້ກັບໄປຫາໄດ້"""
        raise NotImplementedError

    def exists(self, ref):
        raise NotImplementedError


class LocalDirectoryBackend(BaseBackupBackend):
    """ສຳເນົາໄປໂຟນເດີອື່ນ — ໃຫ້ຊີ້ໄປ disk ຄົນລະໜ່ວຍກັບ MEDIA_ROOT

    ຊີ້ໄປໂຟນເດີໃນ disk ໜ່ວຍດຽວກັນກໍຍັງກັນການລຶບຜິດພາດໄດ້ ແຕ່ບໍ່ກັນ disk ເສຍ —
    ຈຶ່ງມີການກວດເຕືອນໄວ້ໃນ run_backup().
    """

    name = "local"

    def __init__(self, root):
        self.root = Path(root)

    def describe(self):
        return f"local:{self.root}"

    def store(self, *, key, fileobj):
        destination = self.root / key
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            with open(destination, "wb") as target:
                shutil.copyfileobj(fileobj, target)
        except OSError as exc:
            raise BackupError(f"ຂຽນໄປ {destination} ບໍ່ໄດ້: {exc}") from exc
        return str(destination)

    def exists(self, ref):
        return Path(ref).exists()


class S3Backend(BaseBackupBackend):
    """S3-compatible (AWS S3, Cloudflare R2, Backblaze B2)

    boto3 ບໍ່ໄດ້ຢູ່ໃນ requirements ພື້ນຖານ — ຕິດຕັ້ງເມື່ອຮ້ານເລືອກໃຊ້ cloud ເທົ່ານັ້ນ
    ຈຶ່ງ import ຢູ່ໃນນີ້ ບໍ່ແມ່ນຫົວໄຟລ໌.
    """

    name = "s3"

    def __init__(self, *, bucket, endpoint_url=None, prefix=""):
        self.bucket = bucket
        self.endpoint_url = endpoint_url
        self.prefix = prefix.strip("/")
        try:
            import boto3
        except ImportError as exc:
            raise BackupError(
                "ຕັ້ງ MEDIA_BACKUP_BACKEND=s3 ແຕ່ຍັງບໍ່ໄດ້ຕິດຕັ້ງ boto3 "
                "— ແລ່ນ: pip install boto3"
            ) from exc
        self._client = boto3.client("s3", endpoint_url=endpoint_url or None)

    def describe(self):
        target = self.endpoint_url or "aws"
        return f"s3:{target}/{self.bucket}"

    def _full_key(self, key):
        return f"{self.prefix}/{key}" if self.prefix else key

    def store(self, *, key, fileobj):
        full_key = self._full_key(key)
        try:
            self._client.upload_fileobj(fileobj, self.bucket, full_key)
        except Exception as exc:  # boto3 ໂຍນ error ຫຼາຍຊະນິດ
            raise BackupError(f"ອັບໂຫຼດ {full_key} ບໍ່ສຳເລັດ: {exc}") from exc
        return f"s3://{self.bucket}/{full_key}"

    def exists(self, ref):
        if not ref.startswith("s3://"):
            return False
        _, _, remainder = ref.partition("s3://")
        bucket, _, key = remainder.partition("/")
        try:
            self._client.head_object(Bucket=bucket, Key=key)
        except Exception:
            return False
        return True


def get_backup_backend():
    """ຄືນປາຍທາງຕາມການຕັ້ງຄ່າ ຫຼື None ຖ້າຍັງບໍ່ໄດ້ຕັ້ງ

    ຄືນ None ບໍ່ແມ່ນ error: ຕອນພັດທະນາ ແລະ ຕອນແລ່ນເທັສບໍ່ຕ້ອງການສຳຮອງ.
    ຜູ້ເອີ້ນເປັນຄົນຕັດສິນວ່າຈະເຕືອນ ຫຼື ຂ້າມ.
    """
    choice = (getattr(settings, "MEDIA_BACKUP_BACKEND", "") or "").strip().lower()

    if choice in ("", "none", "off"):
        return None

    if choice == "local":
        root = getattr(settings, "MEDIA_BACKUP_DIR", "")
        if not root:
            raise BackupError(
                "ຕັ້ງ MEDIA_BACKUP_BACKEND=local ແຕ່ຍັງບໍ່ໄດ້ຕັ້ງ MEDIA_BACKUP_DIR"
            )
        return LocalDirectoryBackend(root)

    if choice == "s3":
        bucket = getattr(settings, "MEDIA_BACKUP_S3_BUCKET", "")
        if not bucket:
            raise BackupError(
                "ຕັ້ງ MEDIA_BACKUP_BACKEND=s3 ແຕ່ຍັງບໍ່ໄດ້ຕັ້ງ MEDIA_BACKUP_S3_BUCKET"
            )
        return S3Backend(
            bucket=bucket,
            endpoint_url=getattr(settings, "MEDIA_BACKUP_S3_ENDPOINT", ""),
            prefix=getattr(settings, "MEDIA_BACKUP_S3_PREFIX", ""),
        )

    raise BackupError(
        f"MEDIA_BACKUP_BACKEND={choice} ບໍ່ຮູ້ຈັກ — ໃຊ້ໄດ້: local, s3, none"
    )
