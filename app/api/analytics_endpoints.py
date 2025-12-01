from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
import time

from app.auth.dependencies import get_current_company, UserContext
from app.db.database import db

router = APIRouter(prefix="/api/company/analytics", tags=["analytics"])

# Pydantic models for response structure
class ChangeIndicator(BaseModel):
    value: str  # e.g., "+15%" or "-5%"
    type: str   # "increase", "decrease", or "neutral"

class OverviewCard(BaseModel):
    count: int
    change: ChangeIndicator

class MessagesTimePoint(BaseModel):
    date: str
    totalMessages: int

class ChatsTimePoint(BaseModel):
    date: str
    newChats: int

# Simplified analytics - removed unnecessary models

class UserWithStats(BaseModel):
    user_id: str
    email: Optional[str]
    name: Optional[str]
    is_anonymous: bool
    chat_count: int
    message_count: int
    created_at: str

class CompanyUsersResponse(BaseModel):
    users: List[UserWithStats]
    total_users: int
    total_chats: int
    total_messages: int
    company_id: str

class OverviewStats(BaseModel):
    totalMessages: OverviewCard
    users: OverviewCard
    totalChats: OverviewCard
    knowledgeBases: OverviewCard
    guestSessions: OverviewCard

class TimeSeries(BaseModel):
    messagesOverTime: List[MessagesTimePoint]
    chatsOverTime: List[ChatsTimePoint]

class AnalyticsMetadata(BaseModel):
    lastUpdated: str
    queryExecutionTime: float
    companyId: str

class AnalyticsDashboard(BaseModel):
    overview: OverviewStats
    timeSeries: TimeSeries
    metadata: AnalyticsMetadata

def get_company_timezone(company_id: str) -> timezone:
    """
    Get the timezone for a company.
    For now returns UTC, but can be extended to fetch from company settings.

    Args:
        company_id: Company identifier

    Returns:
        timezone: Company's timezone (currently always UTC)
    """
    # TODO: Fetch company timezone from database settings
    # For now, default to UTC for all companies
    return timezone.utc

def calculate_change(current: int, previous: int) -> ChangeIndicator:
    """Calculate percentage change between current and previous periods."""
    if previous == 0:
        if current == 0:
            return ChangeIndicator(value="0%", type="neutral")
        else:
            return ChangeIndicator(value="+100%", type="increase")

    change_percent = ((current - previous) / previous) * 100

    if change_percent > 0:
        return ChangeIndicator(value=f"+{change_percent:.1f}%", type="increase")
    elif change_percent < 0:
        return ChangeIndicator(value=f"{change_percent:.1f}%", type="decrease")
    else:
        return ChangeIndicator(value="0%", type="neutral")

def count_records_in_period(records: List[Dict], start_date: datetime, end_date: Optional[datetime] = None) -> int:
    """Count records within a time period."""
    count = 0
    for record in records:
        created_at_str = record.get("created_at")
        if not created_at_str:
            continue

        # Parse ISO format datetime
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except:
            continue

        if end_date:
            if start_date <= created_at < end_date:
                count += 1
        else:
            if created_at >= start_date:
                count += 1

    return count

@router.get("/dashboard")
async def get_dashboard_analytics(
    user: UserContext = Depends(get_current_company)
) -> AnalyticsDashboard:
    """
    Get comprehensive dashboard analytics for the company.
    Returns overview statistics, time series data, user analytics, and knowledge base metrics.
    """
    start_time = time.time()

    try:
        company_id = user.company_id

        # Define time periods with proper timezone handling
        tz = get_company_timezone(company_id)

        # Get current time in the company's timezone
        now = datetime.now(tz)

        # Calculate time periods relative to the target timezone
        last_7_days = now - timedelta(days=7)
        last_14_days = now - timedelta(days=14)

        # ============================================================================
        # FETCH ALL DATA
        # ============================================================================

        # Fetch all messages for the company
        messages_res = db.table("messages").select("*").eq("company_id", company_id).execute()
        all_messages = messages_res.data or []

        # Fetch all users for the company
        users_res = db.table("company_users").select("*").eq("company_id", company_id).execute()
        all_users = users_res.data or []

        # Fetch all chats for the company
        chats_res = db.table("chats").select("*").eq("company_id", company_id).eq("is_deleted", False).execute()
        all_chats = chats_res.data or []

        # Fetch all knowledge bases for the company
        kb_res = db.table("knowledge_bases").select("*").eq("company_id", company_id).execute()
        all_kbs = kb_res.data or []

        # Fetch all guest sessions for the company
        sessions_res = db.table("guest_sessions").select("*").eq("company_id", company_id).execute()
        all_sessions = sessions_res.data or []

        # ============================================================================
        # OVERVIEW STATISTICS
        # ============================================================================

        # Total messages (last 7 days vs previous 7 days)
        current_messages = count_records_in_period(all_messages, last_7_days)
        previous_messages = count_records_in_period(all_messages, last_14_days, last_7_days)

        # Users registered in last 7 days vs previous 7 days
        current_users = count_records_in_period(all_users, last_7_days)
        previous_users = count_records_in_period(all_users, last_14_days, last_7_days)

        # Total chats (last 7 days vs previous 7 days)
        current_chats = count_records_in_period(all_chats, last_7_days)
        previous_chats = count_records_in_period(all_chats, last_14_days, last_7_days)

        # Knowledge bases (last 7 days vs previous 7 days)
        current_kb = count_records_in_period(all_kbs, last_7_days)
        previous_kb = count_records_in_period(all_kbs, last_14_days, last_7_days)

        # Guest sessions created in last 7 days vs previous 7 days
        current_guest_sessions = count_records_in_period(all_sessions, last_7_days)
        previous_guest_sessions = count_records_in_period(all_sessions, last_14_days, last_7_days)

        overview = OverviewStats(
            totalMessages=OverviewCard(
                count=current_messages,
                change=calculate_change(current_messages, previous_messages)
            ),
            users=OverviewCard(
                count=current_users,
                change=calculate_change(current_users, previous_users)
            ),
            totalChats=OverviewCard(
                count=current_chats,
                change=calculate_change(current_chats, previous_chats)
            ),
            knowledgeBases=OverviewCard(
                count=current_kb,
                change=calculate_change(current_kb, previous_kb)
            ),
            guestSessions=OverviewCard(
                count=current_guest_sessions,
                change=calculate_change(current_guest_sessions, previous_guest_sessions)
            )
        )

        # ============================================================================
        # TIME SERIES DATA
        # ============================================================================

        # Daily message counts for last 7 days
        messages_over_time = []
        for i in range(7):
            # Calculate day boundaries in the target timezone
            target_date = now.date() - timedelta(days=i)
            # Create timezone-aware datetime for start of day
            day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=tz)
            day_end = day_start + timedelta(days=1)
            day_date = target_date.strftime("%Y-%m-%d")

            # Count messages for this day
            total_msgs = count_records_in_period(all_messages, day_start, day_end)

            messages_over_time.append(MessagesTimePoint(
                date=day_date,
                totalMessages=total_msgs
            ))

        messages_over_time.reverse()  # Chronological order

        # Daily new chat creation for last 7 days
        chats_over_time = []
        for i in range(7):
            # Calculate day boundaries in the target timezone
            target_date = now.date() - timedelta(days=i)
            # Create timezone-aware datetime for start of day
            day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=tz)
            day_end = day_start + timedelta(days=1)
            day_date = target_date.strftime("%Y-%m-%d")

            # Count chats created this day
            new_chats = count_records_in_period(all_chats, day_start, day_end)

            chats_over_time.append(ChatsTimePoint(
                date=day_date,
                newChats=new_chats
            ))

        chats_over_time.reverse()  # Chronological order

        time_series = TimeSeries(
            messagesOverTime=messages_over_time,
            chatsOverTime=chats_over_time
        )

        # ============================================================================
        # METADATA
        # ============================================================================

        query_time = time.time() - start_time
        metadata = AnalyticsMetadata(
            lastUpdated=now.isoformat(),
            queryExecutionTime=round(query_time, 3),
            companyId=company_id
        )

        return AnalyticsDashboard(
            overview=overview,
            timeSeries=time_series,
            metadata=metadata
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch analytics data: {str(e)}"
        )

@router.get("/users")
async def get_company_users_with_stats(
    user: UserContext = Depends(get_current_company)
) -> CompanyUsersResponse:
    """
    Get all users for the company along with their chat and message counts.
    Returns detailed user statistics including number of chats and messages per user.
    """
    try:
        company_id = user.company_id

        # Get all users for the company
        users_res = db.table("company_users").select("*").eq("company_id", company_id).execute()
        all_users = users_res.data or []

        # Get all chats for the company
        chats_res = db.table("chats").select("*").eq("company_id", company_id).eq("is_deleted", False).execute()
        all_chats = chats_res.data or []

        # Get all messages for the company
        messages_res = db.table("messages").select("*").eq("company_id", company_id).execute()
        all_messages = messages_res.data or []

        # Calculate stats per user
        users_with_stats = []
        total_chats = 0
        total_messages = 0

        for user_data in all_users:
            user_id = user_data["user_id"]
            is_anonymous = user_data.get("is_anonymous", False)

            # Count chats for this user
            chat_count = sum(1 for chat in all_chats if chat.get("user_id") == user_id)

            # Get chat IDs for this user
            user_chat_ids = [chat["chat_id"] for chat in all_chats if chat.get("user_id") == user_id]

            # Count messages in user's chats
            message_count = sum(1 for msg in all_messages if msg.get("chat_id") in user_chat_ids)

            # Add to totals only for non-anonymous users
            if not is_anonymous:
                total_chats += chat_count
                total_messages += message_count

            users_with_stats.append(UserWithStats(
                user_id=user_id,
                email=user_data.get("email"),
                name=user_data.get("name"),
                is_anonymous=is_anonymous,
                chat_count=chat_count,
                message_count=message_count,
                created_at=user_data.get("created_at", "")
            ))

        # Sort by created_at descending
        users_with_stats.sort(key=lambda u: u.created_at, reverse=True)

        return CompanyUsersResponse(
            users=users_with_stats,
            total_users=len(users_with_stats),
            total_chats=total_chats,
            total_messages=total_messages,
            company_id=company_id
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch company users with stats: {str(e)}"
        )