"""Application preferences and one-time migration from the former identity."""
from PyQt5.QtCore import QSettings

from .branding import APP_NAME


def load_settings(destination=None, legacy=None):
    """Copy only known missing preferences; never overwrite new preferences.

    Inject explicit INI settings in tests. The former identity is used solely
    to read existing user preferences, not as the public application name.
    """
    settings = destination if destination is not None else QSettings(APP_NAME, APP_NAME)
    migration_key = '_migration/brand_v1'
    if settings.value(migration_key, False, type=bool):
        return settings
    old = legacy if legacy is not None else QSettings('QingDiff', 'QingDiff')
    for key in ('theme', 'geometry', 'automatic'):
        if not settings.contains(key) and old.contains(key):
            settings.setValue(key, old.value(key))
    settings.setValue(migration_key, True)
    return settings
