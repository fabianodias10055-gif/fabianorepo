#!/usr/bin/env python3
"""Reconciliacao bidirecional entre o ClickUp e o vault "ClickUp Sync".

Duas direcoes:

  empurrar (vault -> ClickUp): le a "01 - Caixa de Entrada.md" do vault; cada
      item "- [ ] Nome" sob um cabecalho "## Pasta / Lista" vira uma tarefa
      nessa lista. A linha e reescrita como feita, com o link da tarefa, entao
      rodar de novo nao duplica nada.

  puxar (ClickUp -> vault): regenera uma nota "Espelho - <Pasta>.md" por pasta
      do workspace, com todas as tarefas e status. Espelhos sao leitura; a
      escrita e sempre pela Caixa de Entrada.

Rodar:
    python reconciliar_vault.py                # empurra e depois puxa
    python reconciliar_vault.py --so-puxar
    python reconciliar_vault.py --so-empurrar

Formato de um item da Caixa de Entrada (sufixos opcionais):
    - [ ] [FABIANO] Nome da tarefa | prioridade: high | due: 2026-08-15
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

import anexar_icones as ai
import clickup_api as api
from sincronizar_vault import _dono_e_categoria, _titulo_limpo


VAULT_DIR = Path(
    os.getenv("CLICKUP_SYNC_VAULT", "")
    or r"C:\Users\LocoDevPC\Documents\Vaults\ClickUp Sync"
)
CAIXA = "01 - Caixa de Entrada.md"

_HEAD_RE = re.compile(r"^##\s+(.+?)\s*$")
_ITEM_RE = re.compile(r"^-\s+\[ \]\s+(.+?)\s*$")
_NIVEIS = {"urgent": 1, "high": 2, "normal": 3, "low": 4}


def _para_ms(data: str) -> int:
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(data, fmt).timestamp() * 1000)
        except ValueError:
            continue
    raise ValueError(f"data invalida: {data!r}")


def analisar_caixa(texto: str) -> list[dict]:
    """Extrai os itens nao enviados da Caixa de Entrada.

    Devolve dicts com: linha (indice), rotulo (cabecalho), nome, prioridade, due.
    """
    itens = []
    rotulo = None
    for i, linha in enumerate(texto.splitlines()):
        m = _HEAD_RE.match(linha)
        if m:
            rotulo = m.group(1)
            continue
        m = _ITEM_RE.match(linha)
        if m and rotulo:
            bruto = m.group(1)
            partes = [p.strip() for p in bruto.split("|")]
            item = {"linha": i, "rotulo": rotulo, "nome": partes[0],
                    "prioridade": "", "due": ""}
            for p in partes[1:]:
                chave, _, valor = p.partition(":")
                chave = chave.strip().lower()
                if chave == "prioridade":
                    item["prioridade"] = valor.strip().lower()
                elif chave == "due":
                    item["due"] = valor.strip()
            itens.append(item)
    return itens


def resolver_lista(rotulo: str, mapa: dict[str, str]) -> str | None:
    """Casa o cabecalho da Caixa com uma lista real, tolerando diferencas.

    Match exato primeiro; depois um unico match por substring. Ambiguidade
    devolve None em vez de chutar.
    """
    r = rotulo.strip().lower()
    if r in mapa:
        return mapa[r]
    candidatos = {lid for nome, lid in mapa.items() if r in nome or nome in r}
    return candidatos.pop() if len(candidatos) == 1 else None


def mapa_de_listas(workspace_id: str) -> dict[str, str]:
    return {nome.lower(): lid for lid, nome in ai.listas_do_workspace(workspace_id)}


def empurrar(workspace_id: str, vault_dir: Path = VAULT_DIR) -> list[dict]:
    """Cria no ClickUp os itens pendentes da Caixa de Entrada e marca as linhas."""
    caminho = vault_dir / CAIXA
    if not caminho.is_file():
        return []
    texto = caminho.read_text(encoding="utf-8")
    itens = analisar_caixa(texto)
    if not itens:
        return []

    mapa = mapa_de_listas(workspace_id)
    linhas = texto.splitlines()
    resultados = []
    hoje = datetime.now().strftime("%Y-%m-%d")
    for item in itens:
        lid = resolver_lista(item["rotulo"], mapa)
        if not lid:
            resultados.append({**item, "erro": f"lista nao encontrada: {item['rotulo']}"})
            continue
        corpo: dict = {"name": item["nome"]}
        if item["prioridade"]:
            if item["prioridade"] not in _NIVEIS:
                resultados.append({**item, "erro": f"prioridade invalida: {item['prioridade']}"})
                continue
            corpo["priority"] = _NIVEIS[item["prioridade"]]
        if item["due"]:
            try:
                corpo["due_date"] = _para_ms(item["due"])
            except ValueError as exc:
                resultados.append({**item, "erro": str(exc)})
                continue
        try:
            t = api.post(f"/list/{lid}/task", json=corpo)
        except api.ClickUpError as exc:
            resultados.append({**item, "erro": str(exc)})
            continue
        linhas[item["linha"]] = (
            f"- [x] [{item['nome']}]({t.get('url')}) - enviada {hoje}"
        )
        resultados.append({**item, "task_id": t.get("id"), "url": t.get("url")})

    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return resultados


def _sanitizar(nome: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "-", nome).strip()


def _nota_da_pasta(pasta: str, tarefas: list[dict]) -> str:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    por_status: dict[str, int] = {}
    for t in tarefas:
        s = (t.get("status") or {}).get("status") or "?"
        por_status[s] = por_status.get(s, 0) + 1

    linhas = [
        "---",
        "tags: [clickup, espelho, gerado]",
        f"gerado: {agora}",
        "fonte: clickup-mcp/reconciliar_vault.py",
        "---",
        "",
        f"# Espelho - {pasta}",
        "",
        "Nota gerada. **Nao editar a mao** - mudancas somem na proxima",
        "sincronizacao. Tarefa nova entra pela [[01 - Caixa de Entrada]].",
        "",
        f"**{len(tarefas)} tarefas.** "
        + " · ".join(f"{k}: {v}" for k, v in sorted(por_status.items())),
        "",
    ]
    tarefas = sorted(tarefas, key=lambda t: (ai.rotulo_da_lista(t), t.get("name", "")))
    lista_atual = None
    for t in tarefas:
        rotulo = ai.rotulo_da_lista(t)
        if rotulo != lista_atual:
            if lista_atual is not None:
                linhas.append("")
            linhas += [f"## {rotulo}", "",
                       "| Tarefa | Dono | Categoria | Status | Prioridade |",
                       "|---|---|---|---|---|"]
            lista_atual = rotulo
        dono, cat = _dono_e_categoria(t.get("name", ""))
        status = (t.get("status") or {}).get("status") or "?"
        prioridade = (t.get("priority") or {}).get("priority") or "-"
        linhas.append(
            f"| [{_titulo_limpo(t.get('name', ''))}]({t.get('url', '')}) "
            f"| {dono} | {cat} | {status} | {prioridade} |"
        )
    return "\n".join(linhas) + "\n"


def puxar(workspace_id: str, vault_dir: Path = VAULT_DIR) -> list[str]:
    """Regenera as notas espelho, uma por pasta, e remove espelhos orfaos."""
    vault_dir.mkdir(parents=True, exist_ok=True)
    tarefas = ai.tarefas_do_workspace(workspace_id)

    # Semeia com todas as pastas da hierarquia: pasta sem tarefa ainda ganha
    # espelho (vazio), senao a area some do vault ate a primeira tarefa.
    por_pasta: dict[str, list[dict]] = {}
    for _lid, rotulo in ai.listas_do_workspace(workspace_id):
        pasta = rotulo.split(" / ", 1)[0] if " / " in rotulo else "Listas Soltas"
        por_pasta.setdefault(pasta, [])
    for t in tarefas:
        pasta = (t.get("folder") or {}).get("name") or ""
        if not pasta or pasta.lower() == "hidden":
            pasta = "Listas Soltas"
        por_pasta.setdefault(pasta, []).append(t)

    atuais = set()
    geradas = []
    for pasta, ts in sorted(por_pasta.items()):
        arquivo = vault_dir / f"Espelho - {_sanitizar(pasta)}.md"
        arquivo.write_text(_nota_da_pasta(pasta, ts), encoding="utf-8")
        atuais.add(arquivo.name)
        geradas.append(arquivo.name)

    # Espelho de pasta que deixou de existir no ClickUp sai do vault tambem.
    for velho in vault_dir.glob("Espelho - *.md"):
        if velho.name not in atuais:
            velho.unlink()
    return geradas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="90171401081")
    ap.add_argument("--so-puxar", action="store_true")
    ap.add_argument("--so-empurrar", action="store_true")
    args = ap.parse_args()

    if not args.so_puxar:
        enviados = empurrar(args.workspace)
        ok = [r for r in enviados if "task_id" in r]
        erros = [r for r in enviados if "erro" in r]
        print(f"empurrar: {len(ok)} tarefas criadas, {len(erros)} erros")
        for r in erros:
            print(f"   ERRO linha {r['linha'] + 1}: {r['erro']}")
    if not args.so_empurrar:
        notas = puxar(args.workspace)
        print(f"puxar: {len(notas)} espelhos gerados em {VAULT_DIR}")
        for n in notas:
            print(f"   - {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
