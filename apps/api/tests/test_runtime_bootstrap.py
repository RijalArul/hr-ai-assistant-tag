from pathlib import Path
import sys
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app import _find_shared_src


class RuntimeBootstrapTests(TestCase):
    def test_find_shared_src_detects_monorepo_shared_package(self) -> None:
        current_dir = ROOT / "apps" / "api" / "app"
        expected = ROOT / "packages" / "shared"

        self.assertEqual(_find_shared_src(current_dir), expected)

    def test_find_shared_src_returns_none_for_shallow_deploy_layout(self) -> None:
        self.assertIsNone(_find_shared_src(Path("/app/app")))
