import streamlit as st
import pandas as pd
import requests
import re
from thefuzz import fuzz, process

# ==========================================
# 1. SÉCURITÉ ET ACCÈS
# ==========================================
st.set_page_config(page_title="CSSF Global Hunter", layout="wide", page_icon="🕵️‍♂️")

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
    # 2. CHARGEMENT DES CSV
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
        # On garde une version propre pour le matching
        full_df['name_clean'] = full_df['Name'].astype(str).str.lower().str.replace(r'[^a-z0-9 ]', '', regex=True).str.strip()
        return full_df

    db = load_db()
    official_names = db['Name'].tolist()

    # ==========================================
    # 3. MOTS-CLÉS DE CHASSE (MULTILINGUE)
    # ==========================================
    # Succession de mots pour la requête Google
    fr = "supervisé OR autorisé OR enregistré OR régulé OR agréé OR surveillance"
    en = "supervised OR authorized OR registered OR regulated OR licensed OR supervision"
    es = "supervisado OR autorizado OR registrado OR regulado OR supervisión"
    it = "supervisionato OR autorizzato OR registrato OR regolato OR vigilanza"
    
    GLOBAL_QUERY = f'Luxembourg CSSF ({fr} OR {en} OR {es} OR {it}) -site:cssf.lu'

    # ==========================================
    # 4. FONCTION DE RECHERCHE ET ANALYSE
    # ==========================================
    def run_global_hunt():
        api_key = st.secrets.get("SERPER_API_KEY")
        url = "https://google.serper.dev/search"
        # On demande 40 résultats pour avoir une large vue
        payload = {"q": GLOBAL_QUERY, "num": 40}
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        
        try:
            r = requests.post(url, headers=headers, json=payload)
            return r.json().get('organic', [])
        except:
            return []

    # ==========================================
    # 5. INTERFACE ET LOGIQUE DE RANKING
    # ==========================================
    st.title("🕵️‍♂️ CSSF Global Hunting Mode")
    st.markdown("Ce mode scanne Google pour trouver des entités mentionnant la CSSF et les compare à vos listes officielles via **Fuzzy Matching**.")

    if st.button("🚀 Lancer le Scan Global Internet"):
        results = run_global_hunt()
        
        if not results:
            st.warning("Aucun résultat renvoyé par le moteur de recherche.")
        else:
            alerts = []

            for res in results:
                # 1. Extraire le nom probable du site (avant le premier séparateur)
                potential_name = res['title'].split('|')[0].split('-')[0].split(':')[0].strip()
                
                # 2. Fuzzy Matching : On cherche le nom le plus proche dans la DB
                # On récupère le meilleur match et son score (0-100)
                best_match, score = process.extractOne(potential_name, official_names, scorer=fuzz.token_set_ratio)
                
                # 3. Calcul du niveau d'alerte
                # Si score > 90 : Probablement l'entité officielle (Risque Faible)
                # Si score entre 60 et 89 : Nom très proche mais pas exact (Risque Moyen/Clonage)
                # Si score < 60 : Aucune correspondance trouvée (Risque Fort / Entité Inconnue)
                
                risk_level = "FAIBLE"
                risk_color = "blue"
                priority = 3
                
                if score < 60:
                    risk_level = "CRITIQUE (Inconnu)"
                    risk_color = "red"
                    priority = 1
                elif score < 90:
                    risk_level = "SUSPECT (Nom proche)"
                    risk_color = "orange"
                    priority = 2

                alerts.append({
                    "title": res['title'],
                    "link": res['link'],
                    "snippet": res.get('snippet', ''),
                    "found_name": potential_name,
                    "best_match": best_match,
                    "match_score": score,
                    "risk": risk_level,
                    "color": risk_color,
                    "priority": priority
                })

            # Tri par priorité (Critique en premier)
            alerts = sorted(alerts, key=lambda x: x['priority'])

            # Affichage
            for a in alerts:
                with st.container():
                    st.markdown(f"""
                    <div style="border-left: 10px solid {a['color']}; padding: 15px; margin: 10px 0; background-color: #f0f2f6; border-radius: 10px;">
                        <span style="color: {a['color']}; font-weight: bold;">[RISQUE {a['risk']}]</span>
                        <h3 style="margin: 5px 0;"><a href="{a['link']}" target="_blank" style="text-decoration: none; color: #1f77b4;">{a['found_name']}</a></h3>
                        <p style="font-size: 0.9em; color: #555;"><strong>Titre complet :</strong> {a['title']}</p>
                        <p style="margin: 5px 0;"><i>"{a['snippet']}"</i></p>
                        <hr style="margin: 10px 0; border: 0; border-top: 1px solid #ddd;">
                        <p style="margin: 0; font-size: 0.85em;">
                            <strong>Analyse :</strong> Correspondance de <b>{a['match_score']}%</b> avec l'entité officielle : <code>{a['best_match']}</code>
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

    st.sidebar.info(f"Base de données : {len(official_names)} entités officielles chargées.")
