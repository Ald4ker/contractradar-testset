"""The field schema (schema/fields.json), importable without crtest.gen's PDF-rendering dependencies."""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "..", "schema", "fields.json")

with open(SCHEMA_PATH, encoding="utf-8") as _f:
    SCHEMA = json.load(_f)
FIELD_NAMES = [f["name"] for f in SCHEMA["fields"]]
