"""
FIDPHA001/test_runner.py
------------------------
Custom Django test runner that appends a structured log entry to
test_log.txt every time the test suite is executed.

How it works:
    Django's default DiscoverRunner is subclassed here. We override two
    methods:
      - run_suite(): intercepts the raw result object before Django
        discards it, storing it on the instance for logging.
      - run_tests(): wraps the parent call with a timer, then calls
        _write_log() once all tests have finished.

    The log file is appended (never overwritten) so you keep a full
    history of every test run.

Registration:
    Activated in settings.py via:
        TEST_RUNNER = "FIDPHA001.test_runner.LoggingTestRunner"

Log file location:
    <project_root>/test_log.txt   (same directory as manage.py)
    This file is listed in .gitignore and will not be committed.

Author: FIDPHA Dev Team
Last updated: April 2026
"""

import time
from datetime import datetime
from pathlib import Path

from django.test.runner import DiscoverRunner


# Path to the log file — sits next to manage.py at the project root
LOG_FILE_PATH = Path(__file__).resolve().parent.parent / "test_log.txt"

# Separator lines used in the log for readability
SEPARATOR_HEAVY = "=" * 80
SEPARATOR_LIGHT = "-" * 80


class LoggingTestRunner(DiscoverRunner):
    """
    A Django test runner that logs every test run to test_log.txt.

    Extends DiscoverRunner without changing any test execution behaviour —
    it only adds the logging side effect after tests complete.
    """

    def run_suite(self, suite, **kwargs):
        """
        Run the test suite and store the raw result for logging.

        We override this method solely to capture the result object
        before the parent's run_tests() converts it to a failure count.
        The result object holds the detailed failure/error lists we need.

        Args:
            suite: The assembled test suite to run.
            **kwargs: Passed through to the parent implementation.

        Returns:
            The raw unittest result object.
        """
        result = super().run_suite(suite, **kwargs)

        # Store on the instance so run_tests() can access it after the
        # parent call returns only an integer (failure count)
        self._suite_result = result

        return result

    def run_tests(self, test_labels, **kwargs):
        """
        Run all tests, then write a log entry with the outcome.

        Args:
            test_labels: The test labels passed on the command line.
            **kwargs: Passed through to the parent implementation.

        Returns:
            int: Number of failures + errors (Django's standard return value).
        """
        self._suite_result = None

        # Time the entire test run
        start_time = time.time()
        failure_count = super().run_tests(test_labels, **kwargs)
        duration = time.time() - start_time

        # Write the log entry if we successfully captured a result object
        if self._suite_result is not None:
            self._write_log(self._suite_result, duration)

        return failure_count

    def _write_log(self, result, duration: float) -> None:
        """
        Append a structured log entry to test_log.txt.

        Args:
            result: The unittest TestResult object from run_suite().
            duration (float): Total elapsed time in seconds.
        """
        total_run = result.testsRun
        total_failures = len(result.failures)
        total_errors = len(result.errors)
        total_skipped = len(result.skipped) if hasattr(result, "skipped") else 0

        # Passed = everything that ran but didn't fail or error
        total_passed = total_run - total_failures - total_errors

        overall_result = "PASSED" if (total_failures + total_errors) == 0 else "FAILED"
        run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            SEPARATOR_HEAVY,
            f"RUN DATE : {run_date}",
            f"DURATION : {duration:.2f}s",
            f"RESULT   : {overall_result}",
            SEPARATOR_LIGHT,
            f"Tests run : {total_run}",
            f"Passed    : {total_passed}",
            f"Failed    : {total_failures}",
            f"Errors    : {total_errors}",
            f"Skipped   : {total_skipped}",
            SEPARATOR_LIGHT,
        ]

        if total_failures == 0 and total_errors == 0:
            lines.append("ALL TESTS PASSED")
        else:
            # List each failed test by its full dotted ID so the developer
            # can copy-paste it directly into: python manage.py test <id>
            if result.failures:
                lines.append("FAILURES:")
                for test, _ in result.failures:
                    lines.append(f"  - {test.id()}")

            if result.errors:
                lines.append("ERRORS:")
                for test, _ in result.errors:
                    lines.append(f"  - {test.id()}")

        lines.append(SEPARATOR_HEAVY)
        lines.append("")  # blank line between entries for readability

        # Append to the log file — create it if it doesn't exist yet
        with open(LOG_FILE_PATH, "a", encoding="utf-8") as log_file:
            log_file.write("\n".join(lines) + "\n")
