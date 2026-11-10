"""Agent skills for the Loop libraries.

Attributes
----------
__version__ : str
    The installed version of the package. The value is ``"0+unknown"`` when
    the package metadata is not available.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("loop-skills")
except PackageNotFoundError:
    __version__ = "0+unknown"
