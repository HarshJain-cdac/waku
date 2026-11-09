"""Moved to waku/nam/dossier.py. This name stays so existing imports keep working.

The module object itself is aliased, not copied: `from waku.tools import nam_dossier`
returns waku.nam.dossier, so a test that patches an attribute here patches the
code that runs.
"""

import sys

from waku.nam import dossier as _moved

sys.modules[__name__] = _moved
