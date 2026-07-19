from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from beams.models import BeamDesign, BeamProject, BeamProjectIssue


class BeamProjectWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="projects@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_create_edit_detail_export_and_designer_preselection(self):
        create_response = self.client.post(reverse("beams:project_create"), {
            "name": "Provost Residence",
            "project_number": "P-2601",
            "status": "active",
            "client_name": "Michael Provost",
            "site_address": "100 Main Street",
            "notes": "Second-floor framing package.",
        })

        project = BeamProject.objects.get(user=self.user)
        self.assertRedirects(create_response, reverse("beams:project_detail", args=[project.pk]))

        detail_response = self.client.get(reverse("beams:project_detail", args=[project.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "Michael Provost")
        self.assertEqual(detail_response.context["rows"], [])

        edit_response = self.client.post(reverse("beams:project_update", args=[project.pk]), {
            "name": "Provost Residence - Phase 2",
            "project_number": "P-2601",
            "status": "complete",
            "client_name": "Michael Provost",
            "site_address": "100 Main Street",
            "notes": "Updated scope.",
        })
        self.assertRedirects(edit_response, reverse("beams:project_detail", args=[project.pk]))
        project.refresh_from_db()
        self.assertEqual(project.name, "Provost Residence - Phase 2")
        self.assertEqual(project.status, "complete")

        designer_response = self.client.get(reverse("beams:design"), {"project": project.pk})
        self.assertEqual(designer_response.status_code, 200)
        self.assertEqual(designer_response.context["form"].initial["project"], project)

        export_response = self.client.get(reverse("beams:project_export_csv", args=[project.pk]))
        self.assertEqual(export_response.status_code, 200)
        self.assertIn("Provost_Residence_-_Phase_2_designs.csv", export_response["Content-Disposition"])
        self.assertIn("Updated scope.", export_response.content.decode())
        self.assertIn("P-2601", export_response.content.decode())
        self.assertIn("Complete", export_response.content.decode())

    def test_project_routes_are_scoped_to_owner(self):
        other_user = get_user_model().objects.create_user(
            email="other-projects@example.com",
            password="test-password",
        )
        project = BeamProject.objects.create(user=other_user, name="Private Project")
        issue = BeamProjectIssue.objects.create(
            project=project, created_by=other_user, label="Private Issue",
        )

        protected_urls = [
            reverse("beams:project_detail", args=[project.pk]),
            reverse("beams:project_update", args=[project.pk]),
            reverse("beams:project_export_csv", args=[project.pk]),
            reverse("beams:project_export_pdf", args=[project.pk]),
            reverse("beams:project_issue_pdf", args=[project.pk, issue.pk]),
        ]
        for url in protected_urls:
            self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(reverse("beams:design"), {"project": project.pk}).status_code, 404)

    def test_selective_issue_package_freezes_revisions_and_protects_them(self):
        project = BeamProject.objects.create(user=self.user, name="Issued Project")
        included = BeamDesign.objects.create(
            user=self.user,
            project=project,
            name="Included Header",
            member_type="beam_header",
            span_ft=8,
            nominal_size="2x12",
            live_load_plf=20,
        )
        excluded = BeamDesign.objects.create(
            user=self.user,
            project=project,
            name="Excluded Header",
            member_type="beam_header",
            span_ft=7,
            nominal_size="2x10",
            live_load_plf=20,
        )

        response = self.client.post(reverse("beams:project_issue_create", args=[project.pk]), {
            "label": "Permit Set",
            "notes": "Selected member only.",
            "design_ids": [included.pk],
        })
        issue = BeamProjectIssue.objects.get(project=project)
        self.assertRedirects(
            response,
            reverse("beams:project_issue_pdf", args=[project.pk, issue.pk]),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            list(issue.members.values_list("design_revision_id", flat=True)),
            [included.pk],
        )
        self.assertNotIn(excluded.pk, issue.members.values_list("design_revision_id", flat=True))

        issued_pdf = self.client.get(
            reverse("beams:project_issue_pdf", args=[project.pk, issue.pk]),
        )
        self.assertEqual(issued_pdf.status_code, 200)
        self.assertTrue(issued_pdf.content.startswith(b"%PDF"))
        self.assertGreater(len(issued_pdf.content), 5_000)

        revised = BeamDesign.objects.create(
            user=self.user,
            project=project,
            name="Included Header",
            member_type="beam_header",
            span_ft=8,
            nominal_size="2x12",
            live_load_plf=20,
            revision_group=included.revision_group,
            revision_number=2,
            supersedes=included,
        )
        with patch("beams.views.render_project_pdf", return_value=b"%PDF-snapshot") as renderer:
            pdf_response = self.client.get(
                reverse("beams:project_issue_pdf", args=[project.pk, issue.pk]),
            )
        self.assertEqual(pdf_response.status_code, 200)
        issued_design_results = renderer.call_args.args[1]
        self.assertEqual([design.pk for design, _ in issued_design_results], [included.pk])
        self.assertNotEqual(issued_design_results[0][0].pk, revised.pk)

        delete_response = self.client.post(reverse("beams:delete", args=[included.pk]))
        self.assertRedirects(delete_response, reverse("beams:detail", args=[included.pk]))
        self.assertTrue(BeamDesign.objects.filter(pk=included.pk).exists())

    def test_project_pdf_package_supports_populated_and_empty_projects(self):
        project = BeamProject.objects.create(
            user=self.user,
            name="Oak Lane Package",
            client_name="Taylor Owner",
            site_address="18 Oak Lane",
            notes="Issue for preliminary review.",
        )
        BeamDesign.objects.create(
            user=self.user,
            project=project,
            name="Garage Header",
            member_type="beam_header",
            span_ft=8,
            nominal_size="2x12",
            dead_load_plf=10,
            live_load_plf=20,
        )

        response = self.client.get(reverse("beams:project_export_pdf", args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("Oak_Lane_Package_calculation_package.pdf", response["Content-Disposition"])
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertGreater(len(response.content), 5_000)

        empty_project = BeamProject.objects.create(user=self.user, name="Empty Package")
        empty_response = self.client.get(reverse("beams:project_export_pdf", args=[empty_project.pk]))
        self.assertEqual(empty_response.status_code, 200)
        self.assertTrue(empty_response.content.startswith(b"%PDF"))
