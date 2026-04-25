import streamlit as st
import pandas as pd
import requests
import re
from urllib.parse import urlparse
from thefuzz import fuzz, process

# ==========================================
# 1. CONFIGURATION ET SÉCURITÉ
# ==========================================
st.set_page_config(page_title="CSSF Hunter - Global Scan", layout="wide", page_icon="🕵️‍♂️")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]: return True

    st.title("🔐 Accès Restreint")
    pwd = st.text_input("Code d'accès :", type="password")
    if st.button("Se connecter"):
        if pwd == st.secrets.get("APP_PASSWORD", "admin"):
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Accès refusé.")
    return False

if check_password():
    # ==========================================
    # 2. CHARGEMENT DES REGISTRES (CSV)
    # ==========================================
    @st.cache_data
    def load_db():
        files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_csv(f))
            except: pass
        if not dfs: return pd.DataFrame(columns=['Name'])
        full_df = pd.concat(dfs, ignore_index=True)
        full_df['Name'] = full_df['Name'].astype(str)
        return full_df

    db = load_db()
    official_names = db['Name'].tolist()

    # ==========================================
    # 3. CHUNKS DE CHASSE (AVEC NOUVEAUX MOTS-CLÉS)
    # ==========================================
    # Ajout de AIFM, GFIA, RAIF, SCSP, SCS
    extra_kws = "AIFM OR GFIA OR RAIF OR SCSP OR SCS"
    
    SEARCH_CHUNKS = {
        "Français": f"Luxembourg CSSF (supervisé OR autorisé OR enregistré OR régulé OR agréé) ({extra_kws})",
        "English": f"Luxembourg CSSF (supervised OR authorized OR registered OR regulated OR licensed) ({extra_kws})",
        "Español": f"Luxembourg CSSF (supervisado OR autorizado OR registrado OR regulado) ({extra_kws})",
        "Italiano": f"Luxembourg CSSF (supervisionato OR autorizzato OR registrato OR regolato) ({extra_kws})"
    }

    # ==========================================
    # 4. FONCTIONS DE CHASSE
    # ==========================================
    def run_chunked_hunt():
        api_key = st.secrets.get("SERPER_API_KEY")
        if not api_key:
            st.error("API Key manquante.")
            return []
            
        url = "https://google.serper.dev/search"
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        all_results = {}

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, (lang, query) in enumerate(SEARCH_CHUNKS.items()):
            status_text.text(f"Scan en cours ({lang})...")
            # Requête excluant le site officiel
            payload = {"q": f"{query} -site:cssf.lu", "num": 25}
            try:
                r = requests.post(url, headers=headers, json=payload)
                organic = r.json().get('organic', [])
                for res in organic:
                    all_results[res['link']] = res
            except Exception as e:
                st.error(f"Erreur {lang}: {e}")
            progress_bar.progress((i + 1) / len(SEARCH_CHUNKS))
        
        status_text.text("Scan Web terminé. Analyse des domaines...")
        return list(all_results.values())

    # ==========================================
    # 5. INTERFACE ET RÉSULTATS
    # ==========================================
    st.title("🕵️‍♂️ CSSF Hunter : Full Internet Scan")
    st.markdown("Recherche de successions de mots-clés : `AIFM, GFIA, RAIF, SCSP, SCS` combinés aux termes de supervision.")

    if st.button("🚀 Lancer la Chasse (Global Search)"):
        raw_hits = run_chunked_hunt()
        
        if not raw_hits:
            st.warning("Aucun résultat suspect.")
        else:
            alerts = []

            for res in raw_hits:
                # Extraction du nom de domaine
                domain = urlparse(res['link']).netloc
                
                # Extraction du nom potentiel depuis le titre
                potential_name = res['title'].split('|')[0].split('-')[0].split(':')[0].strip()
                
                # Fuzzy Matching
                best_match, score = process.extractOne(potential_name, official_names, scorer=fuzz.token_set_ratio)
                
                # Détermination du Risque
                if score < 50:
                    risk, color, priority = "CRITIQUE (Inconnu)", "red", 1
                elif score < 90:
                    risk, color, priority = "SUSPECT (Clonage ?)", "orange", 2
                else:
                    risk, color, priority = "LÉGITIME (Vérifié)", "green", 3

                alerts.append({
                    "domain": domain,
                    "title": res['title'],
                    "link": res['link'],
                    "snippet": res.get('snippet', ''),
                    "found_name": potential_name,
                    "best_match": best_match,
                    "score": score,
                    "risk": risk,
                    "color": color,
                    "priority": priority
                })

            # Tri par priorité (Critiques en premier)
            alerts = sorted(alerts, key=lambda x: x['priority'])

            st.write(f"### 🛡️ Résultats de l'analyse")
            
            for a in alerts:
                if a['priority'] < 3: # On met en avant les suspects et critiques
                    with st.container():
                        st.markdown(f"""
                        <div style="border-left: 10px solid {a['color']}; padding: 15px; margin: 10px 0; background-color: #f1f3f6; border-radius: 8px;">
                            <div style="display: flex; justify-content: space-between;">
                                <strong style="color: {a['color']};">{a['risk']}</strong>
                                <code style="background: #e1e4e8; padding: 2px 5px;">Site : {a['domain']}</code>
                            </div>
                            <h3 style="margin: 10px 0;"><a href="{a['link']}" target="_blank" style="text-decoration:none; color:#1f77b4;">{a['found_name']}</a></h3>
                            <p style="color: #444; font-size: 0.95em;"><i>"{a['snippet']}"</i></p>
                            <div style="margin-top: 10px; font-size: 0.85em; border-top: 1px solid #ccc; padding-top: 5px;">
                                <b>Analyse Registry :</b> {a['score']}% de ressemblance avec <code>{a['best_match']}</code>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    with st.expander(f"✅ {a['domain']} - {a['found_name']} (Match: {a['score']}%)"):
                        st.write(f"Lien : {a['link']}")
                        st.write(f"Snippet : {a['snippet']}")

    st.sidebar.info(f"Base chargée : {len(official_names)} entités AIFM.")
