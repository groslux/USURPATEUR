import streamlit as st
import pandas as pd
import requests
import re
from thefuzz import fuzz, process

# ==========================================
# 1. SÉCURITÉ ET ACCÈS
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
    # 2. CHARGEMENT DES CSV ET PRÉPARATION
    # ==========================================
    @st.cache_data
    def load_db():
        files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
        dfs = []
        for f in files:
            try:
                df = pd.read_csv(f)
                dfs.append(df)
            except: pass
        if not dfs: return pd.DataFrame(columns=['Name'])
        full_df = pd.concat(dfs, ignore_index=True)
        # On nettoie les noms pour le matching
        full_df['Name'] = full_df['Name'].astype(str)
        return full_df

    db = load_db()
    official_names = db['Name'].tolist()

    # ==========================================
    # 3. DÉFINITION DES CHUNKS (GROUPES DE RECHERCHE)
    # ==========================================
    # On divise par langue pour éviter des requêtes trop lourdes
    SEARCH_CHUNKS = {
        "Français": "Luxembourg CSSF (supervisé OR autorisé OR enregistré OR régulé OR agréé)",
        "English": "Luxembourg CSSF (supervised OR authorized OR registered OR regulated OR licensed)",
        "Español": "Luxembourg CSSF (supervisado OR autorizado OR registrado OR regulado OR supervisión)",
        "Italiano": "Luxembourg CSSF (supervisionato OR autorizzato OR registrato OR regolato OR vigilanza)"
    }

    # ==========================================
    # 4. MOTEUR DE CHASSE (CHUNKED SEARCH)
    # ==========================================
    def run_chunked_hunt():
        api_key = st.secrets.get("SERPER_API_KEY")
        if not api_key:
            st.error("API Key manquante dans les secrets.")
            return []
            
        url = "https://google.serper.dev/search"
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        all_results = {} # Utilisation d'un dict pour dédoublonner par URL

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, (lang, query) in enumerate(SEARCH_CHUNKS.items()):
            status_text.text(f"Scan en cours : {lang}...")
            # On demande 20 résultats par langue (donc 80 au total)
            payload = {"q": f"{query} -site:cssf.lu", "num": 20}
            try:
                r = requests.post(url, headers=headers, json=payload)
                organic = r.json().get('organic', [])
                for res in organic:
                    all_results[res['link']] = res # Dédoublonnage automatique par lien
            except Exception as e:
                st.error(f"Erreur sur le chunk {lang}: {e}")
            
            progress_bar.progress((i + 1) / len(SEARCH_CHUNKS))
        
        status_text.text("Scan terminé. Analyse des correspondances...")
        return list(all_results.values())

    # ==========================================
    # 5. INTERFACE
    # ==========================================
    st.title("🕵️‍♂️ CSSF Hunter : Scan Global Internet")
    st.markdown("""
    Cette version divise la recherche en 4 requêtes (FR, EN, ES, IT) pour contourner les limites de Google.
    Les noms détectés sont ensuite comparés à vos fichiers CSV via **Fuzzy Matching**.
    """)

    if st.button("🚀 Lancer la Chasse (Multi-Chunk Scan)"):
        raw_hits = run_chunked_hunt()
        
        if not raw_hits:
            st.warning("Aucun résultat suspect n'est ressorti des 4 scans.")
        else:
            alerts = []

            for res in raw_hits:
                # Nettoyage du titre pour isoler le nom
                potential_name = res['title'].split('|')[0].split('-')[0].split(':')[0].strip()
                
                # Fuzzy Match contre la DB (80% est un bon seuil pour le clonage)
                best_match, score = process.extractOne(potential_name, official_names, scorer=fuzz.token_set_ratio)
                
                # Calcul Risque
                if score < 55:
                    risk, color, priority = "CRITIQUE (Inconnu)", "red", 1
                elif score < 90:
                    risk, color, priority = "SUSPECT (Clonage ?)", "orange", 2
                else:
                    risk, color, priority = "LÉGITIME (Vérifié)", "green", 3

                alerts.append({
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

            # Tri : Critiques et Suspects en haut
            alerts = sorted(alerts, key=lambda x: x['priority'])

            st.write(f"### 🛡️ Résultats de l'analyse ({len(alerts)} sites détectés)")
            
            for a in alerts:
                # On n'affiche que les suspects et critiques pour plus de clarté
                if a['priority'] < 3:
                    with st.container():
                        st.markdown(f"""
                        <div style="border-left: 8px solid {a['color']}; padding: 15px; margin: 10px 0; background-color: #f8f9fa; border-radius: 5px; box-shadow: 2px 2px 5px rgba(0,0,0,0.05);">
                            <strong style="color: {a['color']};">{a['risk']}</strong> | Score Match : {a['score']}%<br>
                            <h4 style="margin: 5px 0;"><a href="{a['link']}" target="_blank">{a['found_name']}</a></h4>
                            <p style="color: #666; font-size: 0.9em; margin-bottom: 5px;"><i>"{a['snippet']}"</i></p>
                            <small>Nom officiel le plus proche : <b>{a['best_match']}</b></small>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    with st.expander(f"✅ {a['found_name']} (Vérifié - {a['score']}%)"):
                        st.write(f"Lien : {a['link']}")
                        st.write(f"Snippet : {a['snippet']}")

    st.sidebar.write(f"📊 Registres : {len(official_names)} entités.")
