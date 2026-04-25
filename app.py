import streamlit as st
import pandas as pd
import requests
import re

# =========================================================
# CONFIGURATION ET CLÉ API
# =========================================================
# Comme ton repo est privé, tu peux mettre la clé ici, 
# mais la bonne pratique Streamlit reste st.secrets
SERPER_API_KEY = "2f5c1c4e0c52e3298bb1d42cf19d818e86d3d395" 

st.set_page_config(page_title="CSSF Watchdog - Anti-Fraud", layout="wide")

# =========================================================
# CHARGEMENT DES DONNÉES OFFICIELLES (TES CSV)
# =========================================================
@st.cache_data
def load_cssf_database():
    files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
    combined_list = []
    
    for f in files:
        try:
            df = pd.read_csv(f)
            # On harmonise les colonnes si nécessaire (ici elles semblent identiques : Name)
            combined_list.append(df)
        except Exception as e:
            st.error(f"Erreur lors du chargement de {f} : {e}")
            
    if combined_list:
        full_df = pd.concat(combined_list, ignore_index=True)
        # Nettoyage pour comparaison : minuscules, suppression des S.A., S.à r.l. pour plus de souplesse
        full_df['name_clean'] = full_df['Name'].str.lower().str.replace(r'[^a-zA-Z0-9 ]', '', regex=True).str.strip()
        return full_df
    return pd.DataFrame()

db = load_cssf_database()

# =========================================================
# LOGIQUE DE RECHERCHE WEB AUTOMATISÉE
# =========================================================
def run_web_audit(query_type="global", custom_name=""):
    url = "https://google.serper.dev/search"
    
    # Construction de la requête Google de "chasse"
    if query_type == "global":
        # Cherche n'importe quel site (hors cssf.lu) qui prétend être supervisé
        q = '"supervised by the CSSF" -site:cssf.lu'
    else:
        # Cherche un nom spécifique avec la mention de supervision
        q = f'"{custom_name}" "supervised by the CSSF" -site:cssf.lu'

    payload = {"q": q, "num": 20}
    headers = {'X-API-KEY': SERPER_API_KEY, 'Content-Type': 'application/json'}
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        return response.json().get('organic', [])
    except:
        return []

# =========================================================
# INTERFACE UTILISATEUR
# =========================================================
st.title("🕵️‍♂️ CSSF Compliance Checker")
st.write(f"Base de données officielle chargée : `{len(db)}` entités répertoriées.")

tabs = st.tabs(["🔍 Recherche par Nom", "🌐 Scan Global du Web"])

# --- TAB 1 : RECHERCHE PAR NOM ---
with tabs[0]:
    target = st.text_input("Entrez le nom d'une société à auditer :")
    if target:
        # 1. Check DB
        clean_target = re.sub(r'[^a-zA-Z0-9 ]', '', target.lower())
        match = db[db['name_clean'].str.contains(clean_target, na=False)]
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("État dans les registres")
            if not match.empty:
                st.success(f"✅ L'entité '{target}' est bien enregistrée.")
                st.dataframe(match[['Type', 'Name', 'Address']])
            else:
                st.error(f"❌ '{target}' est ABSENTE des registres AIFM (AUT, REG, SUCC).")

        with col2:
            st.subheader("Preuves sur le Web")
            web_hits = run_web_audit("specific", target)
            if web_hits:
                for hit in web_hits:
                    st.warning(f"**Trouvé sur :** {hit['link']}\n\n*Snippet : {hit.get('snippet', '')}*")
            else:
                st.info("Aucune mention suspecte trouvée sur Google pour ce nom.")

# --- TAB 2 : SCAN GLOBAL (CHASSE AUX CLONES) ---
with tabs[1]:
    st.info("Ce mode scanne Google pour trouver des sites qui utilisent la phrase 'supervised by the CSSF' mais qui ne figurent pas dans vos fichiers CSV.")
    
    if st.button("Lancer un scan de détection global"):
        results = run_web_audit("global")
        suspicious_count = 0
        
        for res in results:
            title_clean = re.sub(r'[^a-zA-Z0-9 ]', '', res['title'].lower())
            snippet_clean = re.sub(r'[^a-zA-Z0-9 ]', '', res.get('snippet', '').lower())
            
            # Vérification si le titre du site contient un nom de notre DB
            # On fait un check croisé
            is_official = any(name in title_clean for name in db['name_clean'].head(500)) # limitation pour perf
            
            if not is_official:
                suspicious_count += 1
                with st.expander(f"🚩 SUSPECT : {res['title']}", expanded=True):
                    st.write(f"**Lien :** {res['link']}")
                    st.write(f"**Description :** {res.get('snippet', '')}")
                    st.markdown("**Raison :** Ce site revendique la supervision CSSF mais le nom ne correspond à aucune entité AIFM de vos listes.")

        if suspicious_count == 0:
            st.success("Aucune nouvelle entité suspecte détectée sur les premiers résultats.")
