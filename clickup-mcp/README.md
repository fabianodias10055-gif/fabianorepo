# ClickUp MCP

Servidor MCP que dá a uma IA local controle sobre o ClickUp, falando direto com a API pública em vez de passar pelo conector oficial.

## Por Que Existe

O MCP oficial do ClickUp (`mcp.clickup.com`) tem um teto de **50 chamadas por 24 horas** no plano Free e **300** no Unlimited+, em janela deslizante. Estourar esse teto trava tudo — leitura inclusive — por quase um dia inteiro.

Este servidor usa seu token pessoal contra a API pública, onde o teto é **100 requisições por minuto** e o reset acontece em segundos. O mesmo trabalho que travava a conta por 23 horas passa a levar menos de um minuto.

## O Que Faz

47 ferramentas expostas à IA, em grupos:

**Leitura** — `listar_workspaces`, `listar_hierarquia`, `buscar_tarefas`, `buscar_por_nome`, `obter_tarefa`, `listar_membros`, `ler_comentarios`, `listar_campos`, `listar_statuses`, `listar_checklists`, `relatorio_board`, `listar_webhooks`, `ler_tempo`, `ler_audit_log`

**Tarefas** — `criar_tarefa` (com datas, subtarefa via `parent`, tags e responsáveis), `criar_tarefas_em_lote`, `editar_tarefa`, `duplicar_tarefa`, `concluir_tarefa`, `mudar_status_em_lote`, `atribuir_responsaveis`, `seguir_tarefa`, `adicionar_tag`, `remover_tag`, `criar_checklist`, `marcar_item_checklist`, `definir_campo`, `criar_dependencia`, `restaurar_tarefa`, `apagar_tarefa` (desligada por padrão)

**Comentários e anexos** — `comentar_tarefa`, `responder_comentario`, `comentar_lista`, `anexar_arquivo`, `anexar_url`

**Estrutura** — `criar_pasta`, `criar_lista`, `editar_lista`, `convidar_membro`

**Tempo e metas** — `registrar_tempo`, `criar_meta`

**Integrações** — `criar_webhook`, `apagar_webhook` (gancho para n8n), `enviar_email_resend`, `notificar_discord` (exigem as variáveis no `.env`)

**Local** — `sincronizar_vault` (espelho do board no Obsidian), `exportar_board` (JSON/CSV em `exports/`)

Toda escrita é registrada em `alteracoes.jsonl`, com snapshot antes de editar ou apagar; `restaurar_tarefa` recria a partir do snapshot. `CLICKUP_DRY_RUN=true` no `.env` faz toda escrita apenas simular.

## Requisitos

- Python 3.11+
- Uma conta ClickUp em qualquer plano, inclusive o Free
- Um token pessoal da API (`Settings > Apps > API Token`)
- Um cliente MCP local — Claude Desktop, Claude Code, Cursor ou similar

## Setup

```bash
cd clickup-mcp
pip install -r requirements.txt
cp .env.example .env
```

Abra o `.env` e cole seu token em `CLICKUP_API_TOKEN`. O `.env` já está coberto pelo `.gitignore` da raiz do repositório.

Confirme que subiu:

```bash
python server.py
```

O processo fica em silêncio aguardando o protocolo MCP no stdin — isso é o esperado. `Ctrl+C` para sair.

### Ligar ao cliente MCP

No Claude Desktop, edite `claude_desktop_config.json`:

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

Reinicie o cliente. As 47 ferramentas aparecem disponíveis.

## Anexar Ícones em Lote

Script separado que percorre o board e anexa em cada tarefa o ícone da sua categoria, lida do título no padrão `[NOME] [CATEGORIA] Tarefa`:

```bash
python anexar_icones.py --workspace SEU_WORKSPACE_ID --dry-run   # mostra o plano
python anexar_icones.py --workspace SEU_WORKSPACE_ID             # executa
```

Categorias reconhecidas: `YOUTUBE`, `PATREON`, `LINKEDIN`, `GITHUB`, `DISCORD`, `GUMROAD`, `EMAIL`, `RESEND`, `N8N` levam o ícone da marca; `GERAL`, `BRANDING` e `TUTORIAL` levam o banner do Wingman. Tarefas sem categoria conhecida são puladas e listadas no final. `--incremental` só varre o que mudou desde a última execução completa.

Rodar de novo é seguro: tarefas que já têm o anexo são puladas.

Os PNGs já vêm prontos em `assets/icones/`. Para regenerá-los a partir dos SVGs oficiais do pacote `simple-icons`:

```bash
pip install -r requirements-icones.txt
npm pack simple-icons@13 && tar -xzf simple-icons-*.tgz
python gerar_icones.py
```

## Segurança

- **O token dá acesso total à conta, sem escopo.** Trate como senha. Nunca o cole num chat, num commit ou numa issue.
- **`apagar_tarefa` vem desligada.** A API do ClickUp não tem lixeira — exclusão é definitiva. Para habilitar, ponha `CLICKUP_ALLOW_DELETE=true` no `.env`, sabendo do risco.
- **`CLICKUP_MAX_RPM` vem em 80, não 100.** A contagem do ClickUp é por token: se o mesmo token estiver em uso no Zapier ou noutro script, a folga evita que um estoure o outro.

## Limitações Conhecidas

- **Mover tarefa entre listas não está implementado.** A API v2 só faz isso através do recurso *Tasks in Multiple Lists*, que exige plano pago. Mudar de coluna dentro da mesma lista funciona normalmente via `editar_tarefa(status=...)`.
- **Criar, renomear e apagar status (colunas) não é possível.** A API pública não expõe gestão de status; isso é feito na interface do ClickUp.
- **Remover anexo não é possível.** A API permite subir, não apagar. Remoção é feita na interface.

## Verificação Manual

- Rode `python server.py` e confirme que sobe sem erro de token.
- Peça à IA "liste meus workspaces" e confirme que os IDs voltam.
- Peça "mostre a hierarquia do workspace X" e confirme spaces, folders e listas.
- Crie uma tarefa de teste pela IA e confirme que ela aparece no ClickUp.
- Confirme que `alteracoes.jsonl` ganhou uma linha para essa criação.
- Peça para apagar a tarefa de teste e confirme que a ferramenta recusa, explicando como habilitar.
- Rode `anexar_icones.py --dry-run` e confirme que o plano bate com o que você espera antes de executar de verdade.
