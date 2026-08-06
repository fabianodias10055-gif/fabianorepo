# Handoff — continuar numa sessão local

Documento para retomar este trabalho numa sessão do Claude Code rodando **na sua máquina**. Pode apagar depois que terminar.

## Por que sair da sessão remota

A sessão que criou este código roda num container remoto cujo proxy **bloqueia `api.clickup.com`** (403 no CONNECT). Confirmado por teste. Isso significa que o assistente remoto escreveu o código mas nunca conseguiu executá-lo contra a API real.

Na sua máquina não há esse bloqueio. Por isso o passo final tem que ser local.

## O problema original

Anexar um ícone de categoria em cada tarefa do board *Wingman Marketing*. O conector MCP oficial do ClickUp travou no meio: teto de **50 chamadas/24h** no plano Free, janela deslizante. Sobraram 21 anexos pendentes.

Este projeto troca o conector oficial pela API pública (**100 req/min**, reset em segundos), o que resolve o teto de vez.

## Estado atual

**Feito:**

- 25 tarefas renomeadas para o padrão `[NOME] [CATEGORIA] Tarefa`
- Colunas do board reduzidas a `pendente` / `em progresso` / `concluído` (feito na interface pelo usuário)
- Servidor MCP completo, 12 ferramentas, testado até onde dava sem API
- 7 ícones renderizados dos SVGs oficiais do `simple-icons` e conferidos visualmente

**Pendente:**

| O quê | Onde |
|---|---|
| 21 anexos de ícone | Rodar `anexar_icones.py` |
| Apagar `patreon.png` coral (versão errada) | Interface do ClickUp, tarefa `86e2j58gv` |
| Decidir se apaga a tarefa `[TEMP]` | Interface, tarefa `86e2nth2r` |
| Ligar o MCP a um cliente local | Config do Claude Desktop / Cursor |

Duas tarefas **já têm** anexo e serão puladas pelo script: `86e2j588h` (youtube.png, correto) e `86e2j58gv` (patreon.png coral, **errado** — o script não substitui, só pula; a troca é manual).

## Passo a passo

```bash
git clone <repo> && cd fabianorepo
git checkout claude/clickup-access-w6f3ry
cd clickup-mcp

pip install -r requirements.txt
cp .env.example .env
```

Cole o token em `.env` (`CLICKUP_API_TOKEN`). Pegue em **ClickUp → sua foto → Settings → Apps → API Token**. Começa com `pk_`.

```bash
# 1. Ver o plano sem tocar em nada
python anexar_icones.py --workspace 90171401081 --dry-run

# 2. Se o plano bater, executar
python anexar_icones.py --workspace 90171401081
```

Esperado no dry-run: **21 anexos a enviar, 2 pulados, 1 tarefa sem categoria** (a `[TEMP]`, correto).

Distribuição esperada: 13 YouTube, 3 Patreon, 2 LinkedIn, 1 cada de GitHub, Discord, Gumroad, Email, e o banner do Wingman em GERAL e BRANDING.

## IDs úteis

| Item | ID |
|---|---|
| Workspace | `90171401081` |
| Space "Espaço da equipe" | `90176466020` |
| Folder "Wingman Marketing" | `901710208789` |
| Lista "1. Setup (Tarefas Únicas)" | `901715660069` |
| Lista "2. Rotina (Recorrentes)" | `901715660070` |
| Listas 3 e 4 (vazias) | `901715660076`, `901715660078` |
| Único membro do workspace | Fabiano Dias, `222296667` |

O Anderson **não está no workspace** — enquanto não for convidado pela interface, não dá para atribuí-lo como responsável. Por isso o nome dele vive no título das tarefas, não no campo Responsáveis.

## Ligar o MCP ao cliente

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "clickup": {
      "command": "python",
      "args": ["/caminho/absoluto/para/clickup-mcp/server.py"]
    }
  }
}
```

Reinicie o cliente. Peça "liste meus workspaces" para confirmar.

## Armadilhas conhecidas

- **O token não tem escopo.** Acesso total à conta, incluindo apagar. Nunca cole num chat, commit ou issue. O `.env` já está no `.gitignore`.
- **`apagar_tarefa` vem desligada.** A API do ClickUp não tem lixeira. Só ligue (`CLICKUP_ALLOW_DELETE=true`) se souber o que está fazendo.
- **`CLICKUP_MAX_RPM=80`, não 100.** A contagem é por token; se o mesmo token estiver no Zapier ou noutro script, a folga evita estouro cruzado.
- **A API não remove anexos nem gerencia status/colunas.** Ambos são só na interface.
- **Mover tarefa entre listas** exige o recurso *Tasks in Multiple Lists*, de plano pago. Trocar de coluna dentro da mesma lista funciona por `editar_tarefa(status=...)`.
- **Se o MCP oficial ainda estiver travado**, não é problema: este script não usa o MCP oficial. São caminhos independentes.

## O que não foi verificado

Nenhuma chamada real à API do ClickUp foi executada a partir deste código — o proxy da sessão remota impediu. Foram testados: registro das 12 ferramentas no protocolo MCP, o rate limiter (bloqueio na chamada além do teto), a extração de categoria contra os 25 títulos reais, a guarda de exclusão e o erro de token ausente.

**O primeiro `--dry-run` na sua máquina é o primeiro contato real com a API.** Se algo estiver errado nos endpoints, é ali que vai aparecer — por isso rode o dry-run antes.
