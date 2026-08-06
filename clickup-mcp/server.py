"""Servidor MCP para o ClickUp, falando direto com a API publica.

Substitui o MCP oficial (mcp.clickup.com), cujo teto e 50 chamadas/24h no plano
Free e 300 no Unlimited+. Aqui o teto e o da API publica: 100 requisicoes/minuto,
com reset em segundos.

Rodar:  python server.py          (stdio, para clientes MCP locais)
"""

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from mcp.server.fastmcp import FastMCP

import clickup_api as api


BASE_DIR = Path(__file__).resolve().parent
AUDIT_LOG = BASE_DIR / "alteracoes.jsonl"

# Apagar tarefa e irreversivel e a API nao tem lixeira. Fica atras de um
# interruptor explicito para que um pedido ambiguo do usuario nunca vire
# uma exclusao silenciosa.
PERMITIR_APAGAR = os.getenv("CLICKUP_ALLOW_DELETE", "").lower() in {"1", "true", "sim"}

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
        "url": t.get("url"),
    }


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------

@mcp.tool()
def listar_workspaces() -> str:
    """Lista os workspaces (times) da conta. Use para descobrir o workspace_id."""
    times = api.get("/team").get("teams", [])
    return json.dumps(
        [{"id": t["id"], "nome": t["name"]} for t in times], ensure_ascii=False
    )


@mcp.tool()
def listar_hierarquia(workspace_id: str) -> str:
    """Mostra spaces, folders e listas do workspace, com os respectivos IDs.

    Use uma vez no inicio para saber onde as coisas ficam; depois trabalhe com
    os IDs direto, que custa menos chamadas.
    """
    arvore = []
    for space in api.get(f"/team/{workspace_id}/space").get("spaces", []):
        no = {"space_id": space["id"], "space": space["name"], "folders": [], "listas": []}

        for folder in api.get(f"/space/{space['id']}/folder").get("folders", []):
            no["folders"].append({
                "folder_id": folder["id"],
                "folder": folder["name"],
                "listas": [
                    {"list_id": l["id"], "lista": l["name"]}
                    for l in folder.get("lists", [])
                ],
            })

        # Listas soltas no space, fora de qualquer folder.
        for l in api.get(f"/space/{space['id']}/list").get("lists", []):
            no["listas"].append({"list_id": l["id"], "lista": l["name"]})

        arvore.append(no)
    return json.dumps(arvore, ensure_ascii=False, indent=2)


@mcp.tool()
def buscar_tarefas(list_id: str, incluir_concluidas: bool = True) -> str:
    """Lista as tarefas de uma lista.

    A API pagina de 100 em 100; esta funcao percorre todas as paginas sozinha.
    """
    tarefas, pagina = [], 0
    while True:
        resp = api.get(
            f"/list/{list_id}/task",
            params={
                "include_closed": str(incluir_concluidas).lower(),
                "subtasks": "true",
                "page": pagina,
            },
        )
        lote = resp.get("tasks", [])
        tarefas.extend(lote)
        if resp.get("last_page") or not lote:
            break
        pagina += 1

    return json.dumps(
        {"total": len(tarefas), "tarefas": [_resumir_tarefa(t) for t in tarefas]},
        ensure_ascii=False,
    )


@mcp.tool()
def obter_tarefa(task_id: str) -> str:
    """Detalhes completos de uma tarefa, incluindo descricao e anexos."""
    t = api.get(f"/task/{task_id}")
    detalhe = _resumir_tarefa(t)
    detalhe["descricao"] = t.get("description")
    detalhe["anexos"] = [
        {"id": a.get("id"), "nome": a.get("title"), "url": a.get("url")}
        for a in t.get("attachments") or []
    ]
    return json.dumps(detalhe, ensure_ascii=False)


@mcp.tool()
def listar_membros(workspace_id: str) -> str:
    """Lista os membros do workspace com seus IDs, para atribuir responsaveis."""
    for time_ in api.get("/team").get("teams", []):
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
) -> str:
    """Cria uma tarefa. `prioridade`: urgent, high, normal ou low."""
    corpo: dict = {"name": nome}
    if descricao:
        corpo["markdown_description"] = descricao
    if status:
        corpo["status"] = status
    if prioridade:
        niveis = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
        if prioridade not in niveis:
            return json.dumps({"erro": f"prioridade invalida: {prioridade}"})
        corpo["priority"] = niveis[prioridade]

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
) -> str:
    """Edita uma tarefa. Campos vazios ficam como estao.

    Mudar `status` e como se move um card entre colunas do quadro.
    """
    corpo: dict = {}
    if nome:
        corpo["name"] = nome
    if descricao:
        corpo["markdown_description"] = descricao
    if status:
        corpo["status"] = status
    if prioridade:
        niveis = {"urgent": 1, "high": 2, "normal": 3, "low": 4}
        if prioridade not in niveis:
            return json.dumps({"erro": f"prioridade invalida: {prioridade}"})
        corpo["priority"] = niveis[prioridade]

    if not corpo:
        return json.dumps({"erro": "nenhum campo para alterar"})

    t = api.put(f"/task/{task_id}", json=corpo)
    _auditar("editar_tarefa", task_id=task_id, campos=list(corpo))
    return json.dumps(_resumir_tarefa(t), ensure_ascii=False)


@mcp.tool()
def atribuir_responsaveis(task_id: str, user_ids: list[int]) -> str:
    """Define os responsaveis da tarefa. Pegue os IDs com `listar_membros`.

    Substitui a lista atual: quem nao estiver em `user_ids` sai da tarefa.
    """
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
    r = api.post(f"/task/{task_id}/comment", json={"comment_text": texto})
    _auditar("comentar_tarefa", task_id=task_id)
    return json.dumps({"comment_id": r.get("id"), "ok": True}, ensure_ascii=False)


@mcp.tool()
def anexar_arquivo(task_id: str, caminho: str, nome: str = "") -> str:
    """Anexa um arquivo do disco local a tarefa.

    `caminho` e um caminho na maquina onde este servidor roda.
    """
    r = api.upload_attachment(task_id, Path(caminho), nome or None)
    _auditar("anexar_arquivo", task_id=task_id, arquivo=nome or Path(caminho).name)
    return json.dumps(
        {"anexo_id": r.get("id"), "nome": r.get("title"), "url": r.get("url")},
        ensure_ascii=False,
    )


@mcp.tool()
def anexar_url(task_id: str, url: str, nome: str = "") -> str:
    """Baixa um arquivo de uma URL publica e anexa a tarefa.

    O download acontece nesta maquina, nao nos servidores do ClickUp.
    """
    nome = nome or Path(urlparse(url).path).name or "anexo"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()

    with tempfile.NamedTemporaryFile(suffix=f"_{nome}", delete=False) as tmp:
        tmp.write(resp.content)
        tmp_path = Path(tmp.name)
    try:
        r = api.upload_attachment(task_id, tmp_path, nome)
    finally:
        tmp_path.unlink(missing_ok=True)

    _auditar("anexar_url", task_id=task_id, url=url, nome=nome)
    return json.dumps(
        {"anexo_id": r.get("id"), "nome": r.get("title"), "url": r.get("url")},
        ensure_ascii=False,
    )


@mcp.tool()
def apagar_tarefa(task_id: str) -> str:
    """Apaga uma tarefa. IRREVERSIVEL - a API do ClickUp nao tem lixeira.

    Desligado por padrao. Para habilitar, ponha CLICKUP_ALLOW_DELETE=true no .env.
    """
    if not PERMITIR_APAGAR:
        return json.dumps({
            "erro": "exclusao desabilitada",
            "como_habilitar": "defina CLICKUP_ALLOW_DELETE=true no arquivo .env",
        }, ensure_ascii=False)

    antes = api.get(f"/task/{task_id}")
    api.delete(f"/task/{task_id}")
    _auditar("apagar_tarefa", task_id=task_id, nome=antes.get("name"))
    return json.dumps({"apagada": task_id, "nome": antes.get("name")}, ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
