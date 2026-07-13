from django import forms

INPUT_CLASS = (
    "w-full rounded-lg border border-white/10 bg-surface-container px-3 py-2 "
    "text-sm text-on-surface placeholder:text-on-surface-variant "
    "focus:outline-none focus:border-ai-cyan focus:ring-1 focus:ring-ai-cyan"
)


class IntakeForm(forms.Form):
    """ຮັບເຄື່ອງໃໝ່: ຂໍ້ມູນລູກຄ້າ + ຂໍ້ມູນເກີບໃນຟອມດຽວ.

    ລູກຄ້າຖືກຈັບຄູ່ດ້ວຍເບີໂທ — ຖ້າມີເບີນີ້ຢູ່ແລ້ວຈະໃຊ້ລູກຄ້າເກົ່າ, ບໍ່ດັ່ງນັ້ນສ້າງໃໝ່.
    """

    customer_name = forms.CharField(
        label="ຊື່ລູກຄ້າ",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "list": "customer-list"}),
    )
    customer_phone = forms.CharField(
        label="ເບີໂທລູກຄ້າ",
        widget=forms.TextInput(attrs={"class": INPUT_CLASS}),
    )
    brand = forms.CharField(
        label="ຍີ່ຫໍ້", widget=forms.TextInput(attrs={"class": INPUT_CLASS})
    )
    model_name = forms.CharField(
        label="ລຸ້ນ", required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS})
    )
    color = forms.CharField(
        label="ສີ", required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS})
    )
    size = forms.CharField(
        label="ເບີ", required=False, widget=forms.TextInput(attrs={"class": INPUT_CLASS})
    )
    condition_note = forms.CharField(
        label="ສະພາບຕອນຮັບເຄື່ອງ",
        required=False,
        widget=forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 3}),
    )
    pickup_date = forms.DateField(
        label="ວັນນັດຮັບເຄື່ອງ",
        required=False,
        widget=forms.DateInput(attrs={"class": INPUT_CLASS, "type": "date"}),
    )
