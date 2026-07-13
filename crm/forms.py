from django import forms

from .models import Customer

INPUT_CLASS = (
    "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm "
    "focus:outline-none focus:ring-2 focus:ring-slate-800"
)


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "email",
            "line_id",
            "telegram_chat_id",
            "facebook",
            "address",
            "note",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "phone": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "email": forms.EmailInput(attrs={"class": INPUT_CLASS}),
            "line_id": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "telegram_chat_id": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "facebook": forms.TextInput(attrs={"class": INPUT_CLASS}),
            "address": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
            "note": forms.Textarea(attrs={"class": INPUT_CLASS, "rows": 2}),
        }
