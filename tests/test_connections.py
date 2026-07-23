from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from beams.models import BeamProject, ConnectionDesign


class ConnectionDesignerTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="conn@example.com", password="test-password",
        )
        self.client.force_login(self.user)

    def _post(self, action="run", **overrides):
        data = {
            "action": action,
            "loading": "lateral",
            "shear_planes": "single",
            "fastener_type": "bolt",
            "diameter_in": 0.5,
            "fyb_psi": 45000,
            "main_material": "dfl_no2",
            "main_thickness_in": 3.5,
            "side_type": "wood",
            "side_material": "dfl_no2",
            "side_thickness_in": 1.5,
            "load_direction": "parallel",
            "service_condition": "dry",
            "temperature": "normal",
            "load_duration": 1.0,
            "n_fasteners": 4,
            "load_lb": 2000,
            "fastener_spacing_in": "",
            "main_width_in": "",
            "side_width_in": "",
            "end_distance_in": "",
        }
        data.update(overrides)
        return self.client.post(reverse("beams:connection"), data)

    def test_run_shows_result(self):
        response = self._post(action="run")
        self.assertEqual(response.status_code, 200)
        result = response.context["result"]
        self.assertEqual(result.mode, "IIIs")
        self.assertAlmostEqual(result.z, 614.8, delta=1.0)
        self.assertAlmostEqual(result.ratio, 0.813, places=2)

    def test_save_creates_connection_and_detail_recomputes(self):
        response = self._post(action="save", name="Ledger Bolts", project="")
        conn = ConnectionDesign.objects.get(name="Ledger Bolts")
        self.assertRedirects(response, reverse("beams:connection_detail", args=[conn.pk]))
        self.assertEqual(conn.user, self.user)

        result = conn.compute_result()
        self.assertEqual(result.mode, "IIIs")
        self.assertAlmostEqual(result.z, 614.8, delta=1.0)

        detail = self.client.get(reverse("beams:connection_detail", args=[conn.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "Ledger Bolts")

        pdf = self.client.get(reverse("beams:connection_export_pdf", args=[conn.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_double_shear_and_group_factor_persist(self):
        self._post(action="save", name="Splice", shear_planes="double",
                   fastener_spacing_in=3, main_width_in=5.5, side_width_in=5.5, end_distance_in=3.5)
        conn = ConnectionDesign.objects.get(name="Splice")
        self.assertEqual(conn.shear_planes, "double")
        result = conn.compute_result()
        self.assertTrue(result.double_shear)
        self.assertEqual(set(result.yield_result.mode_values), {"Im", "Is", "IIIs", "IV"})
        self.assertLess(result.cg, 1.0)  # group action applied

    def test_withdrawal_save_detail_and_pdf(self):
        # Lag screw, 0.25" dia, DF-L (G=0.50), 3" penetration, 300 lb.
        self._post(action="save", name="Toe-nail Uplift", loading="withdrawal",
                   fastener_type="lag", diameter_in=0.25, main_thickness_in=3.0,
                   load_lb=300)
        conn = ConnectionDesign.objects.get(name="Toe-nail Uplift")
        self.assertEqual(conn.loading, "withdrawal")
        result = conn.compute_result()
        self.assertIsNone(getattr(result, "yield_result", None))
        self.assertTrue(result.applicable)
        # W = 1800 * 0.50^1.5 * 0.25^0.75 = 225.0 lb/in
        self.assertAlmostEqual(result.w_per_inch, 225.0, delta=1.0)

        detail = self.client.get(reverse("beams:connection_detail", args=[conn.pk]))
        self.assertEqual(detail.status_code, 200)
        pdf = self.client.get(reverse("beams:connection_export_pdf", args=[conn.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_withdrawal_bolt_not_applicable(self):
        response = self._post(action="run", loading="withdrawal", fastener_type="bolt")
        result = response.context["result"]
        self.assertFalse(result.applicable)

    def test_wet_service_reduces_lateral_capacity(self):
        dry = self._post(action="run", service_condition="dry").context["result"]
        wet = self._post(action="run", service_condition="wet").context["result"]
        self.assertEqual(wet.cm, 0.7)
        self.assertAlmostEqual(wet.capacity, 0.7 * dry.capacity, places=3)

    def test_wet_service_saved_and_recomputed(self):
        self._post(action="save", name="Wet Ledger", service_condition="wet")
        conn = ConnectionDesign.objects.get(name="Wet Ledger")
        self.assertEqual(conn.service_condition, "wet")
        self.assertEqual(conn.compute_result().cm, 0.7)

    def test_toe_nail_factor_applied_to_nails(self):
        # Toe-nail Ctn = 0.83 laterally, and only for nails/spikes.
        nail = self._post(action="run", fastener_type="nail", diameter_in=0.162,
                          fyb_psi=100000, toe_nail="on").context["result"]
        self.assertEqual(nail.ctn, 0.83)
        # A bolt marked toe-nailed gets no Ctn (not a nail).
        bolt = self._post(action="run", fastener_type="bolt", toe_nail="on").context["result"]
        self.assertEqual(bolt.ctn, 1.0)

    def test_toe_nail_withdrawal_saved(self):
        self._post(action="save", name="Toe Uplift", loading="withdrawal",
                   fastener_type="nail", diameter_in=0.148, main_thickness_in=1.5,
                   load_lb=30, toe_nail="on")
        conn = ConnectionDesign.objects.get(name="Toe Uplift")
        self.assertTrue(conn.toe_nail)
        self.assertEqual(conn.compute_result().ctn, 0.67)

    def test_temperature_factor_saved_and_stacks_with_wet(self):
        # Hot + wet -> Ct = 0.5 and CM = 0.7 both apply.
        self._post(action="save", name="Hot Wet Bolts", temperature="hot", service_condition="wet")
        conn = ConnectionDesign.objects.get(name="Hot Wet Bolts")
        self.assertEqual(conn.temperature, "hot")
        result = conn.compute_result()
        self.assertEqual(result.ct, 0.5)
        self.assertEqual(result.cm, 0.7)

    def test_edge_distance_below_minimum_fails(self):
        # 1/2" bolt needs 0.75" (1.5D) edge; 0.5" is below the minimum.
        bad = self._post(action="run", edge_distance_in=0.5).context["result"]
        self.assertFalse(bad.edge_ok)
        self.assertFalse(bad.passed)  # not permitted even though the ratio passes
        ok = self._post(action="run", edge_distance_in=1.0).context["result"]
        self.assertTrue(ok.edge_ok)
        self.assertTrue(ok.passed)

    def test_edge_distance_saved_and_recomputed(self):
        self._post(action="save", name="Edge Fail", edge_distance_in=0.5)
        conn = ConnectionDesign.objects.get(name="Edge Fail")
        self.assertEqual(conn.edge_distance_in, 0.5)
        self.assertFalse(conn.compute_result().edge_ok)

    def test_steel_side_plate_run(self):
        # 1/2" bolt into a 1/4" A36 steel side plate -> Fes = 87,000 psi.
        r = self._post(action="run", side_type="steel", steel_grade="a36",
                       side_thickness_in=0.25).context["result"]
        self.assertTrue(r.side_steel)
        self.assertAlmostEqual(r.yield_result.fes, 87000.0, places=0)

    def test_steel_side_plate_saved_detail_pdf(self):
        self._post(action="save", name="Steel Plate Bolt", side_type="steel",
                   steel_grade="a572", side_thickness_in=0.25)
        conn = ConnectionDesign.objects.get(name="Steel Plate Bolt")
        self.assertEqual(conn.side_type, "steel")
        self.assertAlmostEqual(conn.compute_result().yield_result.fes, 97500.0, places=0)

        detail = self.client.get(reverse("beams:connection_detail", args=[conn.pk]))
        self.assertContains(detail, "steel")
        pdf = self.client.get(reverse("beams:connection_export_pdf", args=[conn.pk]))
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_connection_in_project_package(self):
        project = BeamProject.objects.create(user=self.user, name="Deck Job")
        self._post(action="save", name="Post Base Bolts", project=project.pk)
        # Add a withdrawal connection so the package exercises both result shapes.
        self._post(action="save", name="Uplift Nails", project=project.pk,
                   loading="withdrawal", fastener_type="nail", diameter_in=0.131,
                   main_thickness_in=2.5, load_lb=90)

        detail = self.client.get(reverse("beams:project_detail", args=[project.pk]))
        self.assertContains(detail, "Post Base Bolts")

        pdf = self.client.get(reverse("beams:project_export_pdf", args=[project.pk]))
        self.assertEqual(pdf.status_code, 200)
        self.assertTrue(pdf.content.startswith(b"%PDF"))

        csv_resp = self.client.get(reverse("beams:project_export_csv", args=[project.pk]))
        body = csv_resp.content.decode()
        self.assertIn("Connections", body)
        self.assertIn("Post Base Bolts", body)
        self.assertIn("Uplift Nails", body)
