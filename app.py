import streamlit as st
import pandas as pd
import requests
import re

# =========================================================
# CONFIGURATION ET SÉCURITÉ (SECRETS)
# =========================================================
# On récupère les clés depuis l'interface Streamlit Cloud
SERPER_API_KEY = st.secrets.get("SERPER_API_KEY")
APP_PASSWORD = st.secrets.get("APP_PASSWORD")

def check_password():
    """Retourne True si l'utilisateur a saisi le bon mot de passe."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False

    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Accès Restreint")
    password_input = st.text_input("Veuillez entrer le mot de passe pour accéder à l'audit :", type="password")
    
    if st.button("Se connecter"):
        if password_input == APP_PASSWORD:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    return False

# On ne lance l'appli que si le mot de passe est bon
if check_password():
    
    st.set_page_config(page_title="CSSF Watchdog - Anti-Fraud", layout="wide")

    # --- CHARGEMENT DES DONNÉES (TES CSV) ---
    @st.cache_data
    def load_cssf_database():
        files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
        combined_list = []
        for f in files:
            try:
                combined_list.append(pd.read_csv(f))
            except:
                continue
        return pd.concat(combined_list, ignore_index=True) if combined_list else pd.DataFrame()

    db = load_cssf_database()

    # --- LOGIQUE DE RECHERCHE ---
    def run_web_audit(q):
        url = "https://google.serper.dev/search"
        payload = {"q": q, "num": 10}
        headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
        try:
            r = requests.post(url, headers=headers, json=payload)
            return r.json().get('organic', [])
        except:
            return []

    # --- INTERFACE ---
    st.title("🕵️‍♂️ CSSF Compliance Checker (Zone Sécurisée)")
    
    target = st.text_input("Nom de la société à vérifier :")
    if target:
        # Recherche simplifiée
        match = db[db['Name'].str.contains(target, case=False, na=False)]
        
        if not match.empty:
            st.success("✅ Entité Officielle trouvée.")
            st.dataframe(match)
        else:
            st.error("❌ Entité ABSENTE des listes.")
            st.info("Recherche de mentions suspectes sur le web...")
            hits = run_web_audit(f'"{target}" "supervised by the CSSF" -site:cssf.lu')
            for h in hits:
                st.warning(f"🚩 Site suspect : {h['link']}")
