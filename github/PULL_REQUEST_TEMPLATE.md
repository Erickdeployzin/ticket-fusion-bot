## Descrição das Alterações

Descreva de forma clara e objetiva o que foi alterado, adicionado ou corrigido neste Pull Request.

## Tipo de Mudança

- [ ] Correção de bug (`fix`)
- [ ] Nova funcionalidade (`feat`)
- [ ] Refatoração interna sem mudança de comportamento (`refactor`)
- [ ] Atualização de documentação (`docs`)
- [ ] Testes ou infraestrutura CI/CD (`test` / `chore`)

## Impacto na Arquitetura

- [ ] Altera modelos em `src/database/schemas.py`
- [ ] Atualiza os 4 provedores de banco (`SQLite`, `MySQL`, `PostgreSQL`, `MongoDB`)
- [ ] Adiciona ou modifica `DynamicItem` / Views persistentes
- [ ] Adiciona novas variáveis de ambiente (atualizado em `.env.example` e `README.md`)

## Checklist Obrigatório

- [ ] Executei `ruff check src tests scripts` sem erros
- [ ] Executei `ruff format --check src tests scripts` sem erros
- [ ] Executei `mypy src` sem erros de tipagem
- [ ] Executei `pytest -v` e adicionei testes cobrindo as alterações
- [ ] Validei permissões e ownership nas interações do Discord