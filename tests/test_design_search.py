from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from beams.models import BeamDesign, BeamProject


class DesignWorkspaceFilterTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            email="workspace@example.com",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.project = BeamProject.objects.create(
            user=self.user,
            name="Maple Street Addition",
            client_name="Jordan Smith",
            site_address="42 Maple Street",
        )
        self.empty_project = BeamProject.objects.create(
            user=self.user,
            name="Future Garage",
            client_name="Avery Taylor",
            status="on_hold",
        )
        self.passing = BeamDesign.objects.create(
            user=self.user,
            project=self.project,
            name="Kitchen Header",
            member_type="beam_header",
            span_ft=8,
            nominal_size="2x12",
            dead_load_plf=10,
            live_load_plf=20,
        )
        self.failing = BeamDesign.objects.create(
            user=self.user,
            project=self.project,
            name="Long Floor Beam",
            member_type="floor_joist",
            span_ft=20,
            nominal_size="2x4",
            dead_load_plf=100,
            live_load_plf=300,
        )

    def test_directory_includes_empty_projects_and_searches_project_context(self):
        response = self.client.get(reverse("beams:list"))

        self.assertContains(response, "Future Garage")
        self.assertContains(response, "0 designs")
        self.assertEqual(response.context["result_count"], 2)

        response = self.client.get(reverse("beams:list"), {"q": "Jordan Smith"})
        self.assertContains(response, "Maple Street Addition")
        self.assertContains(response, "Kitchen Header")
        self.assertNotContains(response, "Future Garage")

        status_response = self.client.get(reverse("beams:list"), {"project_status": "on_hold"})
        self.assertContains(status_response, "Future Garage")
        self.assertNotContains(status_response, "Maple Street Addition")
        self.assertEqual(status_response.context["result_count"], 0)

    def test_status_filter_and_csv_export_use_the_same_result_set(self):
        passing_response = self.client.get(reverse("beams:list"), {"status": "pass"})
        self.assertEqual(passing_response.context["result_count"], 1)
        self.assertContains(passing_response, "Kitchen Header")
        self.assertNotContains(passing_response, "Long Floor Beam")

        failing_export = self.client.get(reverse("beams:export_list_csv"), {"status": "fail"})
        csv_text = failing_export.content.decode()
        self.assertIn("Long Floor Beam", csv_text)
        self.assertNotIn("Kitchen Header", csv_text)

    def test_design_search_and_ownership_scope(self):
        other_user = get_user_model().objects.create_user(
            email="private-workspace@example.com",
            password="test-password",
        )
        private_project = BeamProject.objects.create(user=other_user, name="Private Project")
        BeamDesign.objects.create(
            user=other_user,
            project=private_project,
            name="Private Beam",
            member_type="beam_header",
            span_ft=8,
            nominal_size="2x12",
            live_load_plf=20,
        )

        response = self.client.get(reverse("beams:list"), {"q": "Kitchen"})
        self.assertEqual(response.context["result_count"], 1)
        self.assertContains(response, "Kitchen Header")
        self.assertNotContains(response, "Long Floor Beam")

        unfiltered = self.client.get(reverse("beams:list"))
        self.assertNotContains(unfiltered, "Private Project")
        self.assertNotContains(unfiltered, "Private Beam")
