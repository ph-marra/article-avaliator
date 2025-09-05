# app.py
import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from oauth2client.service_account import ServiceAccountCredentials
import random

# Importar configurações
from config import (
    SOURCE_SHEET_URL,
    RESULTS_SHEET_URL,
    AVALIADORES,
    ASPECTOS_AVALIACAO,
    COLUNAS_ORDENACAO_FALLBACK,
    ORDENS_ORDENACAO_FALLBACK
)

# --- CONFIGURAÇÃO E AUTENTICAÇÃO ---

st.set_page_config(layout="wide", page_title="Ferramenta de Avaliação de Artigos")

# Define o escopo da API do Google
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    'https://www.googleapis.com/auth/spreadsheets',
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

# Cache para a conexão para não reconectar a cada interação
@st.cache_resource
def get_gspread_client():
    """Conecta-se ao Google Sheets usando as credenciais."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    client = gspread.authorize(creds)
    return client

def get_sheet_as_df(client, sheet_url, sheet_name=None):
    """Carrega uma aba específica (ou a primeira) de uma planilha como DataFrame."""
    try:
        sheet = client.open_by_url(sheet_url)
        if sheet_name:
            worksheet = sheet.worksheet(sheet_name)
        else:
            worksheet = sheet.get_worksheet(0) # Pega a primeira aba por padrão
        
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Erro ao carregar a planilha '{sheet_url}'. Verifique a URL e as permissões de compartilhamento. Erro: {e}")
        return pd.DataFrame()

@st.cache_data
def get_all_articles(_client, sheet_url):
    """Carrega artigos de todas as abas de uma planilha."""
    try:
        # Note que o primeiro argumento do cache é o _client, 
        # o sublinhado é uma convenção para dizer ao cache para não "olhar" para ele
        spreadsheet = _client.open_by_url(sheet_url)
        all_dfs = []
        for worksheet in spreadsheet.worksheets():
            data = worksheet.get_all_records()
            if data:
                all_dfs.append(pd.DataFrame(data))
        
        if not all_dfs:
            st.warning("Nenhum dado encontrado na planilha de origem.")
            return pd.DataFrame()

        full_df = pd.concat(all_dfs, ignore_index=True)

        must_exist = ['Title', 'Abstract'] + COLUNAS_ORDENACAO_FALLBACK
        missing_cols = [col for col in must_exist if col not in full_df.columns]

        if missing_cols:
            st.error(f"As seguintes colunas obrigatórias não foram encontradas na planilha de origem: {missing_cols}")
            return pd.DataFrame()
            
        return full_df.drop_duplicates(subset=["Title"])
    except Exception as e:
        st.error(f"Erro ao carregar a planilha de origem '{sheet_url}'. Erro: {e}")
        return pd.DataFrame()

# --- LÓGICA DE SELEÇÃO DE ARTIGOS ---

def selecionar_proximo_artigo(avaliador_cpf, df_artigos, df_resultados):
    """
    Decide qual artigo mostrar para o avaliador.
    Prioridade 1: Artigo avaliado por outro, mas não pelo atual.
    Prioridade 2: Artigo nunca avaliado, seguindo a ordem de fallback.
    """
    # Titles já avaliados pelo usuário atual (incluindo pulados)
    colunas_avaliador = [col for col in df_resultados.columns if col.startswith(f"{avaliador_cpf}/")]
    if not colunas_avaliador:
        titulos_avaliados_pelo_user = set()
    else:
        # Pega Title onde QUALQUER coluna deste avaliador não é nula
        titulos_avaliados_pelo_user = set(df_resultados[df_resultados[colunas_avaliador].notna().any(axis=1)]['Title'])

    # --- Lógica de Prioridade 1 ---
    # Encontrar artigos avaliados por pelo menos uma pessoa
    outros_avaliadores_cpfs = list(AVALIADORES.keys())
    outros_avaliadores_cpfs.remove(avaliador_cpf)
    
    colunas_outros = []
    for cpf in outros_avaliadores_cpfs:
        colunas_outros.extend([col for col in df_resultados.columns if col.startswith(f"{cpf}/")])

    if colunas_outros:
        # Title que já têm alguma avaliação de outros
        avaliados_por_outros = set(df_resultados[df_resultados[colunas_outros].notna().any(axis=1)]['Title'])
        # Interseção: avaliados por outros mas NÃO pelo usuário atual
        para_avaliar_prioridade = list(avaliados_por_outros - titulos_avaliados_pelo_user)
        if para_avaliar_prioridade:
            # Seleciona um aleatoriamente para evitar que todos peguem o mesmo
            titulo_selecionado = random.choice(para_avaliar_prioridade)
            return df_artigos[df_artigos['Title'] == titulo_selecionado].iloc[0]

    # --- Lógica de Prioridade 2 (Fallback) ---
    titulos_ja_no_resultado = set(df_resultados['Title'])
    titulos_virgens = set(df_artigos['Title']) - titulos_ja_no_resultado - titulos_avaliados_pelo_user
    
    if not titulos_virgens:
        return None # Não há mais artigos para avaliar

    df_virgens = df_artigos[df_artigos['Title'].isin(list(titulos_virgens))]
    
    # Ordenar de acordo com a configuração
    df_ordenado = df_virgens.sort_values(
        by=COLUNAS_ORDENACAO_FALLBACK,
        ascending=ORDENS_ORDENACAO_FALLBACK
    )
    
    return df_ordenado.iloc[0]


# --- INTERFACE PRINCIPAL ---

def main():
    st.title("Plataforma de Avaliação de Artigos Científicos")

    # --- TELA DE LOGIN ---
    if 'user_cpf' not in st.session_state:
        st.subheader("Login do Avaliador")
        cpf_input = st.text_input("Digite seu CPF (apenas números):")
        nome_input = st.text_input("Digite seu Nome Completo:")
        
        if st.button("Entrar"):
            if cpf_input in AVALIADORES and AVALIADORES[cpf_input].lower() == nome_input.lower():
                st.session_state.user_cpf = cpf_input
                st.session_state.user_name = AVALIADORES[cpf_input]
                st.rerun() # Recarrega a página para o estado "logado"
            else:
                st.error("CPF ou Nome inválido. Verifique os dados e tente novamente.")
        st.stop() # Para a execução aqui até o login ser bem-sucedido

    # --- PÁGINA DE AVALIAÇÃO (APÓS LOGIN) ---
    avaliador_cpf = st.session_state.user_cpf
    avaliador_nome = st.session_state.user_name
    st.sidebar.success(f"Logado como: **{avaliador_nome}**")
    if st.sidebar.button("Sair"):
        del st.session_state.user_cpf
        del st.session_state.user_name
        st.rerun()

    # Carregar os dados
    client = get_gspread_client()
    df_artigos = get_all_articles(client, SOURCE_SHEET_URL)
    df_resultados = get_sheet_as_df(client, RESULTS_SHEET_URL)

    # st.write("Colunas detectadas na planilha:", df_artigos.columns.tolist())

    if df_artigos.empty:
        st.warning("Não foi possível carregar os artigos. Verifique as configurações.")
        st.stop()
        
    # Inicializa o df_resultados se estiver vazio
    if df_resultados.empty:
        df_resultados = pd.DataFrame(columns=["Title", "Abstract"])

    # Selecionar o próximo artigo
    artigo_para_avaliar = selecionar_proximo_artigo(avaliador_cpf, df_artigos, df_resultados)

    if artigo_para_avaliar is None:
        st.success("🎉 Parabéns! Não há mais artigos para você avaliar no momento.")
        st.info("Aguarde novas avaliações de outros colegas ou a adição de novos artigos.")
        st.stop()

    # Exibir o artigo
    st.markdown("---")
    st.header(artigo_para_avaliar['Title'])
    with st.expander("Clique para ver o Abstract"):
        st.write(artigo_para_avaliar['Abstract'])
    st.markdown("---")
    
    st.subheader("Formulário de Avaliação")

    # Usar um formulário para agrupar os inputs
    with st.form(key='evaluation_form'):
        respostas = {}
        for i, aspecto in enumerate(ASPECTOS_AVALIACAO):
            respostas[f"aspecto_{i+1}"] = st.radio(
                label=aspecto["pergunta"],
                options=aspecto["opcoes"],
                horizontal=True,
                key=f"q_{i}"
            )
        
        # Botões de submissão e pulo dentro do formulário
        col1, col2, _ = st.columns([1, 1, 5])
        submitted = col1.form_submit_button("Salvar Avaliação")
        skipped = col2.form_submit_button("Pular Artigo")

    # --- LÓGICA DE SALVAMENTO ---
    if submitted or skipped:
        titulo_atual = artigo_para_avaliar['Title']
        abstract_atual = artigo_para_avaliar['Abstract']
        
        # Verifica se o artigo já existe no df_resultados
        if titulo_atual not in df_resultados['Title'].values:
            # Adiciona nova linha se não existir
            nova_linha = pd.DataFrame([{"Title": titulo_atual, "Abstract": abstract_atual}])
            df_resultados = pd.concat([df_resultados, nova_linha], ignore_index=True)

        idx_linha = df_resultados[df_resultados['Title'] == titulo_atual].index[0]

        # Salva as respostas
        for i, aspecto in enumerate(ASPECTOS_AVALIACAO):
            nome_coluna = f"{avaliador_cpf}/Aspecto {i+1}"
            valor = respostas[f"aspecto_{i+1}"] if submitted else "PULOU" # Marca como PULOU se o botão for clicado
            df_resultados.loc[idx_linha, nome_coluna] = valor

        # Atualiza a planilha no Google Sheets
        try:
            worksheet_resultados = client.open_by_url(RESULTS_SHEET_URL).get_worksheet(0)
            set_with_dataframe(worksheet_resultados, df_resultados, include_index=False)
            st.success("Sua avaliação foi salva com sucesso!")
            # Aguarda um pouco para o usuário ver a mensagem antes de recarregar
            import time
            time.sleep(1)
            st.rerun()

        except Exception as e:
            st.error(f"Ocorreu um erro ao salvar na planilha: {e}")


if __name__ == "__main__":
    main()