import streamlit as st
import pandas as pd
import requests

# Configuration
st.set_page_config(page_title="CSSF Entity Verifier", layout="wide")

st.title("🛡️ Détecteur d'Entités CSSF Non-Autorisées")
st.markdown("""
Cette application compare les résultats de recherche web avec les listes officielles (AIFM Authorized, Registered et Succursales) 
pour identifier des entités qui prétendraient être supervisées sans l'être.
""")

# --- CHARGEMENT DES FICHIERS LOCAUX ---
@st.cache_data
def load_all_data():
    files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
    dfs = []
    for f in files:
        try:
            temp_df = pd.read_csv(f)
            dfs.append(temp_df)
        except Exception as e:
            st.error(f"Erreur de lecture du fichier {f}: {e}")
    
    # Fusion des 3 listes
    full_df = pd.concat(dfs, ignore_index=True)
    # Nettoyage des noms pour la comparaison
    full_df['name_clean'] = full_df['Name'].astype(str).str.lower().str.strip()
    return full_df

white_list = load_all_data()

# --- FONCTION DE RECHERCHE WEB (via Serper.dev) ---
def web_audit(search_query):
    # Remplacez par votre clé API dans les secrets Streamlit
    api_key = st.secrets.get("SERPER_API_KEY", "VOTRE_CLE_API_ICI")
    url = "https://google.serper.dev/search"
    
    # Requête ciblée pour trouver des mentions de supervision CSSF hors site officiel
    payload = {
        "q": f'"{search_query}" "supervised by the CSSF" -site:cssf.lu',
        "num": 10
    }
    headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.json().get('organic', [])
    except:
        return []

# --- INTERFACE ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🔍 Recherche manuelle")
    search_term = st.text_input("Nom de l'entité à vérifier :", placeholder="Ex: Finance S.A.")
    
    if search_term:
        # Vérification Base de données
        matches = white_list[white_list['name_clean'].str.contains(search_term.lower(), na=False)]
        
        if not matches.empty:
            st.success(f"✅ Trouvé dans la liste officielle ({len(matches)} résultat(s))")
            st.dataframe(matches[['Type', 'Name', 'Address']])
        else:
            st.error("❌ ABSENT de la liste officielle de la CSSF.")
            st.warning("Prudence recommandée si cette entité prétend être supervisée.")

with col2:
    st.subheader("🌐 Scan Web (Anti-Clonage)")
    if search_term:
        with st.spinner("Audit du web en cours..."):
            web_results = web_audit(search_term)
            
            if web_results:
                st.write(f"Résultats mentionnant '{search_term}' et 'supervised by the CSSF' :")
                for res in web_results:
                    with st.expander(f"🚩 {res['title']}"):
                        st.write(f"**URL :** {res['link']}")
                        st.write(f"**Extrait :** {res.get('snippet', '')}")
                        st.info("Vérifiez si le domaine de ce site correspond à l'entité officielle.")
            else:
                st.info("Aucun site web suspect trouvé avec ces mots-clés exacts.")

# --- SCAN GLOBAL (Optionnel) ---
st.divider()
if st.button("🚀 Lancer un Scan Global (Découvrir de nouveaux suspects)"):
    st.write("Recherche de sites utilisant la mention 'supervised by the CSSF' hors registres...")
    results = web_audit("supervised by the CSSF") # Recherche large
    
    for res in results:
        # On vérifie si le titre du site contient une entité de notre liste
        found_in_list = any(name in res['title'].lower() for name in white_list['name_clean'].head(100)) # Exemple simplifié
        
        status = "⚠️ SUSPECT (Non identifié)" if not found_in_list else "✅ Probable Officiel"
        st.write(f"[{status}] {res['title']} - {res['link']}")
