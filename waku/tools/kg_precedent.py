"""Moved to waku/nam/kg_tools.py. This name stays so existing imports keep working.

The module object itself is aliased, not copied: `from waku.tools import kg_precedent`
returns waku.nam.kg_tools, so a test that patches an attribute here patches the
code that runs.
"""

import sys

from waku.nam import kg_tools as _moved

sys.modules[__name__] = _moved
