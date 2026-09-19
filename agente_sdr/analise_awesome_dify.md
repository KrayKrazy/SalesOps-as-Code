# Análise de Engenharia: Repositório Awesome Dify Workflows
**Diretório Mapeado:** `kelevra-workspace/templates-upstream/Awesome-Dify-Workflow` & `Kelevra_Dify_Vault/dify-for-dsl`

Fiz um *deep dive* nos DSLs (Domain Specific Language) extraídos do projeto Awesome Dify. O que você tem nas mãos não são apenas "templates", são padrões de arquitetura de IA (*Design Patterns*) validados pela comunidade open-source. 

Abaixo, faço a engenharia reversa dos 4 padrões mais poderosos que encontrei nos seus arquivos e explico o **Passo a Passo** de como acoplá-los na arquitetura blindada que desenhamos para a Kelevra.

---

## 🔬 Padrão 1: "Deep Researcher" (O SDR Investigador)
**Arquivo de Referência:** `Deep Researcher On Dify.yml` / `DuckDuckGo + LLM.yml`

### Como Funciona no DSL:
Este workflow não responde na hora. Ele usa um padrão chamado **Iterative Search & Synthesize (RAG Dinâmico)**.
1. O LLM recebe um termo (ex: nome da empresa do lead).
2. Ele aciona um nó de busca (DuckDuckGo, Tavily, Google Search).
3. Ele entra em um `Loop Node` (Iteração), onde um Node de Web Scraper raspa o HTML/Texto dos 5 primeiros links.
4. Um LLM intermediário filtra o lixo e consolida um dossiê.
5. O LLM final responde.

### Como Acoplar no Kelevra SDR:
- **A Aplicação:** Enriquecimento de Lead em Tempo Real.
- **Implementação Técnica:** No seu n8n, antes de encaminhar a pergunta do Lead para o Dify responder, se o Lead informar o nome da empresa ("Tenho a Clínica Sorridente em Brasília"), o n8n chama este Workflow de Pesquisa em background via API HTTP.
- O Workflow vai no Google, vê a nota do Google Maps da clínica e o site deles.
- O Workflow devolve o "Dossiê" para o n8n.
- O n8n injeta esse dossiê como variável `sys_context` no Agente de Conversa. 
- **O Agente Mágico:** O bot responde *"Opa, Clínica Sorridente né? Vi aqui que vocês estão com nota 4.2 no Maps e o site de vocês tá meio lento. Cara, o Protocolo Presença Blindada resolve exatamente isso..."* (Conversão garantida, o lead entra em choque com a personalização).

---

## 🛠️ Padrão 2: Integração MCP / SSE API (O SDR Executor)
**Arquivos de Referência:** `dify-mcp-sse+Zapier MCP.yml` / `API????.yml`

### Como Funciona no DSL:
Estes templates utilizam o **Model Context Protocol (MCP)** para integrar ferramentas nativas de código. Em vez de usar requisições HTTP burras, o Dify estabelece um túnel Server-Sent Events (SSE) com um servidor de ferramentas.

### Como Acoplar no Kelevra SDR:
- **A Aplicação:** Integração ultra-baixa latência com seus CRMs (Twenty/Kommo) e Gateways (Cakto).
- **Implementação Técnica:** Se o usuário perguntar *"Solano, minha assinatura no Cakto já compensou?"*, o Dify usando a arquitetura MCP consegue rodar uma function serverless no seu Supabase, bater na API do Cakto, ler o status, e responder ao usuário sem precisar voltar para o n8n e fazer lógicas condicionais complexas. O MCP delega a "Ação" diretamente para a infraestrutura da Kelevra.

---

## 📊 Padrão 3: Text2SQL / AgentFlow (O Consultor Kelevra)
**Arquivos de Referência:** `??????Chatflow??text2sql.yml` / `AgentFlow.yml`

### Como Funciona no DSL:
O usuário não escreve SQL. O LLM recebe a estrutura (Schema) do banco de dados no Prompt do Sistema. Quando o usuário faz a pergunta, o LLM Node 1 gera uma query SQL, o HTTP Node 2 roda a query no Postgres/Supabase, e o LLM Node 3 traduz o JSON devolvido em linguagem humana.

### Como Acoplar no Kelevra SDR:
- **A Aplicação:** Painel de Inteligência (Para você e Gabriela) ou Pós-venda VIP.
- **Implementação Técnica:** Crie um número de WhatsApp "Master" só para a equipe interna.
- Você manda no WhatsApp: *"Agente, quantos leads agendaram call hoje e qual o faturamento projetado no pipeline?"*
- O Dify usa o template Text2SQL. Bate no Supabase `cold_leads`, lê os `status = agendado`, calcula as métricas, e te devolve um áudio/texto sumarizado. Tudo isso orquestrado pelos seus scripts em Node (já notei que você fez scripts `temp_medusa_db.cjs` e afins, essa arquitetura lê esses dados perfeitamente).

---

## 📄 Padrão 4: Artifact & Document Analysis (O Analista de Contratos)
**Arquivos de Referência:** `Artifact.yml` / `Document_chat_template.yml`

### Como Funciona no DSL:
O workflow aceita uploads de arquivos longos (PDFs de contratos, CSVs de planilhas). Usa um nó `Document Extractor` acoplado com um Chunking semântico para o LLM interpretar blocos do documento.

### Como Acoplar no Kelevra SDR:
- **A Aplicação:** Análise de Consultoria Empresarial (seu novo produto).
- **Implementação Técnica:** Quando você vende *Consultoria Empresarial*, o lead frequentemente tem relatórios financeiros, folhas de ponto, etc. Você pode instruir o SDR: *"Manda sua planilha de custos aí pra eu dar uma olhada"*.
- O cliente sobe o CSV no Zap. O n8n baixa, repassa o base64 para a API do Dify com esse Chatflow. O Dify analisa os custos e responde: *"Vi que seu custo com folha tá passando de 60%. O nosso mapeamento de processos via IA pode cortar isso pela metade..."*

---

## 🚀 Plano de Execução Imediata
Qualquer um destes workflows do `Awesome Dify` pode ser importado **com apenas 2 cliques** na interface do seu Dify:
1. Vá em `Studio` -> `Import DSL`.
2. Suba o arquivo YAML.
3. Troque os LLMs chineses (como Kimi ou Qwen que vêm configurados neles) para as suas chaves do `gpt-4o` ou `gemini`.

**Minha Recomendação Sênior:** 
Comece acoplando o conceito do **Deep Researcher**. Ele transforma um simples chatbot num SDR investigativo nível Wall Street. Se me der o OK, eu posso escrever o roteiro de integração de como o n8n vai buscar o nome da clínica no Google Maps (`gmb-claw`) e injetar na veia do Agente Dify para a quebra de gelo perfeita.
