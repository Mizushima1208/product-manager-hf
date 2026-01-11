"""Web search endpoints for manuals and specifications."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import os

router = APIRouter(prefix="/api/search", tags=["search"])

# Tavily API key from environment
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


class SearchRequest(BaseModel):
    """Search request schema."""
    query: str
    search_type: str = "manual"  # manual, spec, parts


class SearchResult(BaseModel):
    """Search result item."""
    title: str
    url: str
    snippet: str
    score: Optional[float] = None


class SearchResponse(BaseModel):
    """Search response schema."""
    results: List[SearchResult]
    query: str


@router.post("", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """Search for manuals, specifications, or parts lists."""

    # Build search query based on type
    type_keywords = {
        "manual": "説明書 取扱説明書 マニュアル PDF",
        "spec": "仕様書 カタログ スペック PDF",
        "parts": "部品表 パーツリスト 部品図 PDF"
    }

    keywords = type_keywords.get(request.search_type, type_keywords["manual"])
    full_query = f"{request.query} {keywords}"

    # Try Tavily first, fall back to DuckDuckGo
    if TAVILY_API_KEY:
        try:
            return await search_with_tavily(full_query, request.query)
        except Exception as e:
            print(f"Tavily search failed: {e}, falling back to DuckDuckGo")

    # Fallback to DuckDuckGo
    return await search_with_duckduckgo(full_query, request.query)


async def search_with_tavily(query: str, original_query: str) -> SearchResponse:
    """Search using Tavily API."""
    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY)
    response = client.search(
        query=query,
        search_depth="basic",
        max_results=10
    )

    results = []
    for item in response.get("results", []):
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", "")[:300],
            score=item.get("score")
        ))

    return SearchResponse(results=results, query=original_query)


async def search_with_duckduckgo(query: str, original_query: str) -> SearchResponse:
    """Search using DuckDuckGo (no API key required)."""
    from duckduckgo_search import DDGS

    results = []
    try:
        with DDGS() as ddgs:
            search_results = list(ddgs.text(query, max_results=10))

            for item in search_results:
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("href", ""),
                    snippet=item.get("body", "")[:300]
                ))
    except Exception as e:
        print(f"DuckDuckGo search error: {e}")
        raise HTTPException(status_code=500, detail="検索に失敗しました")

    return SearchResponse(results=results, query=original_query)


@router.get("/config")
async def get_search_config():
    """Get search configuration status."""
    return {
        "tavily_configured": bool(TAVILY_API_KEY),
        "fallback": "duckduckgo"
    }
