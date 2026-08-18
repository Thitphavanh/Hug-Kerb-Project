"""ສຳຮອງໄຟລ໌ຫຼັກຖານໄປປາຍທາງທີ່ຕັ້ງໄວ້ (Scope 2.3)

ຕັ້ງເປັນ cron ລາຍວັນ ເຊັ່ນ (ຕີ 2 ທຸກຄືນ):

    0 2 * * * cd /srv/hugkerb/core && ./venv/bin/python manage.py backup_media

ແລ່ນຊ້ຳກໍປອດໄພ — ໄຟລ໌ທີ່ສຳຮອງແລ້ວຖືກຂ້າມ.
"""

from django.core.management.base import BaseCommand, CommandError

from media_backup.backends import BackupError, get_backup_backend
from media_backup.models import BackupRun
from media_backup.services import pending_backup_queryset, run_backup


class Command(BaseCommand):
    help = "ສຳຮອງໄຟລ໌ຫຼັກຖານທີ່ຍັງບໍ່ໄດ້ສຳຮອງໄປປາຍທາງທີ່ຕັ້ງໄວ້"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="ສຳຮອງບໍ່ເກີນຈຳນວນນີ້ຕໍ່ຮອບ (ໃຊ້ຕອນສຳຮອງຄັ້ງທຳອິດທີ່ມີໄຟລ໌ຫຼາຍ)",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="ບອກແຕ່ວ່າຍັງຄ້າງເທົ່າໃດ ໂດຍບໍ່ສຳຮອງ",
        )

    def handle(self, *args, **options):
        try:
            backend = get_backup_backend()
        except BackupError as exc:
            raise CommandError(exc.message) from exc

        pending = pending_backup_queryset().count()

        if options["status"]:
            destination = backend.describe() if backend else "ຍັງບໍ່ໄດ້ຕັ້ງ"
            self.stdout.write(f"ປາຍທາງ: {destination}")
            self.stdout.write(f"ໄຟລ໌ທີ່ຍັງບໍ່ໄດ້ສຳຮອງ: {pending}")
            last = BackupRun.objects.first()
            if last:
                self.stdout.write(
                    f"ຮອບລ່າສຸດ: {last.started_at:%Y-%m-%d %H:%M} "
                    f"— {last.get_status_display()} ({last.files_copied} ໄຟລ໌)"
                )
            return

        if backend is None:
            raise CommandError(
                "ຍັງບໍ່ໄດ້ຕັ້ງປາຍທາງສຳຮອງ — ຕັ້ງ MEDIA_BACKUP_BACKEND ໃນ .env "
                "(local ຫຼື s3)"
            )

        if not pending:
            self.stdout.write(self.style.SUCCESS("ສຳຮອງຄົບແລ້ວ — ບໍ່ມີໄຟລ໌ຄ້າງ"))
            return

        self.stdout.write(f"ສຳຮອງ {pending} ໄຟລ໌ ໄປ {backend.describe()} ...")
        try:
            run = run_backup(limit=options["limit"], backend=backend)
        except BackupError as exc:
            raise CommandError(exc.message) from exc

        summary = (
            f"ສຳຮອງໄດ້ {run.files_copied} ໄຟລ໌ "
            f"({run.bytes_copied / 1024 / 1024:.1f} MB), ຕົກ {run.files_failed}"
        )
        if run.status == BackupRun.Status.SUCCESS:
            self.stdout.write(self.style.SUCCESS(summary))
            return

        self.stdout.write(self.style.ERROR(summary))
        if run.detail:
            self.stdout.write(run.detail)
        # ໃຫ້ exit code ບໍ່ເປັນ 0 ເພື່ອໃຫ້ cron/monitoring ຈັບໄດ້ວ່າມີບັນຫາ
        raise CommandError("ສຳຮອງບໍ່ຄົບ — ເບິ່ງລາຍລະອຽດຂ້າງເທິງ")
