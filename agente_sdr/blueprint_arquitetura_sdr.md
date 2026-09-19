# PROJETO EXECUTIVO: ARQUITETURA DE SISTEMAS SDR (NÍVEL STAFF ENGINEER) - V2 (AWESOME DIFY UPDATE)
**Status:** Blueprint de Implementação
**Escopo:** Mapeamento paramétrico e exato de cada nó no n8n e cada bloco no Dify. Integra as arquiteturas avançadas do Awesome Dify (Deep Researcher, MCP, Text2SQL).

Este documento transcende o nível conceitual. É a planta baixa para a construção do ecossistema mais resiliente e avançado possível na atual stack de mercado.

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
   - **CONFIGURAÇÃO CRÍTICA (Fim do SSE):** Ao usar um Dify Chatflow, você **pode e deve** enviar `"response_mode": "blocking"`. Isso elimina completamente a necessidade do código complexo de Parseamento de Streaming do V4 antigo!
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
Dividindo o "cérebro" em áreas especializadas baseadas nos Padrões do Awesome Dify.

### Bloco 1: Start Node
- Configurado com as variáveis de entrada: `sys.query` (a mensagem do usuário) e `lead_phone`.

### Bloco 2: Question Classifier (LLM Node)
**A jogada de Mestre:** Este nó **não responde ao usuário**. Ele apenas lê a mensagem e escolhe um caminho.
- **Modelo:** `gpt-4o-mini` (rápido e barato).
- **Classes de Saída:** `GREETING`, `BANT_REPLY`, `COMPANY_MENTIONED` (Nova intenção mapeada), `OBJECTION_OR_QUESTION`, `HANDOFF_REQUEST`.

### Bloco 3: Roteador Lógico (IF / ELSE Node)

#### Caminho 3.1: Se = `HANDOFF_REQUEST`
- Conecta a um **Answer Node**: `[HANDOFF] Claro, vou pedir para a Gabriela assumir aqui.` -> *Fim do Fluxo.*

#### Caminho 3.2: Se = `OBJECTION_OR_QUESTION`
- Conecta a um **Knowledge Retrieval Node (RAG)** -> Extrai FAQ Kelevra do Git -> **LLM Node Especialista em Objeção**.

#### Caminho 3.3: Se = `COMPANY_MENTIONED` (Integração Deep Researcher)
**Esta é a mágica extraída do Awesome Dify.** Se o usuário mencionar o nome da empresa dele ("Sou da Padaria Pão Quente", "Tenho uma Clínica Sorriso"):
1. **Node: Iteration / Tool (DuckDuckGo Search):** Pesquisa o nome da empresa no DuckDuckGo.
2. **Node: Web Scraper (Jina Reader / Firecrawl):** Lê os 2 primeiros resultados e extrai o texto do site do lead.
3. **Node: LLM (Synthesizer):** Resume a estrutura da empresa do lead em uma variável `company_dossier`.
4. Envia o `company_dossier` para o **LLM Node Especialista em BANT** (Caminho 3.4).

#### Caminho 3.4: Se = `GREETING` ou `BANT_REPLY` (Chega direto, ou vindo do 3.3)
- Conecta ao **LLM Node Especialista em BANT (O Core SDR)**.
- Prompt:
  ```text
  Você é Solano, SDR Hunter da Kelevra.
  Contexto da Empresa do Lead (se houver): {{company_dossier}}
  
  Regra 1: Siga sua tabela BANT para qualificar leads sobre o "Protocolo Presença Blindada".
  Regra 2: Se tiver o contexto da empresa dele, faça "Cold Reading". Diga que analisou a presença digital deles e use isso como gancho para a dor.
  Regra 3: Nunca use bullet points. Mande 2 a 3 linhas curtas, linguajar solto de WhatsApp.
  Regra 4: Se o lead já validou a Dor/Budget, termine EXATAMENTE com: [REUNIAO_MARCADA]
  ```

### Bloco 4: O Output Guardrail (Code Node)
- **Script (Filtro anti-alucinação):**
  ```javascript
  function main(args) {
      let text = args.text;
      text = text.replace(/^-\s/gm, ''); // Remove bullet points
      return { final_response: text.trim() };
  }
  ```

### Bloco 5: End Node
- Devolve a variável `final_response` como saída bloqueante (Blocking API) para o n8n.

---

## PARTE 3: INTEGRAÇÕES AVANÇADAS (Awesome Dify Ecosystem)
Além do Workflow Inbound SDR, construíremos mais 2 Agentes/Fluxos paralelos na sua workspace do Dify baseados nos padrões raspados:

### 1. O "Assistente do Solano" (Text2SQL)
- **Objetivo:** Você mandar áudio no seu WhatsApp pessoal e a IA ler seu banco de dados.
- **Workflow:** `Start` -> `LLM (Gera SQL)` -> `HTTP Request Node (Bate na API do seu banco via PostgREST/Supabase)` -> `LLM (Traduz o JSON para Humano)`.
- **Exemplo de uso:** *"Quantas vendas de E-commerce caíram no Medusa hoje?"* -> Ele transforma em SQL, cruza as tabelas e te manda a resposta no WhatsApp.

### 2. O "Agente MCP" (Integração Direta Cakto/Medusa)
- **Objetivo:** O Dify manipular ferramentas complexas de código sem precisar passar pelo n8n.
- **Workflow:** Usando a integração MCP (Model Context Protocol) que consta no Vault `dify-mcp-sse+Zapier MCP`, podemos conectar um servidor MCP em NodeJS direto no Dify. Isso permite que o Dify cancele boletos no Cakto, estorne compras ou adicione cupons no MedusaJS usando apenas processamento nativo.

---

## 🔒 Considerações de Nível Arquitetural
1. **Idempotência do Webhook:** Com a Tabela de Fila, se a Evolution enviar o mesmo webhook duas vezes, o Supabase rejeita via `UNIQUE(message_id)`.
2. **Personalização Absoluta:** O uso do Deep Researcher no fluxo SDR aumenta a conversão brutalmente porque o Agente prova que "conhece" a empresa do cara antes de tentar vender.
3. **Migração Indolor:** Esse ecossistema pode ser construído paralelamente no n8n. Você mantém seu V4 atual rodando enquanto construímos as Fases MS-01, MS-02 e MS-03. Quando estiverem perfeitos, basta desligar o V4.
