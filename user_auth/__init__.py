# user_auth/__init__.py 
import logging
import os
from . import db_manager

logger = logging.getLogger(__name__)

# Determine the path to state.sqlite relative to this package or a configured path
# This assumes state.sqlite is in the parent directory of user_auth (i.e., the project root)
# For a more robust solution, this path should come from Config or be passed explicitly.
_DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "state.sqlite")

# Optionally, make key functions/classes available at the package level
# from .teams_identity import extract_user_identity
# from .models import UserProfile
# from .utils import get_current_user_profile
# from .permissions import PermissionManager # (Will be created in P3A.2) 