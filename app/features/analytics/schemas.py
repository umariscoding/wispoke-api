from pydantic import BaseModel
from typing import List, Optional


class ChangeIndicator(BaseModel):
    value: str
    type: str


class OverviewCard(BaseModel):
    count: int
    change: ChangeIndicator


class MessagesTimePoint(BaseModel):
    date: str
    totalMessages: int


class ChatsTimePoint(BaseModel):
    date: str
    newChats: int


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
