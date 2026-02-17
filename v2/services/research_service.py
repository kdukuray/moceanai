"""
Web research service using Tavily search API + LLM synthesis.

This service powers the research phase of the V2 pipelines. It:
  1. Generates focused search queries from the topic via LLM
  2. Runs them in parallel through Tavily's search API
  3. Synthesizes the raw results into a structured ResearchBrief

The research phase is optional (toggled by the user) but dramatically
improves script quality by grounding content in real, current facts
instead of relying solely on LLM training data.

Usage:
    service = ResearchService(llm_provider="google")
    brief, trends = await service.run_full_research(
        topic="intermittent fasting",
        target_audience="health-conscious millennials",
        platform="TikTok",
    )

Environment variables required:
    TAVILY_API_KEY -- Tavily search API key
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from tavily import TavilyClient

from v2.core.v2_models import (
    ResearchBrief,
    ResearchQueriesContainer,
    TrendContext,
)
from v2.core.v2_prompts import (
    RESEARCH_QUERIES_PROMPT,
    RESEARCH_SYNTHESIS_PROMPT,
    TREND_ANALYSIS_PROMPT,
)
from v2.services.llm_service import LLMService

logger = logging.getLogger(__name__)


class ResearchService:
    """
    Performs web research and synthesizes findings for content generation.

    Combines Tavily search with LLM analysis to produce structured
    research briefs that scriptwriters can reference for grounded content.
    """

    def __init__(self, llm_provider: str = "google"):
        """
        Initialize the research service.

        Args:
            llm_provider: LLM provider for query generation and synthesis.
        """
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "TAVILY_API_KEY not set in environment. "
                "Get one at https://tavily.com"
            )
        self._tavily = TavilyClient(api_key=api_key)
        self._llm = LLMService(provider=llm_provider)

    async def run_full_research(
        self,
        topic: str,
        target_audience: str,
        platform: str = "YouTube",
    ) -> tuple[ResearchBrief, TrendContext]:
        """
        Run the complete research pipeline: topic research + trend analysis.

        Both run in parallel. Total latency = max(topic_research, trend_analysis).

        Args:
            topic: The video subject.
            target_audience: Who will watch.
            platform: Target platform for trend analysis.

        Returns:
            Tuple of (ResearchBrief, TrendContext).
        """
        research_brief: Optional[ResearchBrief] = None
        trend_context: Optional[TrendContext] = None

        async with asyncio.TaskGroup() as tg:
            research_task = tg.create_task(
                self.research_topic(topic, target_audience)
            )
            trend_task = tg.create_task(
                self.analyze_trends(topic, platform)
            )

        research_brief = research_task.result()
        trend_context = trend_task.result()

        return research_brief, trend_context

    async def research_topic(
        self,
        topic: str,
        target_audience: str,
        num_queries: int = 3,
    ) -> ResearchBrief:
        """
        Research a topic by generating search queries and synthesizing results.

        Steps:
          1. LLM generates focused search queries from the topic
          2. Each query is run through Tavily in parallel
          3. Raw results are synthesized into a ResearchBrief

        Args:
            topic: The video subject.
            target_audience: Who will watch.
            num_queries: Max number of search queries (3-5).

        Returns:
            Synthesized ResearchBrief.
        """
        # Step 1: Generate search queries via LLM
        logger.info(f"Generating research queries for: {topic}")
        queries_result = self._llm.generate_structured(
            system_prompt=RESEARCH_QUERIES_PROMPT,
            user_payload={
                "topic": topic,
                "target_audience": target_audience,
            },
            output_model=ResearchQueriesContainer,
        )
        queries = queries_result.queries[:num_queries]
        logger.info(f"Research queries: {queries}")

        # Step 2: Run all queries through Tavily in parallel
        raw_results = await self._run_searches(queries)

        # Step 3: Synthesize into ResearchBrief
        logger.info("Synthesizing research results...")
        brief = self._llm.generate_structured(
            system_prompt=RESEARCH_SYNTHESIS_PROMPT,
            user_payload={
                "topic": topic,
                "target_audience": target_audience,
                "raw_search_results": raw_results,
            },
            output_model=ResearchBrief,
        )
        logger.info(
            f"Research brief: {len(brief.key_facts)} facts, "
            f"{len(brief.statistics)} stats"
        )
        return brief

    async def analyze_trends(
        self,
        topic: str,
        platform: str = "YouTube",
    ) -> TrendContext:
        """
        Analyze content trends for a topic on a specific platform.

        Searches for what content is performing well and what's saturated,
        then synthesizes into a TrendContext.

        Args:
            topic: The video subject.
            platform: Target platform.

        Returns:
            TrendContext with hooks, saturated angles, and gaps.
        """
        logger.info(f"Analyzing trends for: {topic} on {platform}")

        # Search for trending content on this topic
        trend_query = f"{topic} {platform} viral content trends 2025 2026"
        raw_results = await self._run_searches([trend_query])

        trend_ctx = self._llm.generate_structured(
            system_prompt=TREND_ANALYSIS_PROMPT,
            user_payload={
                "topic": topic,
                "platform": platform,
                "raw_search_results": raw_results,
            },
            output_model=TrendContext,
        )
        logger.info(
            f"Trend analysis: {len(trend_ctx.working_hooks)} hooks, "
            f"{len(trend_ctx.content_gaps)} gaps"
        )
        return trend_ctx

    async def _run_searches(self, queries: list[str]) -> str:
        """
        Run multiple Tavily searches in parallel and concatenate results.

        Args:
            queries: List of search query strings.

        Returns:
            Concatenated search results as a single string.
        """
        results_parts: list[str] = []

        async def _search(query: str) -> str:
            """Run a single Tavily search in a thread."""
            def _sync_search() -> str:
                try:
                    result = self._tavily.search(
                        query=query,
                        search_depth="basic",
                        max_results=5,
                    )
                    snippets = []
                    for r in result.get("results", []):
                        title = r.get("title", "")
                        content = r.get("content", "")
                        url = r.get("url", "")
                        snippets.append(f"[{title}] ({url})\n{content}")
                    return f"\n\n--- Query: {query} ---\n" + "\n\n".join(snippets)
                except Exception as e:
                    logger.warning(f"Tavily search failed for '{query}': {e}")
                    return f"\n\n--- Query: {query} ---\n[Search failed: {e}]"

            return await asyncio.to_thread(_sync_search)

        tasks = []
        async with asyncio.TaskGroup() as tg:
            for q in queries:
                tasks.append(tg.create_task(_search(q)))

        for task in tasks:
            results_parts.append(task.result())

        combined = "\n".join(results_parts)
        logger.info(f"Search results: {len(combined)} chars from {len(queries)} queries")
        return combined
