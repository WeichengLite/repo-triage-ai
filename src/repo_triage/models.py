"""Validated data shared by the GitHub client and future briefing code."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Issue(BaseModel):
    """An open GitHub issue with a bounded body for downstream processing."""

    number: int = Field(gt=0)
    title: str
    body: str = Field(max_length=800)
    labels: list[str]
    comment_count: int = Field(ge=0)
    updated_at: datetime
    html_url: HttpUrl


class IssueTriage(BaseModel):
    """Validated, evidence-grounded maintainer guidance for one issue."""

    model_config = ConfigDict(
        extra="forbid", strict=True, str_strip_whitespace=True
    )

    issue_number: int = Field(gt=0)
    category: Literal["bug", "feature", "docs", "question", "other"]
    urgency: Literal["critical", "high", "medium", "low"]
    summary: str = Field(min_length=1, max_length=180)
    rationale: str = Field(min_length=1, max_length=250)
    next_action: str = Field(min_length=1, max_length=180)
