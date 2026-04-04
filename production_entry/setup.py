# Copyright (c) 2026, production_entry contributors
# For license information, please see license.txt
#
# This file must NOT import frappe. It is executed during isolated `pip`/`uv` builds
# (e.g. Docker bench get-app) where only build-system deps exist.
# Install / migrate logic lives in production_entry/setup.py (package module: production_entry.setup).

from setuptools import setup

setup()
