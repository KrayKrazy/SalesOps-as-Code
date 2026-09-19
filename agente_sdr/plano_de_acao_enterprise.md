# Plano de Ação Master: Arquitetura Enterprise SDR
**Classificação:** Confidencial / Engenharia de Sistemas
**Objetivo:** Transformar o ecossistema atual em uma máquina de vendas assíncrona, tolerante a falhas (fault-tolerant), com gestão de estado estrita e roteamento neural via grafos (Dify Workflows).

Abaixo, o roteiro técnico de implementação, passo a passo, detalhado no nível de banco de dados, middleware e IA.

---

## FASE 1: Fundação de Dados e Gestão de Estado (Supabase)
O banco de dados deixa de ser apenas um "armazenador de IDs" e passa a ser o Controlador de Estado (State Machine) e a Fila de Mensagens (Message Broker).

### Passo 1.1: Alteração do Schema de Leads (State Machine)
Precisamos garantir que a IA saiba quando falar, quando calar, e em que estágio da jornada o cliente está.
**Ação Técnica (SQL a ser executado no Supabase):**
```sql
ALTER TABLE cold_leads 
ADD COLUMN is_bot_active BOOLEAN DEFAULT TRUE,
ADD COLUMN last_interaction_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
ADD COLUMN chatwoot_conversation_id INT NULL,
ADD COLUMN failed_attempts INT DEFAULT 0;
```
*Motivo:* `is_bot_active` cria o "Kill Switch" para humanos (Gabriela) assumirem. `failed_attempts` permite parar de tentar mandar mensagens se a API da Evolution der erro 404 várias vezes.

### Passo 1.2: Criação da Tabela de Fila (Debounce / Message Queue)
Para evitar a "Metralhadora de Mensagens" (várias execuções simultâneas).
**Ação Técnica (SQL):**
```sql
CREATE TABLE webhook_queue (
    id SERIAL PRIMARY KEY,
    remote_jid VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) DEFAULT 'pending', -- pending, processing, done, error
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```
*Motivo:* O n8n não vai mais responder à Evolution na hora. Ele só vai "jogar" a mensagem nessa tabela e encerrar. Isso zera o risco de sobrecarga de memória no n8n.

---

## FASE 2: Ingestão e Desacoplamento no n8n (O Middleware)
Nós vamos quebrar o seu `V4 Estável` em três microsserviços distintos (Sub-workflows).

### Passo 2.1: Microsserviço A - Ingestão (Webhook -> DB)
1. **Webhook Node:** Recebe os dados da Evolution API. Retorna HTTP 200 OK imediatamente (evita timeout na Evolution).
2. **Postgres/Supabase Insert Node:** Salva o `$json.body` inteiro na tabela `webhook_queue` com status `pending`.
3. **Fim da execução.** O fluxo morre aqui. Leva 0.1 segundos para rodar.

### Passo 2.2: Microsserviço B - Cron de Agrupamento (O Debounce Real)
1. **Schedule Trigger:** Roda a cada 10 segundos.
2. **Supabase Query:** `SELECT remote_jid, array_agg(payload) as mensagens FROM webhook_queue WHERE status = 'pending' AND created_at < NOW() - INTERVAL '8 seconds' GROUP BY remote_jid;`
   *(Explicação: Pega todas as mensagens agrupadas por usuário que chegaram há mais de 8 segundos, dando tempo do usuário terminar de digitar).*
3. **Supabase Update:** Marca esses IDs como `status = 'processing'`.
4. **Code Node (Concatenador):** Junta os áudios e textos num único array estruturado.
5. **Execute Workflow Node:** Envia o pacote limpo e agrupado para o Microsserviço C.

---

## FASE 3: Integração Bi-direcional Humana (Chatwoot Sync)
A IA e a Gabriela não podem disputar o mesmo lead. Precisamos sincronizar o estado.

### Passo 3.1: Escutando o Chatwoot
1. Criar um novo Workflow no n8n apenas para o Chatwoot: `Webhook (Chatwoot Events)`.
2. O Chatwoot emite um evento chamado `conversation_updated`.
3. **If Node:** O evento indica que a conversa foi assumida por um Agente Humano (`assignee_id != null`)?
   - **True:** Supabase Update -> `UPDATE cold_leads SET is_bot_active = false WHERE telefone = X`.
4. **If Node 2:** O evento indica que a conversa foi resolvida (`status == resolved`)?
   - **True:** Supabase Update -> `UPDATE cold_leads SET is_bot_active = true WHERE telefone = X` (O bot volta a atender futuros contatos).

---

## FASE 4: Reconstrução do Cérebro (Dify Chatflow DAG)
O Agente baseado em um "Prompt Gigante" é frágil. Vamos transformá-lo num Grafo Acíclico Direcionado (DAG) usando a interface "Chatflow" do Dify.

### Passo 4.1: O Nó Classificador (Intent Recognition)
1. **Start Node** recebe o input concatenado do n8n.
2. **Question Classifier Node (LLM):** Um nó configurado apenas para categorizar a entrada nas seguintes *labels*:
   - `[QUALIFICACAO_BANT]`: Cliente respondendo às perguntas do Solano.
   - `[OBJECAO]`: Cliente achou caro, não tem tempo, ou prefere outra agência.
   - `[SUPORTE_LIXO]`: SPAM, figurinhas aleatórias, mensagens sem sentido.
   - `[ESCALONAMENTO]`: Cliente irritado ou pedindo expressamente por um humano.

### Passo 4.2: O Roteamento Neural (IF / ELSE Branches)
1. **Branch 1 (Qualificação BANT):** Vai para o Nó LLM BANT (prompt restrito a apenas conduzir a marcação do Forms).
2. **Branch 2 (Objeção):** Vai para o Nó de Knowledge Retrieval (RAG). Puxa nosso `faq_kelevra.md` do GitHub e fornece a resposta cirúrgica, voltando para a venda.
3. **Branch 3 (Suporte Lixo):** Vai para um Nó de Código que apenas diz ao sistema para ignorar.
4. **Branch 4 (Escalonamento):** Vai para um Answer Node estático: `[HANDOFF_HUMANO] Certo, vou chamar a Gabriela da nossa equipe para te ajudar agora mesmo.`

### Passo 4.3: O Guardrail de Saída
- O output de qualquer LLM passa por um nó avaliador. Se houver Markdown quebrado, formatações de tabela ou listas numeradas (alucinação do LLM), ele filtra. Apenas texto limpo sai.

---

## FASE 5: Tratamento de Exceções e Resiliência (Sub-Workflows)
De volta ao n8n, no Microsserviço C (Processamento e Resposta).

### Passo 5.1: Fallback do Whisper (OpenAI)
1. No nó do Whisper, habilitar `Continue On Fail = True`.
2. Logo após, adicionar um nó `IF`. Whisper tem Erro?
   - **True:** Envia resposta via Evolution: *"Opa, meu WhatsApp bugou e não tô conseguindo abrir áudio agora. Manda por texto rapidinho?"*
   - **False:** Segue o fluxo normal.

### Passo 5.2: Fallback de Evolução (Envio de Mensagem)
1. No nó final `Responder WhatsApp`, habilitar `Continue On Fail = True`.
2. Se a API retornar erro de "Resource Not Found" (ex: instância caiu), o n8n deve engatilhar um alerta no Telegram/Slack da Kelevra: *"ALERTA CRÍTICO: Instância Evolution offline. Mensagem para o lead [Telefone] não entregue."*

### Passo 5.3: Tratamento de Link de Reunião
1. Se a resposta do Dify contiver `forms.kelevra.shop`, um nó do n8n (Update) imediatamente marca no Supabase o status `stage = agendado` ou `reuniao_solicitada`.

---

## 📈 Conclusão da Arquitetura
Implementar este plano leva a Kelevra de uma "automação de marketing tradicional" para uma "Infraestrutura de IA Enterprise". 

**Vantagens Finais:**
- Tolerância a falhas na OpenAI e Dify.
- Zero envio de mensagens sobrepostas ou interrupção de atendimento humano.
- Custos reduzidos de LLM (pois o Classificador usa modelos menores e mais baratos, chamando os mais potentes apenas na Qualificação).
- Base de código modular, permitindo que a Gabriela e você operem a empresa enquanto a máquina aguenta tráfego massivo.
