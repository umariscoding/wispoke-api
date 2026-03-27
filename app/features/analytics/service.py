"""
Analytics service — business logic for computing analytics.
No HTTP concepts.
"""

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

from app.core.pagination import paginate
from app.features.chat.repository import fetch_all_messages_by_company, fetch_all_chats_by_company
from app.features.users.repository import fetch_all_users_by_company, fetch_all_guest_sessions_by_company
from app.features.documents.repository import fetch_all_knowledge_bases_by_company
from app.features.analytics.schemas import (
    ChangeIndicator,
    OverviewCard,
    MessagesTimePoint,
    ChatsTimePoint,
    UserWithStats,
    OverviewStats,
    TimeSeries,
    AnalyticsMetadata,
    AnalyticsDashboard,
    CompanyUsersResponse,
)


def _calculate_change(current: int, previous: int) -> ChangeIndicator:
    if previous == 0:
        if current == 0:
            return ChangeIndicator(value="0%", type="neutral")
        return ChangeIndicator(value="+100%", type="increase")
    change_percent = ((current - previous) / previous) * 100
    if change_percent > 0:
        return ChangeIndicator(value=f"+{change_percent:.1f}%", type="increase")
    if change_percent < 0:
        return ChangeIndicator(value=f"{change_percent:.1f}%", type="decrease")
    return ChangeIndicator(value="0%", type="neutral")


def _count_records_in_period(
    records: List[Dict], start_date: datetime, end_date: Optional[datetime] = None
) -> int:
    count = 0
    for record in records:
        created_at_str = record.get("created_at")
        if not created_at_str:
            continue
        try:
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        except Exception:
            continue
        if end_date:
            if start_date <= created_at < end_date:
                count += 1
        elif created_at >= start_date:
            count += 1
    return count


def get_dashboard_analytics(company_id: str) -> AnalyticsDashboard:
    start_time = time.time()
    tz = timezone.utc
    now = datetime.now(tz)
    last_7_days = now - timedelta(days=7)
    last_14_days = now - timedelta(days=14)

    all_messages = fetch_all_messages_by_company(company_id)
    all_users = fetch_all_users_by_company(company_id)
    all_chats = fetch_all_chats_by_company(company_id)
    all_kbs = fetch_all_knowledge_bases_by_company(company_id)
    all_sessions = fetch_all_guest_sessions_by_company(company_id)

    current_messages = _count_records_in_period(all_messages, last_7_days)
    previous_messages = _count_records_in_period(all_messages, last_14_days, last_7_days)
    current_users = _count_records_in_period(all_users, last_7_days)
    previous_users = _count_records_in_period(all_users, last_14_days, last_7_days)
    current_chats = _count_records_in_period(all_chats, last_7_days)
    previous_chats = _count_records_in_period(all_chats, last_14_days, last_7_days)
    current_kb = _count_records_in_period(all_kbs, last_7_days)
    previous_kb = _count_records_in_period(all_kbs, last_14_days, last_7_days)
    current_guest = _count_records_in_period(all_sessions, last_7_days)
    previous_guest = _count_records_in_period(all_sessions, last_14_days, last_7_days)

    overview = OverviewStats(
        totalMessages=OverviewCard(count=current_messages, change=_calculate_change(current_messages, previous_messages)),
        users=OverviewCard(count=current_users, change=_calculate_change(current_users, previous_users)),
        totalChats=OverviewCard(count=current_chats, change=_calculate_change(current_chats, previous_chats)),
        knowledgeBases=OverviewCard(count=current_kb, change=_calculate_change(current_kb, previous_kb)),
        guestSessions=OverviewCard(count=current_guest, change=_calculate_change(current_guest, previous_guest)),
    )

    messages_over_time = []
    chats_over_time = []
    for i in range(7):
        target_date = now.date() - timedelta(days=i)
        day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=tz)
        day_end = day_start + timedelta(days=1)
        day_str = target_date.strftime("%Y-%m-%d")
        messages_over_time.append(MessagesTimePoint(
            date=day_str, totalMessages=_count_records_in_period(all_messages, day_start, day_end),
        ))
        chats_over_time.append(ChatsTimePoint(
            date=day_str, newChats=_count_records_in_period(all_chats, day_start, day_end),
        ))

    messages_over_time.reverse()
    chats_over_time.reverse()

    query_time = time.time() - start_time
    metadata = AnalyticsMetadata(
        lastUpdated=now.isoformat(),
        queryExecutionTime=round(query_time, 3),
        companyId=company_id,
    )

    return AnalyticsDashboard(
        overview=overview,
        timeSeries=TimeSeries(messagesOverTime=messages_over_time, chatsOverTime=chats_over_time),
        metadata=metadata,
    )


def get_company_users_with_stats(
    company_id: str, page: int = 1, page_size: int = 20
) -> CompanyUsersResponse:
    all_users = fetch_all_users_by_company(company_id)
    all_chats = fetch_all_chats_by_company(company_id)
    all_messages = fetch_all_messages_by_company(company_id)

    # Build lookup sets for O(n) instead of O(n*m)
    user_chat_map: Dict[str, List[str]] = {}
    for chat in all_chats:
        uid = chat.get("user_id")
        if uid:
            user_chat_map.setdefault(uid, []).append(chat["chat_id"])

    chat_message_count: Dict[str, int] = {}
    for msg in all_messages:
        cid = msg.get("chat_id")
        if cid:
            chat_message_count[cid] = chat_message_count.get(cid, 0) + 1

    users_with_stats = []
    total_chats = 0
    total_messages = 0

    for user_data in all_users:
        user_id = user_data["user_id"]
        is_anonymous = user_data.get("is_anonymous", False)
        user_chats = user_chat_map.get(user_id, [])
        chat_count = len(user_chats)
        message_count = sum(chat_message_count.get(cid, 0) for cid in user_chats)

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
            created_at=user_data.get("created_at", ""),
        ))

    users_with_stats.sort(key=lambda u: u.created_at, reverse=True)
    result = paginate(users_with_stats, page, page_size)

    return CompanyUsersResponse(
        users=result["items"],
        total_users=result["total"],
        total_chats=total_chats,
        total_messages=total_messages,
        company_id=company_id,
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )
