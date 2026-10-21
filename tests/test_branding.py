"""Brand identity and isolated, one-time migration of legacy preferences."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import call, patch


from PyQt5.QtCore import QByteArray, QSettings

from easytextdiff.branding import APP_NAME, DISPLAY_NAME, VERSION
from easytextdiff.preferences import load_settings


class BrandingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="easytextdiff-preferences-")
        self.root = Path(self.temporary.name)
        self.destination = QSettings(str(self.root / "new.ini"), QSettings.IniFormat)
        self.legacy = QSettings(str(self.root / "legacy.ini"), QSettings.IniFormat)

    def tearDown(self):
        self.destination.sync()
        self.legacy.sync()
        self.temporary.cleanup()

    def test_public_identity(self):
        self.assertEqual(APP_NAME, "EasyTextDiff")
        self.assertEqual(DISPLAY_NAME, "轻松文本对比")
        self.assertEqual(VERSION, "1.2.3")

    def test_missing_preferences_migrate_without_changing_legacy(self):
        geometry = QByteArray(b"window-geometry")
        self.legacy.setValue("theme", "dark")
        self.legacy.setValue("geometry", geometry)
        self.legacy.setValue("automatic", False)
        result = load_settings(self.destination, self.legacy)
        self.assertIs(result, self.destination)
        self.assertEqual(result.value("theme"), "dark")
        self.assertEqual(result.value("geometry"), geometry)
        self.assertFalse(result.value("automatic", True, type=bool))
        self.assertTrue(result.value("_migration/brand_v1", False, type=bool))
        self.assertEqual(set(self.legacy.allKeys()), {"theme", "geometry", "automatic"})
        self.assertFalse(self.legacy.value("automatic", True, type=bool))

    def test_existing_new_preferences_are_never_overwritten(self):
        self.destination.setValue("theme", "light")
        self.destination.setValue("automatic", False)
        self.legacy.setValue("theme", "dark")
        self.legacy.setValue("automatic", True)
        self.legacy.setValue("geometry", QByteArray(b"old-geometry"))
        result = load_settings(destination=self.destination, legacy=self.legacy)
        self.assertEqual(result.value("theme"), "light")
        self.assertFalse(result.value("automatic", True, type=bool))
        self.assertEqual(result.value("geometry"), QByteArray(b"old-geometry"))

    def test_only_allowlisted_legacy_preferences_are_copied(self):
        self.legacy.setValue("theme", "system")
        self.legacy.setValue("recent_files", ["private.txt"])
        self.legacy.setValue("unrelated/value", "do not migrate")
        result = load_settings(self.destination, self.legacy)
        self.assertEqual(set(result.allKeys()), {"theme", "_migration/brand_v1"})
        self.assertFalse(result.contains("recent_files"))
        self.assertFalse(result.contains("unrelated/value"))

    def test_migration_is_one_time_even_if_a_new_key_is_later_removed(self):
        self.legacy.setValue("theme", "dark")
        load_settings(self.destination, self.legacy)
        self.destination.remove("theme")
        self.legacy.setValue("theme", "light")
        self.legacy.setValue("automatic", True)
        load_settings(self.destination, self.legacy)
        self.assertFalse(self.destination.contains("theme"))
        self.assertFalse(self.destination.contains("automatic"))

    def test_preexisting_migration_marker_prevents_all_legacy_copies(self):
        self.destination.setValue("_migration/brand_v1", True)
        self.legacy.setValue("theme", "dark")
        load_settings(self.destination, self.legacy)
        self.assertFalse(self.destination.contains("theme"))

    def test_default_namespaces_use_new_identity_and_read_old_identity(self):
        # Patch construction itself: this test never touches the Windows registry.
        with patch("easytextdiff.preferences.QSettings", side_effect=[self.destination, self.legacy]) as factory:
            result = load_settings()
        self.assertIs(result, self.destination)
        self.assertEqual(factory.call_args_list, [call("EasyTextDiff", "EasyTextDiff"),
                                                call("QingDiff", "QingDiff")])


if __name__ == "__main__":
    unittest.main()
