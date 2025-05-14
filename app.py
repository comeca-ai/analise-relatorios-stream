import streamlit as st
import openai
import docx
import re
import io
import pandas as pd
import plotly.express as px

# === CONFIGURAÇÕES DA PÁGINA ===
st.set_page_config(
    page_title="Analisador de Relatórios com IA",
    layout="wide",
)

# === CREDENCIAIS ===
# Tenta carregar da secrets; se não, pede ao usuário
openai_api_key = st.secrets.get("OPENAI_API_KEY") or st.sidebar.text_input(
    "OpenAI API Key", type="password"
)
client = openai.OpenAI(api_key=openai_api_key)

# === FUNÇÕES AUXILIARES ===

def extrair_texto_arquivo(uploaded_file):
    """
    Extrai texto de um arquivo .docx usando python-docx.
    """
    doc = docx.Document(uploaded_file)
    return "\n".join([p.text for p in doc.paragraphs])


def dividir_em_blocos(texto, max_palavras=2000):
    """
    Divide o texto em blocos de até max_palavras palavras.
    """
    palavras = texto.split()
    blocos = []
    for i in range(0, len(palavras), max_palavras):
        blocos.append(" ".join(palavras[i:i+max_palavras]))
    return blocos


def solicitar_analise(texto):
    """
    Chama o GPT para gerar análise e tabelas em Markdown.
    """
    prompt = f"""
Você é um analista de dados experiente, especialista em visualizações.

Com base no conteúdo abaixo, extraia dados e proponha gráficos.
Para cada gráfico, informe:
- Título
- Tipo
- Tabela (sempre em bloco de código Markdown, ex:
```markdown
Coluna1 | Coluna2
--- | ---
valor1 | valor2
```
- Interpretação executiva

{texto}
"""
    resposta = client.chat.completions.create(
        model=modelo,
        messages=[
            {"role": "system", "content": "Você é um analista de dados experiente, especialista em visualizações."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperatura,
    )
    return resposta.choices[0].message.content


def extrair_tabelas_do_texto(texto: str):
    """
    Procura por tabelas Markdown dentro de blocos de código (```markdown … ```),
    e retorna uma lista de DataFrames.
    """
    pattern = r'```(?:\w*\n)?([\s\S]*?\|[\s\S]*?)```'
    matches = re.findall(pattern, texto)
    dataframes = []
    for match in matches:
        table_text = match.strip()
        table_text = re.sub(r'\s*\|\s*', '|', table_text)
        try:
            df = pd.read_csv(io.StringIO(table_text), sep='|', engine='python', skipinitialspace=True)
            df = df.loc[:, df.columns.str.strip() != '']
            df.columns = df.columns.str.strip()
            dataframes.append(df)
        except Exception:
            continue
    return dataframes


def plotar_bar_interativo(df: pd.DataFrame):
    """
    Gera um gráfico de barras interativo com Plotly Express.
    """
    fig = px.bar(
        df,
        x=df.columns[0],
        y=df.columns[1],
        title=f"{df.columns[1]} por {df.columns[0]}",
        labels={df.columns[0]: df.columns[0], df.columns[1]: df.columns[1]},
        hover_data={df.columns[1]: ":,.2f"},
    )
    fig.update_layout(margin=dict(l=40, r=40, t=50, b=40))
    return fig

# === INTERFACE ===
st.title("Analisador de Relatórios com IA")

# Configurações via sidebar
defaul_max = 2000
max_palavras = st.sidebar.slider("Máx. de palavras por bloco", 500, 5000, defaul_max, step=500)
modelo = st.sidebar.selectbox("Modelo OpenAI", ["gpt-4", "gpt-3.5-turbo"], index=0)
temperatura = st.sidebar.slider("Temperatura", 0.0, 1.0, 0.5, step=0.1)

uploaded_file = st.file_uploader("Envie um documento .docx", type=["docx"])

if uploaded_file:
    texto = extrair_texto_arquivo(uploaded_file)
    blocos = dividir_em_blocos(texto, max_palavras)

    for idx, bloco in enumerate(blocos, start=1):
        with st.expander(f"Bloco {idx} de {len(blocos)}"):
            with st.spinner("Gerando análise..."):
                resposta = solicitar_analise(bloco)
                st.markdown(resposta)

            with st.spinner("Gerando gráficos..."):
                tabelas = extrair_tabelas_do_texto(resposta)
                if tabelas:
                    for j, tabela in enumerate(tabelas, start=1):
                        st.dataframe(tabela)
                        fig = plotar_bar_interativo(tabela)
                        st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("Nenhuma tabela detectada para gerar gráficos neste bloco.")


