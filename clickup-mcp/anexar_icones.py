#!/usr/bin/env python3
"""Anexa o icone da categoria em cada tarefa do board Wingman Marketing.

A categoria sai do proprio titulo, que segue o padrao "[NOME] [CATEGORIA] Tarefa".
Tarefas sem categoria conhecida sao puladas e listadas no fim.

Rodar:
    python anexar_icones.py --workspace 90171401081 --dry-run   # so mostra o plano
    python anexar_icones.py --workspace 90171401081             # executa

E seguro rodar de novo: tarefas que ja tem o anexo com o mesmo nome sao puladas.
"""

import argparse
import re
import sys
from pathlib import Path

import clickup_api as api


BASE_DIR = Path(__file__).resolve().parent
ICONES_DIR = BASE_DIR / "assets" / "icones"

# Categoria (como aparece no titulo) -> arquivo em assets/icones/
ICONE_POR_CATEGORIA = {
    "YOUTUBE": "youtube.png",
    "PATREON": "patreon.png",
    "LINKEDIN": "linkedin.png",
    "GITHUB": "github.png",
    "DISCORD": "discord.png",
    "GUMROAD": "gumroad.png",
    "EMAIL": "email.png",
    "RESEND": "resend.png",
    "N8N": "n8n.png",
}

# GERAL, BRANDING e TUTORIAL nao sao marcas de terceiros: levam o banner do
# proprio Wingman.
BANNER_WINGMAN = "https://ai.locodev.dev/og-launch.png"
CATEGORIAS_COM_BANNER = {"GERAL", "BRANDING", "TUTORIAL"}

# 0-9 por causa de tags como [N8N]
TAG_RE = re.compile(r"\[([A-ZÀ-Ú0-9]+)\]")


def categoria_de(titulo: str) -> str | None:
    """Extrai a categoria do titulo.

    O primeiro colchete e o nome da pessoa e o segundo e a categoria, mas nem
    toda tarefa tem os dois - entao procuramos a primeira tag que conhecemos
    em vez de assumir a posicao.
    """
    conhecidas = set(ICONE_POR_CATEGORIA) | CATEGORIAS_COM_BANNER
    for tag in TAG_RE.findall(titulo.upper()):
        if tag in conhecidas:
            return tag
    return None


def listas_do_workspace(workspace_id: str) -> list[tuple[str, str]]:
    """Todas as listas do workspace, como (list_id, nome)."""
    listas = []
    for space in api.get(f"/team/{workspace_id}/space").get("spaces", []):
        for folder in api.get(f"/space/{space['id']}/folder").get("folders", []):
            for l in folder.get("lists", []):
                listas.append((l["id"], f"{folder['name']} / {l['name']}"))
        for l in api.get(f"/space/{space['id']}/list").get("lists", []):
            listas.append((l["id"], l["name"]))
    return listas


def anexos_da_tarefa(task_id: str) -> list[dict]:
    """Anexos de uma tarefa.

    Chamada a parte porque `GET /list/{id}/task` nao devolve o campo
    `attachments` - so o endpoint da tarefa individual devolve. Sem isto a
    guarda de duplicata abaixo nunca dispara e reexecutar duplica os anexos.
    """
    return api.get(f"/task/{task_id}").get("attachments") or []


def tarefas_da_lista(list_id: str) -> list[dict]:
    tarefas, pagina = [], 0
    while True:
        resp = api.get(
            f"/list/{list_id}/task",
            params={"include_closed": "true", "subtasks": "true", "page": pagina},
        )
        lote = resp.get("tasks", [])
        tarefas.extend(lote)
        if resp.get("last_page") or not lote:
            break
        pagina += 1
    return tarefas


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, help="ID do workspace (so digitos)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o plano sem executar")
    args = ap.parse_args()

    faltando = [
        f for f in set(ICONE_POR_CATEGORIA.values())
        if not (ICONES_DIR / f).is_file()
    ]
    if faltando:
        print(f"ERRO: icones ausentes em {ICONES_DIR}: {', '.join(sorted(faltando))}")
        print("Rode: pip install -r requirements-icones.txt && python gerar_icones.py")
        return 1

    enviados = pulados = 0
    sem_categoria: list[str] = []

    for list_id, nome_lista in listas_do_workspace(args.workspace):
        print(f"\n== {nome_lista}")
        for t in tarefas_da_lista(list_id):
            titulo = t.get("name", "")
            cat = categoria_de(titulo)
            if not cat:
                sem_categoria.append(titulo)
                continue

            arquivo = ICONE_POR_CATEGORIA.get(cat)
            nome_anexo = arquivo or "wingman-banner.png"

            # Ja anexado numa execucao anterior? Nao duplica.
            if any(a.get("title") == nome_anexo for a in anexos_da_tarefa(t["id"])):
                pulados += 1
                continue

            if args.dry_run:
                print(f"   [plano] {nome_anexo:20s} <- {titulo[:60]}")
                enviados += 1
                continue

            try:
                if arquivo:
                    api.upload_attachment(t["id"], ICONES_DIR / arquivo, nome_anexo)
                else:
                    import tempfile
                    import requests
                    r = requests.get(BANNER_WINGMAN, timeout=60)
                    r.raise_for_status()
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp.write(r.content)
                        tmp_path = Path(tmp.name)
                    try:
                        api.upload_attachment(t["id"], tmp_path, nome_anexo)
                    finally:
                        tmp_path.unlink(missing_ok=True)
            except Exception as exc:
                print(f"   FALHOU  {titulo[:50]}: {exc}")
                continue

            print(f"   ok      {nome_anexo:20s} -> {titulo[:60]}")
            enviados += 1

    verbo = "seriam enviados" if args.dry_run else "enviados"
    print(f"\n{enviados} anexos {verbo}, {pulados} pulados (ja tinham o anexo)")
    if sem_categoria:
        print(f"\n{len(sem_categoria)} tarefas sem categoria reconhecida:")
        for titulo in sem_categoria:
            print(f"   - {titulo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
