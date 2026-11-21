# Changelog

Todas as alterações notáveis deste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [Unreleased]

### Planejado
- Exportação de relatórios administrativos em CSV/JSON diretamente pelo `/painel`.
- Suporte a webhooks externos para notificações de auditoria.

---

## [1.0.0] - 2026-11-21

### Adicionado
- **Arquitetura Core e Escalabilidade**:
  - Cliente principal baseado em `commands.AutoShardedBot` com encerramento gracioso (`graceful shutdown`).
  - Gerenciador de travas assíncronas com TTL (`LockManager`) para prevenção de condições de corrida entre shards e cliques simultâneos.
  - Criptografia simétrica (`CryptoManager` com Fernet AES-128-CBC + HMAC-SHA256) para proteção de credenciais sensíveis.
  - Controle de acesso baseado em cargos e permissões (`PermissionService`) com hierarquia global e por módulo.
- **Persistência Multi-Banco de Dados**:
  - Camada de abstração `IDatabaseProvider` com modelos validados em **Pydantic v2**.
  - Suporte nativo e intercambiável via `.env` para **SQLite** (`aiosqlite`), **MySQL/MariaDB** (`aiomysql`), **PostgreSQL** (`asyncpg`) e **MongoDB** (`motor`).
  - Utilitário CLI (`scripts/init_db.py`) para criação de schemas/índices (`init`), diagnóstico (`health`) e geração de chaves (`gen-key`).
- **Painel Administrativo Central (`/painel`)**:
  - Interface visual modular organizada em 9 seções: Visão Geral, Cargos e Permissões, Painéis de Tickets, Mensagens e Automações, Logs e Auditoria, Identidade Visual, Fuso Horário, Canais Padrão e Diagnóstico.
- **Sistema Profissional de Tickets**:
  - Criação e publicação de múltiplos painéis independentes com atualização *in-place* (sem duplicar mensagens).
  - Abertura via botão direto ou menu dropdown com roteamento por departamentos, categorias e cargos específicos.
  - Formulários dinâmicos pré-abertura (até 5 perguntas via Modal), controle de horário de expediente, limite simultâneo por usuário e cooldown.
  - Controles internos persistentes: assumir atendimento, notificar equipe com proteção anti-spam, adicionar/remover membros, transferir responsável, alterar departamento/prioridade, renomear canal, fechar, reabrir e excluir.
  - Geração automática e sob demanda de transcripts em **HTML/CSS responsivo** (`Jinja2` com autoescape).
  - Sistema de avaliação pós-atendimento (1 a 5 estrelas com comentário) e ranking de desempenho por atendente.
- **Editor Visual de Mensagens e Componentes Persistentes**:
  - Construtor completo de embeds (título, descrição, cor HEX, autor, thumbnail, banner, rodapé e até 25 campos) com pré-visualização efêmera.
  - Motor extensível de variáveis dinâmicas (`{user}`, `{username}`, `{user_id}`, `{server}`, `{member_count}`, `{date}`, `{time}`, `{created_at}`).
  - Botões e menus dropdown personalizados (`DynamicItem`) 100% persistentes pós-reinicialização com ações de link, atribuição/remoção de cargos, respostas efêmeras e abertura de painéis de tickets.
- **Mensagens Automáticas e Agendador Resiliente**:
  - Disparos automáticos de boas-vindas (`on_member_join`) e despedida (`on_member_remove`).
  - `SchedulerEngine` assíncrono persistente com suporte a agendamentos únicos (`once`), diários (`daily`), semanais (`weekly`) e por intervalo (`interval`), com recuperação automática após reinicializações.
- **Qualidade, Testes e CI/CD**:
  - Suíte de testes automatizados assíncronos com `pytest` e `pytest-asyncio`.
  - Pipeline no GitHub Actions executando `ruff` (lint/format), `mypy` (tipagem estática) e `pytest` em Python 3.11 e 3.12.