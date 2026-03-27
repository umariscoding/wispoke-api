"""
Analytics router — thin HTTP layer for analytics endpoints.
"""

from fastapi import APIRouter, Depends

from app.features.auth.dependencies import get_current_company, UserContext
from app.features.analytics import service
from app.features.analytics.schemas import AnalyticsDashboard, CompanyUsersResponse

router = APIRouter(prefix="/api/company/analytics", tags=["analytics"])


@router.get("/dashboard")
def get_dashboard_analytics(
    user: UserContext = Depends(get_current_company),
) -> AnalyticsDashboard:
    return service.get_dashboard_analytics(user.company_id)


@router.get("/users")
def get_company_users_with_stats(
    page: int = 1,
    page_size: int = 20,
    user: UserContext = Depends(get_current_company),
) -> CompanyUsersResponse:
    return service.get_company_users_with_stats(user.company_id, page=page, page_size=page_size)
