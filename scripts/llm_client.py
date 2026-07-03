"""SiliconFlow LLM client for package description translation."""
import os

import requests

SILICONFLOW_BASE_URL = 'https://api.siliconflow.cn/v1'
SILICONFLOW_MODEL = 'deepseek-ai/DeepSeek-V4-Flash'
DEFAULT_TIMEOUT_SECONDS = 180


def call_llm(prompt, system_prompt, timeout=DEFAULT_TIMEOUT_SECONDS):
    """Call SiliconFlow's OpenAI-compatible chat completions API."""
    headers = {
        'Authorization': f"Bearer {get_siliconflow_api_key()}",
        'Content-Type': 'application/json',
    }
    try:
        response = requests.post(
            f"{SILICONFLOW_BASE_URL}/chat/completions",
            headers=headers,
            json=build_llm_payload(prompt, system_prompt),
            timeout=timeout,
        )
    except requests.Timeout:
        return None, "LLM call timed out"
    except requests.RequestException as exc:
        return None, f"LLM request failed: {exc}"
    if response.status_code >= 400:
        return None, format_http_error(response)
    try:
        envelope = response.json()
    except ValueError as exc:
        return None, f"LLM returned non-JSON response: {exc}"
    return extract_llm_content(envelope)


def get_siliconflow_api_key():
    value = os.environ.get('SILICONFLOW_API_KEY', '').strip()
    if not value:
        raise RuntimeError("SILICONFLOW_API_KEY is required")
    return value


def build_llm_payload(prompt, system_prompt):
    return {
        'model': SILICONFLOW_MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.2,
        'enable_thinking': False,
    }


def extract_llm_content(envelope):
    if not isinstance(envelope, dict):
        return None, "LLM response is not an object"
    choices = envelope.get('choices')
    if not choices:
        return None, "LLM response missing choices"
    content = choices[0].get('message', {}).get('content', '')
    if not content:
        return None, "LLM response missing message content"
    return content, None


def format_http_error(response):
    if is_cloudflare_challenge(response):
        return (
            "FATAL: LLM endpoint returned a Cloudflare challenge page. "
            "Use an API endpoint that accepts non-browser POST requests, or "
            "disable Cloudflare challenge/WAF rules for /v1/chat/completions."
        )
    return f"LLM HTTP {response.status_code}: {response.text[:300]}"


def is_cloudflare_challenge(response):
    content_type = response.headers.get('content-type', '').lower()
    text = response.text[:1000].lower()
    return (
        response.status_code == 403
        and 'text/html' in content_type
        and 'just a moment' in text
    )
