"""
InDoc-CLI: Core Ollama Engine Module.

This module handles all communication with the Ollama API.
"""

import httpx
import logging
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("InDoc.OllamaEngine")


class OllamaEngine:
    """Handles connectivity and generation logic with the Ollama API."""

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        """
        Initialize the Ollama engine.

        Args:
            base_url: The base URL for the Ollama API.
        """
        self.base_url = base_url
        self.client = httpx.Client(timeout=30.0)
        self.system_prompt = (
            "You are a professional Senior Software Documentation Engineer. "
            "Analyze the provided source code and generate high-quality, professional technical documentation. "
            "1. Identify the programming language automatically. "
            "2. Explain the code's purpose, parameters, and return values. "
            "3. List potential edge cases or error handling. "
            "4. Output in clean Markdown format. "
            "5. No conversational filler; documentation only."
        )

    def is_installed(self) -> bool:
        """Check if Ollama service is installed and responding."""
        try:
            self.client.get(f"{self.base_url}/api/tags")
            return True
        except Exception:
            return False

    def get_available_models(self) -> List[str]:
        """
        Fetch available models from Ollama API dynamically.

        Returns:
            List of model names.
        """
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return [model['name'] for model in data.get('models', [])]
        except Exception as e:
            logger.error(f"Failed to fetch models: {e}")
            return []

    def get_active_model(self) -> Optional[str]:
        """
        Get the currently active model from Ollama.

        Returns:
            The active model name or None if not available.
        """
        models = self.get_available_models()
        return models[0] if models else None

    def check_health(self) -> Tuple[bool, str, Optional[str]]:
        """
        Perform a real-time health check.

        Returns:
            Tuple of (is_online, message, active_model).
        """
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get('models', [])
            if models:
                active = models[0]['name']
                return True, "Ollama Service is ONLINE", active
            return True, "Ollama Service is ONLINE", None
        except httpx.ConnectError:
            return False, "Ollama Service is OFFLINE - Connection refused", None
        except Exception as e:
            return False, f"Ollama Service Error: {str(e)}", None

    def generate_documentation(self, code_snippet: str, model: Optional[str] = None) -> str:
        """
        Send code to Ollama API for documentation generation.

        Args:
            code_snippet: The source code to analyze.
            model: The model to use (defaults to first available).

        Returns:
            Generated documentation string.
        """
        target_model = model or self.get_active_model()
        if not target_model:
            return "Error: No model available. Please pull a model first."

        try:
            response = self.client.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": target_model,
                    "system": self.system_prompt,
                    "prompt": f"Code to analyze:\n{code_snippet}",
                    "stream": False
                }
            )
            response.raise_for_status()
            result = response.json()
            return result.get('response', 'No response from model.')
        except httpx.ResponseError as e:
            return f"Error: Ollama Response Error (Status {e.response.status_code}): {e.response.text}"
        except Exception as e:
            logger.error(f"Generation error: {e}")
            if "connection" in str(e).lower():
                return "Error: Could not connect to Ollama. Please ensure the service is running."
            return f"Error: Unexpected engine error: {str(e)}"

    def pull_model(self, model_name: str) -> bool:
        """
        Pull a model from Ollama library.

        Args:
            model_name: Name of the model to pull.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self.client.post(f"{self.base_url}/api/pull", json={"name": model_name})
            return True
        except Exception as e:
            logger.error(f"Failed to pull model {model_name}: {e}")
            return False

    def __del__(self) -> None:
        """Cleanup client connection."""
        self.client.close()
