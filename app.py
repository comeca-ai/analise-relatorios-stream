# No início do arquivo, junto com os demais imports:
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import openai
import docx
import re

def criar_visualizacao(vis_info):
    """
    Cria a visualização adequada com base no tipo informado.
    Versão simplificada com foco na estabilidade.
    """
    try:
        # Extrair informações
        titulo = vis_info.get('titulo', 'Visualização')
        tipo   = vis_info.get('tipo', 'barras').lower()
        df     = vis_info.get('dados')
        interpretacao = vis_info.get('interpretacao', '')
        fonte         = vis_info.get('fonte', '')

        # Verificar se o DataFrame é válido
        if df is None or df.empty:
            st.warning(f"Dados vazios para '{titulo}'. Impossível criar visualização.")
            return

        # Garantir pelo menos duas colunas
        if len(df.columns) < 2:
            df['Valor'] = range(1, len(df) + 1)
            st.info(f"Adicionada coluna de valores para '{titulo}'.")

        # Exemplo de processamento de coluna numérica em formato brasileiro
        for col in df.select_dtypes(include=['object']):
            try:
                df[col] = (
                    df[col].astype(str)
                          .str.replace(',', '.')    # vírgula → ponto
                          .str.replace('%', '')     # remove %
                          .str.replace('R$', '')    # remove R$
                )
            except Exception:
                # se não der pra converter, deixa como está
                pass

        # (o resto da função segue inalterado...)
        fig = px.bar(df, x=df.columns[0], y=df.columns[1], title=titulo)
        st.plotly_chart(fig, use_container_width=True)

    except Exception as e:
        st.error(f"Erro ao criar visualização: {e}")
        return None


def interface_extracao_manual():
    """
    Interface para extração manual de dados.
    """
    try:
        # ... seu código aqui ...
        return resultado

    except Exception as e:
        st.error(f"Erro na interface de extração manual: {e}")
        return None
