"""Controles de seguridad de capa de aplicación.

- Autenticación por API key (la key vive en SSM Parameter Store en AWS, nunca en el código).
- Detección heurística de prompt injection (primera capa; en producción se complementa
  con Amazon Bedrock Guardrails, ver docs/RIESGOS_Y_PRODUCCION.md).
- Enmascarado de PII antes de escribir logs.
"""
from __future__ import annotations

import hmac
import re
import unicodedata
from functools import lru_cache

# --------------------------------------------------------------------------------------
# Prompt injection
# --------------------------------------------------------------------------------------
# Patrones en español e inglés de los intentos más comunes: anular instrucciones,
# cambiar de rol, exfiltrar el prompt del sistema o secretos.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    ("override_instructions", r"\b(ignora|olvida|omite|descarta|ignore|forget|disregard)\w*.{0,40}\b(instrucciones|reglas|indicaciones|instructions|rules|prompt)\b"),
    ("override_instructions", r"\b(ignora|olvida|ignore|forget)\b.{0,20}\b(todo|lo anterior|everything|previous|above)\b"),
    ("role_change", r"\b(ahora eres|act[uú]a como|finge ser|you are now|act as|pretend to be)\b"),
    ("system_prompt_leak", r"\b(prompt|instrucciones|mensaje)\s+(del\s+)?(sistema|system|inicial)\b"),
    ("system_prompt_leak", r"\b(system prompt|revela tus instrucciones|reveal your instructions|show your prompt)\b"),
    ("secret_exfiltration", r"\b(api[\s_-]?key|contrase[nñ]a|password|secret|token|credenciales|credentials)\b.{0,40}\b(mu[eé]stra|revela|dame|imprime|show|reveal|print|give)\w*"),
    ("secret_exfiltration", r"\b(mu[eé]stra|revela|dame|imprime|show|reveal|print|give)\w*.{0,40}\b(api[\s_-]?key|contrase[nñ]a|password|secret|token|credenciales|credentials|variables de entorno|environment variables)\b"),
    ("jailbreak", r"\b(modo desarrollador|developer mode|jailbreak|DAN|sin restricciones|without restrictions)\b"),
    ("delimiter_spoofing", r"</?\s*(system|documents|documento|instructions)\s*>"),
]
_COMPILED = [(name, re.compile(p, re.IGNORECASE | re.DOTALL)) for name, p in _INJECTION_PATTERNS]


def _normalize(text: str) -> str:
    # Quita acentos y caracteres de control/invisibles que se usan para evadir filtros.
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C" or ch in "\n\t")
    return text


def detect_prompt_injection(text: str) -> list[str]:
    """Devuelve la lista de categorías de injection detectadas (vacía si no hay)."""
    normalized = _normalize(text)
    stripped = "".join(
        c for c in unicodedata.normalize("NFD", normalized) if unicodedata.category(c) != "Mn"
    )
    hits = []
    for name, pattern in _COMPILED:
        if (pattern.search(normalized) or pattern.search(stripped)) and name not in hits:
            hits.append(name)
    return hits


def sanitize_for_prompt(text: str) -> str:
    """Neutraliza etiquetas que imitan los delimitadores del prompt (p. ej. </documents>)."""
    return re.sub(r"<\s*(/?)\s*(system|documents|documento|instructions)\s*>", r"[\1\2]", text, flags=re.IGNORECASE)


# --------------------------------------------------------------------------------------
# PII masking para logs
# --------------------------------------------------------------------------------------
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)(\+?\d[\d\s-]{8,}\d)(?!\w)")
_CARD = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


def mask_pii(text: str) -> str:
    if not text:
        return text
    text = _EMAIL.sub("[EMAIL]", text)
    text = _CARD.sub("[NUM]", text)
    text = _PHONE.sub("[TEL]", text)
    return text


# --------------------------------------------------------------------------------------
# API key
# --------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _load_api_key_from_ssm(param_name: str, region: str) -> str:
    import boto3

    ssm = boto3.client("ssm", region_name=region)
    return ssm.get_parameter(Name=param_name, WithDecryption=True)["Parameter"]["Value"]


def get_expected_api_key(settings) -> str:
    if settings.api_key_ssm_param:
        return _load_api_key_from_ssm(settings.api_key_ssm_param, settings.aws_region)
    return settings.api_key


def api_key_is_valid(provided: str | None, expected: str) -> bool:
    if not expected:
        # Sin key configurada solo se permite en entorno local (ver main.py).
        return True
    if not provided:
        return False
    return hmac.compare_digest(provided.encode(), expected.encode())
