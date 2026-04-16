"""
control/apps.py
---------------
App configuration for the custom admin control panel.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

from django.apps import AppConfig


class ControlConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "control"
    verbose_name = "Control Panel"
