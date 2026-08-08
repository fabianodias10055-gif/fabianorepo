"""Servidor MCP para o ClickUp, falando direto com a API publica.

Substitui o MCP oficial (mcp.clickup.com), cujo teto e 50 chamadas/24h no plano
Free e 300 no Unlimited+. Aqui o teto e o da API publica: 100 requisicoes/minuto,
com reset em segundos.

Rodar:  python server.py          (stdio, para clientes MCP locais)

Interruptores por variavel de ambiente (ver .env.example):
    CLICKUP_DRY_RUN=true      toda tool de escrita apenas simula e descreve
    CLICKUP_ALLOW_DELETE=true habilita apagar_tarefa (irreversivel)
    CLICKUP_MAX_DOWNLOAD_MB   teto do download em anexar_url (padrao 50)
"""

import csv
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import requests
from mcp.server.fastmcp import FastMCP

import clickup_api as api


BASE_DIR = Path(__file__).resolve().parent
AUDIT_LOG = BASE_DIR / "alteracoes.jsonl"
EXPORT_DIR = BASE_DIR / "exports"

# Apagar tarefa e irreversivel e a API nao tem lixeira. Fica atras de um
# interruptor explicito para que um pedido ambiguo do usuario nunca vire
# uma exclusao silenciosa.
PERMITIR_APAGAR = os.getenv("CLICKUP_ALLOW_DELETE", "").lower() in {"1", "true", "sim"}

# Modo simulacao global: toda tool de escrita descreve o que faria e nao faz.
# Util para deixar o cliente MCP planejar mudancas grandes antes de liberar.
SIMULAR = os.getenv("CLICKUP_DRY_RUN", "").lower() in {"1", "true", "sim"}

MAX_DOWNLOAD_BYTES = int(os.getenv("CLICKUP_MAX_DOWNLOAD_MB", "50")) * 1024 * 1024

_NIVEIS_PRIORIDADE = {"urgent": 1, "high": 2, "normal": 3, "low": 4}

_TAGS_TITULO_RE = re.compile(r"\[([A-ZÀ-Ú0-9]+)\]")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("clickup-mcp")

mcp = FastMCP("clickup")


# Sync automatico do vault apos escritas. Debounce evita empilhar processos
# numa rajada de tools; o atraso no filho agrupa a rajada num refresh so.
AUTO_SYNC = os.getenv("CLICKUP_AUTO_SYNC", "true").lower() not in {"0", "false", "nao"}
_SYNC_DEBOUNCE_S = 60
_ultimo_sync = 0.0


def _agendar_sync_vault() -> None:
    """Dispara, em segundo plano, um refresh dos espelhos do vault.

    Chamado apos toda mutacao auditada: mudanca feita pelo chat aparece no
    Obsidian em ~15s, sem depender da tarefa agendada de hora em hora.
    """
    global _ultimo_sync
    agora = time.monotonic()
    if not AUTO_SYNC or agora - _ultimo_sync < _SYNC_DEBOUNCE_S:
        return
    _ultimo_sync = agora
    try:
        with (BASE_DIR / "reconciliar.log").open("a", encoding="utf-8") as log_fh:
            subprocess.Popen(
                [sys.executable, str(BASE_DIR / "reconciliar_vault.py"),
                 "--so-puxar", "--atraso", "15"],
                cwd=BASE_DIR, stdout=log_fh, stderr=log_fh,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    except OSError as exc:
        log.warning("nao consegui agendar o sync do vault: %s", exc)


def _auditar(acao: str, **detalhes) -> None:
    """Registra toda mutacao em JSONL, para voce conseguir revisar depois o que
    a IA mexeu sem ter que garimpar o historico de atividade do ClickUp."""
    linha = {
        "quando": datetime.now(timezone.utc).isoformat(),
        "acao": acao,
        **detalhes,
    }
    with AUDIT_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linha, ensure_ascii=False) + "\n")
    if acao != "reconciliar_vault":
        _agendar_sync_vault()


def _simulado(acao: str, **detalhes) -> str:
    return json.dumps(
        {"simulado": True, "acao": acao, **detalhes}, ensure_ascii=False
    )


def _resumir_tarefa(t: dict) -> dict:
    """Devolve so os campos que importam. A resposta crua do ClickUp traz
    dezenas de campos e enche o contexto da IA sem necessidade."""
    return {
        "id": t.get("id"),
        "nome": t.get("name"),
        "status": (t.get("status") or {}).get("status"),
        "prioridade": (t.get("priority") or {}).get("priority"),
        "responsaveis": [a.get("username") for a in t.get("assignees") or []],
        "lista": (t.get("list") or {}).get("name"),
        "due_date": t.get("due_date"),
        "url": t.get("url"),
    }


def _snapshot(t: dict) -> dict:
    """Campos suficientes para recriar a tarefa se algo der errado.

    Vai para o audit log antes de toda edicao/exclusao: como a API nao tem
    lixeira, isto e a nossa lixeira caseira (ver restaurar_tarefa).
    """
    return {
        "task_id": t.get("id"),
        "list_id": (t.get("list") or {}).get("id"),
        "nome": t.get("name"),
        "descricao": t.get("description") or "",
        "status": (t.get("status") or {}).get("status"),
        "prioridade": (t.get("priority") or {}).get("priority"),
        "responsaveis": [a.get("id") for a in t.get("assignees") or []],
        "tags": [tg.get("name") for tg in t.get("tags") or []],
        "due_date": t.get("due_date"),
        "start_date": t.get("start_date"),
        "parent": t.get("parent"),
    }


def _para_ms(data: str) -> int:
    """'2026-08-10' ou '2026-08-10 14:30' -> epoch em milissegundos."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(data, fmt).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"data invalida: {data!r} (use AAAA-MM-DD ou AAAA-MM-DD HH:MM)")


def _rotulo_lista(t: dict) -> str:
    pasta = (t.get("folder") or {}).get("name") or ""
    lista = (t.get("list") or {}).get("name") or "?"
    if pasta and pasta.lower() != "hidden":
        return f"{pasta} / {lista}"
    return lista


def _montar_corpo(dados: dict) -> tuple[dict, str | None]:
    """Monta o corpo de criacao de tarefa a partir de campos opcionais.

    Devolve (corpo, erro). Compartilhado por criar_tarefa,
    criar_tarefas_em_lote e duplicar_tarefa para os campos nao divergirem.
    """
    corpo: dict = {}
    if dados.get("nome"):
        corpo["name"] = dados["nome"]
    if dados.get("descricao"):
        corpo["markdown_description"] = dados["descricao"]
    if dados.get("status"):
        corpo["status"] = dados["status"]
    prioridade = dados.get("prioridade") or ""
    if prioridade:
        if prioridade not in _NIVEIS_PRIORIDADE:
            return {}, f"prioridade invalida: {prioridade}"
        corpo["priority"] = _NIVEIS_PRIORIDADE[prioridade]
    try:
        for campo in ("due_date", "start_date"):
            if dados.get(campo):
                corpo[campo] = _para_ms(dados[campo])
    except ValueError as exc:
        return {}, str(exc)
    if dados.get("parent"):
        corpo["parent"] = dados["parent"]
    if dados.get("tags"):
        corpo["tags"] = dados["tags"]
    if dados.get("responsaveis"):
        corpo["assignees"] = dados["responsaveis"]
    return corpo, None


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------

@mcp.tool()
def listar_workspaces() -> str:
    """Lista os workspaces (times) da conta. Use para descobrir o workspace_id."""
    times = api.get_cacheado("/team").get("teams", [])
    return json.dumps(
        [{"id": t["id"], "nome": t["name"]} for t in times], ensure_ascii=False
    )


@mcp.tool()
def listar_hierarquia(workspace_id: str) -> str:
    """Mostra spaces, folders e listas do workspace, com os respectivos IDs.

    Use uma vez no inicio para saber onde as coisas ficam; depois trabalhe com
    os IDs direto, que custa menos chamadas. A resposta fica em cache por
    alguns minutos (a estrutura quase nao muda).
    """
    arvore = []
    for space in api.get_cacheado(f"/team/{workspace_id}/space").get("spaces", []):
        no = {"space_id": space["id"], "space": space["name"], "folders": [], "listas": []}

        for folder in api.get_cacheado(f"/space/{space['id']}/folder").get("folders", []):
            no["folders"].append({
                "folder_id": folder["id"],
                "folder": folder["name"],
                "listas": [
                    {"list_id": l["id"], "lista": l["name"]}
                    for l in folder.get("lists", [])
                ],
            })

        # Listas soltas no space, fora de qualquer folder.
        for l in api.get_cacheado(f"/space/{space['id']}/list").get("lists", []):
            no["listas"].append({"list_id": l["id"], "lista": l["name"]})

        arvore.append(no)
    return json.dumps(arvore, ensure_ascii=False, indent=2)


@mcp.tool()
def buscar_tarefas(list_id: str, incluir_concluidas: bool = True) -> str:
    """Lista as tarefas de uma lista.

    A API pagina de 100 em 100; esta funcao percorre todas as paginas sozinha.
    """
    tarefas = api.get_paginado(
        f"/list/{list_id}/task",
        params={
            "include_closed": str(incluir_concluidas).lower(),
            "subtasks": "true",
        },
    )
    return json.dumps(
        {"total": len(tarefas), "tarefas": [_resumir_tarefa(t) for t in tarefas]},
        ensure_ascii=False,
    )


@mcp.tool()
def buscar_por_nome(workspace_id: str, texto: str, max_resultados: int = 30) -> str:
    """Procura tarefas pelo nome no workspace inteiro (case-insensitive).

    Nao precisa saber em qual lista a tarefa esta.
    """
    texto_l = texto.lower()
    tarefas = api.get_paginado(
        f"/team/{workspace_id}/task",
        params={"include_closed": "true", "subtasks": "true"},
    )
    achadas = [
        _resumir_tarefa(t)
        for t in tarefas
        if texto_l in (t.get("name") or "").lower()
    ]
    return json.dumps(
        {"total": len(achadas), "tarefas": achadas[:max_resultados]},
        ensure_ascii=False,
    )


@mcp.tool()
def obter_tarefa(task_id: str) -> str:
    """Detalhes completos de uma tarefa, incluindo descricao e anexos."""
    t = api.get(f"/task/{task_id}")
    detalhe = _resumir_tarefa(t)
    detalhe["descricao"] = t.get("description")
    detalhe["tags"] = [tg.get("name") for tg in t.get("tags") or []]
    detalhe["anexos"] = [
        {"id": a.get("id"), "nome": a.get("title"), "url": a.get("url")}
        for a in t.get("attachments") or []
    ]
    return json.dumps(detalhe, ensure_ascii=False)


@mcp.tool()
def listar_membros(workspace_id: str) -> str:
    """Lista os membros do workspace com seus IDs, para atribuir responsaveis."""
    for time_ in api.get_cacheado("/team").get("teams", []):
        if time_["id"] == str(workspace_id):
            return json.dumps(
                [
                    {
                        "id": m["user"]["id"],
                        "nome": m["user"].get("username"),
                        "email": m["user"].get("email"),
                    }
                    for m in time_.get("members", [])
                ],
                ensure_ascii=False,
            )
    return json.dumps({"erro": f"workspace {workspace_id} nao encontrado"})


@mcp.tool()
def ler_comentarios(task_id: str) -> str:
    """Le os comentarios de uma tarefa, do mais novo para o mais velho."""
    coments = api.get(f"/task/{task_id}/comment").get("comments", [])
    return json.dumps(
        [
            {
                "usuario": (c.get("user") or {}).get("username"),
                "texto": c.get("comment_text"),
                "data": c.get("date"),
            }
            for c in coments
        ],
        ensure_ascii=False,
    )


@mcp.tool()
def listar_campos(list_id: str) -> str:
    """Lista os campos personalizados de uma lista, com IDs e tipos.

    Use o field_id em definir_campo.
    """
    campos = api.get(f"/list/{list_id}/field").get("fields", [])
    return json.dumps(
        [
            {"id": c.get("id"), "nome": c.get("name"), "tipo": c.get("type")}
            for c in campos
        ],
        ensure_ascii=False,
    )


@mcp.tool()
def relatorio_board(workspace_id: str, dias_parada: int = 14) -> str:
    """Resumo agregado do workspace numa unica resposta compacta.

    Contagens por status, lista, dono e categoria (tags [ASSIM] no titulo),
    mais as tarefas abertas paradas ha mais de `dias_parada` dias.
    """
    tarefas = api.get_paginado(
        f"/team/{workspace_id}/task",
        params={"include_closed": "true", "subtasks": "true"},
    )
    agora_ms = time.time() * 1000
    por_status: Counter = Counter()
    por_lista: Counter = Counter()
    por_dono: Counter = Counter()
    por_categoria: Counter = Counter()
    paradas = []
    for t in tarefas:
        por_status[(t.get("status") or {}).get("status") or "?"] += 1
        por_lista[_rotulo_lista(t)] += 1
        tags = _TAGS_TITULO_RE.findall((t.get("name") or "").upper())
        por_dono[tags[0] if tags else "SEM DONO"] += 1
        por_categoria[tags[1] if len(tags) > 1 else "SEM CATEGORIA"] += 1

        atualizado = int(t.get("date_updated") or 0)
        aberta = (t.get("status") or {}).get("type") != "closed"
        if aberta and atualizado and agora_ms - atualizado > dias_parada * 86_400_000:
            paradas.append({
                "id": t.get("id"),
                "nome": (t.get("name") or "")[:60],
                "dias_parada": int((agora_ms - atualizado) // 86_400_000),
            })
    paradas.sort(key=lambda p: -p["dias_parada"])
    return json.dumps(
        {
            "total": len(tarefas),
            "por_status": dict(por_status),
            "por_lista": dict(por_lista),
            "por_dono": dict(por_dono),
            "por_categoria": dict(por_categoria),
            "paradas": paradas[:30],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def listar_webhooks(workspace_id: str) -> str:
    """Lista os webhooks registrados no workspace."""
    hooks = api.get(f"/team/{workspace_id}/webhook").get("webhooks", [])
    return json.dumps(
        [
            {
                "id": h.get("id"),
                "endpoint": h.get("endpoint"),
                "eventos": h.get("events"),
                "saude": (h.get("health") or {}).get("status"),
            }
            for h in hooks
        ],
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------
# Escrita
# --------------------------------------------------------------------------

@mcp.tool()
def criar_tarefa(
    list_id: str,
    nome: str,
    descricao: str = "",
    prioridade: str = "",
    status: str = "",
    due_date: str = "",
    start_date: str = "",
    parent: str = "",
    tags: list[str] | None = None,
    responsaveis: list[int] | None = None,
) -> str:
    """Cria uma tarefa (ou subtarefa, se `parent` for o id da tarefa-mae).

    `prioridade`: urgent, high, normal ou low. Datas em AAAA-MM-DD (ou com
    hora: "AAAA-MM-DD HH:MM"). `tags` sao as tags nativas do ClickUp.
    """
    corpo, erro = _montar_corpo({
        "nome": nome, "descricao": descricao, "prioridade": prioridade,
        "status": status, "due_date": due_date, "start_date": start_date,
        "parent": parent, "tags": tags, "responsaveis": responsaveis,
    })
    if erro:
        return json.dumps({"erro": erro}, ensure_ascii=False)

    if SIMULAR:
        return _simulado("criar_tarefa", list_id=list_id, corpo=corpo)

    t = api.post(f"/list/{list_id}/task", json=corpo)
    _auditar("criar_tarefa", task_id=t.get("id"), nome=nome, list_id=list_id)
    return json.dumps(_resumir_tarefa(t), ensure_ascii=False)


@mcp.tool()
def editar_tarefa(
    task_id: str,
    nome: str = "",
    descricao: str = "",
    status: str = "",
    prioridade: str = "",
    due_date: str = "",
    start_date: str = "",
) -> str:
    """Edita uma tarefa. Campos vazios ficam como estao.

    Mudar `status` e como se move um card entre colunas do quadro.
    Datas em AAAA-MM-DD (ou "AAAA-MM-DD HH:MM").
    """
    corpo: dict = {}
    if nome:
        corpo["name"] = nome
    if descricao:
        corpo["markdown_description"] = descricao
    if status:
        corpo["status"] = status
    if prioridade:
        if prioridade not in _NIVEIS_PRIORIDADE:
            return json.dumps({"erro": f"prioridade invalida: {prioridade}"})
        corpo["priority"] = _NIVEIS_PRIORIDADE[prioridade]
    try:
        if due_date:
            corpo["due_date"] = _para_ms(due_date)
        if start_date:
            corpo["start_date"] = _para_ms(start_date)
    except ValueError as exc:
        return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    if not corpo:
        return json.dumps({"erro": "nenhum campo para alterar"})

    if SIMULAR:
        return _simulado("editar_tarefa", task_id=task_id, corpo=corpo)

    # Snapshot antes de tocar: e a lixeira caseira (ver restaurar_tarefa).
    antes = api.get(f"/task/{task_id}")
    t = api.put(f"/task/{task_id}", json=corpo)
    _auditar(
        "editar_tarefa",
        task_id=task_id,
        campos=list(corpo),
        snapshot=_snapshot(antes),
    )
    return json.dumps(_resumir_tarefa(t), ensure_ascii=False)


@mcp.tool()
def atribuir_responsaveis(task_id: str, user_ids: list[int]) -> str:
    """Define os responsaveis da tarefa. Pegue os IDs com `listar_membros`.

    Substitui a lista atual: quem nao estiver em `user_ids` sai da tarefa.
    """
    if SIMULAR:
        return _simulado("atribuir_responsaveis", task_id=task_id, user_ids=user_ids)

    atual = api.get(f"/task/{task_id}")
    remover = [a["id"] for a in atual.get("assignees") or [] if a["id"] not in user_ids]

    t = api.put(
        f"/task/{task_id}",
        json={"assignees": {"add": user_ids, "rem": remover}},
    )
    _auditar("atribuir_responsaveis", task_id=task_id, add=user_ids, rem=remover)
    return json.dumps(_resumir_tarefa(t), ensure_ascii=False)


@mcp.tool()
def comentar_tarefa(task_id: str, texto: str) -> str:
    """Adiciona um comentario a tarefa."""
    if SIMULAR:
        return _simulado("comentar_tarefa", task_id=task_id)

    r = api.post(f"/task/{task_id}/comment", json={"comment_text": texto})
    _auditar("comentar_tarefa", task_id=task_id)
    return json.dumps({"comment_id": r.get("id"), "ok": True}, ensure_ascii=False)


@mcp.tool()
def adicionar_tag(task_id: str, tag: str) -> str:
    """Adiciona uma tag nativa do ClickUp a tarefa (cria no space se nao existir)."""
    if SIMULAR:
        return _simulado("adicionar_tag", task_id=task_id, tag=tag)

    api.post(f"/task/{task_id}/tag/{quote(tag, safe='')}")
    _auditar("adicionar_tag", task_id=task_id, tag=tag)
    return json.dumps({"ok": True, "tag": tag}, ensure_ascii=False)


@mcp.tool()
def remover_tag(task_id: str, tag: str) -> str:
    """Remove uma tag nativa da tarefa."""
    if SIMULAR:
        return _simulado("remover_tag", task_id=task_id, tag=tag)

    api.delete(f"/task/{task_id}/tag/{quote(tag, safe='')}")
    _auditar("remover_tag", task_id=task_id, tag=tag)
    return json.dumps({"ok": True, "tag": tag}, ensure_ascii=False)


@mcp.tool()
def criar_checklist(task_id: str, titulo: str, itens: list[str] | None = None) -> str:
    """Cria uma checklist na tarefa, opcionalmente ja com itens.

    Custa 1 chamada para a checklist + 1 por item.
    """
    if SIMULAR:
        return _simulado(
            "criar_checklist", task_id=task_id, titulo=titulo, itens=itens or []
        )

    r = api.post(f"/task/{task_id}/checklist", json={"name": titulo})
    checklist_id = (r.get("checklist") or {}).get("id")
    if not checklist_id:
        return json.dumps({"erro": f"resposta sem id de checklist: {r}"}, ensure_ascii=False)
    for item in itens or []:
        api.post(f"/checklist/{checklist_id}/checklist_item", json={"name": item})
    _auditar(
        "criar_checklist", task_id=task_id, checklist_id=checklist_id,
        titulo=titulo, itens=len(itens or []),
    )
    return json.dumps(
        {"checklist_id": checklist_id, "itens_criados": len(itens or [])},
        ensure_ascii=False,
    )


@mcp.tool()
def definir_campo(task_id: str, field_id: str, valor: str) -> str:
    """Define um campo personalizado da tarefa. Pegue o field_id em listar_campos.

    `valor` aceita JSON (numeros, listas) ou texto puro.
    """
    try:
        v = json.loads(valor)
    except ValueError:
        v = valor

    if SIMULAR:
        return _simulado("definir_campo", task_id=task_id, field_id=field_id, valor=v)

    api.post(f"/task/{task_id}/field/{field_id}", json={"value": v})
    _auditar("definir_campo", task_id=task_id, field_id=field_id)
    return json.dumps({"ok": True}, ensure_ascii=False)


@mcp.tool()
def criar_dependencia(task_id: str, depende_de: str) -> str:
    """Marca que `task_id` depende de `depende_de` (esta bloqueia aquela)."""
    if SIMULAR:
        return _simulado("criar_dependencia", task_id=task_id, depende_de=depende_de)

    api.post(f"/task/{task_id}/dependency", json={"depends_on": depende_de})
    _auditar("criar_dependencia", task_id=task_id, depende_de=depende_de)
    return json.dumps({"ok": True}, ensure_ascii=False)


@mcp.tool()
def anexar_arquivo(task_id: str, caminho: str, nome: str = "") -> str:
    """Anexa um arquivo do disco local a tarefa.

    `caminho` e um caminho na maquina onde este servidor roda.
    """
    if SIMULAR:
        return _simulado("anexar_arquivo", task_id=task_id, caminho=caminho)

    r = api.upload_attachment(task_id, Path(caminho), nome or None)
    _auditar("anexar_arquivo", task_id=task_id, arquivo=nome or Path(caminho).name)
    return json.dumps(
        {"anexo_id": r.get("id"), "nome": r.get("title"), "url": r.get("url")},
        ensure_ascii=False,
    )


@mcp.tool()
def anexar_url(task_id: str, url: str, nome: str = "") -> str:
    """Baixa um arquivo de uma URL publica e anexa a tarefa.

    O download acontece nesta maquina, em streaming, com teto de
    CLICKUP_MAX_DOWNLOAD_MB (padrao 50 MB) para nao estourar memoria/disco.
    """
    nome = nome or Path(urlparse(url).path).name or "anexo"

    if SIMULAR:
        return _simulado("anexar_url", task_id=task_id, url=url, nome=nome)

    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()

    tmp = tempfile.NamedTemporaryFile(suffix=f"_{nome}", delete=False)
    tmp_path = Path(tmp.name)
    try:
        total = 0
        with tmp:
            for pedaco in resp.iter_content(chunk_size=65536):
                total += len(pedaco)
                if total > MAX_DOWNLOAD_BYTES:
                    return json.dumps({
                        "erro": (
                            f"download passou do teto de "
                            f"{MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB; nada anexado"
                        )
                    }, ensure_ascii=False)
                tmp.write(pedaco)
        r = api.upload_attachment(task_id, tmp_path, nome)
    finally:
        tmp_path.unlink(missing_ok=True)

    _auditar("anexar_url", task_id=task_id, url=url, nome=nome)
    return json.dumps(
        {"anexo_id": r.get("id"), "nome": r.get("title"), "url": r.get("url")},
        ensure_ascii=False,
    )


@mcp.tool()
def criar_webhook(
    workspace_id: str, endpoint_url: str, eventos: list[str] | None = None
) -> str:
    """Registra um webhook: o ClickUp passa a chamar `endpoint_url` a cada evento.

    Sem `eventos`, usa um conjunto util para automacao (criacao, atualizacao,
    mudanca de status, exclusao, comentario). E o gancho para o n8n reagir a
    mudancas em tempo real em vez de fazer polling.
    """
    evs = eventos or [
        "taskCreated",
        "taskUpdated",
        "taskDeleted",
        "taskStatusUpdated",
        "taskCommentPosted",
    ]
    if SIMULAR:
        return _simulado(
            "criar_webhook", workspace_id=workspace_id,
            endpoint=endpoint_url, eventos=evs,
        )

    r = api.post(
        f"/team/{workspace_id}/webhook",
        json={"endpoint": endpoint_url, "events": evs},
    )
    _auditar("criar_webhook", workspace_id=workspace_id, endpoint=endpoint_url)
    return json.dumps(
        {"webhook_id": (r.get("webhook") or {}).get("id") or r.get("id"), "eventos": evs},
        ensure_ascii=False,
    )


@mcp.tool()
def apagar_webhook(webhook_id: str) -> str:
    """Remove um webhook registrado (reversivel: basta criar de novo)."""
    if SIMULAR:
        return _simulado("apagar_webhook", webhook_id=webhook_id)

    api.delete(f"/webhook/{webhook_id}")
    _auditar("apagar_webhook", webhook_id=webhook_id)
    return json.dumps({"ok": True}, ensure_ascii=False)


@mcp.tool()
def enviar_email_resend(assunto: str, html: str, para: list[str] | None = None) -> str:
    """Dispara um email de atualizacao via Resend.

    Requer RESEND_API_KEY e RESEND_FROM no .env. Sem `para`, usa
    RESEND_TO_DEFAULT (emails separados por virgula).
    """
    chave = os.getenv("RESEND_API_KEY", "").strip()
    remetente = os.getenv("RESEND_FROM", "").strip()
    destinos = para or [
        e.strip() for e in os.getenv("RESEND_TO_DEFAULT", "").split(",") if e.strip()
    ]
    if not chave or not remetente:
        return json.dumps({
            "erro": "configure RESEND_API_KEY e RESEND_FROM no .env para habilitar"
        }, ensure_ascii=False)
    if not destinos:
        return json.dumps({
            "erro": "sem destinatarios: passe `para` ou defina RESEND_TO_DEFAULT no .env"
        }, ensure_ascii=False)

    if SIMULAR:
        return _simulado(
            "enviar_email_resend", assunto=assunto, destinatarios=len(destinos)
        )

    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {chave}"},
        json={"from": remetente, "to": destinos, "subject": assunto, "html": html},
        timeout=30,
    )
    if r.status_code >= 400:
        return json.dumps(
            {"erro": f"resend {r.status_code}: {r.text[:300]}"}, ensure_ascii=False
        )
    _auditar("enviar_email_resend", assunto=assunto, destinatarios=len(destinos))
    return json.dumps({"ok": True, "id": r.json().get("id")}, ensure_ascii=False)


@mcp.tool()
def notificar_discord(mensagem: str) -> str:
    """Posta uma mensagem no canal do Discord configurado em DISCORD_WEBHOOK_URL."""
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return json.dumps({
            "erro": "configure DISCORD_WEBHOOK_URL no .env para habilitar"
        }, ensure_ascii=False)

    if SIMULAR:
        return _simulado("notificar_discord", tamanho=len(mensagem))

    r = requests.post(url, json={"content": mensagem[:1900]}, timeout=30)
    if r.status_code >= 400:
        return json.dumps(
            {"erro": f"discord {r.status_code}: {r.text[:300]}"}, ensure_ascii=False
        )
    _auditar("notificar_discord", tamanho=len(mensagem))
    return json.dumps({"ok": True}, ensure_ascii=False)


@mcp.tool()
def restaurar_tarefa(task_id: str) -> str:
    """Recria uma tarefa a partir do ultimo snapshot no audit log.

    Snapshots sao gravados antes de toda edicao/exclusao feita por este
    servidor. A tarefa volta com nome, descricao, status, prioridade,
    responsaveis, tags e datas; anexos e comentarios nao voltam.
    """
    try:
        linhas = AUDIT_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return json.dumps({"erro": "audit log vazio; nada para restaurar"}, ensure_ascii=False)

    snap = None
    for linha in reversed(linhas):
        try:
            registro = json.loads(linha)
        except ValueError:
            continue
        s = registro.get("snapshot")
        if s and s.get("task_id") == task_id:
            snap = s
            break
    if not snap:
        return json.dumps(
            {"erro": f"nenhum snapshot de {task_id} no audit log"}, ensure_ascii=False
        )
    if not snap.get("list_id"):
        return json.dumps({"erro": "snapshot sem list_id; nao da para recriar"}, ensure_ascii=False)

    corpo: dict = {"name": snap.get("nome") or f"(restaurada) {task_id}"}
    if snap.get("descricao"):
        corpo["markdown_description"] = snap["descricao"]
    if snap.get("status"):
        corpo["status"] = snap["status"]
    if snap.get("prioridade") in _NIVEIS_PRIORIDADE:
        corpo["priority"] = _NIVEIS_PRIORIDADE[snap["prioridade"]]
    if snap.get("responsaveis"):
        corpo["assignees"] = snap["responsaveis"]
    if snap.get("tags"):
        corpo["tags"] = snap["tags"]
    for campo in ("due_date", "start_date"):
        if snap.get(campo):
            corpo[campo] = int(snap[campo])
    if snap.get("parent"):
        corpo["parent"] = snap["parent"]

    if SIMULAR:
        return _simulado("restaurar_tarefa", de=task_id, corpo=corpo)

    t = api.post(f"/list/{snap['list_id']}/task", json=corpo)
    _auditar("restaurar_tarefa", original=task_id, nova=t.get("id"))
    resultado = _resumir_tarefa(t)
    resultado["aviso"] = "anexos e comentarios da original nao sao restaurados"
    return json.dumps(resultado, ensure_ascii=False)


@mcp.tool()
def apagar_tarefa(task_id: str) -> str:
    """Apaga uma tarefa. IRREVERSIVEL - a API do ClickUp nao tem lixeira.

    Desligado por padrao. Para habilitar, ponha CLICKUP_ALLOW_DELETE=true no .env.
    O snapshot vai para o audit log; restaurar_tarefa recria o basico.
    """
    if not PERMITIR_APAGAR:
        return json.dumps({
            "erro": "exclusao desabilitada",
            "como_habilitar": "defina CLICKUP_ALLOW_DELETE=true no arquivo .env",
        }, ensure_ascii=False)

    if SIMULAR:
        return _simulado("apagar_tarefa", task_id=task_id)

    antes = api.get(f"/task/{task_id}")
    api.delete(f"/task/{task_id}")
    _auditar(
        "apagar_tarefa", task_id=task_id, nome=antes.get("name"),
        snapshot=_snapshot(antes),
    )
    return json.dumps({"apagada": task_id, "nome": antes.get("name")}, ensure_ascii=False)


# --------------------------------------------------------------------------
# Estrutura do workspace
# --------------------------------------------------------------------------

@mcp.tool()
def criar_lista(nome: str, folder_id: str = "", space_id: str = "") -> str:
    """Cria uma lista dentro de uma pasta (folder_id) ou solta num space (space_id).

    Passe exatamente um dos dois.
    """
    if bool(folder_id) == bool(space_id):
        return json.dumps({"erro": "passe folder_id OU space_id, exatamente um"}, ensure_ascii=False)

    if SIMULAR:
        return _simulado("criar_lista", nome=nome, folder_id=folder_id, space_id=space_id)

    caminho = f"/folder/{folder_id}/list" if folder_id else f"/space/{space_id}/list"
    r = api.post(caminho, json={"name": nome})
    _auditar("criar_lista", list_id=r.get("id"), nome=nome)
    return json.dumps({"list_id": r.get("id"), "nome": r.get("name")}, ensure_ascii=False)


@mcp.tool()
def criar_pasta(space_id: str, nome: str) -> str:
    """Cria uma pasta (folder) num space."""
    if SIMULAR:
        return _simulado("criar_pasta", space_id=space_id, nome=nome)

    r = api.post(f"/space/{space_id}/folder", json={"name": nome})
    _auditar("criar_pasta", folder_id=r.get("id"), nome=nome)
    return json.dumps({"folder_id": r.get("id"), "nome": r.get("name")}, ensure_ascii=False)


@mcp.tool()
def editar_lista(list_id: str, nome: str) -> str:
    """Renomeia uma lista."""
    if SIMULAR:
        return _simulado("editar_lista", list_id=list_id, nome=nome)

    r = api.put(f"/list/{list_id}", json={"name": nome})
    _auditar("editar_lista", list_id=list_id, nome=nome)
    return json.dumps({"list_id": r.get("id"), "nome": r.get("name")}, ensure_ascii=False)


@mcp.tool()
def listar_statuses(list_id: str) -> str:
    """Nomes validos de status (colunas) de uma lista.

    Consulte antes de editar_tarefa(status=...): o nome precisa ser exato.
    """
    info = api.get_cacheado(f"/list/{list_id}", ttl=60)
    return json.dumps(
        [
            {"status": s.get("status"), "tipo": s.get("type")}
            for s in info.get("statuses", [])
        ],
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------
# Pipeline de tarefas
# --------------------------------------------------------------------------

@mcp.tool()
def listar_checklists(task_id: str) -> str:
    """Checklists da tarefa com os IDs necessarios para marcar_item_checklist."""
    t = api.get(f"/task/{task_id}")
    return json.dumps(
        [
            {
                "checklist_id": cl.get("id"),
                "titulo": cl.get("name"),
                "itens": [
                    {
                        "item_id": i.get("id"),
                        "nome": i.get("name"),
                        "feito": bool(i.get("resolved")),
                    }
                    for i in cl.get("items") or []
                ],
            }
            for cl in t.get("checklists") or []
        ],
        ensure_ascii=False,
    )


@mcp.tool()
def marcar_item_checklist(checklist_id: str, item_id: str, feito: bool = True) -> str:
    """Marca (ou desmarca) um item de checklist. IDs vem de listar_checklists."""
    if SIMULAR:
        return _simulado(
            "marcar_item_checklist", checklist_id=checklist_id,
            item_id=item_id, feito=feito,
        )

    api.put(
        f"/checklist/{checklist_id}/checklist_item/{item_id}",
        json={"resolved": feito},
    )
    _auditar("marcar_item_checklist", checklist_id=checklist_id, item_id=item_id, feito=feito)
    return json.dumps({"ok": True, "feito": feito}, ensure_ascii=False)


@mcp.tool()
def duplicar_tarefa(task_id: str, novo_nome: str = "", list_id: str = "") -> str:
    """Clona uma tarefa: nome, descricao, prioridade, tags e checklists.

    De proposito NAO copia datas, status nem responsaveis - um clone de modelo
    comeca do zero. Sem `list_id`, a copia nasce na mesma lista.
    """
    if SIMULAR:
        return _simulado("duplicar_tarefa", task_id=task_id, novo_nome=novo_nome)

    orig = api.get(f"/task/{task_id}")
    destino = list_id or (orig.get("list") or {}).get("id")
    if not destino:
        return json.dumps({"erro": "tarefa original sem lista conhecida"}, ensure_ascii=False)

    dados = {
        "nome": novo_nome or f"{orig.get('name')} (copia)",
        "descricao": orig.get("description") or "",
        "tags": [tg.get("name") for tg in orig.get("tags") or []],
    }
    prioridade = (orig.get("priority") or {}).get("priority") or ""
    if prioridade in _NIVEIS_PRIORIDADE:
        dados["prioridade"] = prioridade
    corpo, erro = _montar_corpo(dados)
    if erro:
        return json.dumps({"erro": erro}, ensure_ascii=False)

    t = api.post(f"/list/{destino}/task", json=corpo)
    for cl in orig.get("checklists") or []:
        r = api.post(f"/task/{t['id']}/checklist", json={"name": cl.get("name")})
        cid = (r.get("checklist") or {}).get("id")
        for item in cl.get("items") or []:
            api.post(f"/checklist/{cid}/checklist_item", json={"name": item.get("name")})

    _auditar("duplicar_tarefa", original=task_id, nova=t.get("id"))
    return json.dumps(_resumir_tarefa(t), ensure_ascii=False)


@mcp.tool()
def criar_tarefas_em_lote(list_id: str, tarefas: list[dict]) -> str:
    """Cria varias tarefas de uma vez na mesma lista.

    Cada item aceita: nome (obrigatorio), descricao, prioridade, status,
    due_date, start_date, parent, tags, responsaveis. Itens invalidos sao
    reportados por posicao sem derrubar o lote.
    """
    if SIMULAR:
        return _simulado("criar_tarefas_em_lote", list_id=list_id, quantidade=len(tarefas))

    criadas, erros = [], []
    for i, dados in enumerate(tarefas):
        corpo, erro = _montar_corpo(dados)
        if erro or not corpo.get("name"):
            erros.append({"posicao": i, "erro": erro or "campo nome obrigatorio"})
            continue
        try:
            t = api.post(f"/list/{list_id}/task", json=corpo)
            criadas.append(_resumir_tarefa(t))
        except Exception as exc:  # noqa: BLE001 - reportado por item
            erros.append({"posicao": i, "nome": dados.get("nome"), "erro": str(exc)})

    _auditar("criar_tarefas_em_lote", list_id=list_id, criadas=len(criadas), erros=len(erros))
    return json.dumps({"criadas": criadas, "erros": erros}, ensure_ascii=False)


@mcp.tool()
def concluir_tarefa(task_id: str) -> str:
    """Move a tarefa para o status de conclusao da lista dela.

    Descobre sozinho o nome da coluna final (tipo closed/done), entao funciona
    em qualquer board sem saber como a coluna se chama.
    """
    if SIMULAR:
        return _simulado("concluir_tarefa", task_id=task_id)

    t = api.get(f"/task/{task_id}")
    lid = (t.get("list") or {}).get("id")
    if not lid:
        return json.dumps({"erro": "tarefa sem lista conhecida"}, ensure_ascii=False)
    statuses = api.get(f"/list/{lid}").get("statuses", [])
    final = next(
        (s.get("status") for s in statuses if s.get("type") == "closed"), None
    ) or next(
        (s.get("status") for s in statuses if s.get("type") == "done"), None
    )
    if not final:
        return json.dumps({
            "erro": "lista sem status de conclusao",
            "statuses": [s.get("status") for s in statuses],
        }, ensure_ascii=False)

    atualizado = api.put(f"/task/{task_id}", json={"status": final})
    _auditar("concluir_tarefa", task_id=task_id, status=final)
    return json.dumps(_resumir_tarefa(atualizado), ensure_ascii=False)


@mcp.tool()
def mudar_status_em_lote(task_ids: list[str], status: str) -> str:
    """Muda o status de varias tarefas de uma vez. Falhas sao reportadas por tarefa."""
    if SIMULAR:
        return _simulado("mudar_status_em_lote", tarefas=task_ids, status=status)

    def mudar(tid: str) -> dict:
        try:
            api.put(f"/task/{tid}", json={"status": status})
            return {"id": tid, "ok": True}
        except Exception as exc:  # noqa: BLE001 - reportado por item
            return {"id": tid, "erro": str(exc)}

    resultados = api.em_paralelo(mudar, task_ids, max_workers=4)
    _auditar("mudar_status_em_lote", status=status, tarefas=len(task_ids))
    return json.dumps(resultados, ensure_ascii=False)


# --------------------------------------------------------------------------
# Comentarios e pessoas
# --------------------------------------------------------------------------

@mcp.tool()
def responder_comentario(comment_id: str, texto: str) -> str:
    """Responde um comentario existente, criando uma thread."""
    if SIMULAR:
        return _simulado("responder_comentario", comment_id=comment_id)

    r = api.post(f"/comment/{comment_id}/reply", json={"comment_text": texto})
    _auditar("responder_comentario", comment_id=comment_id)
    return json.dumps({"ok": True, "reply_id": r.get("id")}, ensure_ascii=False)


@mcp.tool()
def comentar_lista(list_id: str, texto: str) -> str:
    """Comenta na lista inteira (aviso geral), sem escolher tarefa."""
    if SIMULAR:
        return _simulado("comentar_lista", list_id=list_id)

    r = api.post(f"/list/{list_id}/comment", json={"comment_text": texto})
    _auditar("comentar_lista", list_id=list_id)
    return json.dumps({"ok": True, "comment_id": r.get("id")}, ensure_ascii=False)


@mcp.tool()
def seguir_tarefa(task_id: str, user_id: int = 0, seguir: bool = True) -> str:
    """Adiciona (ou remove) um observador da tarefa, sem torna-lo responsavel.

    Sem `user_id`, usa o dono do token. Alguns planos ignoram watchers via API;
    confira o retorno.
    """
    if not user_id:
        user_id = (api.get("/user").get("user") or {}).get("id")

    if SIMULAR:
        return _simulado("seguir_tarefa", task_id=task_id, user_id=user_id, seguir=seguir)

    operacao = "add" if seguir else "rem"
    t = api.put(f"/task/{task_id}", json={"watchers": {operacao: [user_id]}})
    _auditar("seguir_tarefa", task_id=task_id, user_id=user_id, seguir=seguir)
    return json.dumps(_resumir_tarefa(t), ensure_ascii=False)


@mcp.tool()
def convidar_membro(workspace_id: str, email: str) -> str:
    """Convida alguem para o workspace como convidado (guest), por email.

    Atencao: em alguns planos (inclusive o Free) o ClickUp so aceita convite
    pela interface; nesse caso a API devolve o erro e ele e repassado aqui.
    """
    if SIMULAR:
        return _simulado("convidar_membro", workspace_id=workspace_id, email=email)

    r = api.post(f"/team/{workspace_id}/guest", json={"email": email})
    _auditar("convidar_membro", workspace_id=workspace_id, email=email)
    return json.dumps({"ok": True, "resposta": bool(r)}, ensure_ascii=False)


# --------------------------------------------------------------------------
# Tempo e metas
# --------------------------------------------------------------------------

@mcp.tool()
def registrar_tempo(
    workspace_id: str, task_id: str, minutos: int, descricao: str = ""
) -> str:
    """Registra tempo trabalhado numa tarefa (entrada terminando agora)."""
    if minutos <= 0:
        return json.dumps({"erro": "minutos precisa ser maior que zero"}, ensure_ascii=False)

    if SIMULAR:
        return _simulado("registrar_tempo", task_id=task_id, minutos=minutos)

    duracao = minutos * 60_000
    inicio = int(time.time() * 1000) - duracao
    r = api.post(
        f"/team/{workspace_id}/time_entries",
        json={"tid": task_id, "start": inicio, "duration": duracao, "description": descricao},
    )
    _auditar("registrar_tempo", task_id=task_id, minutos=minutos)
    return json.dumps(
        {"ok": True, "entry_id": (r.get("data") or {}).get("id")}, ensure_ascii=False
    )


@mcp.tool()
def ler_tempo(workspace_id: str, task_id: str = "", dias: int = 30) -> str:
    """Entradas de tempo dos ultimos `dias`, opcionalmente de uma tarefa so."""
    params: dict = {"start_date": int((time.time() - dias * 86_400) * 1000)}
    if task_id:
        params["task_id"] = task_id
    entradas = api.get(f"/team/{workspace_id}/time_entries", params=params).get("data", [])
    resumo = [
        {
            "tarefa": (e.get("task") or {}).get("name"),
            "minutos": round(int(e.get("duration") or 0) / 60_000),
            "inicio": e.get("start"),
            "descricao": e.get("description"),
        }
        for e in entradas
    ]
    return json.dumps(
        {"total_minutos": sum(r["minutos"] for r in resumo), "entradas": resumo},
        ensure_ascii=False,
    )


@mcp.tool()
def criar_meta(
    workspace_id: str,
    nome: str,
    descricao: str = "",
    due_date: str = "",
    alvo: int = 0,
    unidade: str = "",
) -> str:
    """Cria uma meta (Goal). Com `alvo` > 0, cria um key result numerico junto.

    Exemplo: nome="20 tutoriais publicados", alvo=20, unidade="tutoriais".
    """
    corpo: dict = {"name": nome, "description": descricao}
    try:
        if due_date:
            corpo["due_date"] = _para_ms(due_date)
    except ValueError as exc:
        return json.dumps({"erro": str(exc)}, ensure_ascii=False)

    if SIMULAR:
        return _simulado("criar_meta", nome=nome, alvo=alvo)

    r = api.post(f"/team/{workspace_id}/goal", json=corpo)
    goal_id = (r.get("goal") or {}).get("id")
    key_result_id = None
    if alvo > 0 and goal_id:
        k = api.post(
            f"/goal/{goal_id}/key_result",
            json={
                "name": nome,
                "type": "number",
                "steps_start": 0,
                "steps_end": alvo,
                "unit": unidade or "itens",
                "owners": [],
                "task_ids": [],
                "list_ids": [],
            },
        )
        key_result_id = (k.get("key_result") or {}).get("id")
    _auditar("criar_meta", goal_id=goal_id, nome=nome, alvo=alvo)
    return json.dumps(
        {"goal_id": goal_id, "key_result_id": key_result_id}, ensure_ascii=False
    )


# --------------------------------------------------------------------------
# Cola local: vault, auditoria, exportacao
# --------------------------------------------------------------------------

@mcp.tool()
def sincronizar_vault(
    workspace_id: str = "90171401081", pasta: str = "Wingman Marketing"
) -> str:
    """Regenera a nota espelho do board no vault Obsidian.

    So le o ClickUp; a escrita e num arquivo local (ver sincronizar_vault.py).
    """
    import sincronizar_vault as _sv

    destino = Path(os.getenv("WINGMAN_VAULT_NOTA", "") or _sv.NOTA_PADRAO)
    if not destino.parent.is_dir():
        return json.dumps(
            {"erro": f"pasta do vault nao existe: {destino.parent}"}, ensure_ascii=False
        )
    conteudo = _sv.gerar_nota(workspace_id, pasta)
    destino.write_text(conteudo, encoding="utf-8")
    return json.dumps(
        {"nota": str(destino), "tamanho": len(conteudo)}, ensure_ascii=False
    )


@mcp.tool()
def reconciliar_vault(
    direcao: str = "ambos", workspace_id: str = "90171401081"
) -> str:
    """Reconcilia o vault "ClickUp Sync" com o ClickUp, nas duas direcoes.

    "empurrar": itens novos da Caixa de Entrada do vault viram tarefas.
    "puxar": regenera as notas espelho por pasta. "ambos": os dois, nessa ordem.
    """
    if direcao not in ("ambos", "empurrar", "puxar"):
        return json.dumps({"erro": "direcao deve ser ambos, empurrar ou puxar"}, ensure_ascii=False)

    import reconciliar_vault as _rv

    saida: dict = {}
    if direcao in ("ambos", "empurrar"):
        if SIMULAR:
            return _simulado("reconciliar_vault", direcao=direcao)
        resultados = _rv.empurrar(workspace_id)
        saida["enviadas"] = [r for r in resultados if "task_id" in r]
        saida["erros"] = [r for r in resultados if "erro" in r]
        if saida["enviadas"]:
            _auditar("reconciliar_vault", enviadas=len(saida["enviadas"]))
    if direcao in ("ambos", "puxar"):
        saida["espelhos"] = _rv.puxar(workspace_id)
    return json.dumps(saida, ensure_ascii=False)


@mcp.tool()
def ler_audit_log(dias: int = 7, acao: str = "") -> str:
    """O que este servidor alterou nos ultimos `dias`, mais recente primeiro.

    `acao` filtra por tipo (ex: "criar_tarefa"). Snapshots sao omitidos do
    retorno; use restaurar_tarefa para aproveita-los.
    """
    try:
        linhas = AUDIT_LOG.read_text(encoding="utf-8").splitlines()
    except OSError:
        return json.dumps([], ensure_ascii=False)

    limite = datetime.now(timezone.utc).timestamp() - dias * 86_400
    saida = []
    for linha in reversed(linhas):
        try:
            registro = json.loads(linha)
            quando = datetime.fromisoformat(registro.get("quando", "")).timestamp()
        except ValueError:
            continue
        if quando < limite:
            break  # o arquivo e ordenado; dali para tras e tudo mais antigo
        if acao and registro.get("acao") != acao:
            continue
        if "snapshot" in registro:
            registro = {**registro, "snapshot": "(guardado)"}
        saida.append(registro)
        if len(saida) >= 100:
            break
    return json.dumps(saida, ensure_ascii=False)


@mcp.tool()
def exportar_board(
    workspace_id: str, pasta_contem: str = "", formato: str = "json"
) -> str:
    """Exporta as tarefas do workspace para um arquivo local em exports/.

    `pasta_contem` filtra pelo rotulo "Pasta / Lista" (ex: "Wingman Marketing").
    `formato`: json ou csv (csv abre direto no Excel).
    """
    if formato not in ("json", "csv"):
        return json.dumps({"erro": "formato deve ser json ou csv"}, ensure_ascii=False)

    tarefas = api.get_paginado(
        f"/team/{workspace_id}/task",
        params={"include_closed": "true", "subtasks": "true"},
    )
    if pasta_contem:
        tarefas = [t for t in tarefas if pasta_contem in _rotulo_lista(t)]

    linhas = [
        {
            "id": t.get("id"),
            "nome": t.get("name"),
            "lista": _rotulo_lista(t),
            "status": (t.get("status") or {}).get("status"),
            "prioridade": (t.get("priority") or {}).get("priority"),
            "responsaveis": "; ".join(
                a.get("username") or "" for a in t.get("assignees") or []
            ),
            "due_date": t.get("due_date"),
            "url": t.get("url"),
        }
        for t in tarefas
    ]

    EXPORT_DIR.mkdir(exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d-%H%M%S")
    destino = EXPORT_DIR / f"board-{carimbo}.{formato}"
    if formato == "json":
        destino.write_text(
            json.dumps(linhas, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    else:
        # utf-8-sig para o Excel reconhecer acentos sem perguntar.
        with destino.open("w", newline="", encoding="utf-8-sig") as fh:
            colunas = ["id", "nome", "lista", "status", "prioridade",
                       "responsaveis", "due_date", "url"]
            escritor = csv.DictWriter(fh, fieldnames=colunas)
            escritor.writeheader()
            escritor.writerows(linhas)

    return json.dumps(
        {"arquivo": str(destino), "tarefas": len(linhas)}, ensure_ascii=False
    )


def main() -> None:
    # Valida o token uma vez no boot: melhor falhar com mensagem clara aqui do
    # que na primeira tool. Nao aborta - com o servidor de pe, o erro chega
    # legivel ao cliente MCP; um processo morto so gera "connection closed".
    try:
        u = api.get("/user").get("user") or {}
        log.info("token valido: usuario %s (id %s)", u.get("username"), u.get("id"))
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira aviso de boot
        log.error("validacao do token falhou no startup: %s", exc)
    if SIMULAR:
        log.warning("CLICKUP_DRY_RUN ativo: tools de escrita apenas simulam")
    if PERMITIR_APAGAR:
        log.warning("CLICKUP_ALLOW_DELETE ativo: apagar_tarefa habilitada")
    mcp.run()


if __name__ == "__main__":
    main()
