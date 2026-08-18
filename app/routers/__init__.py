# Import execution for its deliberate route-registration side effect.
# This keeps app.main stable while agency.router remains the single /v1 parent.
from . import execution as _execution  # noqa: F401,E402
