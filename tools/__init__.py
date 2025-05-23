# Makes the 'tools' directory a Python package.

import logging

# Expose the tool decorator directly from the package if desired
from ._tool_decorator import tool_function as tool

log = logging.getLogger(__name__)
log.debug("tools package initialized.")

# You could potentially put shared tool utility functions, constants,
# or base classes here if the tools grow more complex and share logic.

# Example:
# SHARED_TOOL_CONSTANT = "some_value"

# Example Base Class (if needed):
# class BaseTool:
#     def __init__(self, config):
#         self.config = config
#         # common initialization