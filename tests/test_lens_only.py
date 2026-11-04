"""Google Lens remains the only image search path after upgrading old configs."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from search import SearchResult, SearchService, _EngineUnavailable


@pytest.mark.asyncio
async def test_legacy_engine_settings_still_run_lens_once():
    service = SearchService(
        {"engines": ["baidu", "ascii2d"], "saucenao_api_key": "unused"}
    )
    first = SearchResult(
        platform="X",
        url="https://x.com/i/status/123",
        verified=True,
        engine="google_lens",
        match_type="exact",
    )
    author = SearchResult(
        platform="X",
        account="@artist",
        name="Artist",
        url="https://x.com/artist/status/123",
        verified=True,
        engine="google_lens",
        match_type="exact",
    )
    service._search_lens = AsyncMock(return_value=[first, author])
    service._source_account = AsyncMock(side_effect=lambda result, *args: result)
    with patch("search.recover_x") as recover:
        report = await service.search(b"image")
    service._search_lens.assert_awaited_once_with(b"image")
    recover.assert_not_called()
    assert len(report.exact_sources) == 1
    assert len(report.results) == 1
    assert report.results[0].account == "@artist"
    assert report.results[0].verified
    assert report.engine_results == {"google_lens": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error, message",
    [
        (RuntimeError("https://name:secret@proxy.invalid"), "搜索请求或结果解析失败"),
        (_EngineUnavailable("搜索服务返回 HTTP 403"), "搜索服务返回 HTTP 403"),
    ],
)
async def test_lens_failure_returns_error_without_source_recovery(error, message):
    service = SearchService({})
    service._search_lens = AsyncMock(side_effect=error)
    with patch("search.recover_x") as recover:
        report = await service.search(b"image")
    assert report.errors == {"google_lens": message}
    assert report.engine_results == {"google_lens": 0}
    assert not report.results
    assert "secret" not in str(report)
    recover.assert_not_called()


@pytest.mark.asyncio
async def test_lens_timeout_and_empty_image():
    service = SearchService({})
    service.timeout = 0.01

    async def slow(image):
        await asyncio.sleep(1)

    service._search_lens = AsyncMock(side_effect=slow)
    report = await service.search(b"")
    service._search_lens.assert_not_awaited()
    assert report.errors == {"image": "图片内容为空"}
    report = await service.search(b"image")
    assert report.errors == {"google_lens": "搜索超时"}
    assert not report.results


def test_removed_engine_options_are_absent_from_schema():
    schema = json.loads(
        (Path(__file__).parents[1] / "_conf_schema.json").read_text(encoding="utf-8")
    )
    assert "engines" not in schema
    assert "saucenao_api_key" not in schema
