# Dossiê de Arquitetura: Kelevra SDR Enterprise

## 1. Visão Geral do Ecossistema
A arquitetura "Kelevra SDR" foi desenhada para resolver as maiores vulnerabilidades de chatbots comuns (perda de contexto, concorrência de mensagens, instabilidade de webhooks e limitações cognitivas). 

O sistema é dividido em **5 pilares tecnológicos**:
1. **Evolution API:** Interface de conexão com o WhatsApp.
2. **Supabase (PostgreSQL):** Máquina de estados, Fila de Mensagens (Queue) e Blacklist. Garante que nenhuma mensagem seja perdida se o sistema cair (Zero-Loss).
3. **n8n (Sistema Nervoso):** Orquestra os microsserviços (MS-01, MS-02, MS-03), faz o roteamento e controla o Debounce (agrupamento de mensagens).
4. **Dify (Cérebro):** Motor Cognitivo de IA (LLM/RAG). Substitui workflows complexos do n8n por uma inteligência centralizada de interpretação de texto e regras de negócio.
5. **Chatwoot:** Interface de atendimento humano (Handoff e gestão de tags/caixa de entrada).

---

## 2. Microsserviços Construídos (O que fizemos)

### MS-01: Ingestion & Firewall (O Porteiro)
* **Função:** Receber webhooks brutos da Evolution API.
* **Inteligência:** Antes de salvar no banco, ele lê o número do cliente e faz uma consulta HTTP GET (via Axios nativo no `$helpers`) na tabela `blocked_contacts` do Supabase. 
* **Resultado:** Se o cliente estiver bloqueado (ex: "pago"), o fluxo morre silenciosamente em 10ms. Se estiver limpo, o payload é higienizado e inserido na tabela `webhook_queue` com o status `pending`.

### MS-02: Debounce & Aggregation (O Maestro)
* **Função:** Resolver o problema da "metralhadora de áudios/textos" (quando o cliente manda 5 mensagens picotadas em 10 segundos).
* **Inteligência:** Roda a cada 1 minuto (Cron). Ele puxa todas as mensagens `pending` do Supabase, agrupa (concatena) os textos do mesmo número de telefone, muda o status para `processing` e despacha em um único bloco de contexto para o MS-03.

### MS-03: Delivery & Engine (O Executor)
* **Função:** Fazer a ponte entre os dados limpos, o Cérebro (Dify) e a Saída (WhatsApp).
* **Inteligência:** Recebe o texto consolidado, envia como query para a API do Dify, aguarda a resposta inteligente gerada pela IA, e dispara uma requisição HTTP POST blindada para a Evolution API enviar o texto final ao cliente.

---

## 3. Batalhas e Correções (Os Bugs Invisíveis)

Durante a montagem, o sistema sofreu de "falhas silenciosas". O webhook chegava, mas a resposta não saía. Mapeamos e destruímos 5 grandes vilões:

### 🛡️ Batalha 1: O "Text-Ghost" (Parse de JSON)
* **O Problema:** A coluna `payload` do Supabase é do tipo JSONB, mas a API REST retornava os dados como uma gigantesca string (texto). Quando o MS-02 tentava extrair `payload.message.conversation`, ele recebia `undefined`. Isso gerava uma string vazia enviada ao Dify, que rejeitava com **Erro 400 (Bad Request)**.
* **A Solução:** Injetamos um `JSON.parse(item.payload)` no nó Code do MS-02, forçando o n8n a reconhecer a string como um Objeto estruturado novamente.

### 🛡️ Batalha 2: O Sumiço da Instância (UUID vs Name)
* **O Problema:** A Evolution API exige o *Nome da Instância* (ex: "Número comercial") na URL de disparo de mensagens. Porém, o webhook de entrada só enviava o *ID da Instância* (UUID interno). O MS-02 não sabia o nome e usava um fallback antigo (`SDR_Kelevra`), gerando **Erro 404 (Not Found)** na hora de responder.
* **A Solução:** Mapeamos o UUID `5e4c1e18-b5e0-44ea-bf3a-49c9f4f86dbc` rigidamente para o nome real da instância dentro do código de agregação do MS-02.

### 🛡️ Batalha 3: O Chefão Final (Corrupção de Unicode)
* **O Problema:** Ao escrever "Número comercial" no código injetado via PowerShell, o Windows corrompia o caractere `ú` (transformando em `Nmero`). Quando o MS-03 codificava a URL, enviava um nome inexistente para a Evolution.
* **A Solução:** Substituímos os caracteres especiais pelo código de escape Unicode padrão JavaScript (`N\u00FAmero comercial`). O sistema se tornou à prova de falhas de *encoding*.

### 🛡️ Batalha 4: A Falsa Parada do n8n (Array Splitting)
* **O Problema:** Ao criar o nó "Check Blocklist" no MS-01, se o cliente *não* estivesse bloqueado, o banco retornava um Array vazio `[]`. No n8n, se um nó retorna `[]`, ele entende que não há itens para processar e **aborta o fluxo inteiro**, matando as mensagens de clientes novos.
* **A Solução:** Substituímos os nós visuais por um único nó "Code" blindado, que faz a chamada Axios (via `$helpers.httpRequest`) usando `try/catch` e sempre retorna `$input.all()` caso o array seja vazio, garantindo a passagem do fluxo.

---

## 4. Próximos Passos (Plano de Expansão)
1. **Handoff Inteligente (Chatwoot Kill-Switch):** Usar a tabela do Supabase para adicionar a flag `is_bot_active`. Quando o humano assumir no Chatwoot (via Webhook), a flag vira `false` e o MS-01 barra as requisições para a IA.
2. **Workers Assíncronos (MS-04 - Mídia):** Ativar o fluxo de processamento pesado de áudios (Whisper/Groq) e envio de imagens em paralelo à fila principal.
3. **Módulo de Operações (Text2SQL):** Criar uma ferramenta no Dify para consultar o Supabase e gerar relatórios financeiros direto no WhatsApp do gestor.
