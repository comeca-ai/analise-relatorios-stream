import streamlit as st
import openai
import docx
import re
import io
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
import time
from tenacity import retry, stop_after_attempt, wait_fixed

# === CONFIGURAÇÕES DA PÁGINA ===
st.set_page_config(
    page_title="Analisador Estratégico de Mercado com IA",
    layout="wide",
    initial_sidebar_state="expanded"
)

# === ESTILOS PERSONALIZADOS ===
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1E3A8A;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #2563EB;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .insight-box {
        background-color: #EFF6FF;
        border-left: 4px solid #3B82F6;
        padding: 1rem;
        margin-bottom: 1rem;
    }
    .source-text {
        font-size: 0.8rem;
        color: #6B7280;
        font-style: italic;
        margin-top: 0.2rem;
    }
    .chart-container {
        margin-top: 1.5rem;
        margin-bottom: 2.5rem;
        border: 1px solid #E5E7EB;
        border-radius: 8px;
        padding: 1rem;
        background-color: white;
    }
    .debug-info {
        background-color: #FFFBEB;
        border: 1px solid #FCD34D;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# === CREDENCIAIS ===
# Tenta carregar da secrets; se não, pede ao usuário
openai_api_key = st.secrets.get("OPENAI_API_KEY") or st.sidebar.text_input(
    "OpenAI API Key", type="password"
)

if openai_api_key:
    client = openai.OpenAI(api_key=openai_api_key)
else:
    client = None

# === FUNÇÕES AUXILIARES ===

def extrair_texto_arquivo(uploaded_file):
    """
    Extrai texto de um arquivo .docx usando python-docx.
    """
    doc = docx.Document(uploaded_file)
    return "\n".join([p.text for p in doc.paragraphs])


def dividir_em_blocos(texto, max_tokens=8000):
    """
    Divide o texto em blocos de até max_tokens tokens aproximados.
    Implementação independente do NLTK, usando apenas expressões regulares.
    """
    # Método simples para dividir texto em sentenças usando expressões regulares
    # Divide em frases quando encontra '.', '!', ou '?' seguido por espaço e maiúscula
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', texto)
    
    blocks = []
    current_block = []
    current_token_count = 0
    
    # Estima tokens (aproximadamente 4 caracteres por token)
    for sentence in sentences:
        if not sentence.strip():  # Pula sentenças vazias
            continue
            
        estimated_tokens = len(sentence) // 4
        
        if current_token_count + estimated_tokens > max_tokens and current_block:
            blocks.append(" ".join(current_block))
            current_block = [sentence]
            current_token_count = estimated_tokens
        else:
            current_block.append(sentence)
            current_token_count += estimated_tokens
    
    # Adiciona o último bloco se existir
    if current_block:
        blocks.append(" ".join(current_block))
    
    # Garantir que temos pelo menos um bloco
    if not blocks:
        # Dividir por parágrafos
        paragraphs = texto.split('\n')
        
        if len(paragraphs) > 1:
            # Se temos múltiplos parágrafos, agrupe-os em blocos
            current_block = []
            current_token_count = 0
            
            for paragraph in paragraphs:
                if not paragraph.strip():
                    continue
                    
                estimated_tokens = len(paragraph) // 4
                
                if current_token_count + estimated_tokens > max_tokens and current_block:
                    blocks.append("\n".join(current_block))
                    current_block = [paragraph]
                    current_token_count = estimated_tokens
                else:
                    current_block.append(paragraph)
                    current_token_count += estimated_tokens
            
            if current_block:
                blocks.append("\n".join(current_block))
        
        # Se ainda não temos blocos, divisão simples por palavras
        if not blocks:
            words = texto.split()
            blocks = [" ".join(words[i:i+max_tokens*4]) for i in range(0, len(words), max_tokens*4)]
            
            # Último recurso: apenas use o texto inteiro como um bloco
            if not blocks:
                blocks = [texto]
        
    return blocks


def prompt_aprimorado(texto, tipo_analise, prompts):
    """
    Versão melhorada do prompt que ensina o GPT a responder exatamente no formato esperado.
    """
    # Base do prompt
    base_prompt = prompts[tipo_analise]
    
    # Adicionar exemplos específicos de formatação esperada
    formato_exemplo = """
IMPORTANTE: Para cada conjunto de dados, siga ESTRITAMENTE o seguinte formato:

## Título da Visualização

Tipo de gráfico: [tipo - ex: barras, pizza, linha, radar, área, barras empilhadas, etc.]

```markdown
| Categoria | Valor1 | Valor2 |
| --------- | ------ | ------ |
| Item1     | 10     | 20     |
| Item2     | 15     | 25     |
| Item3     | 5      | 30     |
```

Interpretação: Breve análise dos dados apresentados.

Fonte: Fonte dos dados mencionada no documento.

OBSERVAÇÃO: É ESSENCIAL seguir o formato acima para que o sistema possa gerar as visualizações corretamente.
"""
    
    # Combinar com o prompt existente
    prompt_final = base_prompt.replace("{texto}", formato_exemplo + "\n\n" + texto)
    
    return prompt_final


@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def solicitar_extracao_dados(texto, tipo_analise):
    """
    Chama o GPT para extrair dados e propor visualizações baseadas no prompt.
    Inclui sistema de retry para falhas de API.
    """
    prompts = {
        'mercado': """Você é um analista de dados especializado em visualização de dados sobre análises de mercado.

Extraia dados quantitativos e qualitativos do texto a seguir para criar visualizações informativas sobre o mercado analisado. Foque em:
1. Tamanho e crescimento de mercado (valores, CAGR)
2. Market share dos players
3. Métricas comparativas entre empresas
4. Análises SWOT
5. Tendências do setor
6. Comportamento do consumidor

Para cada conjunto de dados que identificar, forneça:
1. Um título descritivo para a visualização
2. O tipo de gráfico mais apropriado (gráfico de barras, pizza, linha, radar, etc.)
3. Uma tabela estruturada com os dados em formato Markdown delimitado por ```markdown
4. Uma breve interpretação dos dados (2-3 frases)
5. A fonte dos dados citada no documento

ATENÇÃO: Forneça apenas dados que estejam explicitamente mencionados no texto. Não invente ou estime dados não presentes. Estruture os dados em tabelas limpas e adequadas para visualização.

Texto para análise:
{texto}
""",
        'financeiro': """Você é um analista financeiro especializado em visualização de dados.

Extraia dados quantitativos e qualitativos do texto a seguir para criar visualizações informativas sobre análise financeira. Foque em:
1. Receitas, lucros, margens
2. Indicadores financeiros (ROI, ROE, etc.)
3. Composição de receitas/custos
4. Projeções e crescimento
5. Comparativos com competidores
6. Tendências financeiras do setor

Para cada conjunto de dados que identificar, forneça:
1. Um título descritivo para a visualização
2. O tipo de gráfico mais apropriado (gráfico de barras, pizza, linha, área, etc.)
3. Uma tabela estruturada com os dados em formato Markdown delimitado por ```markdown
4. Uma breve interpretação dos dados (2-3 frases)
5. A fonte dos dados citada no documento

ATENÇÃO: Forneça apenas dados que estejam explicitamente mencionados no texto. Não invente ou estime dados não presentes. Estruture os dados em tabelas limpas e adequadas para visualização.

Texto para análise:
{texto}
""",
        'competitivo': """Você é um analista competitivo especializado em visualização de dados.

Extraia dados quantitativos e qualitativos do texto a seguir para criar visualizações informativas sobre a análise competitiva. Foque em:
1. Market share dos players
2. Vantagens competitivas de cada player
3. Comparativos de preços, taxas, comissões
4. Análise SWOT comparativa
5. Posicionamento estratégico
6. Tendências competitivas do setor

Para cada conjunto de dados que identificar, forneça:
1. Um título descritivo para a visualização
2. O tipo de gráfico mais apropriado (matriz 2x2, radar, barras, pizza, etc.)
3. Uma tabela estruturada com os dados em formato Markdown delimitado por ```markdown
4. Uma breve interpretação dos dados (2-3 frases)
5. A fonte dos dados citada no documento

ATENÇÃO: Forneça apenas dados que estejam explicitamente mencionados no texto. Não invente ou estime dados não presentes. Estruture os dados em tabelas limpas e adequadas para visualização.

Texto para análise:
{texto}
"""
    }
    
    if not client:
        return "Por favor, insira uma chave de API OpenAI válida para continuar."
    
    # Melhorar o prompt com o formato esperado
    prompt_melhorado = prompt_aprimorado(texto, tipo_analise, prompts)
    
    try:
        resposta = client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": "Você é um analista de dados especializado em visualizações gráficas de alta qualidade."},
                {"role": "user", "content": prompt_melhorado},
            ],
            temperature=temperatura,
        )
        return resposta.choices[0].message.content
    except Exception as e:
        st.warning(f"Erro na API OpenAI: {str(e)}. Tentando novamente...")
        raise


def extrair_visualizacoes_do_texto(texto: str):
    """
    Versão melhorada que é mais flexível na detecção de visualizações
    """
    # Padrão mais flexível para detectar blocos de visualização
    vis_pattern = r'#+\s+(.*?)\n+(?:.*?(?:tipo|gráfico|chart|visualization).*?:?\s*(.*?)\n+)?(```(?:markdown|md)?\n([\s\S]*?)```)([\s\S]*?)(?=\n#+\s+|$)'
    matches = re.findall(vis_pattern, texto, re.IGNORECASE)
    
    visualizacoes = []
    for match in matches:
        titulo = match[0].strip()
        tipo_grafico = match[1].strip().lower() if match[1] else "barras"  # Default para barras
        tabela_md = match[3].strip()
        
        # Verificar se a tabela está vazia
        if not tabela_md.strip():
            continue
            
        # Extrair a interpretação (texto após a tabela)
        interpretacao = match[4].strip()
        
        # Extrair fonte se mencionada
        fonte_match = re.search(r'fonte.*?:?\s*(.*?)(?:\n|$)', interpretacao, re.IGNORECASE)
        fonte = fonte_match.group(1).strip() if fonte_match else ""
        
        try:
            # Verificar se a tabela está no formato CSV
            if ',' in tabela_md.split('\n')[0] and '|' not in tabela_md.split('\n')[0]:
                df = pd.read_csv(io.StringIO(tabela_md), engine='python', skipinitialspace=True)
            else:
                # Processamento melhorado para tabelas markdown
                # Limpar linhas vazias e espaços extras
                tabela_md = '\n'.join([linha for linha in tabela_md.split('\n') if linha.strip()])
                
                # Remover linha de separação do markdown 
                table_rows = re.sub(r'\n\|\s*[-:]+\s*\|[-:|\s]*\n', '\n', '\n' + tabela_md + '\n')
                
                # Limpar e processar a tabela
                rows = [row.strip() for row in table_rows.split('\n') if row.strip() and row.strip().startswith('|')]
                if not rows:
                    continue
                
                # Extrair células da tabela
                data = []
                headers = []
                for i, row in enumerate(rows):
                    cells = [cell.strip() for cell in row.split('|')[1:-1]]
                    if i == 0:
                        headers = cells
                    else:
                        data.append(cells)
                
                # Criar DataFrame
                df = pd.DataFrame(data, columns=headers)
            
            # Tenta converter colunas numéricas
            for col in df.columns:
                try:
                    # Processar números em formato brasileiro (vírgula como decimal)
                    df[col] = df[col].astype(str).str.replace(',', '.').str.replace('%', '').str.replace('R$', '')
                    df[col] = pd.to_numeric(df[col], errors='coerce')
                except:
                    pass  # Mantém como string se não conseguir converter
            
            visualizacoes.append({
                'titulo': titulo,
                'tipo': tipo_grafico if tipo_grafico else "barras",
                'dados': df,
                'interpretacao': interpretacao,
                'fonte': fonte
            })
        except Exception as e:
            st.error(f"Erro ao processar tabela para '{titulo}': {str(e)}")
            continue
    
    return visualizacoes


def criar_visualizacao_sintetica(texto):
    """
    Cria uma visualização básica de análise de texto quando não há dados estruturados detectados
    """
    import re
    
    # Extrai números do texto
    numeros = re.findall(r'\b\d+(?:[.,]\d+)?(?:\s*%|\s*R\$)?', texto)
    numeros_processados = []
    
    # Processa os números encontrados
    for num in numeros:
        # Remove símbolos e converte vírgula para ponto
        num_clean = num.replace('R$', '').replace('%', '').replace(',', '.')
        try:
            numeros_processados.append(float(num_clean))
        except:
            continue
    
    # Se encontrou números suficientes, cria uma tabela básica
    if len(numeros_processados) >= 3:
        # Identifica possíveis contextos para os números
        contexts = []
        for num in numeros[:10]:  # Limita aos 10 primeiros números
            # Busca o contexto antes do número (até 5 palavras)
            position = texto.find(num)
            if position > 0:
                start = max(0, texto.rfind('.', 0, position))
                context = texto[start:position].strip()
                # Limita para as últimas 3 palavras
                context_words = context.split()[-3:]
                context = ' '.join(context_words)
                contexts.append(context)
            else:
                contexts.append(f"Valor {len(contexts)+1}")
        
        # Cria um dataframe com os números encontrados
        data = {
            'Contexto': contexts[:len(numeros_processados)],
            'Valor': numeros_processados
        }
        
        df = pd.DataFrame(data)
        
        # Retorna como uma visualização
        return [{
            'titulo': 'Valores Numéricos Detectados no Texto',
            'tipo': 'barras',
            'dados': df,
            'interpretacao': 'Análise de valores numéricos encontrados no texto. Estes valores foram extraídos automaticamente e podem precisar de revisão para contexto completo.',
            'fonte': 'Análise automática do texto'
        }]
    
    # Se não foi possível criar uma visualização numérica, retorna uma lista vazia
    return []


def processar_bloco_com_fallback(bloco, tipo_analise):
    """
    Processa o bloco e tenta novamente com um prompt mais simples se falhar
    """
    # Primeira tentativa
    resposta = solicitar_extracao_dados(bloco, tipo_analise)
    visualizacoes = extrair_visualizacoes_do_texto(resposta)
    
    # Logar a resposta para debug (opcional, descomente se necessário)
    # with st.expander("Debug - Resposta do GPT"):
    #     st.code(resposta)
    
    # Se não encontrou visualizações, tenta com um prompt alternativo
    if not visualizacoes:
        st.info("Tentando abordagem alternativa para detecção de dados...")
        prompt_simples = f"""
        Você é um analista de dados especializado em extrair dados numéricos de textos.
        
        Analise o texto abaixo e identifique QUALQUER dado numérico ou estatístico.
        Para cada conjunto de dados que encontrar, crie uma tabela simples em formato markdown.
        
        Cada visualização DEVE seguir EXATAMENTE este formato:
        
        # Título da visualização
        
        Tipo de gráfico: barras
        
        ```markdown
        | Categoria | Valor |
        | --------- | ----- |
        | Item1     | 10    |
        | Item2     | 20    |
        ```
        
        Interpretação: Uma breve explicação.
        
        Fonte: Fonte dos dados.
        
        ===
        
        TEXTO:
        {bloco}
        """
        
        resposta_alternativa = client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": "Você é um especialista em extrair dados numéricos para visualização."},
                {"role": "user", "content": prompt_simples},
            ],
            temperature=0.2,  # Temperatura mais baixa para respostas mais previsíveis
        )
        
        visualizacoes = extrair_visualizacoes_do_texto(resposta_alternativa.choices[0].message.content)
        
        # Logar a resposta alternativa para debug (opcional, descomente se necessário)
        # with st.expander("Debug - Resposta alternativa do GPT"):
        #     st.code(resposta_alternativa.choices[0].message.content)
        
        # Se ainda não encontrou, criar uma visualização sintética
        if not visualizacoes:
            st.info("Gerando visualização baseada em análise de texto...")
            visualizacoes = criar_visualizacao_sintetica(bloco)
    
    return visualizacoes


def interface_extracao_manual(bloco):
    """
    Interface para permitir extração manual de dados quando a automática falha
    """
    st.subheader("Assistente de extração de dados")
    st.write("O sistema não detectou dados estruturados automaticamente. Vamos tentar uma abordagem assistida.")
    
    # Exibir o texto para o usuário
    st.text_area("Texto do bloco:", value=bloco, height=200, disabled=True)
    
    # Opções para o usuário selecionar o tipo de dados presentes
    tipo_dados = st.selectbox("Que tipo de dados estruturados você vê neste texto?", 
                             ["Tabela", "Lista de itens", "Valores percentuais", 
                              "Séries temporais", "Comparações", "Outro"])
    
    # Baseado no tipo, oferecer opções específicas
    if tipo_dados == "Tabela":
        st.info("Cole abaixo os dados em formato de tabela (valores separados por tab ou vírgula)")
        dados_tabela = st.text_area("Dados tabulares:", height=150)
        if st.button("Processar tabela"):
            try:
                df = pd.read_csv(io.StringIO(dados_tabela), sep=None, engine='python')
                st.write("Tabela detectada:")
                st.dataframe(df)
                
                # Criar estrutura de visualização
                return [{
                    'titulo': 'Dados extraídos manualmente',
                    'tipo': 'barras',
                    'dados': df,
                    'interpretacao': 'Dados extraídos manualmente pelo usuário.',
                    'fonte': 'Extração manual'
                }]
            except:
                st.error("Não foi possível interpretar os dados como tabela.")
    
    elif tipo_dados == "Lista de itens":
        st.info("Cole abaixo os itens da lista (um por linha)")
        itens_lista = st.text_area("Itens:", height=150)
        if st.button("Processar lista"):
            itens = [item.strip() for item in itens_lista.split('\n') if item.strip()]
            st.write("Lista detectada:")
            for i, item in enumerate(itens, 1):
                st.write(f"{i}. {item}")
                
            # Criar DataFrame a partir da lista
            df = pd.DataFrame({
                'Item': itens,
                'Valor': range(1, len(itens) + 1)
            })
            
            return [{
                'titulo': 'Lista de Itens',
                'tipo': 'barras',
                'dados': df,
                'interpretacao': 'Lista de itens extraída manualmente pelo usuário.',
                'fonte': 'Extração manual'
            }]
    
    # Outros tipos de dados
    elif tipo_dados in ["Valores percentuais", "Séries temporais", "Comparações"]:
        st.info(f"Extraia os {tipo_dados.lower()} do texto e insira no formato de tabela abaixo")
        dados_manual = st.text_area("Dados (um por linha, no formato 'categoria: valor'):", height=150)
        if st.button("Processar dados"):
            linhas = [linha.strip() for linha in dados_manual.split('\n') if linha.strip()]
            categorias = []
            valores = []
            
            for linha in linhas:
                if ':' in linha:
                    cat, val = linha.split(':', 1)
                    categorias.append(cat.strip())
                    # Tenta converter para número
                    try:
                        val_clean = val.strip().replace('%', '').replace('R$', '').replace(',', '.')
                        valores.append(float(val_clean))
                    except:
                        valores.append(val.strip())
                        
            if categorias and valores:
                df = pd.DataFrame({
                    'Categoria': categorias,
                    'Valor': valores
                })
                
                st.write("Dados extraídos:")
                st.dataframe(df)
                
                return [{
                    'titulo': f'{tipo_dados} Extraídos',
                    'tipo': 'barras' if tipo_dados != "Séries temporais" else 'linha',
                    'dados': df,
                    'interpretacao': f'{tipo_dados} extraídos manualmente pelo usuário.',
                    'fonte': 'Extração manual'
                }]
    
    elif tipo_dados == "Outro":
        st.info("Descreva o tipo de dados que você identificou e como gostaria de visualizá-los:")
        descricao = st.text_input("Descrição dos dados:")
        dados_manual = st.text_area("Insira os dados em formato de tabela (CSV ou valores separados por tab):", height=150)
        tipo_vis = st.selectbox("Tipo de visualização desejada:", 
                               ["Barras", "Pizza", "Linha", "Área", "Radar", "Dispersão"])
        
        if st.button("Processar dados personalizados"):
            try:
                df = pd.read_csv(io.StringIO(dados_manual), sep=None, engine='python')
                st.write("Dados extraídos:")
                st.dataframe(df)
                
                return [{
                    'titulo': descricao or 'Dados Personalizados',
                    'tipo': tipo_vis.lower(),
                    'dados': df,
                    'interpretacao': 'Dados extraídos e formatados manualmente pelo usuário.',
                    'fonte': 'Extração manual'
                }]
            except:
                st.error("Não foi possível processar os dados. Verifique o formato e tente novamente.")
    
    return None


def criar_visualizacao(vis_info):
    """
    Cria a visualização adequada com base no tipo informado.
    """
    titulo = vis_info['titulo']
    tipo = vis_info['tipo']
    df = vis_info['dados']
    interpretacao = vis_info['interpretacao']
    fonte = vis_info['fonte']
    
    if len(df.columns) < 2 or len(df) == 0:
        st.warning(f"Dados insuficientes para criar visualização para '{titulo}'")
        return
    
    # Container para o gráfico com estilo
    st.markdown(f"<div class='chart-container'>", unsafe_allow_html=True)
    st.markdown(f"<h3 class='sub-header'>{titulo}</h3>", unsafe_allow_html=True)
    
    fig = None
    
    # Decidir qual tipo de gráfico gerar com base no tipo informado
    if 'barra' in tipo or 'coluna' in tipo:
        # Identificar se são barras agrupadas ou empilhadas
        if 'empilhada' in tipo or 'stack' in tipo:
            fig = px.bar(
                df, 
                x=df.columns[0], 
                y=df.columns[1:], 
                title=titulo,
                barmode='stack'
            )
        elif '100%' in tipo:
            fig = px.bar(
                df, 
                x=df.columns[0], 
                y=df.columns[1:], 
                title=titulo,
                barmode='relative'
            )
        else:
            fig = px.bar(
                df, 
                x=df.columns[0], 
                y=df.columns[1:], 
                title=titulo,
                barmode='group'
            )
            
        if 'horizontal' in tipo:
            fig.update_layout(autosize=True, height=max(400, 50 * len(df)))
            fig = go.Figure(fig).update_layout(yaxis_autorange="reversed")
            fig.update_layout(xaxis_title=None, yaxis_title=None)
        else:
            fig.update_layout(xaxis_title=None, yaxis_title=None)
            
    elif 'pizza' in tipo or 'torta' in tipo or 'pie' in tipo:
        fig = px.pie(
            df, 
            names=df.columns[0], 
            values=df.columns[1], 
            title=titulo
        )
        fig.update_traces(textposition='inside', textinfo='percent+label')
        
    elif 'linha' in tipo or 'line' in tipo:
        fig = px.line(
            df, 
            x=df.columns[0], 
            y=df.columns[1:], 
            title=titulo,
            markers=True
        )
        fig.update_layout(xaxis_title=None, yaxis_title=None)
        
    elif 'area' in tipo:
        if 'empilhada' in tipo or 'stack' in tipo:
            fig = px.area(
                df, 
                x=df.columns[0], 
                y=df.columns[1:], 
                title=titulo
            )
        else:
            fig = px.area(
                df, 
                x=df.columns[0], 
                y=df.columns[1:], 
                title=titulo,
                groupnorm='fraction'
            )
        fig.update_layout(xaxis_title=None, yaxis_title=None)
            
    elif 'radar' in tipo:
        fig = go.Figure()
        # Considerando que a primeira coluna é o nome das categorias
        categories = df[df.columns[0]].tolist()
        
        # Cada coluna adicional representa um traço no radar
        for col in df.columns[1:]:
            fig.add_trace(go.Scatterpolar(
                r=df[col].tolist(),
                theta=categories,
                fill='toself',
                name=col
            ))
            
        fig.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, df[df.columns[1:]].max().max() * 1.1]
                )
            ),
            title=titulo
        )
        
    elif 'dispersao' in tipo or 'scatter' in tipo or 'bolha' in tipo or 'matriz' in tipo:
        if len(df.columns) >= 3:  # Se tiver 3 colunas, usar a terceira para tamanho
            fig = px.scatter(
                df, 
                x=df.columns[1], 
                y=df.columns[2], 
                size=df.columns[3] if len(df.columns) > 3 else None,
                hover_name=df.columns[0],
                text=df.columns[0],
                title=titulo
            )
            
            # Adicionar linhas de referência se for uma matriz 2x2
            if 'matriz' in tipo or '2x2' in tipo:
                x_mid = (df[df.columns[1]].max() + df[df.columns[1]].min()) / 2
                y_mid = (df[df.columns[2]].max() + df[df.columns[2]].min()) / 2
                
                fig.add_shape(
                    type="line", x0=x_mid, x1=x_mid, y0=df[df.columns[2]].min(), y1=df[df.columns[2]].max(),
                    line=dict(color="gray", width=1, dash="dash")
                )
                fig.add_shape(
                    type="line", x0=df[df.columns[1]].min(), x1=df[df.columns[1]].max(), y0=y_mid, y1=y_mid,
                    line=dict(color="gray", width=1, dash="dash")
                )
        else:
            st.warning(f"Dados insuficientes para gráfico de dispersão '{titulo}'. São necessárias pelo menos 3 colunas.")
            
    elif 'treemap' in tipo:
        if len(df.columns) >= 2:
            fig = px.treemap(
                df,
                path=[df.columns[0]],
                values=df.columns[1],
                title=titulo
            )
            
    elif 'mapa' in tipo and 'calor' in tipo:
        if len(df.columns) >= 3:
            fig = px.density_heatmap(
                df,
                x=df.columns[1],
                y=df.columns[0],
                z=df.columns[2],
                title=titulo
            )
            
    # Se nenhum tipo específico foi identificado, use um gráfico de barras simples
    if fig is None:
        fig = px.bar(
            df, 
            x=df.columns[0], 
            y=df.columns[1], 
            title=titulo
        )
    
    # Configurações comuns para todos os gráficos
    fig.update_layout(
        margin=dict(l=40, r=40, t=50, b=40),
        template="plotly_white",
        height=500,
        title=None  # Removemos o título pois já o exibimos em HTML
    )
    
    # Exibir o gráfico
    st.plotly_chart(fig, use_container_width=True)
    
    # Exibir a interpretação e fonte
    if interpretacao:
        st.markdown(f"<div class='insight-box'>{interpretacao}</div>", unsafe_allow_html=True)
    
    if fonte:
        st.markdown(f"<p class='source-text'>Fonte: {fonte}</p>", unsafe_allow_html=True)
    
    # Mostrar os dados (expandível)
    with st.expander("Ver dados"):
        st.dataframe(df, use_container_width=True)
    
    st.markdown("</div>", unsafe_allow_html=True)


def check_api_key():
    """
    Verifica se a API key está configurada corretamente
    """
    key = openai_api_key
    if not key:
        st.error("OpenAI API key não está configurada!")
        return False
    elif not key.startswith("sk-"):
        st.error("OpenAI API key parece estar mal formatada!")
        return False
    else:
        # Apenas mostra que existe, não a chave em si
        st.sidebar.success(f"API key configurada (começa com: {key[:5]}...)")
        return True


# === INTERFACE ===
st.markdown("<h1 class='main-header'>Analisador Estratégico de Mercado com IA</h1>", unsafe_allow_html=True)
st.markdown("""
Este aplicativo analisa documentos e extrai dados para criar visualizações gráficas automaticamente.
Carregue um documento como um relatório de mercado, análise de setor ou estudo competitivo, e o aplicativo gerará
gráficos interativos com base nos dados encontrados.
""")

# Configurações via sidebar
st.sidebar.header("Configurações")
max_tokens = st.sidebar.slider("Máx. de tokens por bloco", 2000, 8000, 4000, step=1000)
modelo = st.sidebar.selectbox("Modelo OpenAI", ["gpt-4", "gpt-3.5-turbo"], index=0)
temperatura = st.sidebar.slider("Temperatura", 0.0, 1.0, 0.3, step=0.1)
modo_debug = st.sidebar.checkbox("Modo de depuração", value=False)

tipo_analise = st.sidebar.selectbox(
    "Tipo de Análise", 
    ["mercado", "competitivo", "financeiro"], 
    index=0,
    format_func=lambda x: {
        "mercado": "Análise de Mercado", 
        "competitivo": "Análise Competitiva", 
        "financeiro": "Análise Financeira"
    }[x]
)

# Verificar a API key
if openai_api_key:
    check_api_key()

st.sidebar.markdown("---")
st.sidebar.markdown("""
### Sobre
Este aplicativo usa IA para transformar relatórios textuais em visualizações
de dados interativas. Ele extrai dados numéricos e qualitativos do texto
e gera gráficos apropriados.

**Tipos de análise:**
- **Mercado**: Tamanho, crescimento, tendências
- **Competitivo**: Players, market share, SWOT
- **Financeiro**: Receitas, custos, projeções
""")

col1, col2 = st.columns([2, 1])
with col1:
    uploaded_file = st.file_uploader("Envie um documento .docx", type=["docx"])

with col2:
    if not openai_api_key:
        st.warning("⚠️ Por favor, insira uma chave de API OpenAI para continuar.")

if uploaded_file and openai_api_key:
    # Salva o arquivo para evitar carregar novamente durante a sessão
    if 'file_processed' not in st.session_state or st.session_state.file_processed != uploaded_file.name:
        with st.spinner("Processando documento..."):
            texto = extrair_texto_arquivo(uploaded_file)
            blocos = dividir_em_blocos(texto, max_tokens)
            
            # Armazena blocos na session_state
            st.session_state.blocos = blocos
            st.session_state.file_processed = uploaded_file.name
            st.session_state.visualizacoes_por_bloco = []
    
    # Usar dados armazenados
    blocos = st.session_state.blocos
    
    st.markdown(f"<h2 class='sub-header'>Visualizações Extraídas</h2>", unsafe_allow_html=True)
    st.info(f"📄 Documento dividido em {len(blocos)} blocos para análise. Selecione os blocos abaixo para ver as visualizações geradas.")
    
    # Tabs para os blocos
    tabs = st.tabs([f"Bloco {i+1}" for i in range(len(blocos))])
    
    # Para cada bloco
    for i, (tab, bloco) in enumerate(zip(tabs, blocos)):
        with tab:
            # Opção para ver o texto do bloco se modo debug estiver ativado
            if modo_debug:
                with st.expander("Ver texto do bloco", expanded=False):
                    st.text_area(f"Conteúdo do Bloco {i+1}", value=bloco, height=200)
            
            # Verificar se já temos visualizações para este bloco
            if len(st.session_state.visualizacoes_por_bloco) <= i or st.session_state.visualizacoes_por_bloco[i] is None:
                with st.spinner(f"Analisando bloco {i+1} e gerando visualizações..."):
                    # Usar a função com fallback para processamento
                    visualizacoes = processar_bloco_com_fallback(bloco, tipo_analise)
                    
                    # Armazenar para não precisar gerar novamente
                    if len(st.session_state.visualizacoes_por_bloco) <= i:
                        st.session_state.visualizacoes_por_bloco.extend([None] * (i + 1 - len(st.session_state.visualizacoes_por_bloco)))
                    st.session_state.visualizacoes_por_bloco[i] = visualizacoes
            else:
                visualizacoes = st.session_state.visualizacoes_por_bloco[i]
            
            # Se não encontrou visualizações, mostrar alerta e oferecer extração manual
            if not visualizacoes:
                st.warning(f"Nenhuma visualização foi detectada no bloco {i+1}. Isso pode acontecer se o texto não contiver dados estruturados.")
                
                # Botão para extração manual
                if st.button(f"Extrair dados manualmente do Bloco {i+1}", key=f"manual_extract_{i}"):
                    manual_vis = interface_extracao_manual(bloco)
                    if manual_vis:
                        st.session_state.visualizacoes_por_bloco[i] = manual_vis
                        st.experimental_rerun()
                
                continue
            
            # Exibir cada visualização
            for vis_info in visualizacoes:
                criar_visualizacao(vis_info)
                
            # Botões de ação
            col1, col2 = st.columns(2)
            with col1:
                # Botão para regenerar visualizações
                if st.button(f"Regenerar visualizações", key=f"regenerate_block_{i}"):
                    st.session_state.visualizacoes_por_bloco[i] = None
                    st.experimental_rerun()
            
            with col2:
                # Botão para extração manual (mesmo tendo encontrado visualizações)
                if st.button(f"Extrair dados manualmente", key=f"manual_extract_alt_{i}"):
                    manual_vis = interface_extracao_manual(bloco)
                    if manual_vis:
                        # Adicionar às visualizações existentes
                        existing_vis = st.session_state.visualizacoes_por_bloco[i] or []
                        st.session_state.visualizacoes_por_bloco[i] = existing_vis + manual_vis
                        st.experimental_rerun()
else:
    st.info("Carregue um documento para análise e verifique se a chave da API OpenAI está configurada.")
    
    # Mostrar demo se não houver arquivo carregado
    with st.expander("Sobre este aplicativo"):
        st.markdown("""
        ### Como usar este aplicativo
        
        1. Insira sua chave da API OpenAI na barra lateral (ou configure-a nos secrets do Streamlit)
        2. Carregue um documento .docx contendo um relatório de mercado, análise financeira ou dados competitivos
        3. O sistema divide o documento em blocos e analisa cada um usando IA
        4. As visualizações são geradas automaticamente para os dados encontrados
        5. Use as abas para navegar entre os diferentes blocos do documento
        
        ### Recursos
        
        - **Extração automática de dados**: O aplicativo usa GPT-4 para identificar dados estruturados e não estruturados no texto
        - **Múltiplos tipos de gráficos**: Barras, pizza, linhas, radar, dispersão e mais, dependendo dos dados
        - **Interpretação de dados**: Cada visualização inclui uma breve interpretação dos dados
        - **Extração manual**: Se a detecção automática falhar, você pode extrair dados manualmente
        
        ### Melhorias implementadas
        
        - Sistema de retry para falhas da API
        - Detecção de padrões mais flexível
        - Extração manual de dados como alternativa
        - Processamento avançado de tabelas markdown
        - Modo de debug para visualizar as respostas da API
        """)
