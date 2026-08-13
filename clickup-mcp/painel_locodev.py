#!/usr/bin/env python3
"""Gera a nota-painel do ecossistema LocoDev no Obsidian.

Primeira versao do Centro de Operacoes: mede o que JA da para medir hoje
(cobertura da documentacao dos sistemas, varrida direto do disco) e deixa
explicito o que ainda nao tem fonte de dados, em vez de inventar numero.

Rodar:
    python painel_locodev.py
    python painel_locodev.py --destino "F:\\LocoDev Vault\\Painel"

A nota e gerada: nao editar a mao, as mudancas somem na proxima execucao.
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path


VAULTS = Path(r"C:\Users\LocoDevPC\Documents\Vaults")
DESTINO_PADRAO = Path(r"F:\LocoDev Vault\Painel")
# Onde o montar_vault.py criou a estrutura nova. Tem prioridade sobre o vault
# antigo: se a pasta do sistema existe la, e ela que vale.
VAULT_NOVO = Path(r"F:\LocoDev Vault\Sistemas")

# As 5 facetas que um sistema documentado precisa ter. A chave e o nome curto
# que aparece no painel; os padroes casam com o nome do arquivo no vault.
FACETAS = [
    ("ficha", ("ficha", "00 -", "readme", "overview")),
    ("logica", ("logica", "lógica", "como funciona", "01 -")),
    ("setup", ("setup", "instala", "02 -")),
    ("erros", ("erro", "common_error", "troubleshoot", "faq", "03 -")),
    ("blueprints", ("blueprint", "inventario", "inventário", "04 -")),
]

# O catalogo real (42 sistemas), extraido de
# Vaults/LocoDev Blueprint Mastery/72 - Projetos e Tier System.md
CATALOGO = [
    # (slug, nome exibido, categoria)
    ("climb", "Climb", "locomocao"),
    ("crawl-locomotion", "Crawl Locomotion", "locomocao"),
    ("directional-ledge", "Directional Ledge", "locomocao"),
    ("flight", "Flight", "locomocao"),
    ("grapple-hook", "Grapple Hook", "locomocao"),
    ("hang-and-swing", "Hang and Swing", "locomocao"),
    ("ladder", "Ladder", "locomocao"),
    ("ledge-system", "Ledge System", "locomocao"),
    ("motion-matching", "Motion Matching", "locomocao"),
    ("narrow-passage", "Narrow Passage", "locomocao"),
    ("obstacle-avoidance", "Obstacle Avoidance", "locomocao"),
    ("roll-dash", "Roll Dash + Pickup Pistols", "locomocao"),
    ("root-motion", "Root Motion", "locomocao"),
    ("rope", "Rope", "locomocao"),
    ("simple-gliding", "Simple Gliding", "locomocao"),
    ("skateboard", "Skateboard", "locomocao"),
    ("spider-man", "Spider-Man", "locomocao"),
    ("swim", "Swim", "locomocao"),
    ("vault-move", "Vault", "locomocao"),
    ("wall-run", "Wall Run", "locomocao"),
    ("ziplining", "Ziplining", "locomocao"),
    ("advanced-combat-punch", "Advanced Combat Punch", "combate"),
    ("bow-and-arrow", "Bow and Arrow", "combate"),
    ("pistol", "Pistol", "combate"),
    ("sword-combo", "Sword Combo", "combate"),
    ("weapon-system", "Weapon System", "combate"),
    ("hostage", "Hostage", "interacao"),
    ("sneak-cover", "Sneak Cover", "interacao"),
    ("stealth", "Stealth", "interacao"),
    ("telekinesis", "Telekinesis", "interacao"),
]

# Demanda observada. Hoje e manual porque nenhuma pergunta e registrada;
# quando a captura existir, este dicionario sai do banco.
DEMANDA = {
    "ledge-system": 14,
    "obstacle-avoidance": 11,
    "rope": 8,
    "ziplining": 6,
    "grapple-hook": 5,
    "weapon-system": 5,
    "crawl-locomotion": 3,
    "wall-run": 3,
}

# Fontes de dado que o painel quer mostrar, e o estado real de cada uma.
# Verificado no Supabase e no codigo do bot em 2026-08-13.
INSTRUMENTACAO = [
    ("Wingman: eventos", "377.394 linhas", "ok",
     "loco_events, com o texto do prompt de cada usuario"),
    ("Wingman: diagnostico", "971.739 linhas", "ok",
     "loco_diagnostics, ETL para o PostHog a cada 3 min"),
    ("Wingman: conversas", "2.925 linhas", "ok",
     "loco_transcripts, prompt e resposta por turno"),
    ("Discord", "nada gravado", "cego",
     "pergunta sem resposta vira alerta efemero; historico so em RAM"),
    ("YouTube (LocoDev)", "0 comentarios", "cego",
     "a coleta ja roda para 12 videos de concorrentes, nunca para o seu canal"),
    ("Patreon", "2 snapshots de abril", "parcial",
     "log de eventos apaga o que passa de 90 dias"),
    ("Base de conhecimento", "curada a mao", "parcial",
     "so entra por reacao de staff; sem copia local"),
]


def achar_pasta_sistema(slug: str, nome: str) -> Path | None:
    """Procura a pasta do sistema, priorizando a estrutura nova."""
    nova = VAULT_NOVO / slug
    if nova.is_dir():
        return nova

    alvos = {slug.replace("-", " "), nome.lower()}
    for raiz in VAULTS.iterdir():
        if not raiz.is_dir() or raiz.name.startswith("."):
            continue
        for caminho in raiz.rglob("*"):
            if not caminho.is_dir():
                continue
            if "_Migration Backups" in str(caminho):
                continue
            if caminho.name.lower() in alvos:
                return caminho
    return None


def achar_nota_solta(nome: str) -> Path | None:
    """Fallback: uma unica nota com o nome do sistema, sem pasta."""
    padrao = nome.lower()
    for caminho in VAULTS.rglob("*.md"):
        if "_Migration Backups" in str(caminho):
            continue
        if caminho.stem.lower() == padrao or caminho.stem.lower() == f"{padrao} system":
            return caminho
    return None


def medir_facetas(pasta: Path | None, nota: Path | None) -> tuple[list[bool], int]:
    """Quais das 5 facetas existem, e quantos bytes de conteudo ao todo."""
    if pasta is None and nota is None:
        return [False] * len(FACETAS), 0

    arquivos = []
    if pasta is not None:
        arquivos = [p for p in pasta.rglob("*.md")]
    elif nota is not None:
        arquivos = [nota]

    tamanho = 0
    presentes = []
    por_faceta: dict[str, bool] = {}

    for p in arquivos:
        texto = p.read_text(encoding="utf-8", errors="replace")
        # Template vazio nao conta como escrito: o que vale e o conteudo do
        # autor, entao descontamos frontmatter, titulos e comentarios-guia.
        corpo = re.sub(r"^---.*?---", "", texto, count=1, flags=re.S)
        corpo = re.sub(r"<!--.*?-->", "", corpo, flags=re.S)
        corpo = re.sub(r"^\s*[#|>*\-\d.]+.*$", "", corpo, flags=re.M)
        util = len(corpo.strip())
        tamanho += util

        nome_l = p.stem.lower()
        for rotulo, padroes in FACETAS:
            if any(pat in nome_l for pat in padroes):
                por_faceta[rotulo] = por_faceta.get(rotulo, False) or util >= 80
                break

    presentes = [por_faceta.get(rotulo, False) for rotulo, _ in FACETAS]

    # Nota solta unica conta como ficha, mas so isso: nao e documentacao.
    if pasta is None and nota is not None:
        presentes = [True] + [False] * (len(FACETAS) - 1)

    return presentes, tamanho


def barra(n: int, total: int, largura: int = 5) -> str:
    cheios = round((n / total) * largura) if total else 0
    return "█" * cheios + "░" * (largura - cheios)


# Peso de cada faceta na urgencia. Ficha e erros comuns valem mais porque sao
# as que respondem sozinhas a pergunta de quem chega; blueprints e o detalhe
# que so interessa a quem ja comprou.
PESO_FACETA = {"ficha": 3, "logica": 1, "setup": 3, "erros": 2, "blueprints": 1}
PESO_TOTAL = sum(PESO_FACETA.values())


def necessidade(m: dict, demanda_max: int) -> tuple[int, str]:
    """Percentual de necessidade e o rotulo de urgencia.

    Combina duas coisas: quanto falta escrever (ponderado pelo peso de cada
    faceta) e quanta gente ja perguntou. Sistema completo da 0%, mesmo com
    demanda alta; sistema vazio e muito perguntado chega perto de 100%.
    """
    falta = sum(
        PESO_FACETA[rotulo]
        for (rotulo, _), presente in zip(FACETAS, m["facetas"])
        if not presente
    )
    lacuna = falta / PESO_TOTAL  # 0 = completo, 1 = nada escrito
    procura = (m["demanda"] / demanda_max) if demanda_max else 0

    # A demanda pesa mais que a lacuna: documentar o que ninguem pergunta
    # e menos urgente que documentar o que todo mundo pergunta.
    pct = round((lacuna * 0.4 + procura * 0.6) * 100)

    if pct >= 70:
        rotulo = "CRITICO"
    elif pct >= 40:
        rotulo = "urgente"
    elif pct >= 15:
        rotulo = "normal"
    elif pct > 0:
        rotulo = "baixa"
    else:
        rotulo = "ok"
    return pct, rotulo


def gerar() -> str:
    agora = datetime.now().strftime("%Y-%m-%d %H:%M")

    linhas = [
        "---",
        "tags: [locodev, painel, operacao, gerado]",
        f"gerado: {agora}",
        "fonte: clickup-mcp/painel_locodev.py",
        "---",
        "",
        "# Centro de Operacoes LocoDev",
        "",
        "Nota gerada a partir do disco. **Nao editar a mao**: mudancas somem na",
        "proxima execucao. Para atualizar, rode `python painel_locodev.py`.",
        "",
    ]

    # ---- cobertura ----
    medidos = []
    for slug, nome, categoria in CATALOGO:
        pasta = achar_pasta_sistema(slug, nome)
        nota = None if pasta else achar_nota_solta(nome)
        facetas, tamanho = medir_facetas(pasta, nota)
        medidos.append({
            "slug": slug, "nome": nome, "categoria": categoria,
            "facetas": facetas, "n": sum(facetas), "bytes": tamanho,
            "onde": str(pasta or nota or "").replace(str(VAULTS), "..."),
            "demanda": DEMANDA.get(slug, 0),
        })

    total_facetas = len(CATALOGO) * len(FACETAS)
    escritas = sum(m["n"] for m in medidos)
    completos = sum(1 for m in medidos if m["n"] == len(FACETAS))
    vazios = sum(1 for m in medidos if m["n"] == 0)

    linhas += [
        "## Resumo",
        "",
        f"- **Cobertura do catalogo:** {escritas} de {total_facetas} notas escritas "
        f"({escritas * 100 // total_facetas}%)",
        f"- **Sistemas completos:** {completos} de {len(CATALOGO)}",
        f"- **Sistemas sem nenhuma nota:** {vazios}",
        "",
        "---",
        "",
        "## Cobertura da documentacao",
        "",
        "Ordenada por demanda observada. Facetas: ficha, logica, setup, erros, blueprints.",
        "",
        "| Necessidade | Sistema | Cobertura | Facetas | Demanda | Onde esta |",
        "|---|---|---|---|---|---|",
    ]

    demanda_max = max((m["demanda"] for m in medidos), default=0)
    for m in medidos:
        m["pct"], m["urgencia"] = necessidade(m, demanda_max)

    medidos.sort(key=lambda m: (-m["pct"], -m["demanda"], m["nome"]))
    for m in medidos:
        marcas = "".join("+" if f else "." for f in m["facetas"])
        dem = f"{m['demanda']}x" if m["demanda"] else "-"
        onde = m["onde"] or "*nao encontrado*"
        nec = f"**{m['pct']}% {m['urgencia']}**" if m["urgencia"] == "CRITICO" else f"{m['pct']}% {m['urgencia']}"
        linhas.append(
            f"| {nec} | {m['nome']} | {barra(m['n'], len(FACETAS))} {m['n']}/5 "
            f"| `{marcas}` | {dem} | {onde} |"
        )

    criticos = [m for m in medidos if m["urgencia"] == "CRITICO"]
    urgentes = [m for m in medidos if m["urgencia"] == "urgente"]
    linhas += [
        "",
        f"**{len(criticos)} criticos** · **{len(urgentes)} urgentes** · "
        f"{len(medidos) - len(criticos) - len(urgentes)} podem esperar",
        "",
        "> A necessidade combina duas coisas: quanto falta escrever (com peso maior",
        "> para ficha e setup, que sao as que respondem sozinhas) e quanta gente ja",
        "> perguntou. Demanda pesa 60%, lacuna 40%: documentar o que ninguem pergunta",
        "> e menos urgente que documentar o que todo mundo pergunta.",
    ]

    # ---- lacunas ----
    prioridade = [m for m in medidos if m["demanda"] > 0 and m["n"] < len(FACETAS)]
    linhas += [
        "",
        "---",
        "",
        "## Lacunas priorizadas",
        "",
        "Sistemas que as pessoas perguntam e que nao tem documentacao completa.",
        "Esta e a fila de trabalho, em ordem.",
        "",
    ]
    if prioridade:
        prioridade.sort(key=lambda m: -m["pct"])
        for i, m in enumerate(prioridade, 1):
            faltando = [FACETAS[j][0] for j, f in enumerate(m["facetas"]) if not f]
            linhas.append(
                f"{i}. `{m['pct']}% {m['urgencia']}` **{m['nome']}** "
                f"({m['demanda']} perguntas) falta: {', '.join(faltando)}"
            )
    else:
        linhas.append("*Nenhuma lacuna com demanda registrada.*")

    # ---- instrumentacao ----
    linhas += [
        "",
        "---",
        "",
        "## O que ja e medido, e o que e cego",
        "",
        "Verificado no Supabase e no codigo do bot em 2026-08-13.",
        "",
        "| Fonte | Volume | Estado | Observacao |",
        "|---|---|---|---|",
    ]
    for fonte, vol, estado, obs in INSTRUMENTACAO:
        linhas.append(f"| {fonte} | {vol} | {estado} | {obs} |")

    linhas += [
        "",
        "> O produto tem telemetria de primeira; o cliente nao tem nenhuma.",
        "> Ligar os canais cegos e o que falta para este painel mostrar perguntas",
        "> de verdade em vez de so cobertura.",
        "",
        "---",
        "",
        "## O que este painel ainda nao mostra",
        "",
        "Sem fonte de dados hoje. Cada item vira uma secao quando a captura existir:",
        "",
        "- **Perguntas chegando** (quem, de onde, sobre o que): precisa gravar as",
        "  perguntas do Discord, que hoje viram alerta efemero.",
        "- **Disciplina do bot** (confianca, o que respondeu, o que calou): precisa",
        "  do log de resposta com score de similaridade.",
        "- **Comentarios do YouTube**: a coleta ja existe, nunca foi apontada para",
        "  o canal LocoDev.",
        "- **Quem esta perguntando** (assinante ou nao, historico): precisa cruzar",
        "  identidade do Discord com a base de assinantes.",
        "",
        "A demanda usada na tabela de cobertura acima ainda e **estimada a mao**.",
        "Quando a captura existir, ela passa a sair do banco.",
        "",
    ]

    return "\n".join(linhas) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default=str(DESTINO_PADRAO),
                    help="pasta onde a nota e escrita")
    args = ap.parse_args()

    if not VAULTS.is_dir():
        print(f"ERRO: vault nao encontrado em {VAULTS}")
        return 1

    destino = Path(args.destino)
    try:
        destino.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        print(f"ERRO: nao consegui criar {destino}: {exc}")
        return 1

    conteudo = gerar()
    arquivo = destino / "00 - Centro de Operacoes.md"
    arquivo.write_text(conteudo, encoding="utf-8")
    print(f"nota gerada: {arquivo} ({len(conteudo)} caracteres)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
