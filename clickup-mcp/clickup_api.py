"""Cliente HTTP da API pública do ClickUp.

Existe para trocar o MCP oficial (teto de 50 chamadas/24h no plano Free, 300 no
Unlimited+) pela API pública, cujo teto e 100 requisicoes/minuto e reseta em
segundos em vez de quase um dia.

Toda chamada passa pelo mesmo rate limiter de processo, entao nao importa quantas
ferramentas o servidor MCP exponha: o conjunto nunca ultrapassa o teto por minuto.
"""

import logging
import os
import threading
import time
from collections import deque
from pathlib import Path

import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

API_BASE = "https://api.clickup.com/api/v2"

# O teto real da API e 100/min nos planos Free, Unlimited e Business. Ficamos
# abaixo de proposito: o contador do ClickUp e por token, e voce pode estar
# usando o mesmo token em outro lugar (Zapier, Make, outro script).
MAX_REQUESTS_PER_MINUTE = int(os.getenv("CLICKUP_MAX_RPM", "80"))

# Um 429 mesmo assim significa que alguem gastou a cota do token por fora.
# Backoff em vez de desistir, porque a janela do ClickUp reseta em segundos.
MAX_RETRIES = 4

log = logging.getLogger("clickup")


class ClickUpError(RuntimeError):
    """Erro vindo da API do ClickUp, com o corpo da resposta preservado."""


class _RateLimiter:
    """Janela deslizante de 60s. Bloqueia a thread ate haver folga.

    Simples de proposito: o gargalo aqui e a rede, nao a CPU, e uma fila
    assincrona so acrescentaria complexidade sem ganho pratico.
    """

    def __init__(self, max_per_minute: int):
        self.max_per_minute = max_per_minute
        self._calls: deque[float] = deque()
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                agora = time.monotonic()
                while self._calls and agora - self._calls[0] >= 60:
                    self._calls.popleft()
                if len(self._calls) < self.max_per_minute:
                    self._calls.append(agora)
                    return
                espera = 60 - (agora - self._calls[0]) + 0.05
            log.debug("rate limit local atingido, aguardando %.1fs", espera)
            time.sleep(espera)


_limiter = _RateLimiter(MAX_REQUESTS_PER_MINUTE)


def _token() -> str:
    token = os.getenv("CLICKUP_API_TOKEN", "").strip()
    if not token:
        raise ClickUpError(
            "CLICKUP_API_TOKEN nao definido. Copie .env.example para .env e "
            "cole seu token pessoal (ClickUp > Settings > Apps > API Token)."
        )
    return token


def request(method: str, path: str, **kwargs):
    """Faz uma chamada a API, respeitando o limite e repetindo em 429/5xx.

    `path` e relativo a /api/v2 (ex.: "/list/123/task").
    """
    url = f"{API_BASE}{path}"
    # O token pessoal vai cru no header Authorization - a API do ClickUp nao
    # usa o esquema "Bearer" para tokens pk_*.
    headers = {"Authorization": _token(), **kwargs.pop("headers", {})}

    ultimo_erro = None
    for tentativa in range(MAX_RETRIES):
        _limiter.acquire()
        try:
            resp = requests.request(method, url, headers=headers, timeout=30, **kwargs)
        except requests.RequestException as exc:
            ultimo_erro = exc
            espera = 2 ** tentativa
            log.warning("falha de rede (%s), retry em %ss", exc, espera)
            time.sleep(espera)
            continue

        if resp.status_code == 429:
            # A API manda o timestamp exato do reset; usar isso evita tanto
            # dormir demais quanto voltar cedo e levar outro 429.
            reset = resp.headers.get("X-RateLimit-Reset")
            espera = 2 ** tentativa
            if reset:
                try:
                    espera = max(1, int(float(reset) - time.time()) + 1)
                except ValueError:
                    pass
            log.warning("429 do ClickUp, aguardando %ss", espera)
            time.sleep(espera)
            ultimo_erro = ClickUpError(f"429: {resp.text[:200]}")
            continue

        if resp.status_code >= 500:
            espera = 2 ** tentativa
            log.warning("%s do ClickUp, retry em %ss", resp.status_code, espera)
            time.sleep(espera)
            ultimo_erro = ClickUpError(f"{resp.status_code}: {resp.text[:200]}")
            continue

        if resp.status_code >= 400:
            # 4xx que nao seja 429 e erro do nosso lado: repetir nao ajuda.
            raise ClickUpError(f"{resp.status_code}: {resp.text[:500]}")

        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}

    raise ClickUpError(f"esgotadas {MAX_RETRIES} tentativas: {ultimo_erro}")


def get(path: str, **kwargs):
    return request("GET", path, **kwargs)


def post(path: str, **kwargs):
    return request("POST", path, **kwargs)


def put(path: str, **kwargs):
    return request("PUT", path, **kwargs)


def delete(path: str, **kwargs):
    return request("DELETE", path, **kwargs)


def upload_attachment(task_id: str, caminho: Path, nome: str | None = None) -> dict:
    """Sobe um arquivo local como anexo da tarefa.

    Endpoint separado porque e multipart, nao JSON: o arquivo vai no campo
    `attachment` e o nome desejado no campo `filename`.
    """
    caminho = Path(caminho)
    if not caminho.is_file():
        raise ClickUpError(f"arquivo nao encontrado: {caminho}")

    nome = nome or caminho.name
    with caminho.open("rb") as fh:
        return post(
            f"/task/{task_id}/attachment",
            data={"filename": nome},
            files={"attachment": (nome, fh)},
        )
