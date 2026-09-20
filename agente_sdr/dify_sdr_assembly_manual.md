# MANUAL DE MONTAGEM: DIFY SDR CHATFLOW
**Modo do Aplicativo:** Chatflow (Workflow de Conversa Avançado)
**Objetivo:** Construir o grafo neural copiando e colando os prompts e códigos desta documentação para a interface visual do Dify Studio.

---

## 1. NÓ DE ENTRADA (Start)
Adicione as variáveis de contexto que o n8n vai enviar para o Dify.
- **Variável 1:** `lead_phone` (Tipo: String) - Para sabermos com qual número estamos falando (útil para logs e pesquisas).

---

## 2. NÓ CLASSIFICADOR DE PERGUNTAS (Question Classifier)
Em vez de usar um LLM cru, o Dify possui um nó nativo chamado **Question Classifier**. Conecte a saída do `Start` nele.
- **Modelo de IA:** `gpt-4o-mini` ou `flash` (precisa ser rápido e barato).
- **Entrada (Input):** `sys.query` (Mensagem do usuário)
- **Classes de Intenção (Crie 4 rotas exatas):**
  1. `GREETING_OR_BANT`: O usuário disse Oi, está respondendo perguntas sobre a empresa dele, dor ou orçamento.
  2. `COMPANY_MENTION`: O usuário mencionou o NOME explícito da própria empresa, padaria, clínica ou site (Ex: "Sou da Padaria Pão Quente", "Minha clínica Sorriso").
  3. `OBJECTION`: O usuário está questionando o preço, querendo saber mais detalhes técnicos ou falando que "tá caro".
  4. `HANDOFF`: O usuário quer cancelar, pediu pra falar com um humano, ou está muito irritado.

*(O nó criará automaticamente 4 saídas visuais no seu painel).*

---

## 3. AS 4 ROTAS (O que conectar em cada saída)

### 🔴 Rota 4 (HANDOFF)
Conecte direto em um **Answer Node** (Nó de Resposta).
- **Conteúdo:** `[HANDOFF] Claro, entendo perfeitamente. Vou transferir você para a Gabriela do nosso time assumir o atendimento por aqui, um instante.`
- Conecte ao **End Node**.

### 🟡 Rota 3 (OBJECTION)
1. Conecte a um **Knowledge Retrieval Node**.
   - Selecione a Base de Conhecimento RAG do seu Git (`faq_kelevra` / `produtos_e_servicos`).
2. Conecte a um **LLM Node**.
   - **Contexto:** Variável gerada pelo Knowledge Retrieval.
   - **Prompt:** `Use o contexto fornecido para matar a objeção do lead em no MÁXIMO 3 linhas. Fale de forma amigável e descontraída (use 'Opa', 'Cara'). Termine devolvendo a pergunta de BANT ou chamando para a call de 5 min.`

### 🔵 Rota 2 (COMPANY_MENTION - O "Deep Researcher")
1. Conecte a um **Tool Node (DuckDuckGo / Google Search)**.
   - **Query:** `sys.query` + " empresa"
2. Conecte a um **Web Scraper Node** (Jina Reader, Firecrawl ou WebReader nativo).
   - Extrai o texto do primeiro link encontrado.
3. Conecte ao **LLM Especialista SDR** (Abaixo).

### 🟢 Rota 1 (GREETING_OR_BANT)
Conecte diretamente ao **LLM Especialista SDR** (Abaixo).

---

## 4. O CÉREBRO: LLM Especialista SDR (O Vendedor)
Tanto a Rota 1 quanto a Rota 2 terminam neste nó. Este é o core do seu agente.
- **Modelo:** `gpt-4o` ou equivalente forte de raciocínio.
- **Contexto (Se vier da Rota 2):** Injetar o output do Web Scraper.
- **System Prompt (Copie e Cole):**

```text
Você é Solano, SDR Hunter da Kelevra Corp. Seu objetivo é qualificar o lead usando BANT sutil e levá-lo para uma call de 5 minutos.

# Regras de Ouro
1. SEJA HUMANO: Use "Opa", "Cara", aja como um brasileiro profissional mas descontraído.
2. PROIBIDO: NUNCA use tópicos com pontos (bullet points), listas numeradas ou formatação robótica de IA. Escreva textos corridos de no máximo 3 a 4 linhas.
3. PESQUISA (COLD READING): Se você receber contexto do site/pesquisa do lead, cite isso casualmente! (Ex: "Dei uma olhada rápida no site da sua clínica, vi que vocês tem estrutura premium, mas...")
4. UMA PERGUNTA POR VEZ: Nunca faça duas perguntas BANT na mesma mensagem.

# Objetivo Final
Se o lead já validou que tem dor (Ex: sofre com No-Show) e concordou com o serviço, responda confirmando e adicione EXATAMENTE esta tag no final da mensagem para liberar a agenda:
[REUNIAO_MARCADA]
```

---

## 5. NÓ DE CÓDIGO (A Focinheira / Guardrail Anti-Lista)
Conecte o "LLM Especialista SDR" e o "LLM de Objeção" neste nó.
- **Tipo:** Code Node (NodeJS / JavaScript)
- **Variável de Entrada:** `text` (O output gerado pelos LLMs).
- **Código a Injetar:**
```javascript
function main(args) {
    let text = args.text;
    
    // Expressões regulares para arrancar listas de pontos, hífens e asteriscos que a IA insiste em colocar
    text = text.replace(/^[-*•]\s+/gm, ''); 
    text = text.replace(/^\d+\.\s+/gm, '');
    
    // Substitui quebras de linha duplas por espaço para condensar a msg
    text = text.replace(/\n\n/g, ' ');

    return { 
        final_response: text.trim() 
    };
}
```

---

## 6. NÓ DE SAÍDA (End Node)
Conecte o Code Node aqui.
- Variável de Resposta: Selecione a saída `final_response` que veio do Nó de Código.
- No momento que esse nó finalizar, o Dify manda o JSON mastigado de volta pro `MS-03` no n8n.
