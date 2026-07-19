import uuid

from django.conf import settings
from django.db import models

from engine import (
    SIZE_LABELS,
    PointLoad,
    Section,
    UniformLoad,
    default_deflection_settings,
    design_beam,
    get_material,
)
from engine.checks import BeamDesignResult

from .choices import (
    ALL_SIZE_CHOICES,
    DEFAULT_MATERIAL,
    DEFAULT_PLIES,
    DEFAULT_SERVICE_CONDITION,
    MATERIAL_CHOICES,
    MEMBER_TYPE_CHOICES,
    PERFORMANCE_PROFILE_CHOICES,
    PLY_CHOICES,
    SERVICE_CONDITION_CHOICES,
    SPAN_MODE_CHOICES,
    SUBFLOOR_PROFILE_CHOICES,
    SUPPORT_TYPE_CHOICES,
)
from .load_inputs import build_uniform_loads


class BeamProject(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("on_hold", "On Hold"),
        ("complete", "Complete"),
        ("archived", "Archived"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="beam_projects",
    )
    name = models.CharField(max_length=120)
    project_number = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    client_name = models.CharField(max_length=120, blank=True)
    site_address = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "-updated_at"]

    def __str__(self):
        return self.name


class BeamProjectIssue(models.Model):
    project = models.ForeignKey(BeamProject, on_delete=models.CASCADE, related_name="issues")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="beam_project_issues",
    )
    label = models.CharField(max_length=80)
    notes = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.project.name} - {self.label}"


class BeamProjectIssueMember(models.Model):
    issue = models.ForeignKey(BeamProjectIssue, on_delete=models.CASCADE, related_name="members")
    design_revision = models.ForeignKey(
        "BeamDesign", on_delete=models.PROTECT, related_name="project_issue_memberships",
    )
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["position", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=("issue", "design_revision"), name="unique_design_revision_per_project_issue",
            ),
        ]


class BeamLoadTemplate(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="beam_load_templates",
    )
    name = models.CharField(max_length=80)
    uniform_load_basis = models.CharField(max_length=10, default="plf")
    spacing_in = models.FloatField(default=16)
    dead_load_plf = models.FloatField(default=0)
    live_load_plf = models.FloatField(default=0)
    snow_load_plf = models.FloatField(default=0)
    roof_live_load_plf = models.FloatField(default=0)
    wind_load_plf = models.FloatField(default=0)
    point_loads = models.JSONField(default=list, blank=True)
    distributed_loads = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=("user", "name"), name="unique_beam_load_template_name_per_user"),
        ]

    def __str__(self):
        return self.name

    def as_payload(self):
        return {
            "id": self.pk,
            "name": self.name,
            "uniform_load_basis": self.uniform_load_basis,
            "spacing_in": self.spacing_in,
            "dead_load_plf": self.dead_load_plf,
            "live_load_plf": self.live_load_plf,
            "snow_load_plf": self.snow_load_plf,
            "roof_live_load_plf": self.roof_live_load_plf,
            "wind_load_plf": self.wind_load_plf,
            "point_loads": self.point_loads,
            "distributed_loads": self.distributed_loads,
        }


class BeamDesign(models.Model):
    MAX_CONTINUOUS_SPANS = 10

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="beam_designs",
    )
    project = models.ForeignKey(
        BeamProject, on_delete=models.SET_NULL, null=True, blank=True, related_name="designs",
    )
    name = models.CharField(max_length=100, blank=True)
    revision_group = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
    revision_number = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revisions",
    )
    revision_note = models.CharField(max_length=240, blank=True)
    member_type = models.CharField(max_length=40, choices=MEMBER_TYPE_CHOICES)
    performance_profile = models.CharField(max_length=30, choices=PERFORMANCE_PROFILE_CHOICES, default="code_minimum")
    subfloor_profile = models.CharField(max_length=30, choices=SUBFLOOR_PROFILE_CHOICES, default="none")
    span_ft = models.FloatField()
    span_mode = models.CharField(max_length=20, choices=SPAN_MODE_CHOICES, default="inside")
    span_2_ft = models.FloatField(null=True, blank=True)
    span_3_ft = models.FloatField(null=True, blank=True)
    extra_spans_ft = models.JSONField(default=list, blank=True)
    left_overhang_ft = models.FloatField(default=0)
    right_overhang_ft = models.FloatField(default=0)
    uniform_load_basis = models.CharField(max_length=10, default="plf")
    spacing_in = models.FloatField(default=16)
    dead_load_plf = models.FloatField(default=0)
    live_load_plf = models.FloatField(default=0)
    snow_load_plf = models.FloatField(default=0)
    roof_live_load_plf = models.FloatField(default=0)
    wind_load_plf = models.FloatField(default=0)
    material = models.CharField(max_length=20, choices=MATERIAL_CHOICES, default=DEFAULT_MATERIAL)
    service_condition = models.CharField(
        max_length=10, choices=SERVICE_CONDITION_CHOICES, default=DEFAULT_SERVICE_CONDITION,
    )
    nominal_size = models.CharField(max_length=20, choices=ALL_SIZE_CHOICES)
    plies = models.PositiveSmallIntegerField(choices=PLY_CHOICES, default=DEFAULT_PLIES)
    repetitive = models.BooleanField(default=False)
    # Unbraced length of the compression edge, ft. Null/blank means the
    # compression edge is continuously braced (beam stability factor CL = 1.0).
    unbraced_length_ft = models.FloatField(null=True, blank=True)
    bearing_length_left_in = models.FloatField(default=1.5)
    bearing_length_mid_in = models.FloatField(null=True, blank=True)
    bearing_length_mid_2_in = models.FloatField(null=True, blank=True)
    extra_interior_bearing_lengths_in = models.JSONField(default=list, blank=True)
    bearing_length_right_in = models.FloatField(default=1.5)
    support_type_left = models.CharField(
        max_length=20, choices=SUPPORT_TYPE_CHOICES, default="wall_plate",
    )
    support_type_mid = models.CharField(
        max_length=20, choices=SUPPORT_TYPE_CHOICES, default="wall_plate",
    )
    support_type_mid_2 = models.CharField(
        max_length=20, choices=SUPPORT_TYPE_CHOICES, default="wall_plate",
    )
    extra_interior_support_types = models.JSONField(default=list, blank=True)
    support_type_right = models.CharField(
        max_length=20, choices=SUPPORT_TYPE_CHOICES, default="wall_plate",
    )
    deflection_limit_live = models.PositiveIntegerField(null=True, blank=True)
    deflection_limit_total = models.PositiveIntegerField(null=True, blank=True)
    cantilever_deflection_limit_live = models.PositiveIntegerField(null=True, blank=True)
    cantilever_deflection_limit_total = models.PositiveIntegerField(null=True, blank=True)
    # Each entry: {"p": lb, "location_ft": ft, "load_type": one of the supported load types}
    point_loads = models.JSONField(default=list, blank=True)
    # Additive partial-length loads, stored normalized in plf.
    distributed_loads = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name or f"{self.nominal_size} beam, {self.span_display} ft"

    @property
    def section_label(self):
        """Human section label, prefixed with ply count for built-up
        members (e.g. "3-ply 2x10"); LVL sizes show their depth label
        (e.g. '2-ply 11-7/8"') rather than the raw id."""
        base = SIZE_LABELS.get(self.nominal_size, self.nominal_size)
        if self.plies and self.plies > 1:
            return f"{self.plies}-ply {base}"
        return base

    @property
    def entered_spans(self):
        legacy = [span for span in (self.span_ft, self.span_2_ft, self.span_3_ft) if span]
        extras = [float(span) for span in (self.extra_spans_ft or []) if span]
        return (legacy + extras)[:self.MAX_CONTINUOUS_SPANS]

    @property
    def span_display(self):
        return " + ".join(f"{span:g}" for span in self.entered_spans)

    @property
    def interior_support_type_values(self):
        interior_count = max(len(self.entered_spans) - 1, 0)
        values = []
        if interior_count >= 1:
            values.append(self.support_type_mid)
        if interior_count >= 2:
            values.append(self.support_type_mid_2)
        values.extend(str(value) for value in (self.extra_interior_support_types or []))
        return values[:interior_count]

    @property
    def interior_bearing_length_values(self):
        interior_count = max(len(self.entered_spans) - 1, 0)
        values = []
        if interior_count >= 1:
            values.append(self.bearing_length_mid_in)
        if interior_count >= 2:
            values.append(self.bearing_length_mid_2_in)
        values.extend(float(value) for value in (self.extra_interior_bearing_lengths_in or []) if value is not None)
        return values[:interior_count]

    @property
    def support_schedule(self):
        rows = [
            {"label": "B1", "bearing_length_in": self.bearing_length_left_in, "support_type": self.get_support_type_left_display()},
        ]
        support_type_labels = dict(SUPPORT_TYPE_CHOICES)
        for index, (bearing_length, support_type) in enumerate(
            zip(self.interior_bearing_length_values, self.interior_support_type_values),
            start=2,
        ):
            rows.append({
                "label": f"B{index}",
                "bearing_length_in": bearing_length,
                "support_type": support_type_labels.get(support_type, support_type),
            })
        rows.append({
            "label": f"B{len(self.entered_spans) + 1}",
            "bearing_length_in": self.bearing_length_right_in,
            "support_type": self.get_support_type_right_display(),
        })
        return rows

    def compute_result(self) -> BeamDesignResult:
        """Recompute from stored inputs -- the saved row is the source of
        truth, not a frozen snapshot, so results stay correct if the
        engine's formulas are refined later."""
        loads = build_uniform_loads({
            "uniform_load_basis": self.uniform_load_basis,
            "spacing_in": self.spacing_in,
            "dead_load_plf": self.dead_load_plf,
            "live_load_plf": self.live_load_plf,
            "snow_load_plf": self.snow_load_plf,
            "roof_live_load_plf": self.roof_live_load_plf,
            "wind_load_plf": self.wind_load_plf,
        })
        for pl in self.point_loads:
            loads.append(
                PointLoad(p=pl["p"], location=pl["location_ft"], load_type=pl["load_type"]),
            )
        for load in self.distributed_loads:
            loads.append(UniformLoad(
                w=load["w_plf"],
                start=load["start_ft"],
                end=load["end_ft"],
                load_type=load["load_type"],
            ))

        material = get_material(self.material)
        # Glulam is a monolithic section (its size id already encodes the
        # full width), so the ply multiplier never applies to it.
        plies = 1 if material.is_glulam else self.plies
        section = Section.from_nominal(self.nominal_size, plies=plies)
        limits = default_deflection_settings(self.member_type, self.performance_profile, self.subfloor_profile)
        return design_beam(
            span=self.span_ft,
            loads=loads,
            section=section,
            material=material,
            repetitive=self.repetitive,
            bearing_length_left=self.bearing_length_left_in,
            bearing_length_right=self.bearing_length_right_in,
            deflection_limit_live=self.deflection_limit_live or limits["deflection_limit_live"],
            deflection_limit_total=self.deflection_limit_total or limits["deflection_limit_total"],
            cantilever_deflection_limit_live=(
                self.cantilever_deflection_limit_live or limits["cantilever_deflection_limit_live"]
            ),
            cantilever_deflection_limit_total=(
                self.cantilever_deflection_limit_total or limits["cantilever_deflection_limit_total"]
            ),
            span_mode=self.span_mode,
            left_overhang=self.left_overhang_ft,
            right_overhang=self.right_overhang_ft,
            continuous_spans=self.entered_spans if len(self.entered_spans) > 1 else None,
            bearing_lengths=(
                [row["bearing_length_in"] for row in self.support_schedule]
                if len(self.entered_spans) > 1 else None
            ),
            unbraced_length=(self.unbraced_length_ft or 0) * 12 or None,
            wet_service=self.service_condition == "wet",
        )
