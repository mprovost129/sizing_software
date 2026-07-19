from django.contrib import admin

from .models import BeamDesign, BeamProject, BeamProjectIssue

admin.site.register(BeamProject)
admin.site.register(BeamProjectIssue)


@admin.register(BeamDesign)
class BeamDesignAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "member_type", "nominal_size", "plies", "span_ft", "created_at")
    list_filter = ("member_type", "nominal_size", "plies", "repetitive")
    search_fields = ("name", "user__email")
