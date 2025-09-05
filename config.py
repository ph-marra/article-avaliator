# config.py

# --- CONFIGURAÇÕES DO GOOGLE SHEETS ---
# Cole a URL completa da sua planilha de artigos aqui
SOURCE_SHEET_URL = "https://docs.google.com/spreadsheets/d/1kpLJ0AT6TBtZp9EIQhME48wNsA__limTVojXLk1JyfQ/edit?gid=186066836#gid=186066836"

# Cole a URL completa da sua planilha de resultados (inicialmente vazia)
RESULTS_SHEET_URL = "https://docs.google.com/spreadsheets/d/160jjyY1tbn1TmzTeoqLGtOV2Hk8e8YBcb3Al2T8K_so/edit?gid=0#gid=0"

# --- CONFIGURAÇÕES DOS AVALIADORES ---
# Adicione os nomes e CPFs dos avaliadores autorizados.
# O CPF será usado como identificador único.
AVALIADORES = {
    "10809607670": "Pedro Henrique Marra Araújo",
    "78142440644": "Viviane Olímpia Marra",
    # "55566677788": "Nome do Avaliador 2",
    # Adicione mais avaliadores aqui no formato "CPF": "NOME"
}

# --- CONFIGURAÇÕES DA AVALIAÇÃO ---
# Defina os aspectos a serem avaliados.
# Cada item é um dicionário com a 'pergunta' e as 'opcoes' da escala Likert de 5 pontos.
ASPECTOS_AVALIACAO = [
    {
        "pergunta": "Qual a relevância do problema de pesquisa abordado?",
        "opcoes": ["1 - Muito Baixa", "2 - Baixa", "3 - Neutra", "4 - Alta", "5 - Muito Alta"]
    },
    {
        "pergunta": "Qual a clareza da metodologia apresentada?",
        "opcoes": ["1 - Muito Ruim", "2 - Ruim", "3 - Regular", "4 - Boa", "5 - Excelente"]
    },
    {
        "pergunta": "O quão inovadora é a contribuição do artigo?",
        "opcoes": ["1 - Nada Inovadora", "2 - Pouco Inovadora", "3 - Neutro", "4 - Inovadora", "5 - Muito Inovadora"]
    },
    # Adicione mais perguntas aqui
]

# --- CONFIGURAÇÕES DA SELEÇÃO DE ARTIGOS ---

# Lista de colunas para ordenar. A primeira tem prioridade máxima.
COLUNAS_ORDENACAO_FALLBACK = ["Year", "Citations"]

# Lista de ordens correspondente. 
# False = Descendente (DESC), True = Ascendente (ASC).
ORDENS_ORDENACAO_FALLBACK = [False, True]