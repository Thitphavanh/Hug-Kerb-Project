"""ຈັດສະຖານະຄູ່ເກີບໃຫ້ຕົງກັບວຽກບໍລິການ (rollup)

ໃຊ້ແກ້ຂໍ້ມູນເກົ່າທີ່ຕັ້ງສະຖານະໄວ້ກ່ອນມີໂມເດລ AssetService
ເຊັ່ນ ຄູ່ທີ່ເປັນ "ກຳລັງຊັກ" ແຕ່ບໍ່ມີວຽກຊັກຈັກອັນ.

ສຳຄັນ: ອັບເດດຜ່ານ queryset.update() ບໍ່ຜ່ານ save()
ເພື່ອ **ບໍ່ໃຫ້ສົ່ງແຈ້ງເຕືອນຫາລູກຄ້າ** — ນີ້ແມ່ນການແກ້ຂໍ້ມູນ ບໍ່ແມ່ນຄວາມຄືບໜ້າຈິງ
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from asset_intake.models import Asset


class Command(BaseCommand):
    help = "ຈັດ Asset.status ໃຫ້ຕົງກັບສະຖານະວຽກບໍລິການ (ບໍ່ສົ່ງແຈ້ງເຕືອນ)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="ສະແດງສິ່ງທີ່ຈະປ່ຽນ ໂດຍບໍ່ບັນທຶກຈິງ",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        drift = []

        for asset in Asset.objects.prefetch_related("services"):
            computed = asset.compute_status()
            if computed is not None and computed != asset.status:
                drift.append((asset, asset.status, computed))

        if not drift:
            self.stdout.write(self.style.SUCCESS("ທຸກຄູ່ຕົງກັນຢູ່ແລ້ວ — ບໍ່ມີຫຍັງໃຫ້ແກ້"))
            return

        self.stdout.write(f"ພົບ {len(drift)} ຄູ່ທີ່ບໍ່ຕົງ:")
        for asset, old, new in drift:
            self.stdout.write(f"  {asset.ticket_number}: {old} → {new}")

        if dry_run:
            self.stdout.write(self.style.WARNING("\n--dry-run: ບໍ່ໄດ້ບັນທຶກຫຍັງ"))
            return

        now = timezone.now()
        for asset, _old, new in drift:
            Asset.objects.filter(pk=asset.pk).update(status=new, updated_at=now)

        self.stdout.write(
            self.style.SUCCESS(f"\nແກ້ແລ້ວ {len(drift)} ຄູ່ (ບໍ່ໄດ້ສົ່ງແຈ້ງເຕືອນຫາລູກຄ້າ)")
        )
