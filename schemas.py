"""
Database Schemas for LinkedIn Lead Automation MVP

Each Pydantic model corresponds to a MongoDB collection with the
collection name equal to the lowercase class name.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime

# Core app entities

class Campaign(BaseModel):
    name: str = Field(..., description="Campaign name")
    description: Optional[str] = Field(None, description="Optional description")

class Company(BaseModel):
    campaign_id: str = Field(..., description="Related campaign id")
    company_name: str = Field(..., description="Company Name")
    linkedin_url: Optional[str] = Field(None, description="Company LinkedIn URL")

class Template(BaseModel):
    campaign_id: str = Field(..., description="Related campaign id")
    connection_template: str = Field(..., description="Message template for connection request")
    followup_template: str = Field(..., description="Message template for follow-up")

class Prospect(BaseModel):
    campaign_id: str = Field(..., description="Related campaign id")
    company_name: str = Field(..., description="Company name")
    first_name: str = Field(..., description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    job_title: Optional[str] = Field(None, description="Job title")
    profile_url: Optional[str] = Field(None, description="LinkedIn profile URL")
    personalized_line: Optional[str] = Field(None, description="Custom personalized line")
    status: str = Field("pending", description="pending|requested|followed_up|accepted|replied|stopped")
    last_action_at: Optional[datetime] = Field(None, description="When the last action occurred")

class MessageLog(BaseModel):
    campaign_id: str
    prospect_id: str
    type: str = Field(..., description="connection|followup")
    status: str = Field("scheduled", description="scheduled|sent|skipped|stopped")
    scheduled_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    content: Optional[str] = None
    reason: Optional[str] = None

# Optional: Inbox view
class InboxItem(BaseModel):
    campaign_id: str
    prospect_id: str
    message: Optional[str] = None
    replied_at: datetime

