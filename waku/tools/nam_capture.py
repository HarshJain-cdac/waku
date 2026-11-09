"""Moved to waku/nam/capture.py. This name stays so existing imports keep working.

The module object itself is aliased, not copied: `from waku.tools import nam_capture`
returns waku.nam.capture, so a test that patches an attribute here patches the
code that runs.
"""

import sys

from waku.nam import capture as _moved

sys.modules[__name__] = _moved
