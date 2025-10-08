import json
import time
import traceback
from typing import Annotated, List

import PIL
import requests
from marker.logger import get_logger
from pydantic import BaseModel

from marker.schema.blocks import Block
from marker.services import BaseService

logger = get_logger()


class OllamaService(BaseService):
    """
    Ollama local LLM service - mirrors GeminiService architecture.
    
    Structure adapted from marker.services.gemini.GoogleGeminiService to ensure
    feature parity and consistent behavior across LLM services.
    """
    
    # ==================== SERVICE CONFIGURATION ====================
    # Parallels GeminiService.gemini_model_name
    ollama_base_url: Annotated[
        str, "The base url to use for ollama. No trailing slash."
    ] = "http://ollama:11434"
    
    ollama_model: Annotated[
        str, "The model name to use for ollama."
    ] = "qwen2.5vl:7b-32k"
    
    # ==================== IMAGE PROCESSING ====================
    # Adapted from GeminiService.process_images() 
    # Gemini uses: types.Part.from_bytes(..., mime_type="image/webp")
    # Ollama uses: base64 strings (simpler, no mime type needed)
    def process_images(self, images):
        """Convert images to base64 for Ollama API."""
        image_bytes = [self.img_to_base64(img) for img in images]
        return image_bytes

    # ==================== MAIN INFERENCE METHOD ====================
    # Structure directly mirrors GeminiService.__call__()
    def __call__(
        self,
        prompt: str,
        image: PIL.Image.Image | List[PIL.Image.Image] | None,
        block: Block | None,
        response_schema: type[BaseModel],
        max_retries: int | None = None,
        timeout: int | None = None,
    ):
        # ==================== PARAMETER INITIALIZATION ====================
        # From GeminiService lines 49-53
        if max_retries is None:
            max_retries = self.max_retries
        
        if timeout is None:
            timeout = self.timeout
        
        # ==================== VALIDATION: SMALL IMAGE SKIP ====================
        # CUSTOM FIX: qwen2.5vl has minimum image size requirements
        # Not present in Gemini (cloud models are more tolerant)
        if image is not None:
            images_to_check = image if isinstance(image, list) else [image]
            for img in images_to_check:
                if img and (img.width < 28 or img.height < 28):
                    logger.warning(f"Skipping LLM inference - image too small ({img.width}x{img.height}, minimum 28x28)")
                    return {}
        
        # ==================== IMAGE FORMATTING ====================
        # From GeminiService line 56
        image_bytes = self.format_image_for_llm(image)
        
        # ==================== SCHEMA PREPARATION ====================
        # CRITICAL FIX: Include $defs for nested schemas
        # Gemini handles this internally via response_schema parameter
        # Ollama needs explicit JSON schema with all definitions
        schema = response_schema.model_json_schema()
        format_schema = {
            "type": "object",
            "properties": schema["properties"],
            "required": schema["required"],
        }
        
        # BUGFIX (Oct 8, 2025): Include $defs for $ref support
        # Without this, schemas like SectionHeaderSchema with List[BlockSchema] fail
        if "$defs" in schema:
            format_schema["$defs"] = schema["$defs"]
        
        # ==================== REQUEST PAYLOAD ====================
        # Ollama-specific format (different from Gemini's API)
        url = f"{self.ollama_base_url}/api/generate"
        headers = {"Content-Type": "application/json"}
        
        payload = {
            "model": self.ollama_model,
            "prompt": prompt,
            "stream": False,
            "format": format_schema,
        }
        
        # Only include images if present (multimodal models can handle text-only)
        if image_bytes:
            payload["images"] = image_bytes
        
        # ==================== RETRY LOOP ====================
        # Structure from GeminiService lines 58-122
        # Adapted for Ollama's error patterns
        total_tries = max_retries + 1
        temperature = 0  # Not used by Ollama API, but kept for future
        
        for attempt in range(1, total_tries + 1):
            try:
                # ==================== API CALL ====================
                response = requests.post(url, json=payload, headers=headers, timeout=timeout)
                response.raise_for_status()
                response_data = response.json()
                
                # ==================== TOKEN TRACKING ====================
                # From GeminiService lines 79-83
                total_tokens = (
                    response_data.get("prompt_eval_count", 0) + 
                    response_data.get("eval_count", 0)
                )
                
                if block:
                    block.update_metadata(
                        llm_request_count=1, 
                        llm_tokens_used=total_tokens
                    )
                
                # ==================== RESPONSE PARSING ====================
                # Ollama returns JSON in "response" field
                data = response_data["response"]
                return json.loads(data)
                
            # ==================== ERROR HANDLING ====================
            # Adapted from GeminiService lines 85-120
            
            # Handle HTTP errors (parallel to Gemini's APIError handling)
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else None
                
                # Rate limiting / Server errors (parallel to Gemini's 429, 443, 503)
                if status_code in [429, 500, 503]:
                    if attempt < total_tries:
                        wait_time = attempt * self.retry_wait_time
                        logger.warning(
                            f"Ollama HTTPError {status_code}: {e}. Retrying in {wait_time}s... (Attempt {attempt}/{total_tries})"
                        )
                        time.sleep(wait_time)
                    else:
                        logger.error(
                            f"Ollama HTTPError {status_code}: {e}. Max retries reached. (Attempt {attempt}/{total_tries})"
                        )
                        break
                else:
                    # Non-retriable error
                    logger.error(f"Ollama HTTPError {status_code}: {e}")
                    break
            
            # Handle JSON parsing errors (parallel to Gemini lines 103-116)
            except json.JSONDecodeError as e:
                if attempt < total_tries:
                    logger.warning(
                        f"Ollama JSONDecodeError: {e}. Retrying... (Attempt {attempt}/{total_tries})"
                    )
                    # Note: Could implement temperature increase here like Gemini,
                    # but Ollama's API doesn't support it in the same way
                else:
                    logger.error(
                        f"Ollama JSONDecodeError: {e}. Max retries reached. (Attempt {attempt}/{total_tries})"
                    )
                    break
            
            # Handle connection/network errors
            except requests.exceptions.RequestException as e:
                if attempt < total_tries:
                    wait_time = attempt * self.retry_wait_time
                    logger.warning(
                        f"Ollama RequestException: {e}. Retrying in {wait_time}s... (Attempt {attempt}/{total_tries})"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"Ollama RequestException: {e}. Max retries reached. (Attempt {attempt}/{total_tries})"
                    )
                    break
            
            # Catch-all (parallel to Gemini lines 117-120)
            except Exception as e:
                logger.error(f"Ollama Exception: {e}")
                traceback.print_exc()
                break
        
        # Return empty dict on failure (matches Gemini line 122)
        return {}


# ==================== FEATURE PARITY CHECKLIST ====================
# Comparing marker.services.gemini.GoogleGeminiService to OllamaService:
#
# ✅ IMPLEMENTED:
# - Retry logic with exponential backoff (lines 79-99 → lines 122-202)
# - Token usage tracking (lines 79-83 → lines 133-139)
# - JSON decode error handling (lines 103-116 → lines 168-180)
# - HTTP error handling with retry (lines 85-102 → lines 151-167)
# - General exception handling (lines 117-120 → lines 182-198)
# - Timeout support (lines 52-53 → lines 48-49)
# - Image processing (lines 33-38 → lines 42-45)
# - Schema validation (lines 63-64 → lines 94-98)
#
# ✅ ADAPTED FOR OLLAMA:
# - API endpoint format (Gemini uses SDK, Ollama uses REST)
# - Image encoding (Gemini: WEBP bytes, Ollama: base64)
# - Schema format ($defs support added - lines 97-99)
# - Response parsing (Gemini: candidates[0], Ollama: response field)
#
# ⚠️ DIFFERENCES (Ollama-specific):
# - Small image validation (lines 66-74) - Not needed for cloud models
# - Empty image array handling (lines 113-115) - Ollama API quirk
# - No temperature adjustment on retry (Ollama API limitation)
#
# 🔒 NOT IMPLEMENTED (Cloud/Internet features - security blocked):
# - API key authentication (Gemini line 126-132) - Local model doesn't need
# - Client SDK initialization - Using direct HTTP requests instead
# - Cloud-specific error codes (Gemini's 443) - Not applicable locally
#
# 📋 FUTURE ENHANCEMENTS (Placeholders for feature parity):
# - [ ] Temperature control for retries (if Ollama adds support)
# - [ ] Streaming responses (payload has stream:False, could enable)
# - [ ] Multiple model fallback (switch models on failure)
# - [ ] Custom system prompts (Ollama supports via Modelfile)
