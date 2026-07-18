from decimal import Decimal

from django.db import migrations, models


def categorize_services_and_add_basic_clean(apps, schema_editor):
    ServiceType = apps.get_model("pos", "ServiceType")

    category_by_name = {
        "AI Condition Report": "ai_assessment",
        "Color Touch-up": "add_on",
        "Sole Restoration": "add_on",
        "Deep Clean Service": "primary",
        "Premium Spa + Deodorize": "primary",
    }
    for name, category in category_by_name.items():
        ServiceType.objects.filter(name=name).update(category=category)

    ServiceType.objects.update_or_create(
        name="Basic Clean Service",
        defaults={
            "category": "primary",
            "price": Decimal("90000.00"),
            "is_active": True,
        },
    )


def remove_basic_clean(apps, schema_editor):
    ServiceType = apps.get_model("pos", "ServiceType")
    ServiceType.objects.filter(
        name="Basic Clean Service", order_items__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("pos", "0003_order_vat_rate")]

    operations = [
        migrations.AddField(
            model_name="servicetype",
            name="category",
            field=models.CharField(
                choices=[
                    ("ai_assessment", "AI assessment"),
                    ("primary", "Primary service"),
                    ("add_on", "Add-on service"),
                ],
                default="primary",
                max_length=20,
                verbose_name="ໝວດບໍລິການ",
            ),
        ),
        migrations.RunPython(
            categorize_services_and_add_basic_clean,
            reverse_code=remove_basic_clean,
        ),
        migrations.AlterModelOptions(
            name="servicetype",
            options={
                "ordering": ["category", "name"],
                "verbose_name": "ປະເພດບໍລິການ",
                "verbose_name_plural": "ປະເພດບໍລິການ",
            },
        ),
    ]
