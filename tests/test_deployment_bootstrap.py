import ast
import os
import shlex
from datetime import date
from pathlib import Path
from unittest import TestCase as SimpleTestCase
from unittest.mock import patch

from django.core.management import call_command
from django.test import Client, TestCase

from ai_features.models import ClimateScenario
from data_ingestion.models import ClimateHazardData, GreenBond
from greenwash_detector.models import GreenwashFlag
from pricing_analysis.models import PricingGap
from risk_scoring.models import PCRScore


class AllowedHostsConfigurationTests(SimpleTestCase):
    def test_build_imports_registry_with_required_file_option(self):
        from data_ingestion.management.commands.load_cbi_bonds import Command

        build_path = Path(__file__).resolve().parents[1] / "build.sh"
        commands = [shlex.split(line) for line in build_path.read_text().splitlines()]
        registry_command = next(command for command in commands if "load_cbi_bonds" in command)
        parser = Command().create_parser("manage.py", "load_cbi_bonds")
        options = parser.parse_args(registry_command[3:])

        self.assertEqual(options.file, "data/green_bonds-21.csv")
        self.assertFalse(any(
            "loaddata" in command and "greenwash_fixture.json" in command
            for command in commands
        ))

    def test_comma_separated_hosts_are_trimmed_and_empty_hosts_removed(self):
        settings_path = Path(__file__).resolve().parents[1] / "greenlens" / "settings.py"
        settings_tree = ast.parse(settings_path.read_text())
        assignments = [
            node for node in settings_tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "ALLOWED_HOSTS"
                    for target in node.targets)
        ]
        namespace = {"os": os}
        with patch.dict(os.environ, {
            "ALLOWED_HOSTS": " one.example, two.example, ,",
            "RAILWAY_PUBLIC_DOMAIN": "railway.example",
            "RENDER_EXTERNAL_HOSTNAME": "render.example",
        }):
            exec(compile(ast.Module(body=assignments, type_ignores=[]), str(settings_path), "exec"), namespace)

        hosts = namespace["ALLOWED_HOSTS"]
        for hostname in ("one.example", "two.example", "railway.example", "render.example", "localhost"):
            self.assertIn(hostname, hosts)
        self.assertNotIn("", hosts)
        self.assertFalse(any("," in host or host != host.strip() for host in hosts))


class DeploymentBootstrapTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.client = Client(HTTP_HOST="localhost")
        cls.bond = GreenBond.objects.create(
            bond_id="DEPLOY_001",
            issuer_name="Deployment Test Issuer",
            country="India",
            project_category="solar",
            project_description="Deployment bootstrap test bond",
            bond_maturity_years=9,
            issuance_date=date(2024, 4, 1),
            currency="USD",
            amount_millions=125,
            lat=20.5937,
            lon=78.9629,
            location_confidence="country",
        )
        ClimateScenario.objects.create(
            scenario_type="ssp2_4_5",
            description="SSP2-4.5",
            warming_by_2050=2.1,
            warming_by_2100=2.7,
        )

    def test_initialize_demo_data_backfills_missing_layers(self):
        call_command("initialize_demo_data", limit=10)

        self.assertEqual(ClimateHazardData.objects.filter(bond=self.bond).count(), 1)
        self.assertEqual(PCRScore.objects.filter(bond=self.bond).count(), 1)
        self.assertEqual(PricingGap.objects.filter(bond=self.bond).count(), 1)
        self.assertEqual(GreenwashFlag.objects.filter(bond=self.bond).count(), 1)

        flag = GreenwashFlag.objects.get(bond=self.bond)
        self.assertEqual(flag.verification_status, "unverifiable")
        self.assertFalse(flag.is_inconsistent)
        self.assertEqual(flag.confidence, 0.0)
        self.assertIsNone(flag.pre_project_image_date)
        self.assertIsNone(flag.post_project_image_date)

    def test_predictions_page_handles_unscored_database(self):
        response = self.client.get("/ai/predictions/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AI Climate Predictions")

    def test_homepage_handles_real_pcr_score_field(self):
        call_command("initialize_demo_data", limit=10)
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Global Bond Portfolio")
