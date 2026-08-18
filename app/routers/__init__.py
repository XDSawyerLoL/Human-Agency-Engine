# Import in dependency order so nested routers mount deterministically.
# agency -> execution -> adapters -> sandbox/readiness; market mounts directly on agency.
from . import execution as _execution  # noqa: F401,E402
from . import adapters as _adapters  # noqa: F401,E402
from . import sandbox as _sandbox  # noqa: F401,E402
from . import readiness as _readiness  # noqa: F401,E402
from . import market as _market  # noqa: F401,E402
