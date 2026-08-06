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

import json
import logging
import os
import re
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
    corpo: dict = {"name": nome}
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
    if parent:
        corpo["parent"] = parent
    if tags:
        corpo["tags"] = tags
    if responsaveis:
        corpo["assignees"] = responsaveis

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
