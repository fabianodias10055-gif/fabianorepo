"""Cliente HTTP da API pública do ClickUp.

Existe para trocar o MCP oficial (teto de 50 chamadas/24h no plano Free, 300 no
Unlimited+) pela API pública, cujo teto e 100 requisicoes/minuto e reseta em
segundos em vez de quase um dia.

Toda chamada passa pelo mesmo rate limiter de processo, entao nao importa quantas
ferramentas o servidor MCP exponha: o conjunto nunca ultrapassa o teto por minuto.
"""

import json
import logging
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
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

# Conexao persistente: reaproveita o TCP/TLS entre chamadas (keep-alive) em vez
# de pagar um handshake novo por requisicao.
_session = requests.Session()

# Cache opcional de leituras estaveis (hierarquia, membros, workspaces).
# TTL curto e qualquer escrita esvazia tudo - simples e suficiente para um
# processo local de usuario unico.
CACHE_TTL = float(os.getenv("CLICKUP_CACHE_TTL", "300"))
_cache: dict[str, tuple[float, object]] = {}
_cache_lock = threading.Lock()

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
        # O cofre do painel (Windows Credential Manager, servico
        # "locodev-panel") e para onde secrets_store.py --migrate levou os
        # tokens quando o .env foi esvaziado. Procurar so no local antigo
        # deixou a reconciliacao horaria falhando com "token nao definido"
        # mesmo com o token guardado.
        try:
            from secrets_store import get_secret

            token = get_secret("CLICKUP_API_TOKEN").strip()
        except ImportError:
            pass
    if not token:
        # Local antigo (python -m keyring set clickup-mcp api_token), para
        # quem guardou por ele e nunca migrou.
        try:
            import keyring

            token = (keyring.get_password("clickup-mcp", "api_token") or "").strip()
        except ImportError:
            pass
    if not token:
        raise ClickUpError(
            "CLICKUP_API_TOKEN nao definido. Guarde no cofre com: "
            "python secrets_store.py --set CLICKUP_API_TOKEN  (ou copie "
            ".env.example para .env e cole seu token pessoal de "
            "ClickUp > Settings > Apps > API Token)"
        )
    return token


def limpar_cache() -> None:
    with _cache_lock:
        _cache.clear()


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
            resp = _session.request(method, url, headers=headers, timeout=30, **kwargs)
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

        # 401/403 sao categorias proprias: token ruim nao e a mesma coisa que
        # token bom sem permissao, e nenhum dos dois melhora com retry.
        if resp.status_code == 401:
            raise ClickUpError(
                f"401 (token invalido, revogado ou ausente): {resp.text[:300]}"
            )
        if resp.status_code == 403:
            raise ClickUpError(
                f"403 (token valido, mas sem permissao neste recurso): "
                f"{resp.text[:300]}"
            )

        if resp.status_code >= 400:
            # 4xx que nao seja 429 e erro do nosso lado: repetir nao ajuda.
            raise ClickUpError(f"{resp.status_code}: {resp.text[:500]}")

        # Qualquer escrita bem-sucedida pode ter mudado o que os GETs cacheados
        # viram: esvazia tudo em vez de tentar invalidacao fina.
        if method.upper() != "GET":
            limpar_cache()

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


def get_cacheado(path: str, params: dict | None = None, ttl: float | None = None):
    """GET com cache por TTL. So para leituras que mudam raramente
    (hierarquia, membros); tarefas mudam o tempo todo e nao devem passar aqui.
    """
    chave = path + "|" + json.dumps(params or {}, sort_keys=True)
    agora = time.monotonic()
    with _cache_lock:
        hit = _cache.get(chave)
        if hit and agora - hit[0] < (CACHE_TTL if ttl is None else ttl):
            return hit[1]
    dado = get(path, params=params)
    with _cache_lock:
        _cache[chave] = (time.monotonic(), dado)
    return dado


def get_paginado(path: str, params: dict | None = None, chave: str = "tasks") -> list:
    """Percorre todas as paginas de um endpoint paginado por `page`."""
    itens: list = []
    pagina = 0
    while True:
        p = dict(params or {})
        p["page"] = pagina
        resp = get(path, params=p)
        lote = resp.get(chave, [])
        itens.extend(lote)
        if resp.get("last_page") or not lote:
            break
        pagina += 1
    return itens


def em_paralelo(fn, itens, max_workers: int = 8) -> list:
    """Aplica `fn` a cada item em threads, preservando a ordem.

    O rate limiter e compartilhado e thread-safe, entao o teto por minuto
    continua valendo para o conjunto; o ganho e sobrepor a latencia de rede.
    Excecoes propagam para o chamador.
    """
    if not itens:
        return []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        return list(ex.map(fn, itens))


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
