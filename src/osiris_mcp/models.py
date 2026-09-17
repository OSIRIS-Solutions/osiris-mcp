# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Typed, deliberately small data contracts returned to MCP clients."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PaginatedResult(BaseModel):
    """Metadata that lets an MCP client retrieve every matching record."""

    count: int = 0
    total: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None


class ProjectSummary(BaseModel):
    """Allowlisted subset of an OSIRIS project document."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str | None = None
    acronym: str | None = None
    title: str | None = None
    status: str | None = None
    start_date: str | dict[str, Any] | None = None
    end_date: str | dict[str, Any] | None = None
    abstract: str | None = None
    topics: list[Any] = Field(default_factory=list)
    units: list[Any] = Field(default_factory=list)
    persons: list[Any] = Field(default_factory=list)
    source_url: str | None = None


class ProjectSearchResult(PaginatedResult):
    """Paginated project search result."""

    count: int
    projects: list[ProjectSummary]


class CatalogInfo(BaseModel):
    """Availability and size of an instance-specific catalog."""

    model_config = ConfigDict(extra="ignore")

    available: bool
    count: int = 0
    label: dict[str, str] | None = None


class InstanceIdentity(BaseModel):
    """Public identity and locale information for an OSIRIS instance."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str
    name_de: str | None = None
    osiris_version: str | None = None
    base_url: str
    default_language: str
    available_languages: list[str] = Field(default_factory=list)
    timezone: str


class InstanceInfo(BaseModel):
    """Capabilities and catalogs advertised by one OSIRIS installation."""

    model_config = ConfigDict(extra="ignore")

    instance: InstanceIdentity
    features: dict[str, bool] = Field(default_factory=dict)
    catalogs: dict[str, CatalogInfo] = Field(default_factory=dict)
    supported_project_filters: list[str] = Field(default_factory=list)
    supported_activity_filters: list[str] = Field(default_factory=list)
    pagination: dict[str, Any] = Field(default_factory=dict)


class UnitPathItem(BaseModel):
    """One organizational unit in a hierarchy path."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None


class UnitInfo(BaseModel):
    """An exact unit identifier and its human-readable hierarchy."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None
    type: str | None = None
    parent_id: str | None = None
    level: int | None = None
    path: list[UnitPathItem] = Field(default_factory=list)
    active: bool = True


class UnitListResult(PaginatedResult):
    """Search result for instance-specific organizational units."""

    count: int
    units: list[UnitInfo]


class TopicInfo(BaseModel):
    """An exact topic identifier plus localized descriptive text."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None
    subtitle: str | None = None
    subtitle_de: str | None = None
    description: str | None = None
    description_de: str | None = None


class TopicListResult(PaginatedResult):
    """Topic catalog, including explicit feature unavailability."""

    available: bool
    reason: str | None = None
    topics: list[TopicInfo] = Field(default_factory=list)


class ActivityTypeItem(BaseModel):
    """An exact activity type or subtype identifier."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None


class ActivityType(ActivityTypeItem):
    """Top-level activity category and its allowed subtypes."""

    subtypes: list[ActivityTypeItem] = Field(default_factory=list)


class ActivityTypeListResult(BaseModel):
    """Instance-specific activity type catalog."""

    available: bool
    types: list[ActivityType] = Field(default_factory=list)


class ActivityKind(BaseModel):
    """Exact activity type ID and its rendered label."""

    model_config = ConfigDict(extra="ignore")

    id: str
    label: str


class PersonReference(BaseModel):
    """A person account linked to an activity."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str


class ActivityUnitReference(BaseModel):
    """An organizational unit linked to an activity."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None


class ActivityMetrics(BaseModel):
    """Optional bibliometric values with their available provenance dates."""

    model_config = ConfigDict(extra="ignore")

    impact_factor: float | None = None
    citation_count: int | None = None
    sjr: float | None = None
    quartile: str | None = None
    metrics_year: int | None = None
    citation_count_updated_at: str | None = None


class ActivitySummary(BaseModel):
    """Compact evidence bundle for one heterogeneous OSIRIS activity."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: ActivityKind
    subtype: ActivityKind
    title: str
    start_date: str | None = None
    end_date: str | None = None
    persons: list[PersonReference] = Field(default_factory=list)
    units: list[ActivityUnitReference] = Field(default_factory=list)
    citation: str
    identifiers: dict[str, str] = Field(default_factory=dict)
    affiliated: bool | None = None
    online_ahead_of_print: bool = False
    metrics: ActivityMetrics | None = None
    source_url: str | None = None

    @field_validator("identifiers", mode="before")
    @classmethod
    def normalize_identifiers(cls, value: Any) -> Any:
        """Keep identifiers textual even when an older API encodes digits as JSON numbers."""

        if not isinstance(value, dict):
            return value
        return {
            str(key): str(identifier)
            for key, identifier in value.items()
            if identifier is not None
        }


class ActivitySearchResult(PaginatedResult):
    """One page of a complete activity search result."""

    count: int
    activities: list[ActivitySummary]


class PersonUnitReference(BaseModel):
    """A person's current organizational unit."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None
    scientific: bool = False


class PersonSummary(BaseModel):
    """Privacy-conscious identity record returned by person search."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    academic_title: str | None = None
    position: str | None = None
    position_de: str | None = None
    active: bool = True
    units: list[PersonUnitReference] = Field(default_factory=list)
    source_url: str | None = None


class PersonTopicReference(BaseModel):
    """An exact OSIRIS research topic linked to a person."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    name_de: str | None = None


class LocalizedStringList(BaseModel):
    """Short English and German lists."""

    en: list[str] = Field(default_factory=list)
    de: list[str] = Field(default_factory=list)


class LocalizedText(BaseModel):
    """Short English and German text."""

    en: str = ""
    de: str = ""


class PersonDetail(PersonSummary):
    """Compact research profile without contact or account metadata."""

    orcid: str | None = None
    expertise: list[str] = Field(default_factory=list)
    research_interests: LocalizedStringList = Field(default_factory=LocalizedStringList)
    topics: list[PersonTopicReference] = Field(default_factory=list)
    research_profile: LocalizedText = Field(default_factory=LocalizedText)


class OpenAlexTopicEvidence(BaseModel):
    """Publication-derived OpenAlex evidence for an expert match."""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str | None = None
    path: str | None = None
    publication_count: int
    max_score: float


class ExpertEvidence(BaseModel):
    """Fields that directly explain why a person matched a topic query."""

    model_config = ConfigDict(extra="ignore")

    expertise: list[str] = Field(default_factory=list)
    research_interests: list[str] = Field(default_factory=list)
    research_interests_de: list[str] = Field(default_factory=list)
    topics: list[PersonTopicReference] = Field(default_factory=list)
    research_profile: str | None = None
    research_profile_de: str | None = None
    openalex_topics: list[OpenAlexTopicEvidence] = Field(default_factory=list)


class ExpertSummary(PersonSummary):
    """Person summary with transparent expertise evidence."""

    evidence: ExpertEvidence


class PersonSearchResult(PaginatedResult):
    """One page of a complete identity search result."""

    count: int
    persons: list[PersonSummary]


class ExpertSearchResult(PaginatedResult):
    """One page of a complete, evidence-backed expertise search result."""

    count: int
    openalex_enabled: bool
    experts: list[ExpertSummary]
