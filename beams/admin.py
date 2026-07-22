from django.contrib import admin

from .models import (
    BeamDesign,
    BeamProject,
    BeamProjectIssue,
    ColumnDesign,
    ConnectionDesign,
)

admin.site.register(BeamProject)
admin.site.register(BeamProjectIssue)


@admin.register(ConnectionDesign)
class ConnectionDesignAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "fastener_type", "diameter_in", "shear_planes", "created_at")
    list_filter = ("fastener_type", "shear_planes")
    search_fields = ("name", "user__email")


@admin.register(ColumnDesign)
class ColumnDesignAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "material", "nominal_size", "plies", "height_ft", "created_at")
    list_filter = ("material", "nominal_size")
    search_fields = ("name", "user__email")


@admin.register(BeamDesign)
class BeamDesignAdmin(admin.ModelAdmin):
    list_display = ("__str__", "user", "member_type", "nominal_size", "plies", "span_ft", "created_at")
    list_filter = ("member_type", "nominal_size", "plies", "repetitive")
    search_fields = ("name", "user__email")
