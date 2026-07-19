from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from beams.models import BeamDesign


class BeamDesignCopyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="designer@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_saved_design_opens_as_six_row_working_copy(self):
        design = BeamDesign.objects.create(
            user=self.user,
            name="Main Floor Beam",
            member_type="beam_header",
            span_ft=12,
            span_2_ft=10,
            span_3_ft=8,
            extra_spans_ft=[7],
            extra_interior_support_types=["column"],
            extra_interior_bearing_lengths_in=[5.5],
            nominal_size="2x10",
            point_loads=[
                {"p": 900, "location_ft": 5, "load_type": "live"},
            ],
            distributed_loads=[
                {
                    "w": 80,
                    "w_plf": 80,
                    "basis": "plf",
                    "start_ft": 2,
                    "end_ft": 6,
                    "load_type": "dead",
                },
            ],
        )

        response = self.client.get(reverse("beams:design"), {"copy": design.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["source_design"], design)
        self.assertEqual(response.context["form"].initial["name"], "Main Floor Beam Copy")
        self.assertEqual(response.context["form"].initial["span_2_ft"], 10)
        self.assertEqual(len(response.context["point_load_formset"].forms), 6)
        self.assertEqual(len(response.context["distributed_load_formset"].forms), 6)
        self.assertEqual(response.context["point_load_formset"].forms[0].initial["p"], 900)
        self.assertEqual(response.context["distributed_load_formset"].forms[0].initial["w"], 80)
        self.assertEqual(response.context["extra_span_rows"][0]["span_ft"], "7")
        self.assertEqual(response.context["extra_span_rows"][0]["support_type"], "column")
        self.assertEqual(response.context["extra_span_rows"][0]["bearing_length_in"], "5.5")

    def test_copy_lookup_is_scoped_to_logged_in_user(self):
        other_user = get_user_model().objects.create_user(
            email="other@example.com",
            password="test-password",
        )
        other_design = BeamDesign.objects.create(
            user=other_user,
            member_type="beam_header",
            span_ft=10,
            nominal_size="2x8",
        )

        response = self.client.get(reverse("beams:design"), {"copy": other_design.pk})

        self.assertEqual(response.status_code, 404)

        revision_response = self.client.get(reverse("beams:design"), {"revise": other_design.pk})
        self.assertEqual(revision_response.status_code, 404)

    def test_revision_save_links_new_version_and_preserves_original(self):
        original = BeamDesign.objects.create(
            user=self.user,
            name="Revision Beam",
            member_type="beam_header",
            span_ft=8,
            nominal_size="2x10",
            dead_load_plf=10,
            live_load_plf=20,
        )

        open_response = self.client.get(reverse("beams:design"), {"revise": original.pk})
        self.assertTrue(open_response.context["revision_mode"])
        self.assertEqual(open_response.context["form"].initial["name"], "Revision Beam")

        response = self.client.post(reverse("beams:design"), {
            "revision_source_id": original.pk,
            "action": "save",
            "name": "Revision Beam",
            "revision_note": "Increased member depth.",
            "member_type": "beam_header",
            "performance_profile": "code_minimum",
            "subfloor_profile": "none",
            "span_ft": 8,
            "span_mode": "inside",
            "uniform_load_basis": "plf",
            "spacing_in": 16,
            "dead_load_plf": 10,
            "live_load_plf": 20,
            "snow_load_plf": 0,
            "roof_live_load_plf": 0,
            "wind_load_plf": 0,
            "material": "spf_no2",
            "nominal_size": "2x12",
            "bearing_length_left_in": 1.5,
            "bearing_length_right_in": 1.5,
            "support_type_left": "wall_plate",
            "support_type_right": "wall_plate",
            "pl-TOTAL_FORMS": 0,
            "pl-INITIAL_FORMS": 0,
            "dl-TOTAL_FORMS": 0,
            "dl-INITIAL_FORMS": 0,
        })

        revised = BeamDesign.objects.exclude(pk=original.pk).get(user=self.user)
        self.assertRedirects(response, reverse("beams:detail", args=[revised.pk]))
        self.assertEqual(revised.supersedes, original)
        self.assertEqual(revised.revision_group, original.revision_group)
        self.assertEqual(revised.revision_number, 2)
        self.assertEqual(revised.revision_note, "Increased member depth.")
        original.refresh_from_db()
        self.assertEqual(original.nominal_size, "2x10")

        list_response = self.client.get(reverse("beams:list"))
        self.assertEqual(list_response.context["result_count"], 1)

        old_detail = self.client.get(reverse("beams:detail", args=[original.pk]))
        self.assertEqual(old_detail.context["current_revision"], revised)
        self.assertEqual(list(old_detail.context["revision_history"]), [revised, original])
