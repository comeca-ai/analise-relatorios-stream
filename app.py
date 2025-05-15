# ----------------------------
# imports no topo do app.py
# ----------------------------
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import openai
import docx
import re

# ----------------------------
# sua função de visualização
# ----------------------------
def criar_visualizacao(vis_info):
    try:
        titulo = vis_info.get('titulo', 'Visualização')
        df     = vis_info.get('dados')
        if df is None or df.empty:
            st.warning(f"Dados vazios para '{titulo}'.")
            return
        # converter strings brasileiras
        for col in df.select_dtypes(include=['object']):
            try:
                df[col] = (
                    df[col].astype(str)
                          .str.replace(',', '.')
                          .str.replace('%', '')
                          .str.replace('R$', '')
                )
            except Exception:
                pass
        # plot de exemplo: barras
        fig = px.bar(df, x=df.columns[0], y=df.columns[1], title=titulo)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Erro em criar_visualizacao: {e}")

# --------------------------------------------------
# função de interface agora chamando criar_visualizacao
# --------------------------------------------------
def interface_extracao_manual():
    st.title("Análise Manual de Relatórios")
    st.write("Faça upload de CSV ou Excel para ver um gráfico de barras das duas primeiras colunas.")
    uploaded_file = st.file_uploader("Selecione CSV ou XLSX", type=['csv','xlsx'])
    if uploaded_file:
        # lê CSV ou Excel
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)
            st.success(f"Arquivo '{uploaded_file.name}' carregado!")
            # monta e chama o plot
            vis_info = {
                'titulo': uploaded_file.name,
                'dados': df
            }
            criar_visualizacao(vis_info)
        except Exception as e:
            st.error(f"Falha ao ler o arquivo: {e}")
    else:
        st.info("Aguardando upload...")

# --------------------------------------------------
# garante que o Streamlit execute a interface
# --------------------------------------------------
if __name__ == "__main__":
    interface_extracao_manual()
