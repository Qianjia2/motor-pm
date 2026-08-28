"""Knowledge Base — modular routes package."""

# Core router (from original monolith)
from backend_v2.routes._knowledge_core import *

# Register sub-module routers for new endpoints not in core
from backend_v2.routes.knowledge.search import router as search_router
router.include_router(search_router)
