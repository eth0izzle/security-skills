"""Tests for action_search.py — formatting, caching, and search helpers."""

import json
import os
import time

import action_search


class TestFormatActionSummary:
    """Test action summary formatting."""

    def test_basic_format(self):
        action = {"id": "abc123", "name": "Contain Host", "description": "Contain a device", "category": "action", "vendor": "CrowdStrike"}
        output = action_search.format_action_summary(action)
        assert "Contain Host" in output
        assert "abc123" in output
        assert "Contain a device" in output

    def test_non_crowdstrike_vendor_shown(self):
        action = {"id": "x", "name": "Test", "vendor": "Okta"}
        output = action_search.format_action_summary(action)
        assert "[Okta]" in output

    def test_crowdstrike_vendor_hidden(self):
        action = {"id": "x", "name": "Test", "vendor": "CrowdStrike"}
        output = action_search.format_action_summary(action)
        assert "[CrowdStrike]" not in output


class TestFormatActionDetails:
    """Test action detail formatting."""

    def test_includes_input_fields(self):
        action = {
            "id": "abc123",
            "name": "Test Action",
            "category": "action",
            "description": "Does stuff",
            "vendor": "CrowdStrike",
            "properties": {
                "device_id": {"type": "string", "description": "The device ID", "required": True},
            },
        }
        output = action_search.format_action_details(action)
        assert "device_id" in output
        assert "(required)" in output

    def test_plugin_action_flagged(self):
        action = {
            "id": "x",
            "name": "Okta Action",
            "vendor": "Okta",
            "namespace": "plugin:okta",
            "properties": {},
        }
        output = action_search.format_action_details(action)
        assert "config_id" in output

    def test_class_based_action(self):
        action = {
            "id": "x",
            "name": "CreateVariable",
            "vendor": "CrowdStrike",
            "class": "generic",
            "properties": {},
        }
        output = action_search.format_action_details(action)
        assert "version_constraint" in output


class TestCache:
    """Test local action cache."""

    def test_save_and_load(self, tmp_path, monkeypatch):
        cache_file = str(tmp_path / ".action_cache.json")
        monkeypatch.setattr(action_search, "_CACHE_FILE", cache_file)

        resources = [{"id": "a", "name": "Action A"}]
        action_search._save_cache(resources)
        loaded = action_search._load_cache()
        assert loaded == resources

    def test_expired_cache_returns_none(self, tmp_path, monkeypatch):
        cache_file = str(tmp_path / ".action_cache.json")
        monkeypatch.setattr(action_search, "_CACHE_FILE", cache_file)

        with open(cache_file, "w") as f:
            json.dump({"ts": time.time() - 7200, "resources": [{"id": "old"}]}, f)

        assert action_search._load_cache() is None

    def test_clear_cache(self, tmp_path, monkeypatch):
        cache_file = str(tmp_path / ".action_cache.json")
        monkeypatch.setattr(action_search, "_CACHE_FILE", cache_file)

        with open(cache_file, "w") as f:
            f.write("{}")

        assert action_search._clear_cache() is True
        assert not os.path.exists(cache_file)

    def test_clear_nonexistent_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(action_search, "_CACHE_FILE", str(tmp_path / "nope.json"))
        assert action_search._clear_cache() is False


class TestFormatVendorsTable:
    """Test vendor table formatting."""

    def test_formats_vendors(self):
        vendors = {
            "CrowdStrike": {"count": 50, "use_cases": {"Detection", "Response"}, "has_permission": True},
            "Okta": {"count": 10, "use_cases": {"Identity"}, "has_permission": False},
        }
        output = action_search.format_vendors_table(vendors)
        assert "CrowdStrike" in output
        assert "Okta" in output
        assert "60 actions" in output
        assert "2 vendors" in output


class TestUsableBody:
    """Test the partial-404 tolerance in _usable_body.

    The search_activities API returns a top-level 404 when a result set
    includes an action with an orphaned catalog artifact, while still returning
    every action it could resolve. _usable_body must keep those resources rather
    than discard them over the aggregate status.
    """

    def test_status_200_returns_body(self):
        resp = {"status_code": 200, "body": {"resources": [{"id": "1"}]}}
        assert action_search._usable_body(resp) == {"resources": [{"id": "1"}]}

    def test_partial_404_with_resources_returns_body(self):
        # 404 aggregate but resources present (orphaned-artifact case).
        body = {
            "resources": [{"id": "1"}, {"id": "2"}],
            "errors": [{"code": 404, "message": "artifact not found", "id": "orphan"}],
        }
        resp = {"status_code": 404, "body": body}
        assert action_search._usable_body(resp) == body

    def test_404_without_resources_returns_none(self):
        resp = {"status_code": 404, "body": {"resources": [], "errors": [{"code": 404}]}}
        assert action_search._usable_body(resp) is None

    def test_500_without_resources_returns_none(self):
        resp = {"status_code": 500, "body": {"resources": []}}
        assert action_search._usable_body(resp) is None

    def test_missing_body_returns_none(self):
        resp = {"status_code": 404, "body": None}
        assert action_search._usable_body(resp) is None
