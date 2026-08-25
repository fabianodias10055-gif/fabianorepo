# Regras de dados sensiveis

Este repositorio e **PUBLICO no GitHub**. Tudo o que entra num commit fica
exposto na internet para sempre, mesmo que seja removido depois: apagar um
arquivo nao apaga o historico. A unica protecao que funciona e **nunca
deixar o dado sensivel entrar**.

Estas regras sao rigidas. Vale para pessoas e para agentes de IA que
trabalham neste repo.

## O que NUNCA pode estar num arquivo rastreado pelo git

1. **Credenciais de qualquer tipo** — API keys, tokens, senhas, JWTs,
   refresh tokens, service-role keys, connection strings, webhooks com
   token na URL, chaves de descriptografia (MEGA/Drive), secrets de admin.
2. **Emails de clientes/usuarios**, nomes reais ligados a pagamento,
   valores de pagamento por pessoa, telefones, enderecos.
3. **Links de download de produtos pagos** com a chave de acesso embutida
   (ex.: `mega.nz/folder/<id>#<chave>`, Google Drive com token).
4. **Exports de producao** com dados de pessoas: listas de membros,
   snapshots de assinantes, logs com identificadores, boards exportados.
5. **Handles reais de clientes em codigo ou testes.** Use
   `example_user_1`, `Projeto Exemplo`, `cliente@example.com`.

## Onde cada coisa DEVE ficar

| Tipo de dado | Lugar certo | Nunca |
|---|---|---|
| Segredos que agem por voce (API keys, tokens, senhas) | **Windows Credential Manager**, via `python store_secret.py NOME` | `.env` versionado, codigo, docs |
| Config nao-secreta (channel ids, modelos, budgets) | `.env` (esta no `.gitignore`) e `.env.example` **so com placeholders** | valor real no `.env.example` |
| Dados de clientes (emails, assinaturas, uso) | pasta privada local: `%LOCALAPPDATA%\locodev-panel` (`secrets_store.PRIVATE_DIR`) | vault `F:\LocoDev Vault`, repo |
| Links de produto pago / chaves MEGA | pasta privada local; nunca versionar o CSV | repo (`dub_links.csv` esta gitignored) |
| Exports de board/membros/logs | `exports/`, `*.log`, `alteracoes.jsonl` (todos no `.gitignore`) | fora do padrao ignorado |

O **vault (`F:\LocoDev Vault`) nao e um lugar seguro**: ele e lido por
ferramentas, pode sincronizar, e a pagina gerada (`panel.html`) vive dentro
dele. Nada de email de cliente ou chave vai para o vault. Dado de conta vai
para a pasta privada; a pagina carrega **contagens, nunca enderecos**.

## Antes de todo commit

- `git status` e olhe cada arquivo novo. Um `.csv`, `.json`, `.jsonl`,
  `.log` novo e suspeito por padrao: confirme que nao tem dado de pessoa
  nem chave antes de adicionar.
- Se precisar de um segredo no codigo, leia-o em runtime de
  `secrets_store.get_secret(NOME)` (env primeiro, Credential Manager
  depois). Nunca escreva o valor.
- `.env.example` documenta os nomes das variaveis com placeholders
  (`pk_cole_seu_token_aqui`), nunca valores reais.

## Se um segredo vazar mesmo assim

`git rm` nao basta: o valor continua no historico publico. A unica
correcao real e **rotacionar o segredo** (gerar uma nova chave, revogar a
antiga) e, se for um link de produto, **re-gerar o link/pasta**. Rescrever
o historico (git-filter-repo) e opcional e destrutivo; a rotacao e o que
fecha o vazamento.
