"""ສ້າງຜັງບ່ອນເກັບເກີບເລີ່ມຕົ້ນ — ໂຊນ × ຕູ້ × ຊ່ອງ (idempotent, ຮັນຊ້ຳໄດ້)"""

from django.core.management.base import BaseCommand

from asset_intake.models import StorageSlot


class Command(BaseCommand):
    help = "ສ້າງບ່ອນເກັບເກີບເລີ່ມຕົ້ນ (ຄ່າມາດຕະຖານ: ໂຊນ A,B × 2 ຕູ້ × 12 ຊ່ອງ = 48 ບ່ອນ)"

    def add_arguments(self, parser):
        parser.add_argument("--zones", default="A,B", help="ລາຍຊື່ໂຊນ ຄັ່ນດ້ວຍຈຸດ (ຄ່າເລີ່ມຕົ້ນ A,B)")
        parser.add_argument("--cabinets", type=int, default=2, help="ຈຳນວນຕູ້ຕໍ່ໂຊນ")
        parser.add_argument("--slots", type=int, default=12, help="ຈຳນວນຊ່ອງຕໍ່ຕູ້")

    def handle(self, *args, **options):
        zones = [z.strip().upper() for z in options["zones"].split(",") if z.strip()]
        created = 0
        for zone in zones:
            for cabinet in range(1, options["cabinets"] + 1):
                for position in range(1, options["slots"] + 1):
                    _, was_created = StorageSlot.objects.get_or_create(
                        zone=zone, cabinet=cabinet, position=position
                    )
                    created += was_created
        total = StorageSlot.objects.count()
        self.stdout.write(
            self.style.SUCCESS(f"ສ້າງໃໝ່ {created} ບ່ອນ — ມີທັງໝົດ {total} ບ່ອນ")
        )
