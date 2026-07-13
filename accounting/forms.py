from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .labels import localized_category_name
from .models import AccountCategory, Budget, CashBook, CashHandover


INPUT_CLASS = (
    "w-full rounded-lg border border-outline-variant/40 bg-surface-container-lowest "
    "px-3 py-2.5 text-on-surface focus:border-ai-cyan focus:ring-ai-cyan"
)


class CategoryChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, category):
        type_label = _("Income") if category.transaction_type == "IN" else _("Expense")
        return f"{type_label} — {localized_category_name(category)}"


class CashBookForm(forms.ModelForm):
    category = CategoryChoiceField(
        label=_("Category"), queryset=AccountCategory.objects.none()
    )

    class Meta:
        model = CashBook
        fields = [
            "date",
            "time",
            "transaction_type",
            "category",
            "description",
            "amount",
            "currency",
            "payment_method",
            "reference",
            "attachment",
            "status",
            "note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "note": forms.Textarea(attrs={"rows": 3}),
            "attachment": forms.FileInput(attrs={"accept": "image/*,.pdf"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "date": _("Date"),
            "time": _("Time"),
            "transaction_type": _("Transaction type"),
            "category": _("Category"),
            "description": _("Description"),
            "amount": _("Amount"),
            "currency": _("Currency"),
            "payment_method": _("Payment method"),
            "reference": _("Reference number"),
            "attachment": _("Receipt or attachment"),
            "status": _("Status"),
            "note": _("Notes"),
        }
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS
        for name, label in labels.items():
            self.fields[name].label = label
        self.fields["category"].queryset = AccountCategory.objects.filter(is_active=True)
        self.fields["transaction_type"].choices = [
            ("", "---------"),
            ("IN", _("Income")),
            ("OUT", _("Expense")),
        ]
        self.fields["currency"].choices = [
            ("THB", _("Thai baht (THB)")),
            ("LAK", _("Lao kip (LAK)")),
            ("USD", _("US dollar (USD)")),
        ]
        self.fields["payment_method"].choices = [
            ("cash", _("Cash")),
            ("transfer", _("Bank transfer")),
            ("qr", _("QR payment")),
            ("other", _("Other")),
        ]
        self.fields["status"].choices = [
            ("confirmed", _("Confirmed")),
            ("draft", _("Draft")),
            ("void", _("Void")),
        ]
        if not self.is_bound and not self.instance.pk:
            now = timezone.localtime()
            self.initial.update({"date": now.date(), "time": now.strftime("%H:%M")})


class CashHandoverForm(forms.ModelForm):
    class Meta:
        model = CashHandover
        fields = [
            "date",
            "currency",
            "opening_balance",
            "counted_amount",
            "received_by",
            "note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "date": _("Date"),
            "currency": _("Currency"),
            "opening_balance": _("Opening balance"),
            "counted_amount": _("Counted amount"),
            "received_by": _("Receiver"),
            "note": _("Notes"),
        }
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS
        for name, label in labels.items():
            self.fields[name].label = label
        self.fields["currency"].choices = [
            ("THB", _("Thai baht (THB)")),
            ("LAK", _("Lao kip (LAK)")),
            ("USD", _("US dollar (USD)")),
        ]


class AccountCategoryForm(forms.ModelForm):
    class Meta:
        model = AccountCategory
        fields = ["name", "transaction_type", "color"]
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "name": _("Name"),
            "transaction_type": _("Transaction type"),
            "color": _("Color"),
        }
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS
        for name, label in labels.items():
            self.fields[name].label = label
        self.fields["transaction_type"].choices = [
            ("IN", _("Income")),
            ("OUT", _("Expense")),
        ]


class BudgetForm(forms.ModelForm):
    month = forms.DateField(
        label=_("Month"),
        input_formats=["%Y-%m"],
        widget=forms.DateInput(format="%Y-%m", attrs={"type": "month"}),
    )
    category = CategoryChoiceField(
        label=_("Category"), queryset=AccountCategory.objects.none()
    )

    class Meta:
        model = Budget
        fields = ["month", "category", "currency", "amount"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["currency"].label = _("Currency")
        self.fields["amount"].label = _("Budget amount")
        for field in self.fields.values():
            field.widget.attrs["class"] = INPUT_CLASS
        self.fields["category"].queryset = AccountCategory.objects.filter(
            transaction_type="OUT", is_active=True
        )
        self.fields["currency"].choices = [
            ("THB", _("Thai baht (THB)")),
            ("LAK", _("Lao kip (LAK)")),
            ("USD", _("US dollar (USD)")),
        ]
