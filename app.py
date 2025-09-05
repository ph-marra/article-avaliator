import streamlit as st
import pandas as pd
import gspread
from gspread_dataframe import set_with_dataframe
from oauth2client.service_account import ServiceAccountCredentials
import random
import time
from datetime import datetime

# Import configurations from config.py
from config import (
    SOURCE_SHEET_URL,
    RESULTS_SHEET_URL,
    AVALIADORES,
    ASPECTOS_AVALIACAO,
    COLUNAS_ORDENACAO_FALLBACK,
    ORDENS_ORDENACAO_FALLBACK
)

st.set_page_config(layout="wide", page_title="Article Evaluation Tool")

# Defines the scope for the Google API
SCOPE = [
    "https://spreadsheets.google.com/feeds",
    'https://www.googleapis.com/auth/spreadsheets',
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/drive"
]

@st.cache_resource
def get_gspread_client():
    """Connects to Google Sheets using service account credentials."""
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", SCOPE)
    client = gspread.authorize(creds)
    return client

def get_sheet_as_df(client, sheet_url, sheet_name=None):
    """Loads a specific sheet (or the first one) from a spreadsheet as a DataFrame."""
    try:
        sheet = client.open_by_url(sheet_url)
        if sheet_name:
            worksheet = sheet.worksheet(sheet_name)
        else:
            worksheet = sheet.get_worksheet(0)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception as e:
        st.error(f"Error loading spreadsheet '{sheet_url}'. Check the URL and share permissions. Error: {e}")
        return pd.DataFrame()

@st.cache_data
def get_all_articles(_client, sheet_url):
    """Loads and cleans articles from all sheets in a spreadsheet."""
    try:
        spreadsheet = _client.open_by_url(sheet_url)
        all_dfs = []
        for worksheet in spreadsheet.worksheets():
            data = worksheet.get_all_records()
            if data:
                all_dfs.append(pd.DataFrame(data))
        
        if not all_dfs:
            st.warning("No data found in the source spreadsheet.")
            return pd.DataFrame()

        full_df = pd.concat(all_dfs, ignore_index=True)

        # Clean 'Year' and 'Citations' columns, filling empty/invalid values with 0
        for col in ['Year', 'Citations']:
            if col in full_df.columns:
                full_df[col] = pd.to_numeric(full_df[col], errors='coerce').fillna(0).astype(int)

        must_exist = ['Title', 'Abstract'] + [col for col in COLUNAS_ORDENACAO_FALLBACK if col]
        missing_cols = [col for col in must_exist if col not in full_df.columns]

        if missing_cols:
            st.error(f"The following required columns were not found in the source spreadsheet: {missing_cols}")
            return pd.DataFrame()
            
        return full_df.drop_duplicates(subset=["Title"])
    except Exception as e:
        st.error(f"Error loading the source spreadsheet '{sheet_url}'. Error: {e}")
        return pd.DataFrame()

def select_next_article(reviewer_cpf, df_articles, df_results):
    """Decides which article to show to the reviewer from the provided DataFrame."""
    if df_articles.empty:
        return None

    reviewer_cols = [col for col in df_results.columns if col.startswith(f"{reviewer_cpf}/")]
    if not reviewer_cols:
        reviewed_by_user = set()
    else:
        reviewed_by_user = set(df_results[df_results[reviewer_cols].notna().any(axis=1)]['Title'])

    other_reviewers_cpfs = list(AVALIADORES.keys())
    other_reviewers_cpfs.remove(reviewer_cpf)
    
    other_cols = []
    for cpf in other_reviewers_cpfs:
        other_cols.extend([col for col in df_results.columns if col.startswith(f"{cpf}/")])

    if other_cols:
        reviewed_by_others = set(df_results[df_results[other_cols].notna().any(axis=1)]['Title'])
        priority_to_review = list(reviewed_by_others - reviewed_by_user)
        # Ensure priority articles are also within the filtered list
        priority_to_review = [title for title in priority_to_review if title in df_articles['Title'].values]
        if priority_to_review:
            selected_title = random.choice(priority_to_review)
            return df_articles[df_articles['Title'] == selected_title].iloc[0]

    titles_in_results = set(df_results['Title'])
    new_titles = set(df_articles['Title']) - titles_in_results - reviewed_by_user
    
    if not new_titles:
        return None

    df_new = df_articles[df_articles['Title'].isin(list(new_titles))]
    
    df_sorted = df_new.sort_values(
        by=COLUNAS_ORDENACAO_FALLBACK,
        ascending=ORDENS_ORDENACAO_FALLBACK
    )
    
    return df_sorted.iloc[0]


def main():
    st.title("Scientific Article Evaluation Platform")

    if 'editing_title' not in st.session_state:
        st.session_state.editing_title = None

    if 'user_cpf' not in st.session_state:
        st.subheader("Reviewer Login")
        cpf_input = st.text_input("Enter your CPF (numbers only):")
        name_input = st.text_input("Enter your Full Name:")
        
        if st.button("Login"):
            if cpf_input in AVALIADORES and AVALIADORES[cpf_input].lower() == name_input.lower():
                st.session_state.user_cpf = cpf_input
                st.session_state.user_name = AVALIADORES[cpf_input]
                st.rerun()
            else:
                st.error("Invalid CPF or Name. Please check the data and try again.")
        st.stop()

    reviewer_cpf = st.session_state.user_cpf
    reviewer_name = st.session_state.user_name
    st.sidebar.success(f"Logged in as: **{reviewer_name}**")
    if st.sidebar.button("Logout"):
        del st.session_state.user_cpf
        del st.session_state.user_name
        st.session_state.editing_title = None
        st.rerun()

    client = get_gspread_client()
    df_articles = get_all_articles(client, SOURCE_SHEET_URL)
    df_results = get_sheet_as_df(client, RESULTS_SHEET_URL)

    if df_articles.empty:
        st.warning("Could not load articles. Please check the configuration.")
        st.stop()
        
    if df_results.empty:
        df_results = pd.DataFrame(columns=["Title", "Abstract"])

    # --- FILTERS FOR NEW ARTICLES ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Filter New Articles")

    min_year, max_year = int(df_articles['Year'].min()), int(df_articles['Year'].max())
    min_cites, max_cites = int(df_articles['Citations'].min()), int(df_articles['Citations'].max())

    year_range = st.sidebar.slider(
        "Filter by Publication Year:",
        min_value=min_year,
        max_value=max_year,
        value=(min_year, max_year)
    )
    citation_range = st.sidebar.slider(
        "Filter by Number of Citations:",
        min_value=min_cites,
        max_value=max_cites,
        value=(min_cites, max_cites)
    )
    df_articles_filtered = df_articles[
        (df_articles['Year'] >= year_range[0]) &
        (df_articles['Year'] <= year_range[1]) &
        (df_articles['Citations'] >= citation_range[0]) &
        (df_articles['Citations'] <= citation_range[1])
    ]

    # --- REVIEW PAST EVALUATIONS SECTION ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("Review Past Evaluations")
    
    # ... (Rest of the sidebar logic for reviewing remains the same)
    reviewer_cols = [col for col in df_results.columns if col.startswith(f"{reviewer_cpf}/")]
    df_user_evaluations = pd.DataFrame()
    if reviewer_cols:
        df_user_evaluations = df_results[df_results[reviewer_cols].notna().any(axis=1)].copy()

    if not df_user_evaluations.empty:
        show_skipped_only = st.sidebar.checkbox("Show only skipped articles")

        df_display = df_user_evaluations
        if show_skipped_only:
            reviewer_aspect_cols = [col for col in reviewer_cols if "Aspect" in col]
            if reviewer_aspect_cols:
                skipped_mask = df_display[reviewer_aspect_cols].eq("SKIPPED").any(axis=1)
                df_display = df_display[skipped_mask]
            else:
                df_display = pd.DataFrame()

        reviewer_date_col = f"{reviewer_cpf}/EvaluationDate"
        titles_to_display = []
        selectbox_label = "Filtered Articles:"
        
        if reviewer_date_col in df_display.columns:
            date_series = pd.to_datetime(df_display[reviewer_date_col], errors='coerce')
            valid_dates = date_series.dropna()
            unique_days = sorted(valid_dates.dt.date.unique(), reverse=True)

            if unique_days:
                selected_day = st.sidebar.date_input(
                    "Filter by evaluation date:",
                    value=unique_days[0],
                    min_value=unique_days[-1],
                    max_value=unique_days[0]
                )
                day_mask = (date_series.dt.date == selected_day)
                df_final_display = df_display[day_mask]
                titles_to_display = df_final_display['Title'].tolist()
                selectbox_label = f"Articles from {selected_day.strftime('%Y-%m-%d')}:"
            else:
                titles_to_display = df_display['Title'].tolist()
                selectbox_label = "Filtered Articles (no date available):"
        else:
            titles_to_display = df_display['Title'].tolist()
        
        if titles_to_display:
            article_to_review = st.sidebar.selectbox(
                label=selectbox_label,
                options=[""] + titles_to_display
            )
            if st.sidebar.button("Load for Editing"):
                if article_to_review:
                    st.session_state.editing_title = article_to_review
                    st.rerun()
                else:
                    st.sidebar.warning("Please select an article from the list.")
        else:
            st.sidebar.info("No evaluations found for the selected filters.")
    else:
        st.sidebar.info("You have not completed any evaluations yet.")

    # --- MAIN PAGE LOGIC ---
    if st.session_state.editing_title:
        st.info(f"You are editing the evaluation for: **{st.session_state.editing_title}**")
        if st.button("⬅️ Back to Reviewing New Articles"):
            st.session_state.editing_title = None
            st.rerun()
        
        title_in_edit = st.session_state.editing_title
        # Use the original df_articles to find the article to prevent filtering issues
        article_to_evaluate = df_articles[df_articles['Title'] == title_in_edit].iloc[0]
        
        old_answers = {}
        results_row_idx = df_results[df_results['Title'] == title_in_edit].index[0]
        
        for i, aspect in enumerate(ASPECTOS_AVALIACAO):
            col_name = f"{reviewer_cpf}/Aspect {i+1}"
            if col_name in df_results.columns:
                old_answers[f"aspect_{i+1}"] = df_results.loc[results_row_idx, col_name]
    else:
        # Pass the newly filtered dataframe to the selection logic
        article_to_evaluate = select_next_article(reviewer_cpf, df_articles_filtered, df_results)

    if article_to_evaluate is None and not st.session_state.editing_title:
        st.info("No articles match your current filter criteria, or all available articles have been reviewed.")
        st.success("🎉 Congratulations! There are no new articles in the queue for you at this time.")
        st.stop()

    st.markdown("---")
    st.header(article_to_evaluate['Title'])
    
    col1, col2 = st.columns(2)
    with col1:
        if 'Year' in article_to_evaluate and pd.notna(article_to_evaluate['Year']):
            st.markdown(f"**Year:** {article_to_evaluate['Year']}")
    with col2:
        if 'Citations' in article_to_evaluate and pd.notna(article_to_evaluate['Citations']):
            st.markdown(f"**Citations:** {article_to_evaluate['Citations']}")

    with st.expander("Click to see the Abstract"):
        st.write(article_to_evaluate['Abstract'])
    st.markdown("---")
    
    st.subheader("Evaluation Form")
    
    with st.form(key='evaluation_form'):
        responses = {}
        for i, aspect in enumerate(ASPECTOS_AVALIACAO):
            default_index = 0
            if st.session_state.editing_title:
                old_answer = old_answers.get(f"aspect_{i+1}")
                if old_answer in aspect["opcoes"]:
                    default_index = aspect["opcoes"].index(old_answer)

            responses[f"aspect_{i+1}"] = st.radio(
                label=aspect["pergunta"],
                options=aspect["opcoes"],
                horizontal=True,
                key=f"q_{i}",
                index=default_index
            )
        
        col1, col2, _ = st.columns([1.5, 1, 5])
        btn_text = "Update Evaluation" if st.session_state.editing_title else "Save Evaluation"
        submitted = col1.form_submit_button(btn_text)
        
        skipped = False
        if not st.session_state.editing_title:
            skipped = col2.form_submit_button("Skip Article")

    if submitted or skipped:
        current_title = article_to_evaluate['Title']
        current_abstract = article_to_evaluate['Abstract']
        
        if current_title not in df_results['Title'].values:
            new_row = pd.DataFrame([{"Title": current_title, "Abstract": current_abstract}])
            df_results = pd.concat([df_results, new_row], ignore_index=True)

        row_idx = df_results[df_results['Title'] == current_title].index[0]

        date_col = f"{reviewer_cpf}/EvaluationDate"
        if date_col not in df_results.columns or pd.isna(df_results.loc[row_idx, date_col]):
            df_results.loc[row_idx, date_col] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for i, aspect in enumerate(ASPECTOS_AVALIACAO):
            col_name = f"{reviewer_cpf}/Aspect {i+1}"
            value = responses[f"aspect_{i+1}"] if submitted else "SKIPPED"
            df_results.loc[row_idx, col_name] = value

        try:
            results_worksheet = client.open_by_url(RESULTS_SHEET_URL).get_worksheet(0)
            set_with_dataframe(results_worksheet, df_results, include_index=False)
            
            success_msg = "Your evaluation was successfully updated!" if st.session_state.editing_title else "Your evaluation was successfully saved!"
            st.success(success_msg)
            st.session_state.editing_title = None
            time.sleep(1.5)
            st.rerun()

        except Exception as e:
            st.error(f"An error occurred while saving to the spreadsheet: {e}")

if __name__ == "__main__":
    main()