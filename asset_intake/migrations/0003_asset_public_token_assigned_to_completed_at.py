from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

import asset_intake.models


def populate_public_tokens(apps, schema_editor):
    """ໃສ່ token ບໍ່ຊ້ຳກັນໃຫ້ແຖວເກົ່າທີລະແຖວ (default ຂອງ AddField ຈະຊ້ຳກັນ)"""
    Asset = apps.get_model("asset_intake", "Asset")
    for asset in Asset.objects.all().iterator():
        asset.public_token = asset_intake.models.generate_public_token()
        asset.save(update_fields=["public_token"])


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("asset_intake", "0002_alter_asset_status_assetimage"),
    ]

    operations = [
        migrations.AddField(
            model_name="asset",
            name="public_token",
            field=models.CharField(
                default=asset_intake.models.generate_public_token,
                editable=False,
                max_length=32,
                null=True,
                verbose_name="ລະຫັດຕິດຕາມ (ສຳລັບ QR/Portal)",
            ),
        ),
        migrations.RunPython(populate_public_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="asset",
            name="public_token",
            field=models.CharField(
                default=asset_intake.models.generate_public_token,
                editable=False,
                max_length=32,
                unique=True,
                verbose_name="ລະຫັດຕິດຕາມ (ສຳລັບ QR/Portal)",
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="assigned_to",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="assigned_assets",
                to=settings.AUTH_USER_MODEL,
                verbose_name="ຊ່າງຮັບຜິດຊອບ",
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="completed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="ວັນທີສົ່ງມອບ"
            ),
        ),
    ]
