from django import forms

from engine import clear_span, default_deflection_settings

from .choices import (
    ALL_SIZE_CHOICES,
    DEFAULT_MATERIAL,
    DEFAULT_PLIES,
    DEFAULT_SERVICE_CONDITION,
    LOAD_TYPE_CHOICES,
    MATERIAL_CATEGORY,
    MATERIAL_CHOICES,
    MEMBER_TYPE_CHOICES,
    PERFORMANCE_PROFILE_CHOICES,
    PLY_CHOICES,
    SERVICE_CONDITION_CHOICES,
    SIZE_CATEGORY,
    SPAN_MODE_CHOICES,
    SUBFLOOR_PROFILE_CHOICES,
    SUPPORT_TYPE_CHOICES,
    UNIFORM_LOAD_BASIS_FORM_CHOICES,
)
from .continuous import parse_extra_span_rows
from .load_inputs import default_uniform_component_values
from .models import BeamProject


class BeamProjectForm(forms.ModelForm):
    class Meta:
        model = BeamProject
        fields = ("name", "project_number", "status", "client_name", "site_address", "notes")
        widgets = {
            "name": forms.TextInput(attrs={"class": "fc-input", "placeholder": "Project name"}),
            "project_number": forms.TextInput(attrs={"class": "fc-input", "placeholder": "Optional job or project number"}),
            "status": forms.Select(attrs={"class": "fc-select"}),
            "client_name": forms.TextInput(attrs={"class": "fc-input", "placeholder": "Client or owner"}),
            "site_address": forms.TextInput(attrs={"class": "fc-input", "placeholder": "Project address"}),
            "notes": forms.Textarea(attrs={"class": "fc-input", "rows": 5, "placeholder": "Project notes, assumptions, or scope"}),
        }


class BeamDesignForm(forms.Form):
    project = forms.ModelChoiceField(
        label="Project",
        queryset=BeamProject.objects.none(),
        required=False,
        empty_label="No project",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    new_project_name = forms.CharField(
        label="New project name",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    performance_profile = forms.ChoiceField(
        label="Performance target",
        choices=PERFORMANCE_PROFILE_CHOICES,
        initial="code_minimum",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    subfloor_profile = forms.ChoiceField(
        label="Subfloor / floor feel target",
        choices=SUBFLOOR_PROFILE_CHOICES,
        initial="none",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    name = forms.CharField(
        label="Design name (for saving)", required=False, max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    revision_note = forms.CharField(
        label="Revision note",
        required=False,
        max_length=240,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    member_type = forms.ChoiceField(
        label="Member type", choices=MEMBER_TYPE_CHOICES, initial="floor_joist",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    span_ft = forms.FloatField(
        label="Span (ft)", min_value=0.1,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    span_mode = forms.ChoiceField(
        label="Span measured", choices=SPAN_MODE_CHOICES, initial="inside",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    left_overhang_ft = forms.FloatField(
        label="Left cantilever / overhang (ft)", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    right_overhang_ft = forms.FloatField(
        label="Right cantilever / overhang (ft)", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    span_2_ft = forms.FloatField(
        label="Span 2 (ft)", min_value=0.1, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    span_3_ft = forms.FloatField(
        label="Span 3 (ft)", min_value=0.1, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    uniform_load_basis = forms.ChoiceField(
        label="Uniform load input basis", choices=UNIFORM_LOAD_BASIS_FORM_CHOICES, initial="psf",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    spacing_in = forms.FloatField(
        label='On-center spacing (in)', min_value=1, required=False, initial=16,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    dead_load_plf = forms.FloatField(
        label="Dead load", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    live_load_plf = forms.FloatField(
        label="Live load", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    snow_load_plf = forms.FloatField(
        label="Snow load", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    roof_live_load_plf = forms.FloatField(
        label="Roof live load", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    wind_load_plf = forms.FloatField(
        label="Wind load", min_value=0, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    material = forms.ChoiceField(
        label="Material", choices=MATERIAL_CHOICES, initial=DEFAULT_MATERIAL,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    service_condition = forms.ChoiceField(
        label="Service condition", choices=SERVICE_CONDITION_CHOICES, initial=DEFAULT_SERVICE_CONDITION,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    nominal_size = forms.ChoiceField(
        label="Member size", choices=ALL_SIZE_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    plies = forms.TypedChoiceField(
        label="Plies (built-up)", choices=PLY_CHOICES, coerce=int, initial=DEFAULT_PLIES,
        required=False, empty_value=DEFAULT_PLIES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    repetitive = forms.BooleanField(
        label="Repetitive member (≤ 24\" o.c., 3+ members)", required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    unbraced_length_ft = forms.FloatField(
        label="Unbraced compression edge (ft)", min_value=0, required=False,
        help_text="Blank = compression edge continuously braced (CL = 1.0).",
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Continuously braced"}),
    )
    bearing_length_left_in = forms.FloatField(
        label="Bearing length B1 (left, in)", min_value=0.5, initial=1.5,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    bearing_length_right_in = forms.FloatField(
        label="Bearing length B2 (right, in)", min_value=0.5, initial=1.5,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    bearing_length_mid_in = forms.FloatField(
        label="Bearing length B2 (interior, in)", min_value=0.5, initial=3.5, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    bearing_length_mid_2_in = forms.FloatField(
        label="Bearing length B3 (interior, in)", min_value=0.5, initial=3.5, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control"}),
    )
    support_type_left = forms.ChoiceField(
        label="Support B1 (left)", choices=SUPPORT_TYPE_CHOICES, initial="wall_plate",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    support_type_right = forms.ChoiceField(
        label="Support B2 (right)", choices=SUPPORT_TYPE_CHOICES, initial="wall_plate",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    support_type_mid = forms.ChoiceField(
        label="Support B2 (interior)", choices=SUPPORT_TYPE_CHOICES, initial="wall_plate", required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    support_type_mid_2 = forms.ChoiceField(
        label="Support B3 (interior)", choices=SUPPORT_TYPE_CHOICES, initial="wall_plate", required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    # Deflection limits are optional: left blank, each falls back to the
    # member-type/profile default in clean(). The Settings tab still
    # pre-fills them (and JS keeps them synced) so the user normally sees
    # the number, but clearing a field no longer rejects the form.
    deflection_limit_live = forms.IntegerField(
        label="Back-span live/snow limit", min_value=60, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "member-type default"}),
    )
    deflection_limit_total = forms.IntegerField(
        label="Back-span total-load limit", min_value=60, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "member-type default"}),
    )
    cantilever_deflection_limit_live = forms.IntegerField(
        label="Cantilever live/snow limit", min_value=60, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "member-type default"}),
    )
    cantilever_deflection_limit_total = forms.IntegerField(
        label="Cantilever total-load limit", min_value=60, required=False,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "member-type default"}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields["project"].queryset = BeamProject.objects.filter(user=user)
        member_type = self.initial.get("member_type") or self.fields["member_type"].initial
        if self.is_bound:
            member_type = self.data.get(self.add_prefix("member_type")) or member_type
        performance_profile = self.initial.get("performance_profile") or self.fields["performance_profile"].initial
        subfloor_profile = self.initial.get("subfloor_profile") or self.fields["subfloor_profile"].initial
        if self.is_bound:
            performance_profile = self.data.get(self.add_prefix("performance_profile")) or performance_profile
            subfloor_profile = self.data.get(self.add_prefix("subfloor_profile")) or subfloor_profile
        defaults = default_deflection_settings(member_type, performance_profile, subfloor_profile)
        for name, value in defaults.items():
            self.fields[name].initial = value
            if not self.is_bound and not self.initial.get(name):
                self.initial[name] = value
        load_basis = self.initial.get("uniform_load_basis") or self.fields["uniform_load_basis"].initial
        spacing_in = self.initial.get("spacing_in") or self.fields["spacing_in"].initial
        if self.is_bound:
            load_basis = self.data.get(self.add_prefix("uniform_load_basis")) or load_basis
            spacing_raw = self.data.get(self.add_prefix("spacing_in"))
            try:
                spacing_in = float(spacing_raw) if spacing_raw else spacing_in
            except (TypeError, ValueError):
                spacing_in = self.fields["spacing_in"].initial
        load_defaults = default_uniform_component_values(member_type, load_basis, float(spacing_in or 16))
        for name, value in load_defaults.items():
            self.fields[name].initial = value
            if not self.is_bound and not self.initial.get(name):
                self.initial[name] = value

    def clean(self):
        cleaned = super().clean()
        span_ft = cleaned.get("span_ft")
        span_2_ft = cleaned.get("span_2_ft")
        span_3_ft = cleaned.get("span_3_ft")
        extra_span_payload = parse_extra_span_rows(self.data) if self.is_bound else {
            "extra_spans": [], "extra_bearings": [], "has_errors": False,
        }
        span_mode = cleaned.get("span_mode")
        bl = cleaned.get("bearing_length_left_in")
        bm = cleaned.get("bearing_length_mid_in")
        bm2 = cleaned.get("bearing_length_mid_2_in")
        br = cleaned.get("bearing_length_right_in")
        if span_3_ft and not span_2_ft:
            self.add_error("span_3_ft", "Enter Span 2 before adding Span 3.")
        if extra_span_payload["extra_spans"] and not span_3_ft:
            self.add_error("span_3_ft", "Enter Span 3 before adding Span 4 and above.")
        if extra_span_payload["has_errors"]:
            self.add_error("span_3_ft", "Fix the additional continuous-span rows below.")
        if span_ft and span_mode and bl and br:
            try:
                full_spans = [span_ft]
                bearing_chain = [bl]
                if span_2_ft:
                    full_spans.append(span_2_ft)
                    bearing_chain.append(bm or 0)
                if span_3_ft:
                    full_spans.append(span_3_ft)
                    bearing_chain.append(bm2 or 0)
                full_spans.extend(extra_span_payload["extra_spans"])
                bearing_chain.extend(extra_span_payload["extra_bearings"])
                bearing_chain.append(br)
                for i, given_span in enumerate(full_spans):
                    clear_span(given_span, span_mode, bearing_chain[i], bearing_chain[i + 1])
            except ValueError as exc:
                # Attach to span_ft (not a bare non-field error) so the
                # design view's tab-error-routing sends the user to the
                # Spans tab, where this is actually fixable.
                self.add_error("span_ft", str(exc))
        if span_2_ft and not bm:
            self.add_error("bearing_length_mid_in", "Enter the interior support bearing length for multi-span mode.")
        if span_3_ft and not bm2:
            self.add_error("bearing_length_mid_2_in", "Enter the second interior support bearing length for 3-span mode.")
        if cleaned.get("uniform_load_basis") == "psf" and not cleaned.get("spacing_in"):
            self.add_error("spacing_in", "Enter on-center spacing for psf load conversion.")
        # Material and member size must belong to the same category: LVL
        # materials use LVL depths, sawn materials use sawn sizes. The UI
        # keeps these in sync; this guards against a mismatched POST (which
        # would otherwise compute a nonsensical section) and keeps wet
        # service out of LVL (its wet values are not modelled).
        material = cleaned.get("material")
        nominal_size = cleaned.get("nominal_size")
        if material and nominal_size:
            material_cat = MATERIAL_CATEGORY.get(material, "sawn")
            size_cat = SIZE_CATEGORY.get(nominal_size, "sawn")
            cat_label = {"sawn": "sawn-lumber", "lvl": "LVL", "glulam": "glulam"}
            if material_cat != size_cat:
                self.add_error(
                    "nominal_size",
                    f"A {cat_label[material_cat]} material needs a {cat_label[material_cat]} size.",
                )
            # LVL and glulam are modelled dry-service only.
            if material_cat in ("lvl", "glulam") and cleaned.get("service_condition") == "wet":
                self.add_error(
                    "service_condition",
                    f"Wet-service {cat_label[material_cat]} values are not modelled; "
                    "use a dry service condition or a sawn material.",
                )
            # Glulam is a monolithic section, not a built-up member.
            if material_cat == "glulam" and cleaned.get("plies", 1) and cleaned["plies"] > 1:
                cleaned["plies"] = 1
        # Deflection limits are left as-is here (None when blank). Blanks
        # are resolved to the member-type default at use time: the view
        # resolves them for the live run, and BeamDesign.compute_result
        # resolves stored nulls via its own `or default` fallback. Storing
        # null (rather than the resolved number) keeps a saved "use the
        # default" design dynamic, matching the model's design.
        return cleaned


class PointLoadForm(forms.Form):
    p = forms.FloatField(
        label="Point load (lb)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
    )
    location_ft = forms.FloatField(
        label="Location from left end of member (ft)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
    )
    load_type = forms.ChoiceField(
        label="Type", choices=LOAD_TYPE_CHOICES, required=False, initial="live",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def clean(self):
        cleaned = super().clean()
        p = cleaned.get("p")
        location = cleaned.get("location_ft")
        if p and location is None:
            raise forms.ValidationError("Enter a location for this point load.")
        if location is not None and not p:
            raise forms.ValidationError("Enter a magnitude for this point load.")
        return cleaned

    def has_load(self) -> bool:
        return bool(self.cleaned_data.get("p"))


PointLoadFormSet = forms.formset_factory(PointLoadForm, extra=0, min_num=6)


class DistributedLoadForm(forms.Form):
    w = forms.FloatField(
        label="Load intensity", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
    )
    start_ft = forms.FloatField(
        label="Start from left end (ft)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
    )
    end_ft = forms.FloatField(
        label="End from left end (ft)", required=False, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-control form-control-sm"}),
    )
    load_type = forms.ChoiceField(
        label="Type", choices=LOAD_TYPE_CHOICES, required=False, initial="live",
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )

    def clean(self):
        cleaned = super().clean()
        w = cleaned.get("w")
        start = cleaned.get("start_ft")
        end = cleaned.get("end_ft")
        if w and (start is None or end is None):
            raise forms.ValidationError("Enter both start and end locations for this distributed load.")
        if (start is not None or end is not None) and not w:
            raise forms.ValidationError("Enter an intensity for this distributed load.")
        if w and start is not None and end is not None and end <= start:
            raise forms.ValidationError("End location must be greater than start location.")
        return cleaned

    def has_load(self) -> bool:
        return bool(self.cleaned_data.get("w"))


DistributedLoadFormSet = forms.formset_factory(DistributedLoadForm, extra=0, min_num=6)
