# Política de Segurança

## Versões Suportadas

Apenas a versão mais recente na branch principal recebe atualizações de segurança e correções de vulnerabilidades.

| Versão | Suporte de Segurança |
| :--- | :--- |
| `1.0.x` (`main`) | Ativo |
| `< 1.0.0` | Não suportado |

---

## Como Reportar uma Vulnerabilidade

**Não abra issues públicas no GitHub para relatar falhas de segurança.**

Caso identifique qualquer vulnerabilidade no **Fusion Bot** (como escalonamento de privilégios em Views/Modals, bypass de verificação de cargos, injeção de código em transcripts HTML ou exposição de credenciais):

1. Acesse a aba **Security → Advisories → Report a vulnerability** neste repositório e envie um relatório privado.
2. Inclua no relato:
   - Descrição clara da falha e o impacto estimado;
   - Passo a passo exato para reproduzir o comportamento;
   - Logs ou trechos de código relevantes (**remova tokens, chaves Fernet e senhas de banco antes de enviar**).

Você receberá uma resposta inicial em até **48 horas** com a avaliação do problema e o prazo estimado para correção.

---

## Controles de Segurança Integrados

O projeto implementa as seguintes camadas de proteção por padrão:

* **Isolamento de Interações (`BaseOwnerView` e `PermissionService`)**: Painéis administrativos exigem validação de posse da sessão e verificação de permissão global ou por módulo antes de executar qualquer alteração.
* **Proteção contra XSS em Transcripts**: O `TranscriptService` utiliza `Jinja2` com `select_autoescape(["html", "xml"])`, neutralizando tags HTML ou scripts enviados por usuários nas mensagens do ticket.
* **Validação de Hierarquia do Discord**: Antes de adicionar ou remover cargos via botões/dropdowns personalizados, o sistema verifica se o cargo não é `@everyone`, se não é gerenciado por integração (`role.managed`) e se está abaixo do cargo mais alto do bot (`top_role`).
* **Sanitização de URLs**: Links configurados em botões, banners e thumbnails são validados para aceitar apenas esquemas `http://` ou `https://`.
* **Criptografia de Segredos**: Suporte nativo a `FERNET_KEY` (AES-128-CBC + HMAC-SHA256) para cifrar credenciais sensíveis.

---

## Boas Práticas para Administradores (Self-Hosting)

* Nunca versione o arquivo `.env` ou arquivos `.db` (SQLite) em repositórios públicos.
* Gere uma chave criptográfica exclusiva por ambiente executando `python scripts/init_db.py gen-key`.
* Conceda ao bot apenas as permissões necessárias no servidor Discord e mantenha o cargo do bot posicionado apenas acima dos cargos que ele realmente precisa gerenciar.
* Utilize conexões criptografadas (TLS/SSL) ao conectar o bot a bancos de dados externos (MySQL, PostgreSQL ou MongoDB).