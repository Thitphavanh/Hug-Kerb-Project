from django.apps import AppConfig


class AssetIntakeConfig(AppConfig):
    name = "asset_intake"

    def ready(self):
        from . import signals  # noqa: F401  — ລົງທະບຽນ signal ຕອນແອັບພ້ອມ
