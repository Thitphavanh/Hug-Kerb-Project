from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("media_backup", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mediafile",
            name="capture_angle",
            field=models.CharField(
                blank=True,
                choices=[
                    ("front", "Front / toe box"),
                    ("heel", "Heel / rear"),
                    ("side", "Side profile"),
                    ("outsole", "Outsole"),
                    ("size_label", "Size label / SKU"),
                    ("inner", "Inner side / insole"),
                    ("box_accessories", "Box and accessories"),
                    ("defect", "Defect close-up"),
                ],
                max_length=30,
                verbose_name="ມຸມຮູບສຳລັບການປະເມີນ",
            ),
        ),
    ]
