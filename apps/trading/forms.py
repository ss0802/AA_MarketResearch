from django import forms

from apps.market.models import Symbol

from .models import PriceAlert, Trade


class TradeForm(forms.ModelForm):
    market = forms.ChoiceField(choices=Symbol.Market.choices, initial=Symbol.Market.INDIA)
    symbol_code = forms.CharField(max_length=20, label="Symbol")
    maximum_risk = forms.DecimalField(
        max_digits=14, decimal_places=2, required=False, min_value=0,
        help_text="Optional planning amount; quantity remains editable.",
    )
    screener_filters = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Record the filters used, one per line.",
    )
    chart_image = forms.FileField(required=False)

    class Meta:
        model = Trade
        fields = [
            "side", "status", "entry_at", "entry_price", "quantity", "stop_price",
            "target_price", "exit_at", "exit_price", "charges", "setup_name",
            "setup_tags", "thesis", "review_notes",
        ]
        widgets = {
            "entry_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "exit_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
            "thesis": forms.Textarea(attrs={"rows": 3}),
            "review_notes": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        market = cleaned.get("market")
        code = cleaned.get("symbol_code", "").strip().upper()
        matches = Symbol.objects.filter(market=market, symbol=code, is_active=True)
        if not matches.exists():
            self.add_error("symbol_code", "No active symbol was found in that market.")
        elif matches.count() > 1:
            self.add_error("symbol_code", "More than one exchange match exists; symbol is ambiguous.")
        else:
            cleaned["symbol_object"] = matches.first()
        entry = cleaned.get("entry_price")
        stop = cleaned.get("stop_price")
        maximum_risk = cleaned.get("maximum_risk")
        if maximum_risk and entry is not None and stop is not None and entry != stop:
            cleaned["calculated_quantity"] = int(maximum_risk / abs(entry - stop))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.symbol = self.cleaned_data["symbol_object"]
        instance.full_clean()
        if commit:
            instance.save()
        return instance


class PriceAlertForm(forms.ModelForm):
    market = forms.ChoiceField(choices=Symbol.Market.choices, initial=Symbol.Market.US)
    symbol_code = forms.CharField(max_length=20, label="Symbol")

    class Meta:
        model = PriceAlert
        fields = ["direction", "target_price", "notify_in_app", "notify_telegram", "notify_desktop", "notify_sound"]

    def clean(self):
        cleaned = super().clean()
        market = cleaned.get("market")
        code = cleaned.get("symbol_code", "").strip().upper()
        symbol = Symbol.objects.filter(market=market, symbol=code, is_active=True).first()
        if not symbol:
            self.add_error("symbol_code", "No active symbol was found in that market.")
        cleaned["symbol_object"] = symbol
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.symbol = self.cleaned_data["symbol_object"]
        if commit:
            instance.save()
        return instance
