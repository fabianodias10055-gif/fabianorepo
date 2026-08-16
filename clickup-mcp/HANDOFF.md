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

## Trabalho em andamento (parar aqui foi deliberado)

**Colocar o compositor da Inbox nos painéis de vídeo e produto.**
O pedido do usuário: ao abrir um vídeo/produto, cada pergunta deve ter os
controles reais (Find existing answer, Draft with Claude, What is this
about?, Mark as answered, caixa de resposta, Post to YouTube/Discord), não
uma lista só de leitura.

- FEITO (commit 44fc8cf): `composerFor(qid)` devolve o compositor como
  bloco livre; `detailFor(qid)` é o invólucro de tabela. `runReply` tolera
  linha da fila ainda não montada (lazy rendering).
- FALTA: em `videoPanel()` e `productProfile()` (ambos em panel_ui.py),
  trocar a lista `.cev` de perguntas abertas por itens que, ao clicar,
  inserem `composerFor(qid)` ali mesmo. Cuidados:
  - o clique dentro de `.vdet`/`.cdet`/`.pdet` não pode fechar o painel
    (já há guardas de `closest` nos handlers delegados; siga o padrão)
  - `openId`/`closeDet()` são globais da fila; um compositor fora da fila
    não deve mexer neles (abrir na fila fecharia o do painel)
  - após responder com sucesso, o item deve sair da lista do painel
    (runReply já chama `apply()`; o painel de vídeo/produto não reage a
    isso, precisa re-renderizar ou remover o `.cev`)

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
