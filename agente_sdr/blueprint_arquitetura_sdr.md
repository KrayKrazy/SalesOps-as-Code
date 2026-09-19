# PROJETO EXECUTIVO: ARQUITETURA DE SISTEMAS SDR (NÍVEL STAFF ENGINEER)
**Status:** Blueprint de Implementação
**Escopo:** Mapeamento paramétrico e exato de cada nó no n8n e cada bloco no Dify. Nenhuma variável foi deixada ao acaso.

Este documento transcende o nível conceitual. É a planta baixa para a construção do ecossistema mais resiliente possível na atual stack de mercado.

---

## PARTE 1: N8N - ARQUITETURA DE MICROSSERVIÇOS (SUB-WORKFLOWS)
Para blindar o sistema, a execução monolítica (V4 atual) deve ser dividida em 3 workflows distintos no n8n.

### Microsserviço 1: Ingestor & Fila de Mensagens (`MS-01-Ingestion`)
**Objetivo:** Receber o webhook da Evolution, liberar a API instantaneamente e salvar na fila.

1. **Node: Webhook (Trigger)**
   - Path: `evo-inbound-v5`
   - Method: `POST`
   - Respond: `Immediately` (Garante que a Evolution não dê timeout e não reenvie a mesma mensagem).
   - Response Code: `200`
2. **Node: Code (Sanitize Input)**
   - Script:
     ```javascript
     const body = $json.body;
     if (body.key.fromMe) return []; // Ignora mensagens enviadas por nós
     return {
       remote_jid: body.key.remoteJid,
       payload: body,
       timestamp: new Date().toISOString()
     };
     ```
3. **Node: Supabase (Queue Insert)**
   - Operation: `Insert`
   - Table: `webhook_queue`
   - Data to Send:
     - `remote_jid`: `={{$json.remote_jid}}`
     - `payload`: `={{JSON.stringify($json.payload)}}`
     - `status`: `pending`

---

### Microsserviço 2: Debouncer & Roteador de Estado (`MS-02-Debounce`)
**Objetivo:** Rodar a cada 5 segundos, agrupar mensagens fragmentadas do mesmo usuário, verificar se o bot tem permissão para falar e despachar para o processamento.

1. **Node: Schedule Trigger**
   - Interval: `5 seconds`
2. **Node: Postgres/Supabase (Query Customizada)**
   - Query: 
     ```sql
     UPDATE webhook_queue 
     SET status = 'processing' 
     WHERE id IN (
         SELECT id FROM webhook_queue 
         WHERE status = 'pending' AND created_at < NOW() - INTERVAL '5 seconds'
     )
     RETURNING remote_jid, payload;
     ```
3. **Node: Code (Aggregator)**
   - Script:
     *Este nó agrupa todos os payloads que voltaram do Postgres pelo `remote_jid`.*
     ```javascript
     const grouped = {};
     for (const item of $input.all()) {
        const jid = item.json.remote_jid;
        if (!grouped[jid]) grouped[jid] = { texts: [], audios: [], instance: item.json.payload.instance };
        // Lógica de extrair texto ou base64 de áudio de item.json.payload
     }
     return Object.keys(grouped).map(k => ({ json: { remote_jid: k, data: grouped[k] } }));
     ```
4. **Node: Split In Batches** (Tamanho 1)
   - Itera sobre cada cliente agrupado.
5. **Node: Supabase (State Check)**
   - Operation: `Get Many`
   - Table: `cold_leads`
   - Column: `telefone` = `={{ $json.remote_jid.split('@')[0] }}`
6. **Node: IF (Bot Authorized?)**
   - Condition: `{{ $json.is_bot_active }} == true` OR `is empty` (Lead novo).
   - **False Branch:** `Supabase Update` marca `webhook_queue` como `ignored`.
   - **True Branch:** Aciona o `Execute Workflow Node`.
7. **Node: Execute Workflow**
   - Workflow ID: ID do `MS-03-Engine`.
   - Send Data: Payload concatenado.

---

### Microsserviço 3: Engine Híbrido (Processamento, Whisper e Dify) (`MS-03-Engine`)
**Objetivo:** O motor pesado de IA. Tem tratamento de erros nativo.

1. **Node: Execute Workflow Trigger**
2. **Node: IF (Has Audio?)**
   - Condition: `{{ $json.data.audios.length > 0 }}`
   - **True Branch:**
     3. **Node: HTTP Request (Whisper)**
        - **CONFIGURAÇÃO CRÍTICA:** Vá em `Settings` -> Habilitar `Continue On Fail`.
     4. **Node: IF (Whisper Failed?)**
        - Condition: `{{ $json.error != undefined }}`
        - Se True -> **Node: HTTP Request (Evolution Fallback)** envia: *"Opa, a conexão aqui tá ruim pra baixar áudio, me manda digitado rapidinho?"* e encerra fluxo.
        - Se False -> **Node: Code** mescla a transcrição do áudio com o array de `texts`.
3. **Node: Supabase (Upsert Memory)**
   - Cria o lead se não existir, atualiza a data de `last_interaction_at = NOW()`. Puxa o `dify_conversation_id`.
4. **Node: HTTP Request (Dify Chatflow)**
   - URL: `http://dify.kelevra.shop/v1/chat-messages`
   - **CONFIGURAÇÃO CRÍTICA (Fim do SSE):** Ao usar um Dify Chatflow, você **pode e deve** enviar `"response_mode": "blocking"`. Isso faz com que a API retorne um JSON simples com a resposta pronta. **Isso elimina completamente a necessidade do código complexo de Parseamento de Streaming do V4 antigo!**
   - Send Body:
     ```json
     {
       "inputs": { "lead_phone": "={{$json.remote_jid}}" },
       "query": "={{$json.data.texts.join(' | ')}}",
       "response_mode": "blocking",
       "conversation_id": "={{$node['Supabase Memory'].json.dify_conversation_id || ''}}"
     }
     ```
5. **Node: IF (Dify Failed?)**
   - Verifica se Dify retornou Erro 500 ou Timeout.
   - True Branch -> Atualiza `is_bot_active = false` no banco e envia webhook pro Chatwoot avisando a Gabriela.
6. **Node: IF (Handoff Tag?)**
   - Condition: A resposta do Dify contém `[HANDOFF]`?
   - True Branch -> `is_bot_active = false`.
7. **Node: HTTP Request (Responder WhatsApp)**
   - Manda a resposta final via Evolution e limpa a tag `[REUNIAO_MARCADA]` adicionando o link do Forms.

---

## PARTE 2: DIFY - ARQUITETURA DO GRAFO NEURAL (CHATFLOW)
Esqueça o "Prompt Mágico" único. Crie um aplicativo do tipo **Chatflow (Workflow)** no Dify. Isso divide o "cérebro" em áreas especializadas (Lóbulos lógicos).

### Bloco 1: Start Node
- Configurado com as variáveis de entrada exigidas: `sys.query` (a mensagem do usuário) e `lead_phone` (variável customizada).

### Bloco 2: Question Classifier (LLM Node)
**A jogada de Mestre:** Este nó **não responde ao usuário**. Ele apenas lê a mensagem e escolhe um caminho.
- **Modelo:** `gpt-4o-mini` (rápido e barato).
- **Prompt:**
  ```text
  Analise a mensagem do usuário e categorize-a estritamente em UMA destas intenções:
  1. GREETING: O usuário apenas disse Oi, Olá, Tudo bem.
  2. BANT_REPLY: O usuário falou de orçamento, dor, tempo ou respondeu uma pergunta de qualificação.
  3. OBJECTION_OR_QUESTION: O usuário fez uma pergunta técnica sobre a Kelevra ou reclamou de preço/tempo.
  4. HANDOFF_REQUEST: O usuário está irritado ou pediu expressamente para falar com um atendente humano.
  ```
- **Classes de Saída:** `GREETING`, `BANT_REPLY`, `OBJECTION_OR_QUESTION`, `HANDOFF_REQUEST`.

### Bloco 3: Roteador Lógico (IF / ELSE Node)
Conecta o *Question Classifier* a 4 caminhos diferentes baseados na classe de saída.

#### Caminho 3.1: Se = `HANDOFF_REQUEST`
- Conecta a um **Answer Node** (Texto Estático).
- Valor: `[HANDOFF] Claro, vou pedir para a Gabriela do nosso time assumir o atendimento por aqui para te dar um suporte melhor.`
- *Fim do Fluxo.*

#### Caminho 3.2: Se = `OBJECTION_OR_QUESTION`
- Conecta a um **Knowledge Retrieval Node (RAG)**.
- Base selecionada: `FAQ e Contorno de Objeções Kelevra` (O arquivo que subimos pro Git).
- O RAG extrai a resposta certa.
- Conecta a um **LLM Node Especialista em Objeção**:
  - Prompt: `Usando o contexto fornecido pelo RAG, responda a dúvida do cliente em no MÁXIMO 3 linhas. Use tom humanizado e finalize devolvendo a pergunta para a marcação da call de 5 minutos.`

#### Caminho 3.3: Se = `GREETING` ou `BANT_REPLY`
- Conecta ao **LLM Node Especialista em BANT (O Core SDR)**.
- Prompt:
  ```text
  Você é Solano, SDR Hunter da Kelevra.
  Regra 1: Siga sua tabela BANT para qualificar leads sobre o "Protocolo Presença Blindada".
  Regra 2: Nunca use bullet points. Mande 2 a 3 linhas curtas, linguajar solto de WhatsApp ("Opa", "Cara").
  Regra 3: Se o lead já confirmou interesse, ou validou a Dor/Budget, responda convidando para a call e termine a resposta EXATAMENTE com a tag: [REUNIAO_MARCADA]
  ```

### Bloco 4: O Output Guardrail (Code Node)
Todos os LLMs das rotas desembocam neste nó.
- **Ambiente:** JavaScript/Python interno do Dify.
- **Script:**
  ```javascript
  function main(args) {
      let text = args.text;
      // Remove qualquer tentativa do LLM de fazer listas (bullet points) alucinadas
      text = text.replace(/^-\s/gm, '');
      text = text.replace(/^\d+\.\s/gm, '');
      return { final_response: text.trim() };
  }
  ```

### Bloco 5: End Node
- Devolve a variável `final_response` como saída bloqueante (Blocking API Return) de volta para o n8n.

---

## 🔒 3. Considerações de Nível Arquitetural
1. **Idempotência do Webhook:** Com a Tabela de Fila (`webhook_queue`), se a Evolution tentar enviar o mesmo webhook duas vezes (por um glitch de rede), a tabela pode usar a constraint `UNIQUE(message_id)` no banco de dados para rejeitar automaticamente, garantindo que o cliente jamais receba mensagens duplicadas.
2. **Latência Invisível:** O *Debounce* de 5 segundos adiciona um *delay* de 5 segundos na resposta. Para um humano no WhatsApp, responder entre 5 a 15 segundos é a janela perfeita de simulação de "Tempo de digitação".
3. **Migração Indolor:** Esse ecossistema pode ser construído paralelamente no n8n. Você mantém seu V4 atual rodando enquanto construímos o *MS-01, MS-02 e MS-03*. Quando estiverem perfeitos, basta desligar o V4 e ligar os novos.
