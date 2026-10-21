"""CI/backend gate: a missing PostgreSQL opt-in must never look green."""
import pytest


def pytest_sessionfinish(session, exitstatus):
    reporter = session.config.pluginmanager.getplugin("terminalreporter")
    skipped = reporter.stats.get("skipped", []) if reporter else []
    if skipped:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        if reporter:
            reporter.write_sep("=", f"G1 gate rejected {len(skipped)} skipped checks; configure all disposable PostgreSQL URLs", red=True)
