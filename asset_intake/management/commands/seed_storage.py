"""ສ້າງຜັງບ່ອນເກັບເກີບຕາມຊັ້ນວາງຈິງໜ້າຮ້ານ (idempotent, ຮັນຊ້ຳໄດ້)"""

from django.core.management.base import BaseCommand

from asset_intake.models import ZONE_LAYOUT, StorageSlot, zone_label


class Command(BaseCommand):
    help = "ສ້າງບ່ອນເກັບເກີບຕາມຜັງຈິງ: Zone A 30 ຊ່ອງ, Zone B 36 ຊ່ອງ, Zone VIP (V) 10 ຊ່ອງ"

    def add_arguments(self, parser):
        parser.add_argument(
            "--zones",
            default=",".join(ZONE_LAYOUT),
            help="ລາຍຊື່ໂຊນ ຄັ່ນດ້ວຍຈຸດ (ຄ່າເລີ່ມຕົ້ນ A,B,V)",
        )

    def handle(self, *args, **options):
        zones = [z.strip().upper() for z in options["zones"].split(",") if z.strip()]
        created = 0

        for zone in zones:
            layout = ZONE_LAYOUT.get(zone)
            if layout is None:
                self.stderr.write(
                    self.style.WARNING(f"ຂ້າມໂຊນ {zone} — ບໍ່ມີໃນຜັງ ZONE_LAYOUT")
                )
                continue

            per_row = layout["per_row"]
            for position in range(1, layout["slots"] + 1):
                _, was_created = StorageSlot.objects.get_or_create(
                    zone=zone,
                    position=position,
                    defaults={"cabinet": (position - 1) // per_row + 1},
                )
                created += was_created

            self.stdout.write(
                f"  {zone_label(zone)}: {layout['slots']} ຊ່ອງ "
                f"({per_row} ຊ່ອງ/ຊັ້ນວາງ) — "
                f"{zone}-01 … {zone}-{layout['slots']:02d}"
            )

        total = StorageSlot.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f"ສ້າງໃໝ່ {created} ບ່ອນ — ມີທັງໝົດ {total} ບ່ອນ")
        )
