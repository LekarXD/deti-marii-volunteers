"""Fail a bounded gate if any configured check was skipped."""
import pytest


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.getplugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter else []
    if skipped:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        if reporter:
            reporter.write_sep("=", f"Validation gate rejected {len(skipped)} skipped checks; configure the selected test environment", red=True)
