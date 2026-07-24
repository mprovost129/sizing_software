from django.urls import path

from . import views

app_name = "beams"

urlpatterns = [
    path("design/", views.BeamDesignView.as_view(), name="design"),
    path("settings/", views.SettingsView.as_view(), name="settings"),
    path("column/", views.ColumnDesignView.as_view(), name="column"),
    path("connection/", views.ConnectionDesignView.as_view(), name="connection"),
    path("connection/<int:pk>/", views.ConnectionDesignDetailView.as_view(), name="connection_detail"),
    path("connection/<int:pk>/delete/", views.ConnectionDesignDeleteView.as_view(), name="connection_delete"),
    path("connection/<int:pk>/export/pdf/", views.ConnectionDesignExportPDFView.as_view(), name="connection_export_pdf"),
    path("column/<int:pk>/", views.ColumnDesignDetailView.as_view(), name="column_detail"),
    path("column/<int:pk>/delete/", views.ColumnDesignDeleteView.as_view(), name="column_delete"),
    path("column/<int:pk>/export/pdf/", views.ColumnDesignExportPDFView.as_view(), name="column_export_pdf"),
    path("load-templates/create/", views.BeamLoadTemplateCreateView.as_view(), name="create_load_template"),
    path("load-templates/<int:pk>/delete/", views.BeamLoadTemplateDeleteView.as_view(), name="delete_load_template"),
    path("projects/new/", views.BeamProjectCreateView.as_view(), name="project_create"),
    path("projects/<int:pk>/", views.BeamProjectDetailView.as_view(), name="project_detail"),
    path("projects/<int:pk>/edit/", views.BeamProjectUpdateView.as_view(), name="project_update"),
    path("projects/<int:pk>/export/csv/", views.BeamProjectExportCSVView.as_view(), name="project_export_csv"),
    path("projects/<int:pk>/export/pdf/", views.BeamProjectExportPDFView.as_view(), name="project_export_pdf"),
    path("projects/<int:pk>/issues/create/", views.BeamProjectIssueCreateView.as_view(), name="project_issue_create"),
    path("projects/<int:pk>/issues/<int:issue_pk>/pdf/", views.BeamProjectIssuePDFView.as_view(), name="project_issue_pdf"),
    path("", views.BeamDesignListView.as_view(), name="list"),
    path("export/csv/", views.BeamDesignExportListCSVView.as_view(), name="export_list_csv"),
    path("<int:pk>/", views.BeamDesignDetailView.as_view(), name="detail"),
    path("<int:pk>/delete/", views.BeamDesignDeleteView.as_view(), name="delete"),
    path("<int:pk>/export/csv/", views.BeamDesignExportCSVView.as_view(), name="export_csv"),
    path("<int:pk>/export/pdf/", views.BeamDesignExportPDFView.as_view(), name="export_pdf"),
]
