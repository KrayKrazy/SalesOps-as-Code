# ROADMAP ENTERPRISE: KELEVRA SDR v2

Este documento cataloga repositórios open-source e padrões arquiteturais avançados para escalar o ecossistema Kelevra SDR. As soluções aqui mapeadas foram validadas como "Próximos Passos Ideais" para complementar a base n8n + Supabase + Dify.

## 1. O Handoff Inteligente (Chatwoot Kill-Switch)
**O Desafio:** Impedir que o robô (Dify) continue respondendo um cliente depois que um SDR humano assume a conversa no painel do Chatwoot.
**O Repositório:** `fazer-ai/n8n-nodes-chatwoot`
**A Arquitetura Proposta (MS-05):**
* Criamos o microsserviço **MS-05-Handoff** no n8n.
* Esse fluxo possui um nó *Webhook Trigger (Chatwoot)* que fica escutando em tempo real.
* Quando o humano clica em **"Assumir Conversa"** (Assign to me) no Chatwoot, o webhook dispara.
* O MS-05 pega o telefone daquele cliente e altera instantaneamente o banco de dados Supabase: `status = humano_atendendo`.
* O **MS-01 (Porteiro)**, que já consulta o Supabase antes de liberar a mensagem para a fila, passa a bloquear os clientes com esse status.
* Quando o atendimento acaba, o humano clica em "Resolver", o status volta para "limpo" e o Dify volta a operar o cliente.

## 2. Assistente Text2SQL (O Módulo de Operações)
**O Desafio:** Extrair métricas financeiras ou de performance de vendas (ex: quantos clientes pagaram hoje?) diretamente pelo WhatsApp sem precisar abrir dashboards complexos.
**A Inspiração:** `Chat with Postgresql Database` (Awesome n8n Templates).
**A Arquitetura Proposta:**
* Utilizar as *Tools* nativas do **Dify** de consulta a Banco de Dados, protegidas contra injeção de SQL (read-only).
* Criar um novo Agente Dify exclusivo para você (O Assistente do Solano).
* Quando você manda um áudio no seu WhatsApp: *"Solano Assistente, quantos leads agendaram implante hoje?"*, o Dify traduz isso para a query: `SELECT count(*) FROM webhook_queue WHERE date = today`, roda no Supabase e te responde no WhatsApp em 2 segundos: *"Chefe, tivemos 14 agendamentos hoje."*

## 3. Integração n8n ↔ Dify Otimizada
**O Desafio:** Manter dezenas de conexões manuais via HTTP Requests quando formos escalar para 10 ou 20 clientes corporativos diferentes.
**O Repositório:** `YushiYamamoto/n8n-nodes-dify`
**A Arquitetura Proposta:**
* Instalar este nó da comunidade no seu n8n. Ele simplifica visualmente a troca de mensagens, histórico (conversation_id) e upload de arquivos entre o n8n e o Dify, tornando o MS-03 ainda mais enxuto visualmente.

## 4. WhatsApp Flows Nativos via Evolution API (Inovação Futura)
**O Desafio:** Formulários de qualificação gigantes por texto fazem os clientes desistirem.
**O Padrão Arquitetural:** WhatsApp Flows nativos manipulados pela Evolution API v2.
**A Arquitetura Proposta:**
* A Evolution API v2 permite disparar e ler botões nativos, listas suspensas e formulários em tela cheia do WhatsApp (Flows).
* O Dify entende que o cliente quer agendar, então instrui o n8n a enviar um *WhatsApp Flow* (um mini-aplicativo dentro da conversa com o calendário para o cliente escolher a data).
* O cliente preenche, o n8n recebe o JSON via webhook, salva no Supabase e o Dify agradece. Conversão 300% maior que perguntas via texto.

## 5. Infraestrutura "Self-Hosted" All-in-One
**O Repositório:** `kossakovsky/n8n-install`
**A Arquitetura Proposta:**
* Caso o volume de mensagens ultrapasse 20.000 webhooks/hora, usaremos a arquitetura fornecida por este repositório para "conteinerizar" o Dify, Postgres, Redis (n8n em modo queue) na mesma máquina, zerando a latência de rede entre eles e criando uma fortaleza impenetrável de dados locais.
