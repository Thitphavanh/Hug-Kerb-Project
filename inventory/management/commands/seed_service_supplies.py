"""ຕັ້ງສູດອຸປະກອນເລີ່ມຕົ້ນໃຫ້ບໍລິການທີ່ຍັງບໍ່ມີສູດ (Scope 2.1)

ເຫດຜົນທີ່ຕ້ອງມີຄຳສັ່ງນີ້: ກົນໄກຕັດສະຕັອກເຮັດວຽກຖືກຕ້ອງແຕ່ຢູ່ໃນຖານຂໍ້ມູນຈິງ
ມີສູດ 0 ແຖວ ຈຶ່ງບໍ່ຫັກຫຍັງເລີຍ. ຄຳສັ່ງນີ້ໃສ່ຄ່າຕັ້ງຕົ້ນທີ່ສົມເຫດສົມຜົນຕາມ
ປະເພດວຽກ ເພື່ອໃຫ້ລະບົບເດີນໄດ້ທັນທີ ແລ້ວຮ້ານຄ່ອຍປັບຕົວເລກຈິງໃນໜ້າສາງ.

ບໍ່ແຕະສູດທີ່ຕັ້ງໄວ້ແລ້ວ — ຮ້ານປັບຕົວເລກເອງແລ້ວ ຕ້ອງບໍ່ຖືກຂຽນທັບ.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from inventory.models import ServiceSupply, Supply
from pos.models import ServiceType

# ຄຳສຳຄັນໃນຊື່ອຸປະກອນ → ຈຳນວນທີ່ໃຊ້ຕໍ່ 1 ລາຍການ, ແຍກຕາມປະເພດວຽກ.
# ຈັບຄູ່ດ້ວຍຄຳສຳຄັນເພາະຊື່ອຸປະກອນຂອງແຕ່ລະຮ້ານບໍ່ຄືກັນ
DEFAULT_RECIPES = {
    ServiceType.WorkType.WASH: (
        ("ນ້ຳຢາ", 1),
        ("ແປງ", 1),
        ("ຜ້າ", 1),
        ("ຖົງ", 1),
    ),
    ServiceType.WorkType.REPAIR: (
        ("ກາວ", 1),
        ("ຜ້າ", 1),
        ("ຖົງ", 1),
    ),
    ServiceType.WorkType.ASSESS: (("ຖົງ", 1),),
}


class Command(BaseCommand):
    help = "ຕັ້ງສູດອຸປະກອນເລີ່ມຕົ້ນໃຫ້ບໍລິການທີ່ຍັງບໍ່ມີສູດ"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="ສະແດງວ່າຈະສ້າງແຖວໃດແດ່ ໂດຍບໍ່ບັນທຶກ",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        supplies = list(Supply.objects.filter(is_active=True))
        if not supplies:
            self.stdout.write(
                self.style.WARNING("ຍັງບໍ່ມີອຸປະກອນໃນສາງ — ເພີ່ມອຸປະກອນກ່ອນ")
            )
            return

        services_with_recipe = set(
            ServiceSupply.objects.values_list("service_type_id", flat=True)
        )
        created = 0
        skipped = 0

        for service in ServiceType.objects.filter(is_active=True):
            if service.pk in services_with_recipe:
                skipped += 1
                continue

            rows = self._match_supplies(service, supplies)
            if not rows:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {service.name}: ບໍ່ພົບອຸປະກອນທີ່ເໝາະ — ຕັ້ງເອງໃນໜ້າສາງ"
                    )
                )
                continue

            for supply, quantity in rows:
                self.stdout.write(f"  {service.name} → {supply.name} × {quantity}")
                if not dry_run:
                    ServiceSupply.objects.create(
                        service_type=service,
                        supply=supply,
                        quantity_per_unit=quantity,
                    )
                created += 1

        summary = f"ສ້າງສູດ {created} ແຖວ, ຂ້າມບໍລິການທີ່ມີສູດແລ້ວ {skipped} ລາຍການ"
        if dry_run:
            self.stdout.write(self.style.WARNING(f"[dry-run] {summary}"))
            transaction.set_rollback(True)
        else:
            self.stdout.write(self.style.SUCCESS(summary))

    def _match_supplies(self, service, supplies):
        """ຈັບຄູ່ບໍລິການກັບອຸປະກອນຕາມຄຳສຳຄັນ — ອຸປະກອນຕົວໜຶ່ງຕໍ່ໜຶ່ງຄຳສຳຄັນ"""
        rows = []
        used = set()
        for keyword, quantity in DEFAULT_RECIPES.get(service.work_type, ()):
            match = next(
                (
                    s
                    for s in supplies
                    if keyword in s.name and s.pk not in used
                ),
                None,
            )
            if match is not None:
                used.add(match.pk)
                rows.append((match, quantity))
        return rows
