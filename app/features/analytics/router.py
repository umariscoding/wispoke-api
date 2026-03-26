"""
Analytics router — thin HTTP layer for analytics endpoints.
"""

from fastapi import APIRouter, HTTPException, Depends

from app.auth.dependencies import get_current_company, UserContext
from app.features.analytics import service
from app.features.analytics.schemas import AnalyticsDashboard, CompanyUsersResponse

router = APIRouter(prefix="/api/company/analytics", tags=["analytics"])


@router.get("/dashboard")
async def get_dashboard_analytics(
    user: UserContext = Depends(get_current_company),
) -> AnalyticsDashboard:
    try:
        return await service.get_dashboard_analytics(user.company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch analytics data: {str(e)}")


@router.get("/users")
async def get_company_users_with_stats(
    user: UserContext = Depends(get_current_company),
) -> CompanyUsersResponse:
    try:
        return await service.get_company_users_with_stats(user.company_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch company users with stats: {str(e)}")
