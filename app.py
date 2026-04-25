import streamlit as st
import pandas as pd
import requests
import re

# ==========================================
# 1. SÉCURITÉ ET ACCÈS
# ==========================================
st.set_page_config(page_title="CSSF Fraud Hunter Pro", layout="wide", page_icon="🛡️")

def check_password():
    """Vérifie le mot de passe via les secrets Streamlit."""
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if st.session_state["password_correct"]:
        return True

    st.title("🔐 Accès Restreint - CSSF Hunter")
    # Dans Streamlit Cloud, ajoute APP_PASSWORD dans Settings > Secrets
    pwd = st.text_input("Veuillez entrer le code d'accès :", type="password")
    if st.button("Se connecter"):
        if pwd == st.secrets.get("APP_PASSWORD", "admin123"): # fallback pour test local
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    return False

if check_password():
    # ==========================================
    # 2. CHARGEMENT ET FUSION DES LISTES (CSV)
    # ==========================================
    @st.cache_data
    def load_whitelists():
        # Utilisation des noms de fichiers exacts fournis
        files = ['AIFM SUCC .csv', 'AIFM REG.csv', 'AIFM AUT.csv']
        combined_df = pd.DataFrame()
        
        for f in files:
            try:
                df = pd.read_csv(f)
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            except Exception as e:
                st.sidebar.error(f"Erreur : Impossible de lire {f}")
        
        if not combined_df.empty:
            # Nettoyage pour comparaison : minuscule, sans ponctuation
            combined_df['name_clean'] = combined_df['Name'].astype(str).str.lower()
            combined_df['name_clean'] = combined_df['name_clean'].str.replace(r'[^a-z0-9]', '', regex=True).str.strip()
        return combined_df

    white_list = load_whitelists()

    # ==========================================
    # 3. CONFIGURATION DES MOTS-CLÉS
    # ==========================================
    KEYWORDS_GROUPS = {
        "Français": ["supervisé", "autorisé", "enregistré", "régulé", "agréé", "surveillance", "contrôle", "immatriculé"],
        "English": ["supervised", "authorized", "registered", "regulated", "licensed", "supervision", "authority", "oversight", "compliance", "AIFM"],
        "Español": ["supervisado", "autorizado", "registrado", "regulado", "supervisión", "entidad", "licencia", "vigilado"],
        "Italiano": ["supervisionato", "autorizzato", "registrato", "regolato", "vigilanza", "supervisione", "soggetto", "licenza"]
    }

    # ==========================================
    # 4. LOGIQUE DE RANKING ET RECHERCHE
    # ==========================================
    def get_risk_level(site_title, snippet, is_in_whitelist):
        """
        Calcule un score de risque :
        - Score 3 (Rouge) : Mention CSSF + Absent du CSV.
        - Score 2 (Orange) : Nom proche trouvé dans CSV mais site non-officiel.
        - Score 1 (Jaune) : Trouvé dans CSV, simple mention web.
        """
        score = 0
        snippet_lower = snippet.lower()
        title_lower = site_title.lower()
        
        # Critère 1 : Absence dans la base (Facteur majeur)
        if not is_in_whitelist:
            score += 2
        
        # Critère 2 : Densité de mots suspects dans le snippet
        # On compte combien de mots-clés "succession" apparaissent
        all_kws = [item for sublist in KEYWORDS_GROUPS.values() for item in sublist]
        found_kws = sum(1 for kw in all_kws if kw in snippet_lower or kw in title_lower)
        
        if found_kws >= 2:
            score += 1
            
        return min(score, 3)

    def perform_search(entity_name):
        api_key = st.secrets.get("SERPER_API_KEY")
        if not api_key:
            st.error("Clé API Serper manquante dans les secrets.")
            return []

        # Construction de la requête globale multilingue
        all_langs_kws = " OR ".join([kw for lang in KEYWORDS_GROUPS.values() for kw in lang])
        query = f'"{entity_name}" Luxembourg CSSF ({all_langs_kws}) -site:cssf.lu'
        
        url = "https://google.serper.dev/search"
        payload = {"q": query, "num": 20}
        headers = {'X-API-KEY': api_key, 'Content-Type': 'application/json'}
        
        try:
            r = requests.post(url, headers=headers, json=payload)
            return r.json().get('organic', [])
        except:
            return []

    # ==========================================
    # 5. INTERFACE ET RÉSULTATS
    # ==========================================
    st.title("🕵️‍♂️ CSSF Hunter : Détection Multilingue & Ranking")
    
    with st.sidebar:
        st.header("Paramètres")
        st.write(f"📁 **Base officielle :** {len(white_list)} entités.")
        st.divider()
        st.caption("Le ranking analyse la co-présence des termes réglementaires et l'absence dans vos fichiers CSV.")

    query_input = st.text_input("Entrez le nom de la société à auditer (ex: 'Global Wealth Management') :")

    if query_input:
        with st.spinner("Analyse approfondie du web et des registres..."):
            # 1. Check Whitelist
            clean_input = re.sub(r'[^a-z0-9]', '', query_input.lower())
            exact_match = white_list[white_list['name_clean'] == clean_input]
            partial_match = white_list[white_list['name_clean'].str.contains(clean_input, na=False)]
            
            is_verified = not exact_match.empty
            
            # 2. Search Web
            results = perform_search(query_input)
            
            # 3. Process & Rank
            processed_results = []
            for res in results:
                risk = get_risk_level(res['title'], res.get('snippet', ''), is_verified)
                processed_results.append({**res, "risk_score": risk})
            
            # Tri par risque décroissant
            processed_results = sorted(processed_results, key=lambda x: x['risk_score'], reverse=True)

            # --- AFFICHAGE ---
            st.subheader(f"Résultats pour : {query_input}")
            
            # Résumé Whitelist
            if is_verified:
                st.success(f"✅ L'entité '{query_input}' figure dans les listes officielles.")
                with st.expander("Voir détails du registre"):
                    st.table(exact_match[['Type', 'Name', 'Address']])
            elif not partial_match.empty:
                st.warning(f"⚠️ Nom similaire trouvé : {partial_match['Name'].iloc[0]}. Risque d'usurpation (Clonage) possible.")
            else:
                st.error("❌ Entité introuvable dans vos fichiers AIFM (AUT, REG, SUCC).")

            st.divider()

            # Affichage des alertes web
            if not processed_results:
                st.info("Aucune mention suspecte détectée sur le web avec ces mots-clés.")
            else:
                for res in processed_results:
                    # Couleur selon le risque
                    color = "red" if res['risk_score'] == 3 else "orange" if res['risk_score'] == 2 else "blue"
                    icon = "🚨 CRITIQUE" if res['risk_score'] == 3 else "⚠️ SUSPECT" if res['risk_score'] == 2 else "ℹ️ INFO"
                    
                    with st.container():
                        st.markdown(f"""
                        <div style="border-left: 5px solid {color}; padding: 10px; margin: 10px 0; background-color: #f9f9f9; border-radius: 5px;">
                            <h4 style="color: {color}; margin: 0;">{icon} : {res['title']}</h4>
                            <p style="margin: 5px 0;"><strong>Lien :</strong> <a href="{res['link']}" target="_blank">{res['link']}</a></p>
                            <p style="font-style: italic; color: #555;">"{res.get('snippet', '')}"</p>
                        </div>
                        """, unsafe_allow_html=True)
