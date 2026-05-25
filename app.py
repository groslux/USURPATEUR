import streamlit as st
import pandas as pd
import requests
from urllib.parse import urlparse
from thefuzz import fuzz, process
from bs4 import BeautifulSoup

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
        # Ensure these CSV files are in the same directory as your app.py
        files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
        dfs = []
        for f in files:
            try:
                dfs.append(pd.read_csv(f))
            except Exception as e: 
                pass # Silently pass if a file is missing during MVP phase
        if not dfs: return pd.DataFrame(columns=['Name'])
        full_df = pd.concat(dfs, ignore_index=True)
        full_df['Name'] = full_df['Name'].astype(str)
        return full_df

    db = load_db()
    official_names = db['Name'].tolist()

    # ==========================================
    # 3. STRATÉGIE DE CHASSE & SCRAPING
    # ==========================================
    # Google Dorks for discovering targets
    SEARCH_THEMES = [
        "CSSF Luxembourg supervised",
        "CSSF Luxembourg regulated",
        "CSSF Luxembourg AIFM",
        "Alternative Investment Fund Manager Luxembourg",
        "CSSF Luxembourg CASP",           
        "crypto exchange Luxembourg",
        "VASP Luxembourg regulated"
    ]

    # Keyword Dictionaries for Deep Scraping
    CSSF_KEYWORDS = [
        "cssf", "commission de surveillance du secteur financier", 
        "regulated by", "agréé par", "supervisé par", "licence n°"
    ]
    CASP_KEYWORDS = [
        "casp", "vasp", "crypto", "bitcoin", "digital asset", 
        "crypto-actif", "exchange", "wallet", "staking"
    ]
    # Expanded AIFM keywords to catch unlicensed promoters
    AIFM_KEYWORDS = [
        "aifm", "alternative investment fund", "fonds d'investissement alternatif", 
        "raif", "fiar", "fonds d'investissement", "fund manager",
        "private placement", "capital raising", "investment vehicle", "fonds commun"
    ]

    def analyze_site_content(url):
        """Visits the page to check for false regulatory claims or silent CASP/AIFM services."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            response = requests.get(url, headers=headers, timeout=5) 
            soup = BeautifulSoup(response.text, 'html.parser')
            text_content = soup.get_text(separator=' ', strip=True).lower()
            
            claims_cssf = any(kw in text_content for kw in CSSF_KEYWORDS)
            offers_casp = any(kw in text_content for kw in CASP_KEYWORDS)
            offers_aifm = any(kw in text_content for kw in AIFM_KEYWORDS)
            
            return claims_cssf, offers_casp, offers_aifm
        except:
            return False, False, False # Fail silently on timeout/connection error

    def run_multi_theme_hunt():
        api_key = st.secrets.get("SERPER_API_KEY")
        if not api_key:
            st.error("API Key manquante. Veuillez configurer .streamlit/secrets.toml")
            return []
            
        url = "https://google.serper.dev/search"
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        all_results = {}

        progress_bar = st.progress(0)
        status_text = st.empty()

        for i, theme in enumerate(SEARCH_THEMES):
            status_text.text(f"Recherche SERP en cours : {theme}...")
            # Excluding cssf.lu to avoid polluting results with the official site
            payload = {"q": f"{theme} -site:cssf.lu", "num": 10} 
            try:
                r = requests.post(url, headers=headers, json=payload)
                organic = r.json().get('organic', [])
                for res in organic:
                    all_results[res['link']] = res
            except Exception as e:
                st.error(f"Erreur sur le thème {theme}: {e}")
            
            progress_bar.progress((i + 1) / len(SEARCH_THEMES))
        
        status_text.text("Recherche SERP terminée. Lancement de l'analyse HTML...")
        return list(all_results.values())

    # ==========================================
    # 4. INTERFACE ET MOTEUR D'ANALYSE DES RISQUES
    # ==========================================
    st.title("🕵️‍♂️ CSSF Hunter : Active OSINT Scanner")
    st.markdown("Recherche globale + Deep Scraping par thèmes : `AIFM, CASP, Crypto` + Supervision.")

    if st.button("🚀 Lancer le Scan Global (Active Hunting)", type="primary"):
        raw_hits = run_multi_theme_hunt()
        
        if not raw_hits:
            st.warning("Aucun résultat trouvé.")
        else:
            alerts = []
            
            st.info(f"🔍 {len(raw_hits)} liens trouvés. Début de l'inspection approfondie des sites web (Scraping)...")
            scrape_progress = st.progress(0)

            for idx, res in enumerate(raw_hits):
                # 1. Extraction et Nettoyage
                domain = urlparse(res['link']).netloc.replace("www.", "")
                potential_name = res['title'].split('|')[0].split('-')[0].split(':')[0].strip()
                
                # 2. Fuzzy Matching contre les CSV officiels
                best_match, score = process.extractOne(potential_name, official_names, scorer=fuzz.token_set_ratio)
                
                # 3. Deep Scraping (Checking for CSSF, CASP, and AIFM keywords in the HTML)
                claims_cssf, offers_casp, offers_aifm = analyze_site_content(res['link'])
                
                # 4. Détermination du Risque Multi-Facteurs
                if score < 50 and claims_cssf:
                    risk, color, priority = "🚨 CLONE REGLEMENTAIRE (Fausse Déclaration)", "#d32f2f", 1
                elif score < 50 and offers_aifm:
                    risk, color, priority = "🚨 UNREGISTERED AIFM (Activité Illicite/Non-Enregistrée)", "#8e24aa", 1
                elif score < 50 and offers_casp:
                    risk, color, priority = "🚨 UNREGISTERED CASP (Activité Silencieuse)", "#c2185b", 1
                elif score < 50:
                    risk, color, priority = "⚠️ INCONNU (A vérifier manuellement)", "#f57c00", 2
                elif score >= 50 and score < 85:
                    risk, color, priority = "⚠️ SUSPECT (Match Partiel de Nom)", "#ffb300", 3
                else:
                    risk, color, priority = "✅ LÉGITIME (Match DB Confirmé)", "#388e3c", 4

                alerts.append({
                    "domain": domain, "title": res['title'], "link": res['link'],
                    "snippet": res.get('snippet', ''), "found_name": potential_name,
                    "best_match": best_match, "score": score, "risk": risk,
                    "color": color, "priority": priority,
                    "claims": claims_cssf, "casp": offers_casp, "aifm": offers_aifm
                })
                
                scrape_progress.progress((idx + 1) / len(raw_hits))

            # Tri par priorité de risque pour afficher les problèmes en premier
            alerts = sorted(alerts, key=lambda x: x['priority'])

            st.write(f"### 🛡️ Résultats du scan ({len(alerts)} sites analysés)")
            
            for a in alerts:
                if a['priority'] <= 3:
                    # Affichage détaillé pour les entités non légitimes (Priorité 1, 2, 3)
                    with st.container():
                        st.markdown(f"""
                        <div style="border-left: 10px solid {a['color']}; padding: 15px; margin: 10px 0; background-color: #f9f9f9; border-radius: 8px; box-shadow: 1px 1px 3px rgba(0,0,0,0.1);">
                            <div style="display: flex; justify-content: space-between;">
                                <strong style="color: {a['color']}; font-size: 1.1em;">{a['risk']}</strong>
                                <span style="background: #eee; padding: 2px 8px; border-radius: 4px; font-family: monospace;">{a['domain']}</span>
                            </div>
                            <h3 style="margin: 10px 0;"><a href="{a['link']}" target="_blank" style="text-decoration:none; color:#0066cc;">{a['found_name']}</a></h3>
                            <p style="color: #444; font-size: 0.9em; line-height: 1.4;">{a['snippet']}</p>
                            
                            <div style="margin-top: 10px; padding: 10px; background: #fff; border: 1px solid #ddd; border-radius: 4px;">
                                <b style="color: #333;">🕵️‍♂️ Deep Scraping Findings (Mots-clés HTML):</b><br>
                                <span style="color: {'#d32f2f' if a['claims'] else '#888'};">{'✅' if a['claims'] else '❌'} Le site prétend être supervisé par la CSSF</span><br>
                                <span style="color: {'#8e24aa' if a['aifm'] else '#888'};">{'✅' if a['aifm'] else '❌'} Le site offre des services AIFM / Levée de fonds</span><br>
                                <span style="color: {'#c2185b' if a['casp'] else '#888'};">{'✅' if a['casp'] else '❌'} Le site offre des services CASP / Crypto-actifs</span>
                            </div>

                            <div style="margin-top: 10px; font-size: 0.85em; color: #666; border-top: 1px solid #ddd; padding-top: 5px;">
                                <b>Analyse Base de Données CSSF :</b> {a['score']}% de correspondance : <code>{a['best_match']}</code>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    # Affichage compact pour les entités vérifiées (Priorité 4)
                    with st.expander(f"✅ {a['domain']} ({a['found_name']}) - Match CSSF Confirmé ({a['score']}%)"):
                        st.write(f"**Lien :** {a['link']}")
                        st.write(f"**Détection HTML:** CSSF ({a['claims']}), AIFM ({a['aifm']}), CASP ({a['casp']})")
                        st.write(f"**Entité correspondante :** {a['best_match']}")

    st.sidebar.info(f"📊 Base de données : {len(official_names)} entités chargées à partir des registres officiels.")
