# Copyright (c) 2026, production_entry contributors
# For license information, please see license.txt
#
# This file must NOT import frappe. It is executed during isolated `pip`/`uv` builds
# (e.g. Docker bench get-app) where only build-system deps exist.
# Migrate/install hooks: production_entry/install.py (module production_entry.install), not setup.py.

from setuptools import setup

setup()
