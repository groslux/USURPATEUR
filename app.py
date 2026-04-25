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
    # 3. STRATÉGIE DE CHASSE (MULTI-REQUÊTES)
    # ==========================================
    # On définit des thèmes de recherche simples pour ne pas perdre Google
    SEARCH_THEMES = [
        "CSSF Luxembourg supervised",
        "CSSF Luxembourg authorized",
        "CSSF Luxembourg registered",
        "CSSF Luxembourg regulated",
        "CSSF Luxembourg AIFM",
        "CSSF Luxembourg RAIF",
        "CSSF Luxembourg GFIA",
        "CSSF Luxembourg SCSP",
        "CSSF Luxembourg SCS",
        "CSSF Luxembourg authorized manager"
    ]

    def run_multi_theme_hunt():
        api_key = st.secrets.get("SERPER_API_KEY")
        if not api_key:
            st.error("API Key manquante dans les Secrets Streamlit.")
            return []
            
        url = "https://google.serper.dev/search"
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        all_results = {}

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, theme in enumerate(SEARCH_THEMES):
            status_text.text(f"Recherche en cours : {theme}...")
            # On exclut le site officiel pour trouver les autres
            payload = {"q": f"{theme} -site:cssf.lu", "num": 20}
            try:
                r = requests.post(url, headers=headers, json=payload)
                organic = r.json().get('organic', [])
                for res in organic:
                    all_results[res['link']] = res # Dédoublonnage par lien
            except Exception as e:
                st.error(f"Erreur sur le thème {theme}: {e}")
            
            progress_bar.progress((i + 1) / len(SEARCH_THEMES))
        
        status_text.text("Analyse des résultats terminée.")
        return list(all_results.values())

    # ==========================================
    # 4. INTERFACE ET ANALYSE
    # ==========================================
    st.title("🕵️‍♂️ CSSF Hunter : Full Internet Active Scan")
    st.markdown("Recherche globale par thèmes : `AIFM, GFIA, RAIF, SCSP, SCS` + Supervision.")

    if st.button("🚀 Lancer le Scan Global (Active Hunting)"):
        raw_hits = run_multi_theme_hunt()
        
        if not raw_hits:
            st.warning("Aucun résultat trouvé. Vérifiez votre clé API Serper.")
        else:
            alerts = []

            for res in raw_hits:
                # 1. Extraction du domaine
                domain = urlparse(res['link']).netloc
                
                # 2. Extraction du nom probable (nettoyage titre)
                potential_name = res['title'].split('|')[0].split('-')[0].split(':')[0].strip()
                
                # 3. Fuzzy Matching (Comparaison avec les 3 CSV)
                # On utilise token_set_ratio car les noms de fonds sont souvent longs
                best_match, score = process.extractOne(potential_name, official_names, scorer=fuzz.token_set_ratio)
                
                # 4. Détermination du Risque
                if score < 50:
                    risk, color, priority = "🚨 CRITIQUE (Inconnu)", "#d32f2f", 1
                elif score < 85:
                    risk, color, priority = "⚠️ SUSPECT (Clonage ?)", "#f57c00", 2
                else:
                    risk, color, priority = "✅ LÉGITIME (Match)", "#388e3c", 3

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

            # Tri : Critiques et Suspects en haut
            alerts = sorted(alerts, key=lambda x: x['priority'])

            st.write(f"### 🛡️ Résultats du scan ({len(alerts)} sites analysés)")
            
            for a in alerts:
                # On affiche les suspects et critiques de manière détaillée
                if a['priority'] < 3:
                    with st.container():
                        st.markdown(f"""
                        <div style="border-left: 10px solid {a['color']}; padding: 15px; margin: 10px 0; background-color: #f9f9f9; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.1);">
                            <div style="display: flex; justify-content: space-between;">
                                <strong style="color: {a['color']}; font-size: 1.1em;">{a['risk']}</strong>
                                <span style="background: #eee; padding: 2px 8px; border-radius: 4px; font-family: monospace;">{a['domain']}</span>
                            </div>
                            <h3 style="margin: 10px 0;"><a href="{a['link']}" target="_blank" style="text-decoration:none; color:#0066cc;">{a['found_name']}</a></h3>
                            <p style="color: #444; font-size: 0.9em; line-height: 1.4;">{a['snippet']}</p>
                            <div style="margin-top: 10px; font-size: 0.85em; color: #666; border-top: 1px solid #ddd; padding-top: 5px;">
                                <b>Analyse des registres :</b> {a['score']}% de correspondance avec l'entité officielle : <code>{a['best_match']}</code>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Les légitimes sont rangés dans des menus déroulants pour ne pas polluer
                    with st.expander(f"✅ {a['domain']} ({a['found_name']}) - Match {a['score']}%"):
                        st.write(f"**Titre complet :** {a['title']}")
                        st.write(f"**Lien :** {a['link']}")
                        st.write(f"**Snippet :** {a['snippet']}")

    st.sidebar.info(f"Base de données : {len(official_names)} entités AIFM chargées.")
