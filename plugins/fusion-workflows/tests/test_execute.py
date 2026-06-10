"""Tests for execute.py — parameter handling and response parsing."""

import inspect
from unittest.mock import MagicMock

import execute


class TestExecuteWorkflow:
    """Test workflow execution request building."""

    def test_params_merged_with_definition_id(self):
        """Verify the request body structure matches what the API expects."""
        sig = inspect.signature(execute.execute_workflow)
        params = list(sig.parameters.keys())
        assert "definition_id" in params
        assert "params" in params
        assert "depth" in params

    def test_execution_id_parsed_from_bare_string(self, monkeypatch):
        """The execute endpoint returns resources as bare ID strings, not dicts."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "status_code": 200,
            "body": {"resources": ["6c0b22c26ec8358b5df2098ddad0e304"], "errors": []},
            "headers": {},
        }
        monkeypatch.setattr(execute, "get_client", lambda: mock_client)
        ok, exec_id, _ = execute.execute_workflow("def_id", {})
        assert ok is True
        assert exec_id == "6c0b22c26ec8358b5df2098ddad0e304"

    def test_execution_id_parsed_from_dict(self, monkeypatch):
        """Still handle the object shape defensively."""
        mock_client = MagicMock()
        mock_client.execute.return_value = {
            "status_code": 200,
            "body": {"resources": [{"id": "abc123"}], "errors": []},
            "headers": {},
        }
        monkeypatch.setattr(execute, "get_client", lambda: mock_client)
        ok, exec_id, _ = execute.execute_workflow("def_id", {})
        assert ok is True
        assert exec_id == "abc123"


class TestPollResults:
    """Test result polling logic."""

    def test_poll_timeout_returns_none(self, monkeypatch):
        """Verify timeout behavior without hitting real API."""
        call_count = 0
        mock_client = MagicMock()

        def mock_execution_results(**kwargs):
            nonlocal call_count
            call_count += 1
            return {"status_code": 200, "body": {"resources": [{"status": "In progress"}]}, "headers": {}}

        mock_client.execution_results = mock_execution_results
        monkeypatch.setattr(execute, "get_client", lambda: mock_client)
        result = execute.poll_results("fake_id", timeout=1, interval=0.1)
        assert result is None
        assert call_count > 0

    def test_poll_succeeded_returns_result(self, monkeypatch):
        """Verify a terminal Succeeded status is returned (real API casing)."""
        mock_client = MagicMock()
        mock_client.execution_results.return_value = {
            "status_code": 200,
            "body": {"resources": [{"status": "Succeeded", "output": {"key": "value"}}]},
            "headers": {},
        }
        monkeypatch.setattr(execute, "get_client", lambda: mock_client)
        result = execute.poll_results("fake_id", timeout=5, interval=0.1)
        assert result is not None
        assert result["status"] == "Succeeded"
        assert result["output"] == {"key": "value"}

    def test_poll_failed_returns_result(self, monkeypatch):
        """Verify capitalized Failed status is terminal (not retried forever)."""
        mock_client = MagicMock()
        mock_client.execution_results.return_value = {
            "status_code": 200,
            "body": {"resources": [{"status": "Failed"}]},
            "headers": {},
        }
        monkeypatch.setattr(execute, "get_client", lambda: mock_client)
        result = execute.poll_results("fake_id", timeout=5, interval=0.1)
        assert result["status"] == "Failed"
