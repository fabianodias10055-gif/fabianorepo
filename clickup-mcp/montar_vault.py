#!/usr/bin/env python3
"""Monta a estrutura de pastas e notas do vault LocoDev.

Uma pasta por entidade (sistema, video) e uma nota por faceta dentro dela.
O nome da pasta vira o filtro da busca, o nome do arquivo vira a secao.

IDEMPOTENTE de proposito: nunca sobrescreve arquivo que ja existe. Rodar de
novo so cria o que falta, entao da para rodar sempre que o catalogo crescer.

Rodar:
    python montar_vault.py
    python montar_vault.py --destino "F:\\LocoDev Vault"
    python montar_vault.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path


VAULTS_ORIGEM = Path(r"C:\Users\LocoDevPC\Documents\Vaults")
DESTINO_PADRAO = Path(r"F:\LocoDev Vault")

# (slug, nome, categoria)
CATALOGO = [
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

# Videos ja conhecidos, para semear a pasta do YouTube.
VIDEOS = [
    ("2024-05-20 Rope Locomotion System", "rope",
     "https://www.youtube.com/@locodev"),
    ("2026-03-22 Obstacle Avoidance System", "obstacle-avoidance",
     "https://www.youtube.com/@locodev"),
]


def fm(campos: dict) -> str:
    """Frontmatter YAML simples, na ordem em que os campos vem."""
    linhas = ["---"]
    for k, v in campos.items():
        linhas.append(f"{k}: {v}" if v != "" else f"{k}:")
    linhas.append("---")
    return "\n".join(linhas)


def ficha(slug: str, nome: str, categoria: str) -> str:
    return f"""{fm({
        "sistema": slug, "nome": nome, "categoria": categoria,
        "faceta": "ficha", "acesso": "publico", "status": "rascunho",
        "tier": "", "video": "", "patreon": "", "arquivos": "",
    })}

# {nome}

## O que faz

<!-- Uma frase que um iniciante entende, sem jargao. -->

## Para quem e

<!-- Que tipo de jogo ou projeto precisa disso. -->

## Compatibilidade

<!-- Esta tabela responde a pergunta que mais chega. Preencha mesmo que a
     resposta seja "nao testado": nao saber e uma resposta valida, mentir nao. -->

| Item | Situacao | Observacao |
|---|---|---|
| Unreal Engine | | |
| GASP + ALS | | |
| GASP Mover | | |
| Outros plugins | | |

## Pre-requisitos

<!-- O que precisa estar no projeto antes de instalar. -->

## Onde esta

- **Video:**
- **Post no Patreon:**
- **Arquivos:**

## Licenca

<!-- Pode usar comercialmente? Precisa dar credito? Pode redistribuir? -->
"""


def logica(slug: str, nome: str) -> str:
    return f"""{fm({
        "sistema": slug, "faceta": "logica", "acesso": "publico",
        "status": "rascunho",
    })}

# {nome} - Como funciona

## A ideia em uma frase

<!-- Se voce so pudesse explicar em uma linha, o que diria. -->

## Passo a passo

1.
2.
3.

## Conceitos de Unreal envolvidos

<!-- Ex: Event Overlap, Physics Constraints, Timeline, Motion Warping.
     Serve para quem quer ENTENDER, nao so copiar. -->

## Decisoes de projeto

<!-- Por que foi feito assim e nao de outro jeito. E o que separa o seu
     conteudo de um tutorial qualquer. -->

![](media/)
"""


def setup(slug: str, nome: str) -> str:
    return f"""{fm({
        "sistema": slug, "faceta": "setup", "acesso": "publico",
        "status": "rascunho",
    })}

# {nome} - Instalacao

## Antes de comecar

- [ ] Versao da engine:
- [ ] Plugins necessarios:

## Passos

- [ ] 1.
- [ ] 2.
- [ ] 3.

## Como saber que funcionou

<!-- O teste concreto: aperte X, deve acontecer Y. -->

## Configuracoes que costumam precisar de ajuste

<!-- Valores, canais de colisao, Object Types, escalas. -->

![](media/)
"""


def erros(slug: str, nome: str) -> str:
    return f"""{fm({
        "sistema": slug, "faceta": "erros", "acesso": "publico",
        "status": "rascunho",
    })}

# {nome} - Erros comuns

<!-- ESTA e a nota que mais economiza seu tempo. Toda vez que alguem
     perguntar algo no Discord ou no YouTube e voce responder, cole aqui.
     Da proxima vez o bot responde sozinho. -->

## Sintoma:

**Causa:**

**Solucao:**

---

## Sintoma:

**Causa:**

**Solucao:**
"""


def blueprints(slug: str, nome: str) -> str:
    return f"""{fm({
        "sistema": slug, "faceta": "blueprints", "acesso": "publico",
        "status": "rascunho",
    })}

# {nome} - Inventario

## Blueprints

| Asset | Tipo | O que faz |
|---|---|---|
| | | |

## Inputs

| Acao | Tecla / botao | Onde e tratada |
|---|---|---|
| | | |

## Assets de apoio

<!-- Animacoes, curvas, data tables, materiais, sons. -->

## O que voce pode trocar sem quebrar

<!-- Onde o sistema aceita customizacao. -->
"""


FACETAS = [
    ("00 - Ficha.md", ficha),
    ("01 - Logica.md", logica),
    ("02 - Setup.md", setup),
    ("03 - Erros comuns.md", erros),
    ("04 - Blueprints.md", blueprints),
]


def video_ficha(pasta: str, sistema: str, url: str) -> str:
    return f"""{fm({
        "video": pasta, "sistema": sistema, "faceta": "ficha",
        "acesso": "publico", "status": "rascunho", "url": url,
        "publicado": pasta[:10], "views": "",
    })}

# {pasta[11:]}

## Sobre o que e

## Qual sistema ensina

[[../../../Sistemas/{sistema}/00 - Ficha|{sistema}]]

## Links citados no video

## Observacoes

<!-- Ex: post do Patreon correspondente, versao da engine usada na gravacao. -->
"""


def video_descricao(pasta: str) -> str:
    return f"""{fm({"video": pasta, "faceta": "descricao", "acesso": "publico"})}

# Descricao publicada

<!-- Cole aqui a descricao atual do YouTube. Serve de fonte para o bot e
     de historico de quando voce muda os links. -->
"""


def video_transcricao(pasta: str) -> str:
    return f"""{fm({"video": pasta, "faceta": "transcricao", "acesso": "publico"})}

# Transcricao

<!-- Gerada por yt-dlp --write-auto-sub. Formato: [mm:ss] texto.
     Esta e a nota que faz o bot citar o minuto exato do video. -->
"""


def video_comentarios(pasta: str) -> str:
    return f"""{fm({"video": pasta, "faceta": "comentarios", "acesso": "publico"})}

# Comentarios

<!-- Coletados pela YouTube Data API. E o FAQ que a audiencia escreveu.
     Comentario respondido por voce vale ouro: e resposta pronta. -->

| Quem | Comentario | Sua resposta |
|---|---|---|
| | | |
"""


VIDEO_FACETAS = [
    ("00 - Ficha.md", lambda p, s, u: video_ficha(p, s, u)),
    ("01 - Descricao.md", lambda p, s, u: video_descricao(p)),
    ("02 - Transcricao.md", lambda p, s, u: video_transcricao(p)),
    ("03 - Comentarios.md", lambda p, s, u: video_comentarios(p)),
]


def migrar_existente(slug: str, nome: str) -> dict[str, str]:
    """Puxa o conteudo que ja existe no vault antigo, se houver.

    Hoje so 2 sistemas tem nota (Ledge e Rope), com secoes 'O que faz',
    'Logica' e 'Conceitos UE5'. Aproveita em vez de deixar o autor
    reescrever do zero.
    """
    achados: dict[str, str] = {}
    candidatos = [
        VAULTS_ORIGEM / "LocoDev Negocio UE5" / "05-Systems-UE5" / f"{nome}.md",
        VAULTS_ORIGEM / "LocoDev Negocio UE5" / "05-Systems-UE5" / f"{nome} System.md",
    ]
    origem = next((c for c in candidatos if c.is_file()), None)
    if not origem:
        return achados

    texto = origem.read_text(encoding="utf-8", errors="replace")
    achados["_origem"] = str(origem)

    m = re.search(r"\*\*O que faz:\*\*\s*\n(.+?)(?=\n\*\*|\n---|\Z)", texto, re.S)
    if m:
        achados["o_que_faz"] = m.group(1).strip()

    m = re.search(r"\*\*L[oó]gica:\*\*\s*\n(.+?)(?=\n\*\*|\n---|\Z)", texto, re.S)
    if m:
        achados["logica"] = m.group(1).strip()

    m = re.search(r"\*\*Conceitos UE5:\*\*\s*\n(.+?)(?=\n\*\*|\n---|\Z)", texto, re.S)
    if m:
        achados["conceitos"] = m.group(1).strip()

    return achados


def aplicar_migracao(conteudo: str, faceta: str, dados: dict[str, str]) -> str:
    """Injeta o conteudo migrado no lugar certo do template."""
    if not dados:
        return conteudo
    origem = dados.get("_origem", "")
    nota = f"\n<!-- migrado de {origem} em 2026-08-13 -->\n"

    if faceta == "ficha" and "o_que_faz" in dados:
        conteudo = conteudo.replace(
            "## O que faz\n\n<!-- Uma frase que um iniciante entende, sem jargao. -->",
            f"## O que faz\n{nota}\n{dados['o_que_faz']}",
        )
    if faceta == "logica":
        if "logica" in dados:
            conteudo = conteudo.replace(
                "## Passo a passo\n\n1.\n2.\n3.",
                f"## Passo a passo\n{nota}\n{dados['logica']}",
            )
        if "conceitos" in dados:
            conteudo = conteudo.replace(
                "## Conceitos de Unreal envolvidos\n",
                f"## Conceitos de Unreal envolvidos\n\n{dados['conceitos']}\n",
            )
    return conteudo


def escrever(caminho: Path, conteudo: str, dry: bool, contadores: dict) -> None:
    if caminho.exists():
        contadores["pulados"] += 1
        return
    contadores["criados"] += 1
    if dry:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(conteudo, encoding="utf-8")


def indice_sistemas(destino: Path) -> str:
    linhas = [
        fm({"tags": "[locodev, sistemas, indice]"}),
        "",
        "# Sistemas UE5",
        "",
        "Uma pasta por sistema, cinco notas por pasta. Sempre a mesma anatomia:",
        "",
        "| Nota | Serve para |",
        "|---|---|",
        "| `00 - Ficha` | o que e, compatibilidade, onde estao os arquivos, licenca |",
        "| `01 - Logica` | como funciona por dentro, para quem quer entender |",
        "| `02 - Setup` | checklist de instalacao |",
        "| `03 - Erros comuns` | o FAQ tecnico, alimentado pelo suporte do dia a dia |",
        "| `04 - Blueprints` | inventario de assets, inputs e pontos de customizacao |",
        "",
        "Imagens vao em `media/` dentro da pasta do sistema.",
        "",
        "## Por onde comecar",
        "",
        "Pela demanda, nao pela ordem alfabetica. Hoje a fila e:",
        "",
        "1. **Obstacle Avoidance** - o short deu 23 mil views e nao ha uma linha escrita",
        "2. **Ledge System** - o mais perguntado no suporte",
        "3. **Rope** - pedido em aberto no Discord",
        "4. **Ziplining** e **Grapple Hook** - perguntados e sem nada",
        "5. **Weapon System** - o post que mais converteu no Patreon",
        "",
        "E dentro de cada um, comece pela **Ficha**: a tabela de compatibilidade",
        "sozinha ja responde a pergunta que mais chega.",
        "",
        "## Catalogo",
        "",
        "| Sistema | Categoria | Pasta |",
        "|---|---|---|",
    ]
    for slug, nome, cat in CATALOGO:
        linhas.append(f"| {nome} | {cat} | [[{slug}/00 - Ficha\\|{slug}]] |")
    return "\n".join(linhas) + "\n"


def indice_youtube() -> str:
    return f"""{fm({"tags": "[locodev, youtube, indice]"})}

# Videos do canal

Uma pasta por video, quatro notas por pasta:

| Nota | Serve para |
|---|---|
| `00 - Ficha` | link, data, views, qual sistema ensina |
| `01 - Descricao` | a descricao publicada no YouTube |
| `02 - Transcricao` | o texto do video com marca de tempo |
| `03 - Comentarios` | o FAQ que a audiencia escreveu |

Nome da pasta: `AAAA-MM-DD Titulo do video`. A data na frente mantem a ordem
cronologica e serve de identificador estavel.

## Como preencher a transcricao

O bot ja tem o `yt-dlp` integrado. O comando que gera o material:

```
yt-dlp --write-auto-sub --skip-download --sub-lang pt,en <url>
```

Sem transcricao, responder alguem exige abrir o video. Com ela, o bot cita
o minuto exato.
"""


def leiame(destino: Path) -> str:
    return f"""{fm({"tags": "[locodev, vault, indice]", "criado": "2026-08-13"})}

# Vault LocoDev

Base de conhecimento do ecossistema. O vault e onde voce **escreve**; a nuvem
e a copia que **responde** clientes, assinantes e qualquer pessoa com duvida,
sem voce ter que abrir o projeto no Unreal ou cacar o minuto do video.

## Estrutura

```
{destino.name}/
├── Painel/          nota gerada, mostra cobertura e lacunas
├── Sistemas/        uma pasta por sistema UE5, 5 notas cada
└── YouTube/Videos/  uma pasta por video, 4 notas cada
```

## As regras

1. **A pasta e o identificador.** O nome da pasta vira o filtro da busca.
   Renomear reorganiza a base inteira na proxima sincronizacao.
2. **Uma nota por faceta.** Nao junte setup com logica na mesma nota: a busca
   devolve a nota inteira, e voce quer devolver a resposta certa.
3. **Imagens em `media/`** dentro da pasta da entidade, referenciadas com
   caminho relativo. Elas viajam junto com o trecho na resposta.
4. **O frontmatter e lido pela maquina.** Os campos `sistema`, `faceta` e
   `acesso` viram colunas no banco. `acesso: interno` nunca sai pela porta
   publica.
5. **Nao editar a nota do Painel.** Ela e gerada; rode `painel_locodev.py`.

## Scripts

Em `fabianorepo/clickup-mcp/`:

- `montar_vault.py` cria pastas e notas que faltam (nunca sobrescreve)
- `painel_locodev.py` regenera a nota do Painel
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", default=str(DESTINO_PADRAO))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    destino = Path(args.destino)
    c = {"criados": 0, "pulados": 0, "migrados": 0}

    escrever(destino / "00 - Como funciona este vault.md", leiame(destino), args.dry_run, c)
    escrever(destino / "Sistemas" / "00 - Indice.md", indice_sistemas(destino), args.dry_run, c)
    escrever(destino / "YouTube" / "00 - Indice.md", indice_youtube(), args.dry_run, c)

    for slug, nome, categoria in CATALOGO:
        pasta = destino / "Sistemas" / slug
        dados = migrar_existente(slug, nome)
        if dados:
            c["migrados"] += 1
        for arquivo, gerador in FACETAS:
            faceta = arquivo.split(" - ")[1].replace(".md", "").split()[0].lower()
            conteudo = gerador(slug, nome, categoria) if gerador is ficha else gerador(slug, nome)
            conteudo = aplicar_migracao(conteudo, faceta, dados)
            escrever(pasta / arquivo, conteudo, args.dry_run, c)
        if not args.dry_run:
            (pasta / "media").mkdir(parents=True, exist_ok=True)
            marcador = pasta / "media" / ".gitkeep"
            if not marcador.exists():
                marcador.write_text("", encoding="utf-8")

    for nome_pasta, sistema, url in VIDEOS:
        pasta = destino / "YouTube" / "Videos" / nome_pasta
        for arquivo, gerador in VIDEO_FACETAS:
            escrever(pasta / arquivo, gerador(nome_pasta, sistema, url), args.dry_run, c)
        if not args.dry_run:
            (pasta / "media").mkdir(parents=True, exist_ok=True)

    verbo = "seriam criados" if args.dry_run else "criados"
    print(f"{c['criados']} arquivos {verbo}, {c['pulados']} pulados (ja existiam)")
    print(f"{c['migrados']} sistemas com conteudo migrado do vault antigo")
    print(f"destino: {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
