# Import execution first, then mount adapter routes beneath it.
# This keeps app.main stable while agency.router remains the single /v1 parent.
from . import execution as _execution  # noqa: F401,E402
from . import adapters as _adapters  # noqa: F401,E402
