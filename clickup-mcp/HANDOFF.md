# Handoff: painel LocoDev

Estado em 2026-08-15, fim da sessão. Árvore limpa, tudo commitado e
empurrado em `claude/clickup-access-w6f3ry`.

## Antes de qualquer edição

Leia `MEMORY.md` do projeto (carrega sozinho). As três armadilhas que mais
custam tempo:

1. **Editou `panel.py`/`panel_ui.py`? Reinicie o watcher**, senão a página
   é reconstruída com o código antigo em memória e a mudança "não aparece":
   `Stop-ScheduledTask 'LocoDev Panel Watcher'; sleep 3; Start-ScheduledTask 'LocoDev Panel Watcher'`
2. **Scripts rodam com o Python do venv**
   (`.venv\Scripts\python.exe`), o do sistema não tem `keyring` e falha
   como se os tokens não existissem.
3. **Deploy do bot Discord vem de `origin/master`** (Railway). Mudança no
   bot = cherry-pick só dos commits do bot numa branch nova sobre
   origin/master. NUNCA merge da branch do painel: a master tem moderação
   que a branch não tem.

Nomes duplicados morderam duas vezes hoje (parâmetro `extra`, classe CSS
`prow`). Antes de criar nome novo em `panel_ui.py`, grep primeiro.

## Trabalho em andamento

Nenhum. O compositor nos painéis de vídeo e produto foi entregue em
2026-08-15 (commit afff2a6): clicar numa pergunta aberta (ou no botão
Answer) insere `composerFor(qid)` ali mesmo, com os controles reais, e o
painel se redesenha a partir de `QDATA` quando um reply ou mark conclui.
Regras que a implementação respeita e que valem para quem mexer depois:

- `openId`/`closeDet()` continuam sendo só da fila. Os handlers de
  sucesso agora fecham o detalhe da fila apenas se ele mostra a própria
  pergunta da ação (`if (openId === qid) closeDet()`).
- O bloco avançar-para-a-próxima do `runReply` só roda para replies
  vindos da fila (`fromQueue`, decidido antes do fetch).
- `busy()` conta um compositor de painel aberto como estado de edição,
  senão o reload de época o destruiria após 20s parado.
- O handler de mark chama `fillRow(row)` antes de tocar no `.pill`:
  linhas da fila são montadas sob demanda e podem não existir ainda.
- Caminho não testado de ponta a ponta: o Post real para YouTube/Discord
  a partir do painel (postaria para um cliente de verdade). Todo o resto
  foi testado ao vivo, incluindo mark/reopen com escrita no vault.

## Pendências do usuário (lembrar, não fazer por ele)

1. **Railway**: colar o Access Token novo do Patreon na variável
   `PATREON_ACCESS_TOKEN` do bot. Sem isso /top_patrons e /check_patron
   seguem cegos. O token novo está no cofre local (`patreon_api.py --status`).
2. **Catálogo**: decidir se ragdoll-physics, pickup-and-drop e
   push-and-pull viram sistemas. 54 perguntas órfãs esperam por isso.
3. **79 pagamentos recusados** no Patreon: 34 com email, 17 com Discord,
   os 3 maiores já pagaram US$600/460/278. Oferecido gerar lista com
   contato; usuário ainda não pediu.

## O que está no ar e funcionando

- Painel em 127.0.0.1:8765, telas: Home (needs attention/today/business/
  community), Inbox, Answered, Customers (CRM com status/notas/tags no
  vault em `Customers/*.md`), Sales (funil Patreon), Products (abre com
  quem espera), Videos (fila de trabalho, abre com perguntas e filtro
  `state.vid`), Links, Knowledge, Writing, Admin (saúde das integrações).
- Token de sessão persiste no cofre (`PANEL_SESSION_TOKEN`): reiniciar o
  servidor não desloga mais as abas.
- Patreon: `patreon_api.py` renova o token sozinho (margem de 1 dia);
  `collect_patreon.py` agendado 2x/dia ('LocoDev Patreon Collector').
- Bot Discord responde sozinho em 6 canais com conhecimento do vault
  (export a cada 2h -> Drive -> bot puxa a cada 1h). Aprovadas com ✅ são
  as únicas postadas literalmente.
- Toda resposta enviada grava proveniência (written_by/kept/confidence/
  waited_days) no bloco do `02 - Answered.md`.
- Links do YouTube reconstruídos: 859/863 perguntas têm permalink
  (`watch?v=<vid>&lc=<comment>`).
- Página: 3,9 MB (era 9,2). Linhas da fila montadas sob demanda
  (`fillRow`); marcas de canal em sprite; handlers delegados.

## Ideias aprovadas mas não iniciadas

- Answered com as métricas de proveniência (reuso, taxa de edição, tempo
  economizado) quando houver respostas novas suficientes para contar.
- Eliminar o `data-txt` duplicado (~400 KB) usando QDATA na busca.
- WhatsApp: usuário mandou pular. Não retomar sem ele pedir.
