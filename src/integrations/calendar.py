"""
Calendar Integration for Team Capacity Planner

Pulls PTO, meetings, and out-of-office from Google Calendar or Outlook.
"""

import os
from datetime import datetime, timedelta, date
from typing import Optional, Literal
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

import httpx


@dataclass
class CalendarEvent:
    """Represents a calendar event."""
    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    attendees: list[str] = field(default_factory=list)
    location: Optional[str] = None
    description: Optional[str] = None
    
    @property
    def duration_hours(self) -> float:
        """Event duration in hours."""
        return (self.end - self.start).total_seconds() / 3600
    
    @property
    def is_pto(self) -> bool:
        """Check if event looks like PTO."""
        pto_keywords = ["pto", "vacation", "holiday", "time off", "ooo", "out of office", "leave"]
        title_lower = self.title.lower()
        return any(kw in title_lower for kw in pto_keywords)
    
    @property
    def is_meeting(self) -> bool:
        """Check if event is a meeting (has attendees)."""
        return len(self.attendees) > 1


@dataclass
class PTOPeriod:
    """Represents a PTO/vacation period."""
    user: str
    start_date: date
    end_date: date
    reason: str = "PTO"
    
    @property
    def days(self) -> int:
        """Number of days off (excluding weekends)."""
        count = 0
        current = self.start_date
        while current <= self.end_date:
            if current.weekday() < 5:  # Monday = 0, Friday = 4
                count += 1
            current += timedelta(days=1)
        return count
    
    def overlaps(self, other: "PTOPeriod") -> bool:
        """Check if this PTO overlaps with another."""
        return not (self.end_date < other.start_date or self.start_date > other.end_date)


@dataclass
class UserAvailability:
    """User's availability summary."""
    user: str
    email: str
    pto_periods: list[PTOPeriod] = field(default_factory=list)
    meeting_hours_this_week: float = 0.0
    meeting_hours_next_week: float = 0.0
    
    @property
    def is_available_today(self) -> bool:
        today = date.today()
        return not any(
            pto.start_date <= today <= pto.end_date
            for pto in self.pto_periods
        )
    
    @property
    def next_pto(self) -> Optional[PTOPeriod]:
        """Get next upcoming PTO."""
        today = date.today()
        future_pto = [p for p in self.pto_periods if p.end_date >= today]
        return min(future_pto, key=lambda p: p.start_date) if future_pto else None
    
    @property
    def meeting_load_score(self) -> float:
        """Score based on meeting hours (40hr week = 100%)."""
        return (self.meeting_hours_this_week / 40) * 100


class CalendarProvider(ABC):
    """Abstract base class for calendar providers."""
    
    @abstractmethod
    async def get_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: Optional[str] = None
    ) -> list[CalendarEvent]:
        """Get events in a date range."""
        pass
    
    @abstractmethod
    async def get_user_availability(
        self,
        email: str,
        days_ahead: int = 30
    ) -> UserAvailability:
        """Get user's availability including PTO."""
        pass


class GoogleCalendarClient(CalendarProvider):
    """
    Google Calendar API client.
    
    Requires OAuth2 credentials or service account.
    
    Usage:
        client = GoogleCalendarClient(credentials_file="credentials.json")
        events = await client.get_events(start, end)
    """
    
    BASE_URL = "https://www.googleapis.com/calendar/v3"
    
    def __init__(
        self,
        credentials_file: Optional[str] = None,
        token: Optional[str] = None
    ):
        self.credentials_file = credentials_file or os.getenv("GOOGLE_CREDENTIALS_FILE")
        self.token = token or os.getenv("GOOGLE_CALENDAR_TOKEN")
        
        # In production, would use google-auth library for proper OAuth
        if not self.token:
            raise ValueError(
                "Google Calendar token required. "
                "Set GOOGLE_CALENDAR_TOKEN env var or implement OAuth flow."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
    
    async def _request(
        self,
        endpoint: str,
        params: Optional[dict] = None
    ) -> dict:
        """Make authenticated request to Google Calendar API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: str = "primary"
    ) -> list[CalendarEvent]:
        """Get events from Google Calendar."""
        params = {
            "timeMin": start.isoformat() + "Z",
            "timeMax": end.isoformat() + "Z",
            "singleEvents": "true",
            "orderBy": "startTime"
        }
        
        result = await self._request(f"/calendars/{calendar_id}/events", params)
        
        events = []
        for item in result.get("items", []):
            start_data = item.get("start", {})
            end_data = item.get("end", {})
            
            # Handle all-day events vs timed events
            if "date" in start_data:
                event_start = datetime.fromisoformat(start_data["date"])
                event_end = datetime.fromisoformat(end_data["date"])
                all_day = True
            else:
                event_start = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00"))
                event_end = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00"))
                all_day = False
            
            attendees = [
                a.get("email", "") 
                for a in item.get("attendees", [])
            ]
            
            events.append(CalendarEvent(
                id=item["id"],
                title=item.get("summary", "No Title"),
                start=event_start,
                end=event_end,
                all_day=all_day,
                attendees=attendees,
                location=item.get("location"),
                description=item.get("description")
            ))
        
        return events
    
    async def get_user_availability(
        self,
        email: str,
        days_ahead: int = 30
    ) -> UserAvailability:
        """Get user's availability from their calendar."""
        now = datetime.now()
        end = now + timedelta(days=days_ahead)
        
        events = await self.get_events(now, end, calendar_id=email)
        
        # Extract PTO events
        pto_periods = []
        for event in events:
            if event.is_pto:
                pto_periods.append(PTOPeriod(
                    user=email,
                    start_date=event.start.date(),
                    end_date=event.end.date() - timedelta(days=1) if event.all_day else event.end.date(),
                    reason=event.title
                ))
        
        # Calculate meeting hours
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        next_week_end = week_end + timedelta(days=7)
        
        this_week_meetings = sum(
            e.duration_hours for e in events
            if e.is_meeting and week_start <= e.start < week_end
        )
        
        next_week_meetings = sum(
            e.duration_hours for e in events
            if e.is_meeting and week_end <= e.start < next_week_end
        )
        
        return UserAvailability(
            user=email.split("@")[0],
            email=email,
            pto_periods=pto_periods,
            meeting_hours_this_week=this_week_meetings,
            meeting_hours_next_week=next_week_meetings
        )


class OutlookCalendarClient(CalendarProvider):
    """
    Microsoft Outlook/Graph API client.
    
    Usage:
        client = OutlookCalendarClient(token="access_token")
        events = await client.get_events(start, end)
    """
    
    BASE_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.getenv("OUTLOOK_TOKEN")
        
        if not self.token:
            raise ValueError(
                "Outlook token required. "
                "Set OUTLOOK_TOKEN env var or implement OAuth flow."
            )
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json"
        }
    
    async def _request(
        self,
        endpoint: str,
        params: Optional[dict] = None
    ) -> dict:
        """Make authenticated request to Microsoft Graph API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def get_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: Optional[str] = None
    ) -> list[CalendarEvent]:
        """Get events from Outlook Calendar."""
        endpoint = "/me/calendar/events" if not calendar_id else f"/users/{calendar_id}/calendar/events"
        
        params = {
            "$filter": f"start/dateTime ge '{start.isoformat()}' and end/dateTime le '{end.isoformat()}'",
            "$orderby": "start/dateTime",
            "$top": 100
        }
        
        result = await self._request(endpoint, params)
        
        events = []
        for item in result.get("value", []):
            event_start = datetime.fromisoformat(item["start"]["dateTime"])
            event_end = datetime.fromisoformat(item["end"]["dateTime"])
            all_day = item.get("isAllDay", False)
            
            attendees = [
                a.get("emailAddress", {}).get("address", "")
                for a in item.get("attendees", [])
            ]
            
            events.append(CalendarEvent(
                id=item["id"],
                title=item.get("subject", "No Title"),
                start=event_start,
                end=event_end,
                all_day=all_day,
                attendees=attendees,
                location=item.get("location", {}).get("displayName"),
                description=item.get("bodyPreview")
            ))
        
        return events
    
    async def get_user_availability(
        self,
        email: str,
        days_ahead: int = 30
    ) -> UserAvailability:
        """Get user's availability from Outlook."""
        now = datetime.now()
        end = now + timedelta(days=days_ahead)
        
        events = await self.get_events(now, end, calendar_id=email)
        
        # Extract PTO events
        pto_periods = []
        for event in events:
            if event.is_pto:
                pto_periods.append(PTOPeriod(
                    user=email,
                    start_date=event.start.date(),
                    end_date=event.end.date(),
                    reason=event.title
                ))
        
        # Calculate meeting hours (same as Google)
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=7)
        next_week_end = week_end + timedelta(days=7)
        
        this_week_meetings = sum(
            e.duration_hours for e in events
            if e.is_meeting and week_start <= e.start < week_end
        )
        
        next_week_meetings = sum(
            e.duration_hours for e in events
            if e.is_meeting and week_end <= e.start < next_week_end
        )
        
        return UserAvailability(
            user=email.split("@")[0],
            email=email,
            pto_periods=pto_periods,
            meeting_hours_this_week=this_week_meetings,
            meeting_hours_next_week=next_week_meetings
        )


class CalendarClient:
    """
    Unified calendar client that supports multiple providers.
    
    Usage:
        client = CalendarClient(provider="google")
        availability = await client.get_team_availability(["alice@co.com", "bob@co.com"])
    """
    
    def __init__(
        self,
        provider: Literal["google", "outlook"] = "google",
        **kwargs
    ):
        self.provider = provider
        
        if provider == "google":
            self.client = GoogleCalendarClient(**kwargs)
        elif provider == "outlook":
            self.client = OutlookCalendarClient(**kwargs)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    async def get_events(
        self,
        start: datetime,
        end: datetime,
        calendar_id: Optional[str] = None
    ) -> list[CalendarEvent]:
        """Get events from calendar."""
        return await self.client.get_events(start, end, calendar_id)
    
    async def get_user_availability(
        self,
        email: str,
        days_ahead: int = 30
    ) -> UserAvailability:
        """Get user's availability."""
        return await self.client.get_user_availability(email, days_ahead)
    
    async def get_team_availability(
        self,
        emails: list[str],
        days_ahead: int = 30
    ) -> list[UserAvailability]:
        """Get availability for multiple team members."""
        availabilities = []
        for email in emails:
            try:
                avail = await self.get_user_availability(email, days_ahead)
                availabilities.append(avail)
            except Exception as e:
                # Log error but continue with other users
                print(f"Error fetching availability for {email}: {e}")
        
        return availabilities
    
    async def find_pto_conflicts(
        self,
        emails: list[str],
        days_ahead: int = 30,
        min_coverage: int = 2
    ) -> list[dict]:
        """
        Find dates where too many people are on PTO.
        
        Args:
            emails: Team members' emails
            days_ahead: How far to look
            min_coverage: Minimum people needed available
            
        Returns:
            List of conflict dates with details
        """
        availabilities = await self.get_team_availability(emails, days_ahead)
        
        # Build a map of date -> who's out
        date_pto_map = {}
        today = date.today()
        
        for i in range(days_ahead):
            check_date = today + timedelta(days=i)
            if check_date.weekday() >= 5:  # Skip weekends
                continue
            
            people_out = []
            for avail in availabilities:
                for pto in avail.pto_periods:
                    if pto.start_date <= check_date <= pto.end_date:
                        people_out.append(avail.user)
                        break
            
            date_pto_map[check_date] = people_out
        
        # Find conflicts
        total_people = len(emails)
        conflicts = []
        
        for check_date, people_out in date_pto_map.items():
            available = total_people - len(people_out)
            if available < min_coverage:
                conflicts.append({
                    "date": check_date.isoformat(),
                    "people_out": people_out,
                    "available_count": available,
                    "severity": "critical" if available == 0 else "warning"
                })
        
        return conflicts


# Convenience function
async def get_team_pto_conflicts(
    provider: str,
    emails: list[str],
    days_ahead: int = 30,
    min_coverage: int = 2,
    **kwargs
) -> list[dict]:
    """
    Quick function to find PTO conflicts.
    
    Example:
        conflicts = await get_team_pto_conflicts(
            provider="google",
            emails=["alice@company.com", "bob@company.com"],
            days_ahead=30,
            min_coverage=2,
            token="google_token"
        )
        
        for conflict in conflicts:
            print(f"{conflict['date']}: {conflict['people_out']} out")
    """
    client = CalendarClient(provider=provider, **kwargs)
    return await client.find_pto_conflicts(emails, days_ahead, min_coverage)
