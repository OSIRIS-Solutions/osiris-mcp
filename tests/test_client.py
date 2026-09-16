import httpx

from osiris_mcp.client import OsirisClient
from osiris_mcp.config import Settings


async def test_project_search_uses_header_and_allowlisted_fields() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": [
                    {
                        "id": "project-1",
                        "name": "AI-BIO",
                        "title": "Artificial intelligence for biodiversity",
                        "abstract": "A research project.",
                        "internal_note": "must not leave the adapter",
                    }
                ],
            },
        )

    settings = Settings(
        base_url="https://osiris.example.org",
        client_id="osc_test-client",
        api_key="very-secret",
    )
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.search_projects(
            query="biodiversity",
            active_on="2026-09-14",
            status="active",
            topic="artificial-intelligence",
            unit="BIO",
            limit=5,
        )

    assert captured_request is not None
    assert captured_request.headers["X-OSIRIS-Client-ID"] == "osc_test-client"
    assert captured_request.headers["X-API-Key"] == "very-secret"
    assert "very-secret" not in str(captured_request.url)
    assert captured_request.url.path == "/api/mcp/projects"
    assert captured_request.url.params["q"] == "biodiversity"
    assert captured_request.url.params["active_on"] == "2026-09-14"
    assert captured_request.url.params["status"] == "active"
    assert captured_request.url.params["topic"] == "artificial-intelligence"
    assert captured_request.url.params["unit"] == "BIO"
    assert result.count == 1
    assert result.projects[0].title == "Artificial intelligence for biodiversity"
    assert "internal_note" not in result.projects[0].model_dump()


async def test_project_search_rejects_excessive_limit() -> None:
    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    ) as client:
        try:
            await client.search_projects(limit=51)
        except ValueError as exc:
            assert str(exc) == "limit must be between 1 and 50"
        else:
            raise AssertionError("expected an excessive limit to be rejected")


async def test_project_search_rejects_invalid_date() -> None:
    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    ) as client:
        try:
            await client.search_projects(active_on="14.09.2026")
        except ValueError as exc:
            assert str(exc) == "active_on must use the YYYY-MM-DD format"
        else:
            raise AssertionError("expected an invalid date to be rejected")


async def test_get_project_uses_dedicated_endpoint_and_allowlist() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": [{
                    "id": "dfee6418bdc6d2aa988db731",
                    "name": "AQUASHIELD",
                    "title": "Low-Energy Water Filtration Materials",
                    "internal_note": "must not leave the adapter",
                }],
            },
        )

    settings = Settings(base_url="https://osiris.example.org", api_key="secret")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        project = await client.get_project("dfee6418bdc6d2aa988db731")

    assert captured_request is not None
    assert captured_request.url.path == "/api/mcp/projects/dfee6418bdc6d2aa988db731"
    assert project.name == "AQUASHIELD"
    assert "internal_note" not in project.model_dump()


async def test_instance_info_exposes_capabilities_without_extra_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/mcp/instance"
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": {
                    "instance": {
                        "id": "ANKH",
                        "name": "ANKH Climate Research Center",
                        "osiris_version": "2.1.1",
                        "base_url": "https://osiris.example.org",
                        "default_language": "en",
                        "available_languages": ["en", "de"],
                        "timezone": "UTC",
                        "private_setting": "must not leave the adapter",
                    },
                    "features": {"projects": True, "topics": True},
                    "catalogs": {
                        "topics": {"available": True, "count": 5},
                        "units": {"available": True, "count": 8},
                    },
                    "supported_project_filters": ["query", "topic", "unit"],
                    "internal": "must not leave the adapter",
                },
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.get_instance_info()

    assert result.instance.id == "ANKH"
    assert result.catalogs["topics"].count == 5
    assert "private_setting" not in result.instance.model_dump()
    assert "internal" not in result.model_dump()


async def test_unit_catalog_resolves_exact_ids_and_paths() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": [{
                    "id": "RML",
                    "name": "Resilient Materials Lab",
                    "parent_id": "ANKH",
                    "level": 1,
                    "path": [
                        {"id": "ANKH", "name": "ANKH Climate Research Center"},
                        {"id": "RML", "name": "Resilient Materials Lab"},
                    ],
                    "active": True,
                    "secret": "must not leave the adapter",
                }],
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.list_units(query="materials", limit=12)

    assert captured_request is not None
    assert captured_request.url.params["q"] == "materials"
    assert captured_request.url.params["limit"] == "12"
    assert result.units[0].id == "RML"
    assert result.units[0].path[-1].id == "RML"
    assert "secret" not in result.units[0].model_dump()


async def test_topic_catalog_reports_unavailable_feature() -> None:
    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": {
                    "available": False,
                    "reason": "The topics feature is not enabled.",
                    "topics": [],
                },
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.list_topics()

    assert result.available is False
    assert result.reason == "The topics feature is not enabled."
    assert result.topics == []


async def test_catalog_rejects_excessive_limit() -> None:
    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    ) as client:
        try:
            await client.list_units(limit=201)
        except ValueError as exc:
            assert str(exc) == "limit must be between 1 and 200"
        else:
            raise AssertionError("expected an excessive limit to be rejected")


async def test_activity_type_catalog_preserves_exact_ids() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/mcp/activity-types"
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": {
                    "available": True,
                    "types": [{
                        "id": "publication",
                        "name": "Publications",
                        "subtypes": [{"id": "article", "name": "Journal Article"}],
                    }],
                },
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.list_activity_types()

    assert result.types[0].id == "publication"
    assert result.types[0].subtypes[0].id == "article"


async def test_activity_search_returns_only_compact_evidence() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": [{
                    "id": "6a94001d84a9e02d3f003b97",
                    "type": {"id": "publication", "label": "Publications"},
                    "subtype": {"id": "article", "label": "Journal Article"},
                    "title": "The DSMZ Digital Diversity Annotation Hub",
                    "start_date": "2026-08-17",
                    "end_date": "2026-08-17",
                    "persons": [{"id": "julia", "name": "Julia Koblitz"}],
                    "units": [{"id": "PSL", "name": "Predictive Systems Lab"}],
                    "citation": "Quadros E. et al. (2026) ...",
                    "identifiers": {
                        "doi": "10.1515/jib-2025-0058",
                        "pubmed": 42520009,
                    },
                    "affiliated": True,
                    "online_ahead_of_print": False,
                    "metrics": {
                        "impact_factor": 2,
                        "citation_count": 0,
                        "sjr": 0.445,
                        "quartile": "Q2",
                        "metrics_year": 2025,
                        "citation_count_updated_at": "2026-08-30",
                    },
                    "history": [{"private": "must not leave the adapter"}],
                    "openalex": {"verbose": "must not leave the adapter"},
                }],
            },
        )

    settings = Settings(base_url="https://osiris.example.org", api_key="secret")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.search_activities(
            query="diversity",
            from_date="2026-01-01",
            to_date="2026-12-31",
            type="publication",
            subtype="article",
            person="julia",
            unit="PSL",
            topic="ai-prediction",
            include_unaffiliated=True,
            include_online_ahead_of_print=True,
            limit=5,
        )

    assert captured_request is not None
    assert captured_request.url.path == "/api/mcp/activities"
    assert captured_request.url.params["from_date"] == "2026-01-01"
    assert captured_request.url.params["to_date"] == "2026-12-31"
    assert captured_request.url.params["type"] == "publication"
    assert captured_request.url.params["subtype"] == "article"
    assert captured_request.url.params["person"] == "julia"
    assert captured_request.url.params["unit"] == "PSL"
    assert captured_request.url.params["topic"] == "ai-prediction"
    assert captured_request.url.params["include_unaffiliated"] == "true"
    assert captured_request.url.params["include_online_ahead_of_print"] == "true"
    activity = result.activities[0]
    assert activity.identifiers["doi"] == "10.1515/jib-2025-0058"
    assert activity.identifiers["pubmed"] == "42520009"
    assert activity.affiliated is True
    assert activity.online_ahead_of_print is False
    assert activity.metrics is not None
    assert activity.metrics.impact_factor == 2.0
    assert activity.metrics.citation_count == 0
    assert activity.metrics.sjr == 0.445
    assert activity.metrics.quartile == "Q2"
    assert activity.metrics.metrics_year == 2025
    assert activity.metrics.citation_count_updated_at == "2026-08-30"
    assert activity.source_url.endswith("/activities/view/6a94001d84a9e02d3f003b97")
    assert "history" not in activity.model_dump()
    assert "openalex" not in activity.model_dump()


async def test_activity_search_rejects_reversed_date_range() -> None:
    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    ) as client:
        try:
            await client.search_activities(
                from_date="2026-12-31",
                to_date="2026-01-01",
            )
        except ValueError as exc:
            assert str(exc) == "from_date must not be after to_date"
        else:
            raise AssertionError("expected a reversed date range to be rejected")


async def test_activity_search_exposes_complete_pagination_metadata() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "total": 3,
                "offset": 1,
                "limit": 1,
                "has_more": True,
                "next_offset": 2,
                "data": [{
                    "id": "6a94001d84a9e02d3f003b97",
                    "type": {"id": "publication", "label": "Publications"},
                    "subtype": {"id": "article", "label": "Journal Article"},
                    "title": "Second result",
                    "persons": [],
                    "units": [],
                    "citation": "A compact citation.",
                    "identifiers": {},
                }],
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.search_activities(limit=1, offset=1)

    assert captured_request is not None
    assert captured_request.url.params["offset"] == "1"
    assert result.count == 1
    assert result.total == 3
    assert result.has_more is True
    assert result.next_offset == 2


async def test_activity_search_rejects_invalid_offset() -> None:
    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(lambda _: httpx.Response(200)),
    ) as client:
        try:
            await client.search_activities(offset=-1)
        except ValueError as exc:
            assert str(exc) == "offset must be between 0 and 1000000"
        else:
            raise AssertionError("expected a negative offset to be rejected")


async def test_get_activity_uses_dedicated_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/mcp/activities/6a94001d84a9e02d3f003b97"
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": [{
                    "id": "6a94001d84a9e02d3f003b97",
                    "type": {"id": "publication", "label": "Publications"},
                    "subtype": {"id": "article", "label": "Journal Article"},
                    "title": "The DSMZ Digital Diversity Annotation Hub",
                    "persons": [],
                    "units": [],
                    "citation": "A compact citation.",
                    "identifiers": {},
                }],
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.get_activity("6a94001d84a9e02d3f003b97")

    assert result.citation == "A compact citation."
    assert result.affiliated is None
    assert result.online_ahead_of_print is False
    assert result.metrics is None


async def test_search_people_resolves_identity_without_private_fields() -> None:
    captured_request: httpx.Request | None = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": [{
                    "id": "julia",
                    "name": "Julia Koblitz",
                    "academic_title": "Dr.",
                    "position": "Developer of OSIRIS Portfolio",
                    "active": True,
                    "units": [{
                        "id": "PSL",
                        "name": "Predictive Systems Lab",
                        "scientific": True,
                    }],
                    "mail": "must not leave the adapter",
                    "lastlogin": "must not leave the adapter",
                }],
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.search_people("Julia", unit="PSL", limit=5)

    assert captured_request is not None
    assert captured_request.url.params["active_only"] == "true"
    assert captured_request.url.params["unit"] == "PSL"
    person = result.persons[0]
    assert person.id == "julia"
    assert person.units[0].scientific is True
    assert person.source_url == "https://osiris.example.org/profile/julia"
    assert "mail" not in person.model_dump()
    assert "lastlogin" not in person.model_dump()


async def test_get_person_returns_compact_research_profile() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/mcp/persons/julia"
        return httpx.Response(
            200,
            json={
                "status": 200,
                "data": {
                    "id": "julia",
                    "name": "Julia Koblitz",
                    "active": True,
                    "units": [],
                    "orcid": "0000-0002-7260-2129",
                    "expertise": ["Artificial Intelligence"],
                    "research_interests": {
                        "en": ["Data Integration"],
                        "de": ["Datenintegration"],
                    },
                    "topics": [{"id": "ai-prediction", "name": "AI & Prediction"}],
                    "research_profile": {
                        "en": "Research about data.",
                        "de": "",
                    },
                    "biography": "must not leave the adapter",
                    "roles": ["must not leave the adapter"],
                },
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        person = await client.get_person("julia")

    assert person.orcid == "0000-0002-7260-2129"
    assert person.topics[0].id == "ai-prediction"
    assert "biography" not in person.model_dump()
    assert "roles" not in person.model_dump()


async def test_search_experts_keeps_openalex_evidence_explicit() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/mcp/experts"
        return httpx.Response(
            200,
            json={
                "status": 200,
                "count": 1,
                "data": {
                    "openalex_enabled": True,
                    "experts": [{
                        "id": "julia",
                        "name": "Julia Koblitz",
                        "active": True,
                        "units": [],
                        "evidence": {
                            "expertise": ["Artificial Intelligence"],
                            "openalex_topics": [{
                                "id": "T12072",
                                "name": "Machine Learning and Algorithms",
                                "path": "Computer Science → Artificial Intelligence",
                                "publication_count": 2,
                                "max_score": 0.93,
                            }],
                        },
                    }],
                },
            },
        )

    settings = Settings(base_url="https://osiris.example.org")
    async with OsirisClient(
        settings,
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await client.search_experts("Artificial Intelligence")

    assert result.openalex_enabled is True
    assert result.experts[0].evidence.expertise == ["Artificial Intelligence"]
    assert result.experts[0].evidence.openalex_topics[0].publication_count == 2
