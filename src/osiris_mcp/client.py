"""Narrow HTTP adapter for the existing OSIRIS API."""

from datetime import date
import re
from typing import Any
from urllib.parse import quote

import httpx

from .config import Settings
from .models import (
    ActivitySearchResult,
    ActivitySummary,
    ActivityTypeListResult,
    InstanceInfo,
    ExpertSearchResult,
    PersonDetail,
    PersonSearchResult,
    PersonSummary,
    ProjectSearchResult,
    ProjectSummary,
    TopicListResult,
    UnitInfo,
    UnitListResult,
)


class OsirisApiError(RuntimeError):
    """Raised when OSIRIS returns an invalid or unsuccessful API response."""


class OsirisClient:
    """Call only explicitly implemented OSIRIS endpoints.

    The class intentionally has no generic public ``request`` method. This keeps
    MCP tools from turning into an unrestricted proxy for OSIRIS.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if settings.base_url is None:
            raise ValueError("OSIRIS_BASE_URL is not configured")

        self._base_url = str(settings.base_url).rstrip("/")
        headers = {"Accept": "application/json"}
        if settings.client_id:
            headers["X-OSIRIS-Client-ID"] = settings.client_id
        if settings.api_key is not None:
            headers["X-API-Key"] = settings.api_key.get_secret_value()

        self._http = httpx.AsyncClient(
            headers=headers,
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    async def __aenter__(self) -> "OsirisClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_instance_info(self) -> InstanceInfo:
        """Return identity, capabilities, and catalogs for this installation."""

        response = await self._http.get(f"{self._base_url}/api/mcp/instance")
        data = self._response_data(response, "instance information", dict)
        return InstanceInfo.model_validate(data)

    async def list_units(
        self,
        *,
        query: str | None = None,
        limit: int = 50,
    ) -> UnitListResult:
        """Resolve human-readable unit names to exact instance-specific IDs."""

        params = self._catalog_params(query=query, limit=limit)
        response = await self._http.get(
            f"{self._base_url}/api/mcp/units",
            params=params,
        )
        data = self._response_data(response, "unit catalog", list)
        units = [UnitInfo.model_validate(item) for item in data if isinstance(item, dict)]
        return UnitListResult(count=len(units), units=units)

    async def list_topics(
        self,
        *,
        query: str | None = None,
        limit: int = 50,
    ) -> TopicListResult:
        """Resolve topic names to exact IDs, or report that topics are disabled."""

        params = self._catalog_params(query=query, limit=limit)
        response = await self._http.get(
            f"{self._base_url}/api/mcp/topics",
            params=params,
        )
        data = self._response_data(response, "topic catalog", dict)
        return TopicListResult.model_validate(data)

    async def list_activity_types(self) -> ActivityTypeListResult:
        """Return the exact activity category and subtype IDs for this instance."""

        response = await self._http.get(f"{self._base_url}/api/mcp/activity-types")
        data = self._response_data(response, "activity type catalog", dict)
        return ActivityTypeListResult.model_validate(data)

    async def search_activities(
        self,
        *,
        query: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        type: str | None = None,
        subtype: str | None = None,
        person: str | None = None,
        unit: str | None = None,
        topic: str | None = None,
        limit: int = 10,
    ) -> ActivitySearchResult:
        """Search activities while returning only compact evidence bundles."""

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        params: list[tuple[str, str]] = [("limit", str(limit))]
        if query:
            params.append(("q", query.strip()))

        parsed_dates: dict[str, date] = {}
        for name, value in (("from_date", from_date), ("to_date", to_date)):
            if not value:
                continue
            try:
                parsed_dates[name] = date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(f"{name} must use the YYYY-MM-DD format") from exc
            params.append((name, parsed_dates[name].isoformat()))
        if (
            "from_date" in parsed_dates
            and "to_date" in parsed_dates
            and parsed_dates["from_date"] > parsed_dates["to_date"]
        ):
            raise ValueError("from_date must not be after to_date")

        for name, value in (
            ("type", type),
            ("subtype", subtype),
            ("person", person),
            ("unit", unit),
            ("topic", topic),
        ):
            if value:
                params.append((name, value.strip()))

        response = await self._http.get(
            f"{self._base_url}/api/mcp/activities",
            params=params,
        )
        data = self._response_data(response, "activity search", list)
        activities = [
            self._activity(item) for item in data[:limit] if isinstance(item, dict)
        ]
        return ActivitySearchResult(count=len(activities), activities=activities)

    async def get_activity(self, activity_id: str) -> ActivitySummary:
        """Return one compact activity evidence bundle by MongoDB object ID."""

        if re.fullmatch(r"[a-fA-F0-9]{24}", activity_id) is None:
            raise ValueError("activity_id must be a 24-character hexadecimal ID")
        response = await self._http.get(
            f"{self._base_url}/api/mcp/activities/{activity_id}"
        )
        if response.status_code == 404:
            raise OsirisApiError("OSIRIS activity was not found")
        data = self._response_data(response, "activity lookup", list)
        if len(data) != 1 or not isinstance(data[0], dict):
            raise OsirisApiError("OSIRIS returned invalid activity lookup data")
        return self._activity(data[0])

    async def search_people(
        self,
        query: str,
        *,
        unit: str | None = None,
        active_only: bool = True,
        limit: int = 10,
    ) -> PersonSearchResult:
        """Resolve a name, username, alias, or ORCID to OSIRIS person IDs."""

        query = query.strip()
        if not 2 <= len(query) <= 200:
            raise ValueError("query must contain between 2 and 200 characters")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        params = [
            ("q", query),
            ("active_only", str(active_only).lower()),
            ("limit", str(limit)),
        ]
        if unit:
            params.append(("unit", unit.strip()))
        response = await self._http.get(
            f"{self._base_url}/api/mcp/persons",
            params=params,
        )
        data = self._response_data(response, "person search", list)
        persons = [
            self._person(item) for item in data[:limit] if isinstance(item, dict)
        ]
        return PersonSearchResult(count=len(persons), persons=persons)

    async def get_person(self, person_id: str) -> PersonDetail:
        """Return one compact public research profile by username."""

        person_id = person_id.strip()
        if not 1 <= len(person_id) <= 200 or "/" in person_id:
            raise ValueError("person_id must be a valid OSIRIS username")
        response = await self._http.get(
            f"{self._base_url}/api/mcp/persons/{quote(person_id, safe='')}"
        )
        if response.status_code == 404:
            raise OsirisApiError("OSIRIS person was not found")
        data = self._response_data(response, "person lookup", dict)
        person = PersonDetail.model_validate(data)
        person.source_url = f"{self._base_url}/profile/{quote(person.id, safe='')}"
        return person

    async def search_experts(
        self,
        query: str,
        *,
        unit: str | None = None,
        limit: int = 10,
    ) -> ExpertSearchResult:
        """Find active researchers using explicit, traceable expertise evidence."""

        query = query.strip()
        if not 2 <= len(query) <= 200:
            raise ValueError("query must contain between 2 and 200 characters")
        if not 1 <= limit <= 25:
            raise ValueError("limit must be between 1 and 25")
        params = [("q", query), ("limit", str(limit))]
        if unit:
            params.append(("unit", unit.strip()))
        response = await self._http.get(
            f"{self._base_url}/api/mcp/experts",
            params=params,
        )
        data = self._response_data(response, "expert search", dict)
        result = ExpertSearchResult.model_validate(
            {
                "count": len(data.get("experts", [])),
                **data,
            }
        )
        for person in result.experts:
            person.source_url = (
                f"{self._base_url}/profile/{quote(person.id, safe='')}"
            )
        return result

    async def search_projects(
        self,
        *,
        query: str | None = None,
        active_on: str | None = None,
        status: str | None = None,
        topic: str | None = None,
        unit: str | None = None,
        limit: int = 10,
    ) -> ProjectSearchResult:
        """Search projects using a fixed input and output allowlist."""

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")

        params: list[tuple[str, str]] = [
            ("limit", str(limit)),
        ]
        if query:
            params.append(("q", query.strip()))
        if active_on:
            try:
                parsed_date = date.fromisoformat(active_on)
            except ValueError as exc:
                raise ValueError("active_on must use the YYYY-MM-DD format") from exc
            params.append(("active_on", parsed_date.isoformat()))
        for name, value in (("status", status), ("topic", topic), ("unit", unit)):
            if value:
                params.append((name, value.strip()))

        response = await self._http.get(
            f"{self._base_url}/api/mcp/projects",
            params=params,
        )
        if response.status_code != 200:
            raise OsirisApiError(
                f"OSIRIS project search failed with HTTP {response.status_code}"
            )

        try:
            payload: dict[str, Any] = response.json()
            if payload.get("status") != 200 or not isinstance(payload.get("data"), list):
                raise ValueError("unexpected response envelope")
        except (TypeError, ValueError) as exc:
            raise OsirisApiError("OSIRIS returned an invalid project response") from exc

        projects: list[ProjectSummary] = []
        for item in payload["data"][:limit]:
            if not isinstance(item, dict):
                continue
            project = ProjectSummary.model_validate(item)
            project.source_url = f"{self._base_url}/projects/view/{project.id}"
            projects.append(project)

        return ProjectSearchResult(count=len(projects), projects=projects)

    async def get_project(self, project_id: str) -> ProjectSummary:
        """Return one allowlisted project by its MongoDB object ID."""

        if re.fullmatch(r"[a-fA-F0-9]{24}", project_id) is None:
            raise ValueError("project_id must be a 24-character hexadecimal ID")

        response = await self._http.get(
            f"{self._base_url}/api/mcp/projects/{project_id}"
        )
        if response.status_code == 404:
            raise OsirisApiError("OSIRIS project was not found")
        if response.status_code != 200:
            raise OsirisApiError(
                f"OSIRIS project lookup failed with HTTP {response.status_code}"
            )

        try:
            payload: dict[str, Any] = response.json()
            data = payload.get("data")
            if payload.get("status") != 200 or not isinstance(data, list) or len(data) != 1:
                raise ValueError("unexpected response envelope")
            project = ProjectSummary.model_validate(data[0])
        except (TypeError, ValueError) as exc:
            raise OsirisApiError("OSIRIS returned an invalid project response") from exc

        project.source_url = f"{self._base_url}/projects/view/{project.id}"
        return project

    @staticmethod
    def _catalog_params(*, query: str | None, limit: int) -> list[tuple[str, str]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        params = [("limit", str(limit))]
        if query:
            params.append(("q", query.strip()))
        return params

    @staticmethod
    def _response_data(
        response: httpx.Response,
        description: str,
        expected_type: type[dict] | type[list],
    ) -> Any:
        if response.status_code != 200:
            raise OsirisApiError(
                f"OSIRIS {description} request failed with HTTP {response.status_code}"
            )
        try:
            payload = response.json()
            data = payload.get("data")
            if payload.get("status") != 200 or not isinstance(data, expected_type):
                raise ValueError("unexpected response envelope")
            return data
        except (AttributeError, TypeError, ValueError) as exc:
            raise OsirisApiError(
                f"OSIRIS returned invalid {description} data"
            ) from exc

    def _activity(self, item: dict[str, Any]) -> ActivitySummary:
        activity = ActivitySummary.model_validate(item)
        activity.source_url = f"{self._base_url}/activities/view/{activity.id}"
        return activity

    def _person(self, item: dict[str, Any]) -> PersonSummary:
        person = PersonSummary.model_validate(item)
        person.source_url = f"{self._base_url}/profile/{quote(person.id, safe='')}"
        return person
