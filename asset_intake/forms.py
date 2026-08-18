from django import forms
from django.utils.translation import gettext_lazy as _

INPUT_CLASS = (
    "w-full rounded-lg border border-white/10 bg-surface-container px-3 py-2 "
    "text-sm text-on-surface placeholder:text-on-surface-variant "
    "focus:outline-none focus:border-ai-cyan focus:ring-1 focus:ring-ai-cyan"
)


class IntakeForm(forms.Form):
    """ຮັບເຄື່ອງໃໝ່: ຂໍ້ມູນລູກຄ້າ + ຂໍ້ມູນເກີບໃນຟອມດຽວ.

    ລູກຄ້າຖືກຈັບຄູ່ດ້ວຍເບີໂທ — ຖ້າມີເບີນີ້ຢູ່ແລ້ວຈະໃຊ້ລູກຄ້າເກົ່າ, ບໍ່ດັ່ງນັ້ນສ້າງໃໝ່.
    """

    # ລູກຄ້າທີ່ເລືອກຈາກຊ່ອງຄົ້ນຫາ — ຜູກດ້ວຍ id ບໍ່ແມ່ນເບີໂທ ເພື່ອບໍ່ໃຫ້ຊື່ຊ້ຳກັນ
    # ໄປສ້າງລູກຄ້າໃໝ່ ຫຼື ທັບຂໍ້ມູນຄົນອື່ນ ຕອນເບີໂທຖືກແກ້ໜ້າຮ້ານ
    customer_id = forms.IntegerField(
        required=False,
        widget=forms.HiddenInput(attrs={"id": "id_customer_id"}),
    )
    customer_name = forms.CharField(
        label=_("Customer name"),
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_customer_name",
                "autocomplete": "off",
                "placeholder": _("e.g. John Doe"),
            }
        ),
    )
    customer_phone = forms.CharField(
        label=_("Customer phone"),
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_customer_phone",
                "type": "tel",
                "placeholder": "20XXXXXXXX / 020XXXXXXXX",
            }
        ),
    )
    # ຍີ່ຫໍ້ເປັນລາຍການສັ້ນທີ່ຮ້ານຄຸມເອງ → ໃຊ້ dropdown ໃຫ້ຊື່ສະກົດຄືກັນທຸກເທື່ອ
    # (ແຕ່ກ່ອນພິມເອງ ຈຶ່ງມີທັງ "nike" ແລະ "Nike" ໃນຖານຂໍ້ມູນ)
    brand = forms.ChoiceField(
        label=_("Brand"),
        choices=[],
        widget=forms.Select(attrs={"class": INPUT_CLASS, "id": "id_brand"}),
    )
    # ລຸ້ນມີຫຼາຍ ແລະ ອອກໃໝ່ຕະຫຼອດ → ຊ່ອງພິມ + ລາຍການແນະນຳຕາມຍີ່ຫໍ້ທີ່ເລືອກ
    # ບໍ່ບັງຄັບໃຫ້ເລືອກຈາກລາຍການ ບໍ່ດັ່ງນັ້ນລຸ້ນໃໝ່ຈະຮັບເຄື່ອງບໍ່ໄດ້ໜ້າຮ້ານ
    model_name = forms.CharField(
        label=_("Model"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_model_name",
                "list": "model-options",
                "autocomplete": "off",
                "placeholder": "Air Jordan 1, Dunk Low...",
            }
        ),
    )
    color = forms.CharField(
        label=_("Color"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_color",
                "placeholder": "White / Black / Red...",
            }
        ),
    )
    size = forms.CharField(
        label=_("Size"),
        required=False,
        widget=forms.TextInput(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_size",
                "placeholder": "42 EU / 8.5 US...",
            }
        ),
    )
    condition_note = forms.CharField(
        label=_("Condition at intake"),
        required=False,
        widget=forms.Textarea(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_condition_note",
                "rows": 3,
                "placeholder": _("Describe existing stains, scratches, yellowing, or special customer requests..."),
            }
        ),
    )
    pickup_date = forms.DateField(
        label=_("Pickup date"),
        required=False,
        widget=forms.DateInput(
            attrs={
                "class": INPUT_CLASS,
                "id": "id_pickup_date",
                "type": "date",
            }
        ),
    )


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ດຶງຍີ່ຫໍ້ຕອນສ້າງຟອມ ບໍ່ແມ່ນຕອນ import — ບໍ່ດັ່ງນັ້ນຮ້ານເພີ່ມຍີ່ຫໍ້ໃໝ່
        # ແລ້ວຕ້ອງຣີສະຕາດເຊີບເວີຈຶ່ງຈະເຫັນ
        from .models import Brand

        names = list(
            Brand.objects.filter(is_active=True).values_list("name", flat=True)
        )
        self.fields["brand"].choices = [(name, name) for name in names]
