#!/usr/bin/env python3
"""Escreve o estado do board Wingman Marketing de volta no vault Obsidian.

Fecha o ciclo vault -> ClickUp -> vault: a nota gerada mostra o que esta no
board sem abrir o ClickUp, e deixa claro que e um espelho (nao editar a mao).

Rodar:
    python sincronizar_vault.py                     # workspace e caminho padrao
    python sincronizar_vault.py --workspace 123     # outro workspace

O caminho da nota pode ser trocado com a variavel WINGMAN_VAULT_NOTA no .env.
"""

import argparse
import re
import sys
from collections import Counter
from datetime import datetime
from itertools import groupby
from pathlib import Path

import os

import anexar_icones as ai


NOTA_PADRAO = Path(
    r"C:\Users\LocoDevPC\Documents\Vaults\Wingman Marketing"
    r"\02 - Estado do Board (gerado).md"
)

TAGS_RE = re.compile(r"\[([A-ZÀ-Ú0-9]+)\]")


def _dono_e_categoria(titulo: str) -> tuple[str, str]:
    tags = TAGS_RE.findall(titulo.upper())
    dono = tags[0] if tags else "-"
    categoria = tags[1] if len(tags) > 1 else "-"
    return dono, categoria


def _titulo_limpo(titulo: str) -> str:
    limpo = re.sub(r"^(\[[^\]]+\]\s*)+", "", titulo).strip()
    # Pipes quebrariam a tabela markdown.
    return limpo.replace("|", "/")


def gerar_nota(workspace_id: str, apenas_pasta: str = "Wingman Marketing") -> str:
    tarefas = [
        t for t in ai.tarefas_do_workspace(workspace_id)
        if apenas_pasta in ai.rotulo_da_lista(t)
    ]
    tarefas.sort(key=lambda t: (ai.rotulo_da_lista(t), t.get("name", "")))

    por_status = Counter(
        (t.get("status") or {}).get("status") or "?" for t in tarefas
    )
    por_dono = Counter(_dono_e_categoria(t.get("name", ""))[0] for t in tarefas)

    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    linhas = [
        "---",
        "tags: [wingman, clickup, gerado]",
        f"gerado: {agora}",
        "fonte: clickup-mcp/sincronizar_vault.py",
        "---",
        "",
        "# Estado do Board - Wingman Marketing (gerado)",
        "",
        "Arquivo gerado automaticamente a partir do ClickUp. **Nao editar a mao**:",
        "qualquer mudanca some na proxima sincronizacao. Para atualizar, rode",
        "`python sincronizar_vault.py` em `fabianorepo/clickup-mcp/`.",
        "",
        f"**Total: {len(tarefas)} tarefas.** "
        + " · ".join(f"{k}: {v}" for k, v in sorted(por_status.items())),
        "",
        "Por dono: "
        + " · ".join(f"{k}: {v}" for k, v in sorted(por_dono.items())),
        "",
    ]

    for rotulo, grupo in groupby(tarefas, key=ai.rotulo_da_lista):
        grupo = list(grupo)
        linhas += [
            f"## {rotulo} ({len(grupo)})",
            "",
            "| Tarefa | Dono | Categoria | Status |",
            "|---|---|---|---|",
        ]
        for t in grupo:
            dono, cat = _dono_e_categoria(t.get("name", ""))
            status = (t.get("status") or {}).get("status") or "?"
            linhas.append(
                f"| [{_titulo_limpo(t.get('name', ''))}]({t.get('url', '')}) "
                f"| {dono} | {cat} | {status} |"
            )
        linhas.append("")

    return "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default="90171401081")
    ap.add_argument("--pasta", default="Wingman Marketing",
                    help="so listas cujo rotulo contem este texto")
    args = ap.parse_args()

    destino = Path(os.getenv("WINGMAN_VAULT_NOTA", "") or NOTA_PADRAO)
    if not destino.parent.is_dir():
        print(f"ERRO: pasta do vault nao existe: {destino.parent}")
        return 1

    conteudo = gerar_nota(args.workspace, args.pasta)
    destino.write_text(conteudo, encoding="utf-8")
    print(f"nota gerada: {destino} ({len(conteudo)} caracteres)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
