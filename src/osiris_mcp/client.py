# SPDX-FileCopyrightText: 2026 Julia Koblitz, OSIRIS Solutions GmbH
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Narrow HTTP adapter for the existing OSIRIS API."""

from datetime import date
import re
from typing import Any, Literal, TypeVar
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ValidationError

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


ModelT = TypeVar("ModelT", bound=BaseModel)


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

    async def _get(
        self,
        url: str,
        *,
        params: list[tuple[str, str]] | None = None,
    ) -> httpx.Response:
        """Perform a GET without exposing transport details to MCP clients."""

        try:
            return await self._http.get(url, params=params)
        except httpx.RequestError as exc:
            raise OsirisApiError(
                "OSIRIS could not be reached; no request ID is available"
            ) from exc

    async def get_instance_info(self) -> InstanceInfo:
        """Return identity, capabilities, and catalogs for this installation."""

        response = await self._get(f"{self._base_url}/api/mcp/instance")
        data = self._response_data(response, "instance information", dict)
        return self._validated_model(
            response,
            InstanceInfo,
            data,
            "instance information",
        )

    async def list_units(
        self,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> UnitListResult:
        """Resolve human-readable unit names to exact instance-specific IDs."""

        params = self._catalog_params(query=query, limit=limit, offset=offset)
        response = await self._get(
            f"{self._base_url}/api/mcp/units",
            params=params,
        )
        data, payload = self._response_envelope(response, "unit catalog", list)
        units = [
            self._validated_model(response, UnitInfo, item, "unit catalog")
            for item in data
            if isinstance(item, dict)
        ]
        return self._validated_model(
            response,
            UnitListResult,
            {
                **self._page_metadata(payload, len(units), limit, offset),
                "units": units,
            },
            "unit catalog",
        )

    async def list_topics(
        self,
        *,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> TopicListResult:
        """Resolve topic names to exact IDs, or report that topics are disabled."""

        params = self._catalog_params(query=query, limit=limit, offset=offset)
        response = await self._get(
            f"{self._base_url}/api/mcp/topics",
            params=params,
        )
        data, payload = self._response_envelope(response, "topic catalog", dict)
        return self._validated_model(
            response,
            TopicListResult,
            {
                **data,
                **self._page_metadata(
                    payload,
                    len(data.get("topics", [])),
                    limit,
                    offset,
                ),
            },
            "topic catalog",
        )

    async def list_activity_types(self) -> ActivityTypeListResult:
        """Return the exact activity category and subtype IDs for this instance."""

        response = await self._get(f"{self._base_url}/api/mcp/activity-types")
        data = self._response_data(response, "activity type catalog", dict)
        return self._validated_model(
            response,
            ActivityTypeListResult,
            data,
            "activity type catalog",
        )

    async def search_activities(
        self,
        *,
        query: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        date_field: Literal["start", "end"] = "start",
        type: str | None = None,
        subtype: str | None = None,
        person: str | None = None,
        unit: str | None = None,
        topic: str | None = None,
        include_unaffiliated: bool = False,
        include_online_ahead_of_print: bool = False,
        limit: int = 10,
        offset: int = 0,
    ) -> ActivitySearchResult:
        """Search activities while returning only compact evidence bundles."""

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        self._validate_offset(offset)
        params: list[tuple[str, str]] = [
            ("limit", str(limit)),
            ("offset", str(offset)),
        ]
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
        if date_field not in {"start", "end"}:
            raise ValueError("date_field must be start or end")
        if date_field != "start":
            params.append(("date_field", date_field))

        for name, value in (
            ("type", type),
            ("subtype", subtype),
            ("person", person),
            ("unit", unit),
            ("topic", topic),
        ):
            if value:
                params.append((name, value.strip()))

        if include_unaffiliated:
            params.append(("include_unaffiliated", "true"))
        if include_online_ahead_of_print:
            params.append(("include_online_ahead_of_print", "true"))

        response = await self._get(
            f"{self._base_url}/api/mcp/activities",
            params=params,
        )
        data, payload = self._response_envelope(response, "activity search", list)
        activities = [
            self._activity(response, item)
            for item in data[:limit]
            if isinstance(item, dict)
        ]
        return self._validated_model(
            response,
            ActivitySearchResult,
            {
                **self._page_metadata(payload, len(activities), limit, offset),
                "activities": activities,
            },
            "activity search",
        )

    async def get_activity(self, activity_id: str) -> ActivitySummary:
        """Return one compact activity evidence bundle by MongoDB object ID."""

        if re.fullmatch(r"[a-fA-F0-9]{24}", activity_id) is None:
            raise ValueError("activity_id must be a 24-character hexadecimal ID")
        response = await self._get(
            f"{self._base_url}/api/mcp/activities/{activity_id}"
        )
        if response.status_code == 404:
            raise self._api_error(response, "OSIRIS activity was not found")
        data = self._response_data(response, "activity lookup", list)
        if len(data) != 1 or not isinstance(data[0], dict):
            raise self._api_error(
                response,
                "OSIRIS returned invalid activity lookup data",
            )
        return self._activity(response, data[0])

    async def search_people(
        self,
        query: str,
        *,
        unit: str | None = None,
        active_only: bool = True,
        limit: int = 10,
        offset: int = 0,
    ) -> PersonSearchResult:
        """Resolve a name, username, alias, or ORCID to OSIRIS person IDs."""

        query = query.strip()
        if not 2 <= len(query) <= 200:
            raise ValueError("query must contain between 2 and 200 characters")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        self._validate_offset(offset)
        params = [
            ("q", query),
            ("active_only", str(active_only).lower()),
            ("limit", str(limit)),
            ("offset", str(offset)),
        ]
        if unit:
            params.append(("unit", unit.strip()))
        response = await self._get(
            f"{self._base_url}/api/mcp/persons",
            params=params,
        )
        data, payload = self._response_envelope(response, "person search", list)
        persons = [
            self._person(response, item)
            for item in data[:limit]
            if isinstance(item, dict)
        ]
        return self._validated_model(
            response,
            PersonSearchResult,
            {
                **self._page_metadata(payload, len(persons), limit, offset),
                "persons": persons,
            },
            "person search",
        )

    async def get_person(self, person_id: str) -> PersonDetail:
        """Return one compact public research profile by username."""

        person_id = person_id.strip()
        if not 1 <= len(person_id) <= 200 or "/" in person_id:
            raise ValueError("person_id must be a valid OSIRIS username")
        response = await self._get(
            f"{self._base_url}/api/mcp/persons/{quote(person_id, safe='')}"
        )
        if response.status_code == 404:
            raise self._api_error(response, "OSIRIS person was not found")
        data = self._response_data(response, "person lookup", dict)
        person = self._validated_model(
            response,
            PersonDetail,
            data,
            "person lookup",
        )
        person.source_url = f"{self._base_url}/profile/{quote(person.id, safe='')}"
        return person

    async def search_experts(
        self,
        query: str,
        *,
        unit: str | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> ExpertSearchResult:
        """Find active researchers using explicit, traceable expertise evidence."""

        query = query.strip()
        if not 2 <= len(query) <= 200:
            raise ValueError("query must contain between 2 and 200 characters")
        if not 1 <= limit <= 25:
            raise ValueError("limit must be between 1 and 25")
        self._validate_offset(offset)
        params = [("q", query), ("limit", str(limit)), ("offset", str(offset))]
        if unit:
            params.append(("unit", unit.strip()))
        response = await self._get(
            f"{self._base_url}/api/mcp/experts",
            params=params,
        )
        data, payload = self._response_envelope(response, "expert search", dict)
        result = self._validated_model(
            response,
            ExpertSearchResult,
            {
                **data,
                **self._page_metadata(
                    payload,
                    len(data.get("experts", [])),
                    limit,
                    offset,
                ),
            },
            "expert search",
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
        offset: int = 0,
    ) -> ProjectSearchResult:
        """Search projects using a fixed input and output allowlist."""

        if not 1 <= limit <= 50:
            raise ValueError("limit must be between 1 and 50")
        self._validate_offset(offset)

        params: list[tuple[str, str]] = [
            ("limit", str(limit)),
            ("offset", str(offset)),
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

        response = await self._get(
            f"{self._base_url}/api/mcp/projects",
            params=params,
        )
        data, payload = self._response_envelope(response, "project search", list)

        projects: list[ProjectSummary] = []
        for item in data[:limit]:
            if not isinstance(item, dict):
                continue
            project = self._validated_model(
                response,
                ProjectSummary,
                item,
                "project search",
            )
            project.source_url = f"{self._base_url}/projects/view/{project.id}"
            projects.append(project)

        return self._validated_model(
            response,
            ProjectSearchResult,
            {
                **self._page_metadata(payload, len(projects), limit, offset),
                "projects": projects,
            },
            "project search",
        )

    async def get_project(self, project_id: str) -> ProjectSummary:
        """Return one allowlisted project by its MongoDB object ID."""

        if re.fullmatch(r"[a-fA-F0-9]{24}", project_id) is None:
            raise ValueError("project_id must be a 24-character hexadecimal ID")

        response = await self._get(
            f"{self._base_url}/api/mcp/projects/{project_id}"
        )
        if response.status_code == 404:
            raise self._api_error(response, "OSIRIS project was not found")
        data = self._response_data(response, "project lookup", list)
        if len(data) != 1 or not isinstance(data[0], dict):
            raise self._api_error(
                response,
                "OSIRIS returned invalid project lookup data",
            )
        project = self._validated_model(
            response,
            ProjectSummary,
            data[0],
            "project lookup",
        )

        project.source_url = f"{self._base_url}/projects/view/{project.id}"
        return project

    @staticmethod
    def _catalog_params(
        *,
        query: str | None,
        limit: int,
        offset: int,
    ) -> list[tuple[str, str]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        OsirisClient._validate_offset(offset)
        params = [("limit", str(limit)), ("offset", str(offset))]
        if query:
            params.append(("q", query.strip()))
        return params

    @staticmethod
    def _response_data(
        response: httpx.Response,
        description: str,
        expected_type: type[dict] | type[list],
    ) -> Any:
        data, _ = OsirisClient._response_envelope(
            response,
            description,
            expected_type,
        )
        return data

    @staticmethod
    def _response_envelope(
        response: httpx.Response,
        description: str,
        expected_type: type[dict] | type[list],
    ) -> tuple[Any, dict[str, Any]]:
        if response.status_code != 200:
            raise OsirisClient._api_error(
                response,
                f"OSIRIS {description} request failed with HTTP {response.status_code}",
            )
        try:
            payload = response.json()
            data = payload.get("data")
            if payload.get("status") != 200 or not isinstance(data, expected_type):
                raise ValueError("unexpected response envelope")
            return data, payload
        except (AttributeError, TypeError, ValueError) as exc:
            raise OsirisClient._api_error(
                response,
                f"OSIRIS returned invalid {description} data",
            ) from exc

    @staticmethod
    def _api_error(response: httpx.Response, message: str) -> OsirisApiError:
        """Create a safe client error with a support reference, if available."""

        request_id = response.headers.get("X-Request-ID", "").strip()
        if not request_id:
            try:
                payload = response.json()
                candidate = payload.get("request_id")
                if isinstance(candidate, str):
                    request_id = candidate.strip()
            except (AttributeError, TypeError, ValueError):
                pass

        if re.fullmatch(r"req_[a-f0-9]{32}", request_id):
            message += f" (request ID: {request_id})"
        return OsirisApiError(message)

    @staticmethod
    def _validated_model(
        response: httpx.Response,
        model_type: type[ModelT],
        data: Any,
        description: str,
    ) -> ModelT:
        """Validate OSIRIS data without leaking rejected values in errors."""

        try:
            return model_type.model_validate(data)
        except ValidationError as exc:
            raise OsirisClient._api_error(
                response,
                f"OSIRIS returned invalid {description} data",
            ) from exc

    @staticmethod
    def _validate_offset(offset: int) -> None:
        if not 0 <= offset <= 1_000_000:
            raise ValueError("offset must be between 0 and 1000000")

    @staticmethod
    def _page_metadata(
        payload: dict[str, Any],
        item_count: int,
        requested_limit: int,
        requested_offset: int,
    ) -> dict[str, Any]:
        count = payload.get("count", item_count)
        total = payload.get("total", count)
        offset = payload.get("offset", requested_offset)
        limit = payload.get("limit", requested_limit)
        has_more = payload.get("has_more", item_count > 0 and offset + count < total)
        next_offset = payload.get("next_offset")
        if has_more and next_offset is None:
            next_offset = offset + count
        return {
            "count": count,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "next_offset": next_offset,
        }

    def _activity(
        self,
        response: httpx.Response,
        item: dict[str, Any],
    ) -> ActivitySummary:
        activity = self._validated_model(
            response,
            ActivitySummary,
            item,
            "activity",
        )
        activity.source_url = f"{self._base_url}/activities/view/{activity.id}"
        return activity

    def _person(
        self,
        response: httpx.Response,
        item: dict[str, Any],
    ) -> PersonSummary:
        person = self._validated_model(
            response,
            PersonSummary,
            item,
            "person",
        )
        person.source_url = f"{self._base_url}/profile/{quote(person.id, safe='')}"
        return person
