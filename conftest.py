import os

# Allow synchronous Django ORM calls from within pytest-playwright's async
# event loop. Without this, django_db_setup raises SynchronousOnlyOperation
# because playwright's session-scoped event loop is already running when
# pytest-django tries to create the test database.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
