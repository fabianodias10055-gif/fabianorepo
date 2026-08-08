#!/usr/bin/env python3
"""Anexa o icone da categoria em cada tarefa do board Wingman Marketing.

A categoria sai do proprio titulo, que segue o padrao "[NOME] [CATEGORIA] Tarefa".
Tarefas sem categoria conhecida sao puladas e listadas no fim.

Rodar:
    python anexar_icones.py --workspace 90171401081 --dry-run   # so mostra o plano
    python anexar_icones.py --workspace 90171401081             # executa
    python anexar_icones.py --workspace 90171401081 --incremental
        # so olha tarefas alteradas desde a ultima execucao completa

E seguro rodar de novo: tarefas que ja tem o anexo com o mesmo nome e tamanho
sao puladas. Nome igual com conteudo diferente e reportado como divergente e
NAO e substituido (a API do ClickUp nao remove anexos; a troca e manual).
"""

import argparse
import json
import re
import sys
import tempfile
import time
from itertools import groupby
from pathlib import Path

import requests

import clickup_api as api


BASE_DIR = Path(__file__).resolve().parent
ICONES_DIR = BASE_DIR / "assets" / "icones"
CURSOR_PATH = BASE_DIR / ".ultima_varredura.json"

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
    "CLICKUP": "clickup.png",
    # capcut.png vem do icone PWA oficial (512px reduzido), nao do
    # simple-icons: o pacote nao tem a marca CapCut.
    "CAPCUT": "capcut.png",
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
    return api.get_paginado(
        f"/list/{list_id}/task",
        params={"include_closed": "true", "subtasks": "true"},
    )


def tarefas_do_workspace(workspace_id: str, desde_ms: int | None = None) -> list[dict]:
    """Todas as tarefas do workspace numa unica varredura paginada.

    Usa GET /team/{id}/task, que devolve o workspace inteiro com lista e pasta
    em cada tarefa - as N chamadas por lista viram ~1 por pagina de 100.
    `desde_ms` liga o filtro date_updated_gt (varredura incremental).
    """
    params = {"include_closed": "true", "subtasks": "true"}
    if desde_ms:
        params["date_updated_gt"] = str(int(desde_ms))
    return api.get_paginado(f"/team/{workspace_id}/task", params=params)


def rotulo_da_lista(t: dict) -> str:
    """"Pasta / Lista" da tarefa; listas soltas vem com folder "hidden"."""
    pasta = (t.get("folder") or {}).get("name") or ""
    lista = (t.get("list") or {}).get("name") or "?"
    if pasta and pasta.lower() != "hidden":
        return f"{pasta} / {lista}"
    return lista


def estado_do_anexo(anexos: list[dict], nome: str, tamanho: int | None) -> str:
    """'ok' se ja existe com este nome e tamanho; 'divergente' se o nome existe
    mas o conteudo e outro (caso real: patreon.png coral com o mesmo nome do
    correto); 'ausente' se nao existe.
    """
    for a in anexos:
        if a.get("title") == nome:
            if tamanho is not None and int(a.get("size") or 0) != tamanho:
                return "divergente"
            return "ok"
    return "ausente"


class _Banner:
    """Download unico e preguicoso do banner do Wingman."""

    def __init__(self):
        self._path: Path | None = None

    def path(self) -> Path:
        if self._path is None:
            r = requests.get(BANNER_WINGMAN, timeout=60)
            r.raise_for_status()
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(r.content)
                self._path = Path(tmp.name)
        return self._path

    def limpar(self) -> None:
        if self._path is not None:
            self._path.unlink(missing_ok=True)
            self._path = None


def _ler_cursor(workspace_id: str) -> int | None:
    try:
        return json.loads(CURSOR_PATH.read_text(encoding="utf-8")).get(workspace_id)
    except (OSError, ValueError):
        return None


def _salvar_cursor(workspace_id: str, quando_ms: int) -> None:
    try:
        dados = json.loads(CURSOR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    dados[workspace_id] = quando_ms
    CURSOR_PATH.write_text(json.dumps(dados), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True, help="ID do workspace (so digitos)")
    ap.add_argument("--dry-run", action="store_true", help="mostra o plano sem executar")
    ap.add_argument(
        "--incremental",
        action="store_true",
        help="so tarefas alteradas desde a ultima execucao completa (cursor local)",
    )
    args = ap.parse_args()

    faltando = [
        f for f in set(ICONE_POR_CATEGORIA.values())
        if not (ICONES_DIR / f).is_file()
    ]
    if faltando:
        print(f"ERRO: icones ausentes em {ICONES_DIR}: {', '.join(sorted(faltando))}")
        print("Rode: pip install -r requirements-icones.txt && python gerar_icones.py")
        return 1

    cursor = _ler_cursor(args.workspace) if args.incremental else None
    if args.incremental and cursor is None:
        print("(sem cursor salvo para este workspace; fazendo varredura completa)")

    # O cursor da proxima execucao e o inicio desta: tarefas alteradas durante
    # a varredura reaparecem na proxima, em vez de caírem num vao.
    inicio_ms = int(time.time() * 1000)

    tarefas = tarefas_do_workspace(args.workspace, cursor)

    com_cat: list[tuple[dict, str]] = []
    sem_categoria: list[str] = []
    for t in tarefas:
        cat = categoria_de(t.get("name", ""))
        if cat:
            com_cat.append((t, cat))
        else:
            sem_categoria.append(t.get("name", ""))

    # A checagem de duplicata exige 1 GET por tarefa (o endpoint de listagem
    # nao traz anexos); em paralelo, a latencia se sobrepoe.
    anexos_por_tarefa = api.em_paralelo(
        lambda par: anexos_da_tarefa(par[0]["id"]), com_cat
    )

    banner = _Banner()
    plano: list[tuple[dict, str, str, Path]] = []
    pulados = 0
    divergentes: list[tuple[str, str, str]] = []
    try:
        for (t, cat), anexos in zip(com_cat, anexos_por_tarefa):
            arquivo = ICONE_POR_CATEGORIA.get(cat)
            nome_anexo = arquivo or "wingman-banner.png"
            caminho = (ICONES_DIR / arquivo) if arquivo else banner.path()
            estado = estado_do_anexo(anexos, nome_anexo, caminho.stat().st_size)
            if estado == "ok":
                pulados += 1
            elif estado == "divergente":
                divergentes.append((rotulo_da_lista(t), t.get("name", ""), nome_anexo))
            else:
                plano.append((t, rotulo_da_lista(t), nome_anexo, caminho))

        enviados = 0
        falhas = 0
        plano.sort(key=lambda item: item[1])
        if args.dry_run:
            for rot, grupo in groupby(plano, key=lambda item: item[1]):
                print(f"\n== {rot}")
                for t, _, nome_anexo, _c in grupo:
                    print(f"   [plano] {nome_anexo:20s} <- {t.get('name', '')[:60]}")
            enviados = len(plano)
        else:
            def enviar(item):
                t, _, nome_anexo, caminho = item
                try:
                    api.upload_attachment(t["id"], caminho, nome_anexo)
                    return None
                except Exception as exc:  # noqa: BLE001 - reportado por item
                    return exc

            resultados = api.em_paralelo(enviar, plano, max_workers=4)
            for rot, grupo in groupby(
                zip(plano, resultados), key=lambda par: par[0][1]
            ):
                print(f"\n== {rot}")
                for (t, _, nome_anexo, _c), erro in grupo:
                    if erro is None:
                        print(f"   ok      {nome_anexo:20s} -> {t.get('name', '')[:60]}")
                        enviados += 1
                    else:
                        print(f"   FALHOU  {t.get('name', '')[:50]}: {erro}")
                        falhas += 1
    finally:
        banner.limpar()

    verbo = "seriam enviados" if args.dry_run else "enviados"
    print(f"\n{enviados} anexos {verbo}, {pulados} pulados (ja tinham o anexo)")
    if divergentes:
        print(
            f"\n{len(divergentes)} anexos com o nome esperado mas conteudo diferente "
            "(nao substituo; a API nao remove anexos, troque pela interface):"
        )
        for rot, titulo, nome_anexo in divergentes:
            print(f"   - {nome_anexo}: {titulo[:60]}  [{rot}]")
    if sem_categoria:
        print(f"\n{len(sem_categoria)} tarefas sem categoria reconhecida:")
        for titulo in sem_categoria:
            print(f"   - {titulo}")

    if not args.dry_run and falhas == 0:
        _salvar_cursor(args.workspace, inicio_ms)
    return 0 if falhas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
