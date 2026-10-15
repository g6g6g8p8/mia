from fastapi import APIRouter

from mia.app import Owner
from mia import access, backup_jobs
from mia.db import transaction
from fastapi import HTTPException

router = APIRouter()

# This module intentionally kept minimal: backups/access endpoints are defined in mia/routers/ia.py
# and system-wide endpoints can be extended here if needed.
