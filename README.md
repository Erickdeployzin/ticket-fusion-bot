# Fusion Bot

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![discord.py 2.4+](https://img.shields.io/badge/discord.py-2.4%2B-5865F2.svg?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Pydantic v2](https://img.shields.io/badge/Pydantic-v2-E92063.svg?logo=pydantic&logoColor=white)](https://docs.pydantic.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-10B981.svg)](LICENSE)

Plataforma modular e escalável para administração de comunidades no Discord, desenvolvida em **Python 3.11+** com **discord.py (`AutoShardedBot`)**, **Pydantic v2**, arquitetura **Repository + Service Layer** e suporte nativo multi-banco de dados (**SQLite**, **MySQL/MariaDB**, **PostgreSQL** e **MongoDB**).

---

## Sumário

- [Guia Rápido de Uso (Comandos, Configurações e Menus)](#guia-rápido-de-uso-comandos-configurações-e-menus)
- [Visão Geral e Diferenciais](#visão-geral-e-diferenciais)
- [Funcionalidades Principais](#funcionalidades-principais)
  - [1. Painel Administrativo Central (`/painel`)](#1-painel-administrativo-central-painel)
  - [2. Sistema Profissional de Tickets](#2-sistema-profissional-de-tickets)
  - [3. Editor Visual de Mensagens e Componentes Interativos](#3-editor-visual-de-mensagens-e-componentes-interativos)
  - [4. Mensagens Automáticas e Agendador Persistente](#4-mensagens-automáticas-e-agendador-persistente)
---

## Guia Rápido de Uso (Comandos, Configurações e Menus)

Se você quer apenas colocar o bot no ar e configurar tudo no seu servidor Discord sem mexer em código após a instalação:

### 1. Comando Principal
* **`/painel`**: Abre o **Painel Administrativo Central** interativo para o administrador ou membro autorizado. A partir dele, você navega por todas as configurações, painéis de tickets, mensagens automáticas, logs e diagnósticos usando menus dropdown, botões e janelas modais (sem precisar decorar dezenas de comandos de texto).

### 2. Menus e Seções do `/painel`
Ao executar `/painel`, utilize o menu seletor de seções para acessar:
* **Visão Geral**: Exibe métricas do servidor (membros, ID), estado dos módulos (Tickets e Automações), tickets abertos, painéis criados, automações ativas e últimos registros administrativos, além de botões de atalho rápido (`Tickets`, `Automações`, `Permissões` e `Atualizar Dados`).
* **Cargos e Permissões**: Define cargos administrativos globais e delega acesso por módulo (como equipe de tickets e gestores de automações), mantendo a validação para dono do servidor e permissões nativas (`Administrador` / `Gerenciar Servidor`).
* **Painéis de Tickets**: Ativa ou desativa o módulo de tickets, configura padrões globais e abre o **Gerenciador de Painéis de Tickets** para criar, editar, publicar ou atualizar painéis nos canais do servidor.
* **Mensagens e Automações**: Ativa ou desativa o módulo de automações e abre o **Gerenciador de Mensagens e Automações** para montar embeds, botões, dropdowns, mensagens de entrada/saída e agendamentos.
* **Logs e Auditoria**: Visualiza os registros recentes de ações administrativas, tickets e automações e configura os canais de log por categoria.
* **Identidade Visual**: Ajusta a cor padrão (HEX) e o rodapé padrão das embeds geradas pelo painel e sistemas do bot.
* **Fuso Horário**: Define o fuso horário utilizado nas datas, horas, horários de expediente e agendamentos do servidor (ex.: `America/Sao_Paulo`).
* **Canais Padrão**: Configura categoria padrão para novos tickets, canal padrão para envio de transcripts em HTML e canal padrão para avaliações.
* **Diagnóstico do Sistema**: Consulta saúde e latência do banco de dados, status de cache/locks, latência do Gateway, shard atual, uptime e versões do ambiente.

### 3. Como Usar os Painéis de Tickets e Menus Internos
* **Abertura pelo Membro**: No canal onde o painel foi publicado, o usuário clica no **Botão Direto** ou escolhe um setor no **Dropdown de Departamentos**. Se o painel tiver perguntas pré-abertura, o bot abre um formulário (Modal) antes de criar o canal privado do ticket.
* **Controles Dentro do Canal do Ticket**:
  * **Assumir Atendimento**: Vincula o atendente responsável ao ticket.
  * **Notificar Equipe**: Alerta a equipe configurada (com proteção de cooldown contra spam de ping).
  * **Transcript HTML**: Gera e envia o histórico do atendimento em formato HTML responsivo.
  * **Fechar Ticket** / **Reabrir Ticket** / **Excluir Ticket**: Encerra o atendimento (com transcript e avaliação pós-atendimento), reabre caso necessário ou exclui o canal após confirmação.
  * **Menu de Mais Ações da Equipe**: Permite adicionar ou remover membros no canal, transferir o responsável, alterar o departamento, mudar a prioridade (`Baixa`, `Normal`, `Alta`, `Urgente`) ou renomear o canal.
* **Avaliação Pós-Atendimento**: Após o fechamento do ticket, o usuário pode selecionar de **1 a 5 estrelas** e adicionar um comentário opcional sobre o atendimento.

### 4. Como Usar o Editor de Mensagens e Agendamentos
* **Editor Visual de Mensagens**: Configure texto externo, título, descrição, cor HEX, autor, thumbnail, banner, rodapé e até 25 campos, além de botões (link, cargo, resposta efêmera ou abertura de painel de tickets) e menus dropdown. Use a pré-visualização antes de publicar ou atualizar a mensagem no canal.
* **Eventos e Agendamentos**: Configure mensagens automáticas na entrada (`on_member_join`) e saída (`on_member_remove`) de membros, ou agende envios recorrentes/únicos (`once`, `daily`, `weekly` ou `interval`) respeitando o fuso horário configurado.

---

## Visão Geral e Diferenciais

O **Fusion Bot** foi projetado para eliminar a necessidade de editar arquivos JSON/YAML manualmente ou depender de múltiplos bots desconexos. Toda a operação — desde a identidade visual até painéis de atendimento, formulários modais, botões interativos e agendamentos recorrentes — é configurada diretamente pelo Discord por meio de interfaces nativas persistentes.

* **Persistência Real Pós-Reinicialização**: Todos os botões, menus dropdown, painéis de tickets e mensagens personalizadas utilizam `discord.ui.DynamicItem` e `custom_id` determinísticos (`timeout=None`), permanecendo funcionais mesmo após reinicializações do servidor.
* **Independência de Banco de Dados**: Troque entre **SQLite**, **MySQL**, **PostgreSQL** ou **MongoDB** alterando apenas a variável `DB_BACKEND` no `.env`, sem modificar nenhuma linha de regra de negócio.
* **Preparado para Alta Escala**: Construído sobre `commands.AutoShardedBot` com travas assíncronas (`LockManager`) por recurso para evitar condições de corrida e duplicação de disparos entre shards.

---

## Funcionalidades Principais

### 1. Painel Administrativo Central (`/painel`)
* **Navegação Modular em 9 Seções**: Visão Geral, Cargos e Permissões, Painéis de Tickets, Mensagens e Automações, Logs e Auditoria, Identidade Visual, Fuso Horário, Canais Padrão e Diagnóstico do Sistema.
* **Controle de Acesso Granular (RBAC)**:
  * Proprietário do servidor e membros com permissão `Administrador` ou `Gerenciar Servidor`;
  * Cargos Administrativos Globais configuráveis;
  * Delegação granular por módulo (**Equipe de Tickets** e **Gestores de Automações**).
* **Auditoria Completa**: Registro estruturado de ações administrativas, eventos de tickets, disparos de automações e falhas operacionais tanto no banco de dados quanto em canais dedicados de log.

### 2. Sistema Profissional de Tickets
* **Múltiplos Painéis Independentes**: Crie painéis separados por finalidade (Suporte Técnico, Financeiro, Denúncias, VIP, Parcerias) com publicação e atualização *in-place* (edita a mensagem existente sem duplicar no canal).
* **Modos de Abertura Flexíveis**:
  * **Botão Direto**: Abertura imediata com texto, emoji e cor configuráveis;
  * **Dropdown de Departamentos**: Roteamento automático por setor com categorias Discord e cargos de equipe específicos por departamento.
* **Formulários Dinâmicos Pré-Abertura**: Adicione até 5 perguntas (curtas ou parágrafo, obrigatórias ou opcionais) exibidas via Modal antes da criação do canal privado.
* **Controle de Expediente e Proteção Anti-Spam**:
  * Horário de funcionamento configurável (inclusive turnos noturnos) com aviso automático de ausência;
  * Limite de tickets simultâneos por usuário e cooldown entre aberturas.
* **Controles Internos Persistentes no Canal**:
  * Assumir atendimento, notificar equipe (com cooldown anti-ping), adicionar/remover participantes, transferir responsável, alterar departamento, definir prioridade (`Baixa`, `Normal`, `Alta`, `Urgente`), renomear canal, fechar, reabrir e excluir com confirmação.
* **Transcripts Profissionais em HTML**: Exportação automática no fechamento e sob demanda em layout HTML/CSS responsivo com avatares, timestamps no fuso horário do servidor, embeds, anexos e respostas do formulário inicial.
* **Avaliação Pós-Atendimento (1 a 5 Estrelas)**: Envio automático de solicitação de nota e comentário via DM (com fallback no canal) e ranking de desempenho médio por atendente.

### 3. Editor Visual de Mensagens e Componentes Interativos
* **Construtor Completo de Embeds**: Edite conteúdo externo, título, descrição, cor HEX, autor (nome + ícone), thumbnail, banner, rodapé e até 25 campos customizados com pré-visualização efêmera antes de publicar.
* **Botões e Dropdowns Personalizados**:
  * **Estilos**: `primary` (azul), `secondary` (cinza), `success` (verde), `danger` (vermelho) e `link` (URL externa validada);
  * **Ações Nativas**: Abrir URL externa, alternar cargo (`toggle_role`), adicionar cargo (`add_role`), remover cargo (`remove_role`), enviar resposta privada (`send_ephemeral`) ou abrir diretamente um painel de tickets (`open_ticket_panel`).
* **Edição Sem Reenvio**: Mensagens estáticas e anúncios já publicados são atualizados diretamente no canal original.

### 4. Mensagens Automáticas e Agendador Persistente
* **Eventos de Membros**: Mensagens automáticas configuráveis para entrada (`on_member_join`) e saída (`on_member_remove`) de membros.
* **SchedulerEngine Resiliente**:
  * Suporta disparos únicos (`once`), diários (`daily`), semanais (`weekly`) e por intervalo em minutos (`interval`);
  * Recuperação automática de disparos pendentes após reinicializações e controle de limite máximo de execuções (`max_runs`).

---

## Arquitetura e Stack Tecnológica

| Camada | Tecnologias | Responsabilidade |
| :--- | :--- | :--- |
| **Apresentação** | `discord.py` (`AutoShardedBot`, `DynamicItem`, `Modal`, `View`) | Comandos slash, eventos do Gateway e interfaces interativas persistentes |
| **Serviços** | Python `asyncio`, `Jinja2`, `zoneinfo` | Regras de negócio, renderização de placeholders, transcripts HTML e auditoria |
| **Segurança** | `cryptography` (`Fernet`), `PermissionService`, `LockManager` | Criptografia de credenciais, validação RBAC, hierarquia de cargos e locks |
| **Dados** | `Pydantic v2`, `aiosqlite`, `aiomysql`, `asyncpg`, `motor` | Schemas unificados e repositórios assíncronos multi-banco |

---
