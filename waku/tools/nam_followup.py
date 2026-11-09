"""Moved to waku/nam/followup.py. This name stays so existing imports keep working.

The module object itself is aliased, not copied: `from waku.tools import nam_followup`
returns waku.nam.followup, so a test that patches an attribute here patches the
code that runs.
"""

import sys

from waku.nam import followup as _moved

sys.modules[__name__] = _moved
