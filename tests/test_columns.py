from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from beams.models import BeamProject, ColumnDesign
from engine import Section, design_column, get_material


class ColumnDesignerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="columns@example.com", password="test-password",
        )
        self.client.force_login(self.user)

    def _post(self, action="run", **overrides):
        data = {
            "action": action,
            "material": "spf_no2",
            "nominal_size": "2x6",
            "plies": 3,
            "dead_load_lb": 10000,
            "live_load_lb": 5000,
            "snow_load_lb": 0,
            "roof_live_load_lb": 0,
            "wind_load_lb": 0,
            "height_ft": 8,
            "unbraced_length_d_ft": "",
            "unbraced_length_b_ft": "",
            "end_condition": "1.0",
            "lateral_load_plf": "",
            "lateral_load_type": "wind",
            "bending_unbraced_length_ft": "",
        }
        data.update(overrides)
        return self.client.post(reverse("beams:column"), data)

    def test_run_shows_result(self):
        response = self._post(action="run")
        self.assertEqual(response.status_code, 200)
        result = response.context["result"]
        self.assertEqual(result.compression.governing_combo, "D+L")
        self.assertAlmostEqual(result.compression.ratio, 0.835, places=2)

    def test_save_creates_column_and_detail_recomputes(self):
        response = self._post(action="save", name="Garage Post", project="")
        column = ColumnDesign.objects.get(name="Garage Post")
        self.assertRedirects(response, reverse("beams:column_detail", args=[column.pk]))
        self.assertEqual(column.user, self.user)
        self.assertEqual(column.plies, 3)

        # Stored inputs recompute to the same result the engine gives directly.
        result = column.compute_result()
        direct = design_column(
            {"dead": 10000, "live": 5000, "snow": 0, "roof_live": 0, "wind": 0},
            Section.from_nominal("2x6", plies=3), get_material("spf_no2"),
            unbraced_length_d=96.0, unbraced_length_b=96.0, ke=1.0,
        )
        self.assertAlmostEqual(result.compression.ratio, direct.compression.ratio, places=6)

        detail = self.client.get(reverse("beams:column_detail", args=[column.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Garage Post")

        pdf = self.client.get(reverse("beams:column_export_pdf", args=[column.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")

    def test_glulam_column_forces_single_ply(self):
        response = self._post(action="save", name="Glulam Post", material="gl_24f_1_8e",
                              nominal_size="gl_5.125x12", plies=3, height_ft=12)
        column = ColumnDesign.objects.get(name="Glulam Post")
        self.assertRedirects(response, reverse("beams:column_detail", args=[column.pk]))
        self.assertEqual(column.plies, 1)  # glulam is monolithic

    def test_material_size_mismatch_is_rejected(self):
        response = self._post(action="run", material="spf_no2", nominal_size="lvl_14")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("result", response.context)
        self.assertFormError(response.context["form"], "nominal_size",
                             "A sawn-lumber material needs a sawn-lumber section.")

    def test_saved_column_can_belong_to_project(self):
        project = BeamProject.objects.create(user=self.user, name="Job 42")
        self._post(action="save", name="Ridge Post", project=project.pk)
        column = ColumnDesign.objects.get(name="Ridge Post")
        self.assertEqual(column.project, project)

    def test_project_package_includes_columns(self):
        project = BeamProject.objects.create(user=self.user, name="Job 99")
        self._post(action="save", name="Corner Post", project=project.pk)

        pdf = self.client.get(reverse("beams:project_export_pdf", args=[project.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        csv_resp = self.client.get(reverse("beams:project_export_csv", args=[project.pk]))
        body = csv_resp.content.decode()
        self.assertIn("Columns", body)
        self.assertIn("Corner Post", body)

    def test_project_detail_lists_columns(self):
        project = BeamProject.objects.create(user=self.user, name="Job 7")
        self._post(action="save", name="Deck Post", project=project.pk)
        detail = self.client.get(reverse("beams:project_detail", args=[project.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Deck Post")

    def test_beam_column_run_and_save_detail_pdf(self):
        # A lateral load turns the column into a beam-column (interaction check).
        run = self._post(action="run", material="dfl_no1", nominal_size="4x6", plies=1,
                         dead_load_lb=3000, live_load_lb=1000, height_ft=10,
                         lateral_load_plf=120, lateral_load_type="wind")
        result = run.context["result"]
        self.assertTrue(hasattr(result, "interaction"))
        self.assertEqual(result.interaction.governing_combo, "D+W")
        self.assertAlmostEqual(result.interaction.ratio, 0.617, places=2)

        save = self._post(action="save", name="Wind Stud", material="dfl_no1", nominal_size="4x6", plies=1,
                          dead_load_lb=3000, live_load_lb=1000, height_ft=10,
                          lateral_load_plf=120, lateral_load_type="wind")
        column = ColumnDesign.objects.get(name="Wind Stud")
        self.assertRedirects(save, reverse("beams:column_detail", args=[column.pk]))
        self.assertTrue(column.is_beam_column)
        # Saved inputs recompute to a beam-column result.
        recomputed = column.compute_result()
        self.assertTrue(hasattr(recomputed, "interaction"))
        self.assertAlmostEqual(recomputed.interaction.ratio, 0.617, places=2)

        detail = self.client.get(reverse("beams:column_detail", args=[column.pk]))
        self.assertContains(detail, "beam-column")
        pdf = self.client.get(reverse("beams:column_export_pdf", args=[column.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_beam_column_in_project_package(self):
        project = BeamProject.objects.create(user=self.user, name="Job Wind")
        self._post(action="save", name="Braced Stud", project=project.pk, material="dfl_no1",
                   nominal_size="4x6", dead_load_lb=3000, height_ft=10, lateral_load_plf=100)
        pdf = self.client.get(reverse("beams:project_export_pdf", args=[project.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))
        csv_resp = self.client.get(reverse("beams:project_export_csv", args=[project.pk]))
        self.assertIn("Braced Stud", csv_resp.content.decode())
