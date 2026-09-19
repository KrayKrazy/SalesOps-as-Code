# Arquitetura de Ecossistema de IA Nível Enterprise (SDR Kelevra)
**Documento de Engenharia e Análise de Resiliência**

Como um Engenheiro de Software Sênior analisando a sua infraestrutura atual, devo dizer que a base (Evolution + n8n + Dify + Supabase) é excelente e muito superior ao que 95% do mercado utiliza. No entanto, para escalar isso sem falhas (um sistema "blindado"), precisamos deixar de pensar como "criadores de automação" e passar a pensar como **Arquitetos de Sistemas Distribuídos**.

Abaixo, faço uma dissecação profunda das vulnerabilidades ocultas do nosso ecossistema atual e a arquitetura definitiva para resolver cada uma delas.

---

## 🛑 1. Vulnerabilidades Críticas Atuais (Single Points of Failure)

### A. Race Conditions (A Síndrome da "Metralhadora de Mensagens")
**O Problema:** Se um lead ansioso mandar 5 mensagens seguidas no WhatsApp em um intervalo de 3 segundos ("Oi", "Tudo bem?", "Tenho uma clínica", "Quero ajuda", "Como funciona?"), a Evolution vai disparar 5 webhooks quase simultâneos. O n8n vai abrir 5 execuções paralelas.
O que acontece hoje:
1. As 5 execuções batem no Supabase ao mesmo tempo.
2. Nenhuma delas encontra um `dify_conversation_id` ainda (pois a primeira não teve tempo de salvar).
3. O n8n dispara 5 requisições para o Dify criando **5 conversas paralelas** para o mesmo cliente. O Dify enlouquece, perde o contexto, e o cliente recebe 5 respostas dessincronizadas.
**A Solução:** Implementar um mecanismo de **Debounce / Fila**. O n8n precisa enfileirar as mensagens de um mesmo número por ~5 a 10 segundos, concatená-las em um único bloco de texto e enviar uma única requisição ao Dify.

### B. Colisão de Estado (IA vs Humano)
**O Problema:** A Gabriela (humana) entra no Chatwoot e começa a falar com o cliente. O cliente responde. O Webhook da Evolution ainda está ativo, o n8n recebe a mensagem, envia pro Dify, e a IA responde por cima da Gabriela. O cliente fica confuso falando com a IA e com o humano ao mesmo tempo.
**A Solução:** O Supabase precisa ser a **Fonte da Verdade (State Machine)**. Precisamos de uma coluna booleana `is_bot_active` na tabela `cold_leads`.
- Sempre que a Gabriela assumir no Chatwoot, um webhook do Chatwoot avisa o n8n para dar `UPDATE cold_leads SET is_bot_active = false`.
- O nó principal do n8n (Inbound) deve verificar essa flag logo após o webhook. Se `is_bot_active == false`, o fluxo morre ali mesmo. A IA é silenciada.

### C. Ausência de Circuit Breakers (Falhas em APIs Terceiras)
**O Problema:** Se a API da OpenAI (Whisper) cair, ou se o Dify der erro 500/Timeout, o nó do n8n gera um `NodeApiError`, o fluxo quebra e o cliente fica no vácuo eterno, sem resposta.
**A Solução:** Nós de `Error Trigger` e `Try/Catch` (Sub-workflows). 
- Se o Whisper falhar, em vez do fluxo quebrar, o n8n deve ter uma rota de escape que manda uma mensagem estática pro cliente: *"Opa, estou num ambiente meio barulhento agora e não consegui ouvir seu áudio. Consegue me mandar por texto?"*
- Se o Dify cair, o n8n manda para o Chatwoot: *"🚨 URGENTE: Dify fora do ar. Assuma o lead [Nome] manualmente."*

---

## 🧠 2. Reengenharia Profunda: O Agente Dify (De Prompt para Chatflow)

Hoje, o Dify funciona como um **Agente Baseado em Prompt** (ReAct). Colocamos todas as regras (BANT, Inbound, objeções) em um texto gigante. 
Para um sistema blindado de SDR, LLMs puros são imprevisíveis. Eles alucinam e saem do script.

**A Evolução (Dify Chatflow / Workflow):**
Precisamos migrar o Agente para um **Workflow do Dify** com nós lógicos:
1. **Nó Classificador de Intenção (LLM Router):** A primeira coisa que o Dify faz não é gerar uma resposta, é classificar a mensagem do cliente em categorias estritas:
   - `[QUALIFICACAO]`: O cliente está respondendo BANT.
   - `[OBJECAO_PRECO]`: O cliente reclamou de preço.
   - `[DUVIDA_TECNICA]`: O cliente quer saber como o produto funciona.
   - `[HANDOFF_HUMANO]`: O cliente quer falar com atendente, ou está irritado.
2. **Nós Especialistas:** Dependendo da rota, um LLM menor e mais rápido com um prompt *minúsculo e ultra-focado* gera a resposta.
   - Se for `[HANDOFF_HUMANO]`, o Dify simplesmente devolve a tag `[PAUSAR_BOT]`. O n8n lê isso, pausa a flag no Supabase e alerta a Gabriela.
3. **Nó de Guardrail (Filtro de Saída):** Um último nó de código simples no Dify verifica se a resposta final contém bullet points ou é maior que 300 caracteres. Se for, ele força um re-escrita curta.

---

## 🏗️ 3. A Nova Arquitetura de Workflows no n8n

Para blindar o sistema, o V4 Estável deve ser particionado em **Microsserviços**. Ter um fluxo gigante ("monolito") dificulta a manutenção e aumenta as chances de erro.

### Microsserviço 1: Ingestão e Controle de Fila (O Porteiro)
1. Webhook Evolution recebe mensagem.
2. Salva no banco de dados temporário (ou variável de cache do n8n) com o `message_id`.
3. Aguarda 8 segundos (Nó *Wait*).
4. Verifica se chegaram mais mensagens desse número. Concatena todas.
5. Verifica no Supabase: `is_bot_active == true?`. Se não, morre aqui.
6. Envia o payload concatenado para o Microsserviço 2 (Processamento) via *Execute Workflow*.

### Microsserviço 2: Processamento Multimídia e IA (O Cérebro)
1. Recebe a requisição sanitizada.
2. Possui blocos `Try/Catch` para o Áudio (Whisper) e Imagem (Visão).
3. Envia para o Dify (Chatflow).
4. Se o Dify retornar erro (timeout/502), ativa a rota de falha (Avisa no Chatwoot).
5. Se o Dify retornar sucesso, passa para o Microsserviço 3.

### Microsserviço 3: Execução e Roteamento (Os Músculos)
1. Avalia a resposta do Dify.
2. O Dify retornou a tag `[REUNIAO_MARCADA]`? Se sim, adiciona o link do Forms no texto e atualiza o Supabase (`status = agendado`).
3. O Dify retornou a tag `[HANDOFF]`? Atualiza Supabase (`is_bot_active = false`) e move no Chatwoot para a caixa da Gabriela.
4. Nó HTTP dispara a resposta final via Evolution API.

---

## 🗺️ 4. Plano de Ação e Próximos Passos (Roadmap de Evolução)

Para transformar essa teoria em realidade sem quebrar o que já funciona hoje, sugiro as seguintes fases de engenharia que posso implementar para você:

**Fase 1: Implementação da State Machine (Blindagem contra Colisão)**
- Alterar o banco no Supabase, inserindo `is_bot_active (boolean, default true)`.
- Adicionar um nó no n8n logo após o Webhook para checar essa flag.
- Configurar webhook de Handoff do Chatwoot.

**Fase 2: Implementação de Tratamento de Erros e Try/Catch**
- Refatorar o V4 Estável usando a funcionalidade de *Sub-Workflows* ou *Error Trigger* do n8n, garantindo que o Whisper ou o Dify nunca derrubem a conversa no silêncio.

**Fase 3: Migração do Dify para Chatflow (Workflow Lógico)**
- Criar a estrutura no Dify onde um "Classificador de Intenção" atua antes do gerador de texto, dividindo BANT, Objeções e Suporte.

**Fase 4: Sistema de Fila (Debounce) Anti-Spam**
- Montar a lógica de aglomeração de mensagens (concatenar 5 áudios enviados rapidamente em 1 único prompt de texto para o Dify).
