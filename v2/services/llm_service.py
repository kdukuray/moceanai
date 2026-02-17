"""
Multi-provider LLM service with retry logic and structured output.

This module wraps LangChain's chat models to provide a clean interface for
the pipeline. Key features:

  - **Multi-provider support**: Google Gemini, OpenAI, Anthropic, xAI, DeepSeek.
    Just pass the provider name; the module handles model name and API key lookup.

  - **Structured output**: Pass a Pydantic model and get validated, typed JSON
    back from the LLM. No manual JSON parsing needed.

  - **Automatic retries**: All calls use tenacity with 3 attempts and exponential
    backoff. This handles transient API errors, rate limits, and timeouts.

Usage:
    llm = LLMService(provider="google")
    result = llm.generate_structured(
        system_prompt=GOAL_GENERATION_PROMPT,
        user_payload={"topic": "credit scores", ...},
        output_model=GoalContainer,
    )
    print(result.goal)  # Typed access to the LLM's response

To add a new provider:
    1. Add it to LLM_MODELS and LLM_PROVIDER_MAP in config.py
    2. Ensure the API key env var is set (e.g., DEEPSEEK_API_KEY)
    3. That's it — the service will use it automatically
"""

from __future__ import annotations

import json
import logging
from typing import Type, TypeVar

from langchain.chat_models import init_chat_model
from langchain.messages import HumanMessage, SystemMessage
from pydantic import BaseModel
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from v2.core.config import LLM_MODELS, LLM_PROVIDER_MAP

logger = logging.getLogger(__name__)

# Generic type variable for structured output models
T = TypeVar("T", bound=BaseModel)


class LLMService:
    """
    Wraps LangChain chat models with retries and structured output.

    Attributes:
        provider: The LLM provider key (e.g., "google", "openai").
        _model:   The initialized LangChain chat model instance.
    """

    def __init__(self, provider: str = "google"):
        """
        Initialize the LLM service for a specific provider.

        Args:
            provider: One of "google", "openai", "anthropic", "xai", "deepseek".
                      The model name and API config are looked up from config.py.
        """
        self.provider = provider
        provider_key = LLM_PROVIDER_MAP.get(provider, "google-genai")
        model_name = LLM_MODELS.get(provider, "gemini-2.5-pro")
        self._model = init_chat_model(model_provider=provider_key, model=model_name)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def generate_structured(
        self,
        system_prompt: str,
        user_payload: dict | str,
        output_model: Type[T],
    ) -> T:
        """
        Call the LLM with a system prompt and user payload, returning
        a validated Pydantic model instance.

        This uses LangChain's `.with_structured_output()` which instructs
        the LLM to return JSON matching the Pydantic schema.

        Args:
            system_prompt: The system message defining the LLM's role/task.
            user_payload:  The user data (dict auto-serialized to JSON string).
            output_model:  Pydantic model class for response validation.

        Returns:
            Instance of output_model populated from the LLM's response.

        Raises:
            Exception: After 3 failed attempts (propagated from tenacity).
        """
        structured_model = self._model.with_structured_output(output_model)

        # Convert dict payloads to JSON strings
        payload_str = (
            json.dumps(user_payload)
            if isinstance(user_payload, dict)
            else user_payload
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=payload_str),
        ]

        logger.info(
            f"LLM call: provider={self.provider}, model={output_model.__name__}"
        )
        result = structured_model.invoke(messages)
        logger.info(f"LLM response received: {output_model.__name__}")
        return result

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def generate_text(self, system_prompt: str, user_payload: dict | str) -> str:
        """
        Call the LLM and return raw text response (no structured output).

        Args:
            system_prompt: The system message.
            user_payload:  The user data.

        Returns:
            Raw text content from the LLM response.
        """
        payload_str = (
            json.dumps(user_payload)
            if isinstance(user_payload, dict)
            else user_payload
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=payload_str),
        ]
        response = self._model.invoke(messages)
        return response.content
