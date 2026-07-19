import csv

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Max, Q
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View
from django.views.generic import ListView

from engine import (
    PointLoad,
    Section,
    UniformLoad,
    clear_span,
    default_deflection_settings,
    design_beam,
    get_material,
)
from engine.sections import GLULAM_SIZES, LVL_SIZES, NOMINAL_SIZES

from .choices import MEMBER_TYPE_CHOICES
from .continuous import (
    blank_extra_span_rows,
    full_span_values,
    interior_bearing_values,
    parse_extra_span_rows,
    support_type_sequence,
)
from .forms import (
    BeamDesignForm,
    BeamProjectForm,
    DistributedLoadFormSet,
    PointLoadFormSet,
)
from .load_inputs import (
    build_uniform_loads,
    entered_uniform_loads_to_plf,
    normalize_uniform_component,
)
from .models import (
    BeamDesign,
    BeamLoadTemplate,
    BeamProject,
    BeamProjectIssue,
    BeamProjectIssueMember,
)
from .pdf import render_beam_design_pdf, render_project_pdf

MEMBER_TYPE_LABEL_MAP = dict(MEMBER_TYPE_CHOICES)

COPYABLE_DESIGN_FIELDS = (
    "project", "member_type", "performance_profile", "subfloor_profile",
    "span_ft", "span_2_ft", "span_3_ft", "span_mode",
    "left_overhang_ft", "right_overhang_ft",
    "uniform_load_basis", "spacing_in",
    "dead_load_plf", "live_load_plf", "snow_load_plf", "roof_live_load_plf", "wind_load_plf",
    "material", "service_condition", "nominal_size", "plies", "repetitive", "unbraced_length_ft",
    "bearing_length_left_in", "bearing_length_mid_in", "bearing_length_mid_2_in", "bearing_length_right_in",
    "support_type_left", "support_type_mid", "support_type_mid_2", "support_type_right",
    "deflection_limit_live", "deflection_limit_total",
    "cantilever_deflection_limit_live", "cantilever_deflection_limit_total",
)

TAB_FIELDS = {
    "spans": (
        "span_ft", "span_2_ft", "span_3_ft", "span_mode", "left_overhang_ft", "right_overhang_ft",
        "support_type_left", "support_type_mid", "support_type_mid_2", "support_type_right",
        "bearing_length_left_in", "bearing_length_mid_in", "bearing_length_mid_2_in", "bearing_length_right_in",
    ),
    "loads": (
        "uniform_load_basis", "spacing_in",
        "dead_load_plf", "live_load_plf", "snow_load_plf",
        "roof_live_load_plf", "wind_load_plf",
    ),
    "settings": (
        "project", "new_project_name", "name", "member_type", "performance_profile", "subfloor_profile",
        "material", "service_condition", "nominal_size", "plies", "repetitive", "unbraced_length_ft",
        "deflection_limit_live", "deflection_limit_total",
        "cantilever_deflection_limit_live", "cantilever_deflection_limit_total",
    ),
}


def _active_tab(form, *formsets):
    if any(
        formset.non_form_errors() or any(row_form.errors for row_form in formset)
        for formset in formsets
    ):
        return "loads"
    for tab, fields in TAB_FIELDS.items():
        if any(form.errors.get(field) for field in fields):
            return tab
    if form.non_field_errors():
        return "loads"
    return "spans"


def _build_loads(form, point_load_formset, distributed_load_formset, total_length):
    """total_length: span + left/right overhangs -- point loads may be
    located anywhere on the member, including on an overhang, not just
    within the back span."""
    data = form.cleaned_data
    loads = build_uniform_loads(data)

    point_load_dicts = []
    for pl_form in point_load_formset:
        if not pl_form.has_load():
            continue
        location = pl_form.cleaned_data["location_ft"]
        if location > total_length:
            pl_form.add_error("location_ft", "Location must be within the member's overall length.")
            continue
        load_type = pl_form.cleaned_data.get("load_type") or "live"
        loads.append(PointLoad(p=pl_form.cleaned_data["p"], location=location, load_type=load_type))
        point_load_dicts.append(
            {"p": pl_form.cleaned_data["p"], "location_ft": location, "load_type": load_type},
        )
    distributed_load_dicts = []
    basis = data.get("uniform_load_basis") or "plf"
    spacing_in = data.get("spacing_in") or 0
    for load_form in distributed_load_formset:
        if not load_form.has_load():
            continue
        start = load_form.cleaned_data["start_ft"]
        end = load_form.cleaned_data["end_ft"]
        if end > total_length:
            load_form.add_error("end_ft", "End location must be within the member's overall length.")
            continue
        load_type = load_form.cleaned_data.get("load_type") or "live"
        entered_w = load_form.cleaned_data["w"]
        w_plf = normalize_uniform_component(entered_w, basis, spacing_in)
        loads.append(UniformLoad(w=w_plf, start=start, end=end, load_type=load_type))
        distributed_load_dicts.append({
            "w": entered_w,
            "w_plf": w_plf,
            "basis": basis,
            "start_ft": start,
            "end_ft": end,
            "load_type": load_type,
        })
    return loads, point_load_dicts, distributed_load_dicts


def _run_design(data, loads, nominal_size):
    """Run design_beam for a given nominal size using form data."""
    # Glulam is a monolithic section (no ply multiplier); its size id
    # already encodes the full width.
    plies = 1 if get_material(data["material"]).is_glulam else (data.get("plies") or 1)
    section = Section.from_nominal(nominal_size, plies=plies)
    span_values = full_span_values(data)
    continuous_spans = span_values if len(span_values) > 1 else None
    bearing_lengths = None
    if continuous_spans:
        bearing_lengths = [data["bearing_length_left_in"], *interior_bearing_values(data), data["bearing_length_right_in"]]
    # Blank deflection-limit fields fall back to the member-type/profile
    # default (mirrors BeamDesign.compute_result for saved designs).
    limit_defaults = default_deflection_settings(
        data["member_type"],
        data.get("performance_profile") or "code_minimum",
        data.get("subfloor_profile") or "none",
    )
    return design_beam(
        span=data["span_ft"],
        loads=loads,
        section=section,
        material=get_material(data["material"]),
        repetitive=data["repetitive"],
        bearing_length_left=data["bearing_length_left_in"],
        bearing_length_right=data["bearing_length_right_in"],
        deflection_limit_live=data.get("deflection_limit_live") or limit_defaults["deflection_limit_live"],
        deflection_limit_total=data.get("deflection_limit_total") or limit_defaults["deflection_limit_total"],
        cantilever_deflection_limit_live=(
            data.get("cantilever_deflection_limit_live") or limit_defaults["cantilever_deflection_limit_live"]
        ),
        cantilever_deflection_limit_total=(
            data.get("cantilever_deflection_limit_total") or limit_defaults["cantilever_deflection_limit_total"]
        ),
        span_mode=data["span_mode"],
        left_overhang=data.get("left_overhang_ft") or 0,
        right_overhang=data.get("right_overhang_ft") or 0,
        continuous_spans=continuous_spans,
        bearing_lengths=bearing_lengths,
        unbraced_length=(data.get("unbraced_length_ft") or 0) * 12 or None,
        wet_service=(data.get("service_condition") or "dry") == "wet",
    )


def _analysis_total_length(data):
    span_values = full_span_values(data)
    if len(span_values) > 1:
        bearing_lengths = [
            data["bearing_length_left_in"],
            *interior_bearing_values(data),
            data["bearing_length_right_in"],
        ]
        clear_spans = [
            clear_span(span, data["span_mode"], bearing_lengths[i], bearing_lengths[i + 1])
            for i, span in enumerate(span_values)
        ]
    else:
        clear_spans = [clear_span(
            data["span_ft"],
            data["span_mode"],
            data["bearing_length_left_in"],
            data["bearing_length_right_in"],
        )]
    return sum(clear_spans) + (data.get("left_overhang_ft") or 0) + (data.get("right_overhang_ft") or 0)


def _copy_initial(design):
    initial = {field: getattr(design, field) for field in COPYABLE_DESIGN_FIELDS}
    base_name = design.name or f"{design.nominal_size} design"
    initial["name"] = f"{base_name[:94]} Copy"
    return initial


def _revision_initial(design):
    initial = _copy_initial(design)
    initial["name"] = design.name
    initial["revision_note"] = ""
    return initial


def _copy_extra_span_rows(design):
    rows = blank_extra_span_rows()
    support_types = design.extra_interior_support_types or []
    bearings = design.extra_interior_bearing_lengths_in or []
    for index, span in enumerate((design.extra_spans_ft or [])[:len(rows)]):
        rows[index]["span_ft"] = f"{float(span):g}"
        if index < len(support_types):
            rows[index]["support_type"] = support_types[index]
        if index < len(bearings):
            rows[index]["bearing_length_in"] = f"{float(bearings[index]):g}"
    return rows


def _copy_distributed_loads(design):
    rows = []
    spacing_factor = (design.spacing_in or 0) / 12
    for load in (design.distributed_loads or [])[:6]:
        entered_w = load.get("w")
        if entered_w is None:
            entered_w = load["w_plf"] / spacing_factor if design.uniform_load_basis == "psf" and spacing_factor else load["w_plf"]
        rows.append({
            "w": entered_w,
            "start_ft": load["start_ft"],
            "end_ft": load["end_ft"],
            "load_type": load["load_type"],
        })
    return rows


def _copy_point_loads(design):
    return [
        {"p": load["p"], "location_ft": load["location_ft"], "load_type": load["load_type"]}
        for load in (design.point_loads or [])[:6]
    ]


def _load_template_payloads(user):
    return [template.as_payload() for template in BeamLoadTemplate.objects.filter(user=user)]


def _filtered_design_queryset(user, query="", project_status=""):
    designs = BeamDesign.objects.filter(user=user, revisions__isnull=True).select_related("project")
    if project_status:
        designs = designs.filter(project__status=project_status)
    if query:
        designs = designs.filter(
            Q(name__icontains=query)
            | Q(project__name__icontains=query)
            | Q(project__client_name__icontains=query)
            | Q(project__site_address__icontains=query)
            | Q(project__project_number__icontains=query)
            | Q(member_type__icontains=query)
            | Q(material__icontains=query)
            | Q(nominal_size__icontains=query)
        )
    return designs.order_by("project__name", "-created_at")


def _filtered_design_rows(user, query="", status="", project_status=""):
    rows = [
        (design, design.compute_result())
        for design in _filtered_design_queryset(user, query, project_status)
    ]
    if status == "pass":
        return [(design, result) for design, result in rows if result.passed]
    if status == "fail":
        return [(design, result) for design, result in rows if not result.passed]
    return rows


def _nonnegative_post_float(data, field_name, default=0.0):
    raw_value = data.get(field_name, "")
    if raw_value in (None, ""):
        return default
    value = float(raw_value)
    if value < 0:
        raise ValueError
    return value


class BeamDesignView(LoginRequiredMixin, View):
    template_name = "beams/design.html"

    def get(self, request):
        initial = {}
        source_design = None
        revision_mode = False
        revise_id = request.GET.get("revise", "")
        copy_id = request.GET.get("copy", "")
        if revise_id.isdigit():
            source_design = get_object_or_404(BeamDesign, pk=int(revise_id), user=request.user)
            initial.update(_revision_initial(source_design))
            revision_mode = True
        elif copy_id.isdigit():
            source_design = get_object_or_404(BeamDesign, pk=int(copy_id), user=request.user)
            initial.update(_copy_initial(source_design))
        project_id = request.GET.get("project", "")
        if project_id.isdigit():
            initial["project"] = get_object_or_404(BeamProject, pk=int(project_id), user=request.user)
        if request.GET.get("size") in NOMINAL_SIZES or request.GET.get("size") in LVL_SIZES or request.GET.get("size") in GLULAM_SIZES:
            initial["nominal_size"] = request.GET["size"]
        context = {
            "form": BeamDesignForm(initial=initial, user=request.user),
            "point_load_formset": PointLoadFormSet(
                prefix="pl", initial=_copy_point_loads(source_design) if source_design else None,
            ),
            "distributed_load_formset": DistributedLoadFormSet(
                prefix="dl", initial=_copy_distributed_loads(source_design) if source_design else None,
            ),
            "active_tab": "spans",
            "extra_span_rows": _copy_extra_span_rows(source_design) if source_design else blank_extra_span_rows(),
            "source_design": source_design,
            "revision_mode": revision_mode,
            "load_templates": _load_template_payloads(request.user),
        }
        return render(request, self.template_name, context)

    def post(self, request):
        form = BeamDesignForm(request.POST, user=request.user)
        formset = PointLoadFormSet(request.POST, prefix="pl")
        distributed_formset = DistributedLoadFormSet(request.POST, prefix="dl")
        extra_span_payload = parse_extra_span_rows(request.POST)
        context = {
            "form": form,
            "point_load_formset": formset,
            "distributed_load_formset": distributed_formset,
            "extra_span_rows": extra_span_payload["rows"],
            "load_templates": _load_template_payloads(request.user),
        }
        revision_source = None
        revision_source_id = request.POST.get("revision_source_id", "")
        source_id = request.POST.get("source_design_id", "")
        if revision_source_id.isdigit():
            revision_source = get_object_or_404(
                BeamDesign, pk=int(revision_source_id), user=request.user,
            )
            context["source_design"] = revision_source
            context["revision_mode"] = True
        if source_id.isdigit():
            context["source_design"] = get_object_or_404(BeamDesign, pk=int(source_id), user=request.user)

        def error_response():
            context["active_tab"] = _active_tab(form, formset, distributed_formset)
            return render(request, self.template_name, context)

        if not (form.is_valid() and formset.is_valid() and distributed_formset.is_valid()):
            return error_response()
        if revision_source:
            latest_revision = BeamDesign.objects.filter(
                user=request.user,
                revision_group=revision_source.revision_group,
            ).order_by("-revision_number").first()
            if latest_revision.pk != revision_source.pk:
                form.add_error(
                    None,
                    "A newer revision already exists. Open the current revision before revising again.",
                )
                return error_response()
        data = dict(form.cleaned_data)
        data["extra_spans_ft"] = extra_span_payload["extra_spans"]
        data["extra_interior_support_types"] = extra_span_payload["extra_support_types"]
        data["extra_interior_bearing_lengths_in"] = extra_span_payload["extra_bearings"]
        span = data["span_ft"]
        span_2 = data.get("span_2_ft") or 0
        span_3 = data.get("span_3_ft") or 0
        left_overhang = data.get("left_overhang_ft") or 0
        right_overhang = data.get("right_overhang_ft") or 0
        total_input_length = _analysis_total_length(data)
        loads, point_load_dicts, distributed_load_dicts = _build_loads(
            form, formset, distributed_formset, total_input_length,
        )

        if any(pl_form.errors for pl_form in formset) or any(load_form.errors for load_form in distributed_formset):
            return error_response()

        if not loads:
            form.add_error(None, "Enter at least one load (uniform or point).")
            return error_response()

        action = request.POST.get("action", "run")

        if action == "all_sizes" and len(full_span_values(data)) > 1:
            form.add_error(None, "All Sizes is not yet supported for multi-span mode. Run a single section for now.")
            return error_response()

        if action == "save":
            project = data.get("project")
            new_project_name = (data.get("new_project_name") or "").strip()
            if new_project_name:
                project, _ = BeamProject.objects.get_or_create(
                    user=request.user,
                    name=new_project_name,
                )
            revision_number = 1
            revision_group = None
            if revision_source:
                revision_group = revision_source.revision_group
                revision_number = (
                    BeamDesign.objects.filter(
                        user=request.user, revision_group=revision_group,
                    ).aggregate(number=Max("revision_number"))["number"] or 0
                ) + 1
            revision_fields = {
                "revision_number": revision_number,
                "revision_note": data.get("revision_note") or "",
                "supersedes": revision_source,
            }
            if revision_group:
                revision_fields["revision_group"] = revision_group
            design = BeamDesign.objects.create(
                user=request.user,
                project=project,
                name=data["name"],
                member_type=data["member_type"],
                performance_profile=data["performance_profile"],
                subfloor_profile=data["subfloor_profile"],
                span_ft=span,
                span_2_ft=data.get("span_2_ft"),
                span_3_ft=data.get("span_3_ft"),
                extra_spans_ft=data.get("extra_spans_ft") or [],
                span_mode=data["span_mode"],
                left_overhang_ft=left_overhang,
                right_overhang_ft=right_overhang,
                uniform_load_basis=data["uniform_load_basis"],
                spacing_in=data["spacing_in"] or 16,
                dead_load_plf=data.get("dead_load_plf") or 0,
                live_load_plf=data.get("live_load_plf") or 0,
                snow_load_plf=data.get("snow_load_plf") or 0,
                roof_live_load_plf=data.get("roof_live_load_plf") or 0,
                wind_load_plf=data.get("wind_load_plf") or 0,
                material=data["material"],
                service_condition=data.get("service_condition") or "dry",
                nominal_size=data["nominal_size"],
                plies=data.get("plies") or 1,
                repetitive=data["repetitive"],
                unbraced_length_ft=data.get("unbraced_length_ft"),
                bearing_length_left_in=data["bearing_length_left_in"],
                bearing_length_mid_in=data.get("bearing_length_mid_in"),
                bearing_length_mid_2_in=data.get("bearing_length_mid_2_in"),
                extra_interior_bearing_lengths_in=data.get("extra_interior_bearing_lengths_in") or [],
                bearing_length_right_in=data["bearing_length_right_in"],
                support_type_left=data["support_type_left"],
                support_type_mid=data.get("support_type_mid") or "wall_plate",
                support_type_mid_2=data.get("support_type_mid_2") or "wall_plate",
                extra_interior_support_types=data.get("extra_interior_support_types") or [],
                support_type_right=data["support_type_right"],
                deflection_limit_live=data["deflection_limit_live"],
                deflection_limit_total=data["deflection_limit_total"],
                cantilever_deflection_limit_live=data["cantilever_deflection_limit_live"],
                cantilever_deflection_limit_total=data["cantilever_deflection_limit_total"],
                point_loads=point_load_dicts,
                distributed_loads=distributed_load_dicts,
                **revision_fields,
            )
            return redirect("beams:detail", pk=design.pk)

        if action == "all_sizes":
            # Run all sizes, find most economical (first passing in size order)
            scan_rows = []
            economy_size = None
            economy_ratio = None
            # Scan the size set matching the selected material's category.
            scan_material = get_material(data["material"])
            if scan_material.is_lvl:
                scan_sizes = LVL_SIZES
            elif scan_material.is_glulam:
                scan_sizes = GLULAM_SIZES
            else:
                scan_sizes = NOMINAL_SIZES
            for nominal in scan_sizes:
                result = _run_design(data, loads, nominal)
                scan_rows.append({"nominal": nominal, "result": result, "passed": result.passed})
                if result.passed and economy_size is None:
                    economy_size = nominal
                    economy_ratio = result.governing.ratio

            context["scan_rows"] = scan_rows
            context["economy_size"] = economy_size
            context["economy_ratio"] = economy_ratio
            context["span"] = span
            context["span_2"] = span_2
            context["span_3"] = span_3
            context["extra_spans"] = data.get("extra_spans_ft") or []
            context["uniform_load_basis"] = data["uniform_load_basis"]
            context["spacing_in"] = data.get("spacing_in") or 16
            context["dead"] = data.get("dead_load_plf") or 0
            context["live"] = data.get("live_load_plf") or 0
            context["snow"] = data.get("snow_load_plf") or 0
            context["roof_live"] = data.get("roof_live_load_plf") or 0
            context["wind"] = data.get("wind_load_plf") or 0
            context["repetitive"] = data["repetitive"]
            context["member_type_label"] = MEMBER_TYPE_LABEL_MAP.get(data["member_type"], data["member_type"])
            context["material_label"] = get_material(data["material"]).name
            return render(request, "beams/all_sizes.html", context)

        # Default: run single analysis
        context["result"] = _run_design(data, loads, data["nominal_size"])
        context["distributed_loads"] = distributed_load_dicts
        context["support_type_sequence"] = support_type_sequence(data)[:len(context["result"].summary.support_positions)]
        context["active_tab"] = "spans"
        return render(request, self.template_name, context)


class BeamDesignListView(LoginRequiredMixin, ListView):
    model = BeamDesign
    template_name = "beams/list.html"
    context_object_name = "designs"

    def get_queryset(self):
        project_status = self.request.GET.get("project_status", "")
        if project_status not in dict(BeamProject.STATUS_CHOICES):
            project_status = ""
        return _filtered_design_queryset(
            self.request.user,
            self.request.GET.get("q", "").strip(),
            project_status,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        query = self.request.GET.get("q", "").strip()
        status = self.request.GET.get("status", "")
        if status not in {"pass", "fail"}:
            status = ""
        project_status = self.request.GET.get("project_status", "")
        if project_status not in dict(BeamProject.STATUS_CHOICES):
            project_status = ""
        rows = _filtered_design_rows(self.request.user, query, status, project_status)
        grouped = []
        current_project_id = object()
        current_group = None
        for design, result in rows:
            project_id = design.project_id or "unassigned"
            if project_id != current_project_id:
                current_group = {
                    "project": design.project,
                    "rows": [],
                }
                grouped.append(current_group)
                current_project_id = project_id
            current_group["rows"].append((design, result))
        context["rows"] = rows
        context["project_groups"] = grouped
        projects = BeamProject.objects.filter(user=self.request.user).annotate(
            design_count=Count("designs", filter=Q(designs__revisions__isnull=True)),
        )
        if query:
            projects = projects.filter(
                Q(name__icontains=query)
                | Q(client_name__icontains=query)
                | Q(site_address__icontains=query)
                | Q(project_number__icontains=query)
                | Q(designs__name__icontains=query)
            ).distinct()
        if project_status:
            projects = projects.filter(status=project_status)
        context["projects"] = projects
        context["project_count"] = BeamProject.objects.filter(user=self.request.user).count()
        context["total_design_count"] = BeamDesign.objects.filter(
            user=self.request.user, revisions__isnull=True,
        ).count()
        context["result_count"] = len(rows)
        context["search_query"] = query
        context["status_filter"] = status
        context["project_status_filter"] = project_status
        context["project_status_choices"] = BeamProject.STATUS_CHOICES
        context["filters_active"] = bool(query or status or project_status)
        return context


class BeamProjectCreateView(LoginRequiredMixin, View):
    template_name = "beams/project_form.html"

    def get(self, request):
        return render(request, self.template_name, {"form": BeamProjectForm(), "project": None})

    def post(self, request):
        form = BeamProjectForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "project": None})
        project = form.save(commit=False)
        project.user = request.user
        project.save()
        return redirect("beams:project_detail", pk=project.pk)


class BeamProjectDetailView(LoginRequiredMixin, View):
    template_name = "beams/project_detail.html"

    def get(self, request, pk):
        project = get_object_or_404(BeamProject, pk=pk, user=request.user)
        rows = [
            (design, design.compute_result())
            for design in project.designs.filter(revisions__isnull=True)
        ]
        return render(request, self.template_name, {
            "project": project,
            "rows": rows,
            "passing_count": sum(1 for _, result in rows if result.passed),
            "failing_count": sum(1 for _, result in rows if not result.passed),
            "issues": project.issues.select_related("created_by").all(),
        })


class BeamProjectUpdateView(LoginRequiredMixin, View):
    template_name = "beams/project_form.html"

    def get_project(self, request, pk):
        return get_object_or_404(BeamProject, pk=pk, user=request.user)

    def get(self, request, pk):
        project = self.get_project(request, pk)
        return render(request, self.template_name, {"form": BeamProjectForm(instance=project), "project": project})

    def post(self, request, pk):
        project = self.get_project(request, pk)
        form = BeamProjectForm(request.POST, instance=project)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "project": project})
        form.save()
        return redirect("beams:project_detail", pk=project.pk)


class BeamProjectExportCSVView(LoginRequiredMixin, View):
    def get(self, request, pk):
        project = get_object_or_404(BeamProject, pk=pk, user=request.user)
        response = HttpResponse(content_type="text/csv")
        filename = project.name.replace(" ", "_") or f"project-{project.pk}"
        response["Content-Disposition"] = f'attachment; filename="{filename}_designs.csv"'
        writer = csv.writer(response)
        writer.writerow(["Project", project.name])
        writer.writerow(["Project number", project.project_number])
        writer.writerow(["Project status", project.get_status_display()])
        writer.writerow(["Client", project.client_name])
        writer.writerow(["Site address", project.site_address])
        writer.writerow(["Notes", project.notes])
        writer.writerow([])
        writer.writerow([
            "Name", "Revision", "Revision note", "Member type", "Material", "Spans (ft)", "Section",
            "Governing check", "Ratio", "Status", "Created",
        ])
        for design in project.designs.filter(revisions__isnull=True):
            result = design.compute_result()
            writer.writerow([
                design.name or f"Beam design #{design.pk}",
                design.revision_number,
                design.revision_note,
                MEMBER_TYPE_LABEL_MAP.get(design.member_type, design.member_type),
                design.get_material_display(),
                design.span_display,
                design.section_label,
                result.governing.name,
                f"{result.governing.ratio:.3f}",
                "PASS" if result.passed else "FAIL",
                design.created_at.isoformat(),
            ])
        return response


class BeamProjectExportPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        project = get_object_or_404(BeamProject, pk=pk, user=request.user)
        design_results = [
            (design, design.compute_result())
            for design in project.designs.select_related("project").filter(revisions__isnull=True)
        ]
        pdf_bytes = render_project_pdf(project, design_results)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = project.name.replace(" ", "_") or f"project-{project.pk}"
        response["Content-Disposition"] = f'attachment; filename="{filename}_calculation_package.pdf"'
        return response


class BeamProjectIssueCreateView(LoginRequiredMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(BeamProject, pk=pk, user=request.user)
        label = request.POST.get("label", "").strip()
        notes = request.POST.get("notes", "").strip()
        selected_ids = [value for value in request.POST.getlist("design_ids") if value.isdigit()]
        selected_designs = {
            str(design.pk): design
            for design in BeamDesign.objects.filter(
                user=request.user,
                project=project,
                revisions__isnull=True,
                pk__in=[int(value) for value in selected_ids],
            )
        }
        ordered_designs = [selected_designs[value] for value in selected_ids if value in selected_designs]

        if not label or len(label) > 80:
            messages.error(request, "Enter an issue label of 80 characters or fewer.")
            return redirect("beams:project_detail", pk=project.pk)
        if len(notes) > 240:
            messages.error(request, "Issue notes must be 240 characters or fewer.")
            return redirect("beams:project_detail", pk=project.pk)
        if not ordered_designs:
            messages.error(request, "Select at least one current member design for the issue package.")
            return redirect("beams:project_detail", pk=project.pk)

        issue = BeamProjectIssue.objects.create(
            project=project,
            created_by=request.user,
            label=label,
            notes=notes,
        )
        BeamProjectIssueMember.objects.bulk_create([
            BeamProjectIssueMember(issue=issue, design_revision=design, position=position)
            for position, design in enumerate(ordered_designs)
        ])
        return redirect("beams:project_issue_pdf", pk=project.pk, issue_pk=issue.pk)


class BeamProjectIssuePDFView(LoginRequiredMixin, View):
    def get(self, request, pk, issue_pk):
        project = get_object_or_404(BeamProject, pk=pk, user=request.user)
        issue = get_object_or_404(BeamProjectIssue, pk=issue_pk, project=project)
        ordered_designs = [
            member.design_revision
            for member in issue.members.select_related("design_revision").all()
        ]
        design_results = [(design, design.compute_result()) for design in ordered_designs]
        pdf_bytes = render_project_pdf(project, design_results, issue=issue)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        project_name = project.name.replace(" ", "_") or f"project-{project.pk}"
        issue_label = issue.label.replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="{project_name}_{issue_label}.pdf"'
        return response


class BeamDesignDetailView(LoginRequiredMixin, View):
    template_name = "beams/detail.html"

    def get(self, request, pk):
        design = get_object_or_404(BeamDesign, pk=pk, user=request.user)
        result = design.compute_result()
        revision_history = BeamDesign.objects.filter(
            user=request.user,
            revision_group=design.revision_group,
        ).order_by("-revision_number")
        context = {
            "design": design,
            "result": result,
            "distributed_loads": design.distributed_loads,
            "support_type_sequence": [
                design.support_type_left,
                *design.interior_support_type_values,
                design.support_type_right,
            ][:len(result.summary.support_positions)],
            "revision_history": revision_history,
            "current_revision": revision_history.first(),
        }
        return render(request, self.template_name, context)


class BeamDesignDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        design = get_object_or_404(BeamDesign, pk=pk, user=request.user)
        try:
            design.delete()
        except ProtectedError:
            messages.error(
                request,
                "This revision is part of an issued project package and cannot be deleted.",
            )
            return redirect("beams:detail", pk=design.pk)
        return redirect("beams:list")


class BeamLoadTemplateCreateView(LoginRequiredMixin, View):
    def post(self, request):
        name = (request.POST.get("load_template_name") or "").strip()
        if not name:
            return JsonResponse({"error": "Enter a template name."}, status=400)
        if len(name) > 80:
            return JsonResponse({"error": "Template names are limited to 80 characters."}, status=400)

        basis = request.POST.get("uniform_load_basis") or "plf"
        if basis not in {"psf", "plf"}:
            return JsonResponse({"error": "Choose a valid load basis."}, status=400)
        try:
            spacing_in = _nonnegative_post_float(request.POST, "spacing_in", 16)
            if spacing_in <= 0:
                raise ValueError
            baseline = {
                field: _nonnegative_post_float(request.POST, field)
                for field in (
                    "dead_load_plf", "live_load_plf", "snow_load_plf",
                    "roof_live_load_plf", "wind_load_plf",
                )
            }
        except (TypeError, ValueError):
            return JsonResponse({"error": "Load values and spacing must be valid nonnegative numbers."}, status=400)

        point_formset = PointLoadFormSet(request.POST, prefix="pl")
        distributed_formset = DistributedLoadFormSet(request.POST, prefix="dl")
        if not (point_formset.is_valid() and distributed_formset.is_valid()):
            return JsonResponse({"error": "Complete or clear invalid load rows before saving the template."}, status=400)

        point_loads = [
            {
                "p": form.cleaned_data["p"],
                "location_ft": form.cleaned_data["location_ft"],
                "load_type": form.cleaned_data.get("load_type") or "live",
            }
            for form in point_formset
            if form.has_load()
        ]
        distributed_loads = [
            {
                "w": form.cleaned_data["w"],
                "start_ft": form.cleaned_data["start_ft"],
                "end_ft": form.cleaned_data["end_ft"],
                "load_type": form.cleaned_data.get("load_type") or "live",
            }
            for form in distributed_formset
            if form.has_load()
        ]
        if not any(baseline.values()) and not point_loads and not distributed_loads:
            return JsonResponse({"error": "Enter at least one load before saving a template."}, status=400)

        template, created = BeamLoadTemplate.objects.update_or_create(
            user=request.user,
            name=name,
            defaults={
                "uniform_load_basis": basis,
                "spacing_in": spacing_in,
                **baseline,
                "point_loads": point_loads,
                "distributed_loads": distributed_loads,
            },
        )
        return JsonResponse({"template": template.as_payload(), "created": created})


class BeamLoadTemplateDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        template = get_object_or_404(BeamLoadTemplate, pk=pk, user=request.user)
        template.delete()
        return JsonResponse({"deleted": pk})


def _check_rows_for_csv(result):
    return [
        (
            c.name, f"{c.demand:.3f}", f"{c.capacity:.3f}", f"{c.ratio:.3f}", c.governing_combo,
            "OK" if c.passed else "FAIL",
            f"{c.required_length:.3f}" if c.required_length is not None else "",
        )
        for c in result.checks
    ]


class BeamDesignExportCSVView(LoginRequiredMixin, View):
    def get(self, request, pk):
        design = get_object_or_404(BeamDesign, pk=pk, user=request.user)
        result = design.compute_result()

        response = HttpResponse(content_type="text/csv")
        filename = (design.name or f"beam-design-{design.pk}").replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="{filename}.csv"'
        writer = csv.writer(response)

        writer.writerow(["Design", design.name or f"Beam design #{design.pk}"])
        writer.writerow(["Project", design.project.name if design.project else ""])
        writer.writerow(["Member type", MEMBER_TYPE_LABEL_MAP.get(design.member_type, design.member_type)])
        writer.writerow(["Performance target", design.get_performance_profile_display()])
        writer.writerow(["Subfloor / floor feel target", design.get_subfloor_profile_display()])
        writer.writerow(["Span mode", design.get_span_mode_display()])
        for index, span_value in enumerate(design.entered_spans, start=1):
            label = "Span, as given (ft)" if index == 1 else f"Span {index}, as given (ft)"
            writer.writerow([label, span_value])
        writer.writerow(["Span, clear/analysis (ft)", f"{result.summary.span:.3f}"])
        if result.summary.support_positions and len(result.summary.support_positions) > 2:
            writer.writerow(["Continuous total length (ft)", f"{result.summary.total_length:.3f}"])
            for index, clear_span in enumerate(result.summary.span_segments, start=1):
                writer.writerow([f"Analysis span B{index}-B{index + 1} (ft)", f"{clear_span:.3f}"])
        writer.writerow(["Section", f"{design.section_label} {result.summary.material_name}"])
        writer.writerow(["Plies", design.plies])
        writer.writerow(["Uniform load basis", design.uniform_load_basis])
        writer.writerow(["Spacing (in)", design.spacing_in])
        entered_unit = "psf" if design.uniform_load_basis == "psf" else "plf"
        writer.writerow([f"Dead load (entered {entered_unit})", design.dead_load_plf])
        writer.writerow([f"Live load (entered {entered_unit})", design.live_load_plf])
        writer.writerow([f"Snow load (entered {entered_unit})", design.snow_load_plf])
        writer.writerow([f"Roof live load (entered {entered_unit})", design.roof_live_load_plf])
        writer.writerow([f"Wind load (entered {entered_unit})", design.wind_load_plf])
        normalized = entered_uniform_loads_to_plf({
            "uniform_load_basis": design.uniform_load_basis,
            "spacing_in": design.spacing_in,
            "dead_load_plf": design.dead_load_plf,
            "live_load_plf": design.live_load_plf,
            "snow_load_plf": design.snow_load_plf,
            "roof_live_load_plf": design.roof_live_load_plf,
            "wind_load_plf": design.wind_load_plf,
        })
        writer.writerow(["Dead load (analysis plf)", f"{normalized['dead']:.3f}"])
        writer.writerow(["Live load (analysis plf)", f"{normalized['live']:.3f}"])
        writer.writerow(["Snow load (analysis plf)", f"{normalized['snow']:.3f}"])
        writer.writerow(["Roof live load (analysis plf)", f"{normalized['roof_live']:.3f}"])
        writer.writerow(["Wind load (analysis plf)", f"{normalized['wind']:.3f}"])
        for index, load in enumerate(design.distributed_loads, start=1):
            writer.writerow([
                f"Distributed zone {index}",
                f"{load['w']:g} {load.get('basis', design.uniform_load_basis)}",
                f"{load['w_plf']:g} plf",
                str(load["load_type"]).replace("_", " ").title(),
                f"{load['start_ft']:g} ft to {load['end_ft']:g} ft",
            ])
        for index, load in enumerate(design.point_loads, start=1):
            writer.writerow([
                f"Point load {index}",
                f"{load['p']:g} lb",
                str(load["load_type"]).replace("_", " ").title(),
                f"at {load['location_ft']:g} ft",
            ])
        writer.writerow(["Repetitive", design.repetitive])
        if design.service_condition == "wet":
            writer.writerow(["Service condition", "Wet / exterior"])
            writer.writerow(["CM (Fb, Fv, Fc_perp, E)", (
                f"{result.summary.cm_fb:.2f}, {result.summary.cm_fv:.2f}, "
                f"{result.summary.cm_fcperp:.2f}, {result.summary.cm_e:.2f}"
            )])
        else:
            writer.writerow(["Service condition", "Dry / interior (CM = 1.0)"])
        if design.unbraced_length_ft:
            writer.writerow(["Unbraced compression edge (ft)", design.unbraced_length_ft])
            writer.writerow(["Beam stability factor CL", f"{result.summary.cl:.3f}"])
            writer.writerow(["Slenderness ratio RB", f"{result.summary.rb:.1f}"])
        else:
            writer.writerow(["Compression edge bracing", "Continuously braced (CL = 1.0)"])
        defaults = default_deflection_settings(
            design.member_type,
            design.performance_profile,
            design.subfloor_profile,
        )
        writer.writerow([
            "Back-span live/snow deflection limit",
            f"L/{design.deflection_limit_live or defaults['deflection_limit_live']}",
        ])
        writer.writerow([
            "Back-span total-load deflection limit",
            f"L/{design.deflection_limit_total or defaults['deflection_limit_total']}",
        ])
        writer.writerow([
            "Cantilever live/snow deflection limit",
            f"L/{design.cantilever_deflection_limit_live or defaults['cantilever_deflection_limit_live']}",
        ])
        writer.writerow([
            "Cantilever total-load deflection limit",
            f"L/{design.cantilever_deflection_limit_total or defaults['cantilever_deflection_limit_total']}",
        ])
        writer.writerow(["Bearing length B1 (left, in)", design.bearing_length_left_in])
        for support in design.support_schedule[1:-1]:
            writer.writerow([f"Bearing length {support['label']} (interior, in)", support["bearing_length_in"]])
        writer.writerow([f"Bearing length {design.support_schedule[-1]['label']} (right, in)", design.bearing_length_right_in])
        writer.writerow(["Support B1 (left)", design.get_support_type_left_display()])
        for support in design.support_schedule[1:-1]:
            writer.writerow([f"Support {support['label']} (interior)", support["support_type"]])
        writer.writerow([f"Support {design.support_schedule[-1]['label']} (right)", design.get_support_type_right_display()])
        writer.writerow(["Overall", "PASS" if result.passed else "FAIL"])
        writer.writerow(["Governing check", result.governing.name, f"{result.governing.ratio:.3f}"])
        writer.writerow([])
        writer.writerow(["Check", "Demand", "Capacity", "Ratio", "Combo", "Status", "Required Length (in)"])
        writer.writerows(_check_rows_for_csv(result))
        return response


class BeamDesignExportPDFView(LoginRequiredMixin, View):
    def get(self, request, pk):
        design = get_object_or_404(BeamDesign, pk=pk, user=request.user)
        result = design.compute_result()
        pdf_bytes = render_beam_design_pdf(design, result)

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        filename = (design.name or f"beam-design-{design.pk}").replace(" ", "_")
        response["Content-Disposition"] = f'attachment; filename="{filename}.pdf"'
        return response


class BeamDesignExportListCSVView(LoginRequiredMixin, View):
    def get(self, request):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="beam_designs.csv"'
        writer = csv.writer(response)
        writer.writerow([
            "Project", "Project status", "Name", "Revision", "Member type", "Material", "Span (ft)", "Section", "Governing check",
            "Ratio", "Status", "Created",
        ])
        query = request.GET.get("q", "").strip()
        status = request.GET.get("status", "")
        if status not in {"pass", "fail"}:
            status = ""
        project_status = request.GET.get("project_status", "")
        if project_status not in dict(BeamProject.STATUS_CHOICES):
            project_status = ""
        for design, result in _filtered_design_rows(request.user, query, status, project_status):
            span_label = design.span_display
            writer.writerow([
                design.project.name if design.project else "",
                design.project.get_status_display() if design.project else "",
                design.name or f"Beam design #{design.pk}",
                design.revision_number,
                MEMBER_TYPE_LABEL_MAP.get(design.member_type, design.member_type),
                design.get_material_display(),
                span_label,
                f"{design.section_label} {design.get_material_display()}",
                result.governing.name,
                f"{result.governing.ratio:.3f}",
                "PASS" if result.passed else "FAIL",
                design.created_at.isoformat(),
            ])
        return response
