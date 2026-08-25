# Instrucoes do projeto

## REGRA RIGIDA: dados sensiveis (leia SECURITY.md)

Este repositorio e **PUBLICO no GitHub**. Um commit expoe o dado para
sempre; remover depois nao apaga o historico. A regra completa esta em
[SECURITY.md](SECURITY.md) e e obrigatoria.

Resumo do que **NUNCA** pode entrar num arquivo rastreado pelo git:
- Credenciais: API keys, tokens, senhas, JWTs, service-role keys, webhooks
  com token, chaves de descriptografia (MEGA/Drive), admin secrets.
- Emails/nomes de clientes, valores de pagamento por pessoa, telefones.
- Links de produto pago com chave embutida.
- Exports de producao com dados de pessoas (membros, assinantes, logs, boards).
- Handles reais de clientes em codigo ou testes (use `example_user_N`).

Onde cada coisa vai:
- **Segredos** -> Windows Credential Manager, via `python store_secret.py NOME`;
  no codigo, leia com `secrets_store.get_secret(NOME)`, nunca o valor cru.
- **Config nao-secreta** -> `.env` (gitignored); `.env.example` so com placeholders.
- **Dados de clientes** (emails, uso, assinaturas) -> pasta privada local
  `%LOCALAPPDATA%\locodev-panel` (`secrets_store.PRIVATE_DIR`).
- **O vault `F:\LocoDev Vault` NAO e seguro**: sincroniza, e lido por
  ferramentas, e a `panel.html` vive nele. Nada de email de cliente ou
  chave no vault; a pagina carrega contagens, nunca enderecos.

Antes de todo commit: `git status` e olhe cada arquivo novo. Um `.csv`,
`.json`, `.jsonl` ou `.log` novo e suspeito por padrao -- confirme que nao
carrega dado de pessoa nem chave antes de `git add`.
