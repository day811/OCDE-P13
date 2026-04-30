import streamlit as st

# Configuration de la page
st.set_page_config(page_title="Yves Dangel | Senior Data Engineer", layout="wide")

# --- STYLE CSS (Pour moderniser l'interface) ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; color: #ffffff; }
    .stButton>button { border-radius: 20px; border: 1px solid #0078d4; }
    .highlight { color: #0078d4; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- HEADER ---
col1, col2 = st.columns([1, 3])
with col1:
    st.image("web_portal/assets/photo_yves.png", width=200) # À ajouter
with col2:
    st.title("Yves Dangel")
    st.subheader("Expert IT & Senior Data Engineer")
    st.markdown("""
    **35 ans d'expertise en infrastructures et production ,** aujourd'hui au service de l'ingénierie des données et de l'intelligence artificielle.
    """)
    st.write("📍 Occitanie, France ")

st.divider()

# --- LE PITCH : L'HYBRIDE ---
st.header("Pourquoi mon profil est unique ?")
c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Expérience Systèmes", "35 ans", help="Infrastructures, Réseaux, Production ")
with c2:
    st.metric("Projets Data Validés", "10/13", help="Cursus OpenClassrooms (Niveau 7 - Bac+5) ")
with c3:
    st.metric("Spécialisation", "RAG & Cloud", help="LangChain, Azure AI Search, Gemini ")

st.info("💡 **Ma force :** Je ne me contente pas de coder des pipelines, je conçois des architectures résilientes et scalables, forgées par des décennies de gestion de systèmes critiques.")

# --- TIMELINE DYNAMIQUE D'EVOLUTION ---
st.header("L'évolution d'une expertise")
st.write("Plutôt qu'une liste chronologique, voici comment ma stack a évolué pour répondre aux enjeux de demain.")

eras = {
    "2024 - Aujourd'hui : L'ère de la Data & IA": [
        "Architectures RAG (LangChain, FAISS, Azure AI Search) ",
        "Pipelines Data complexes (Python, Spark, Docker) ",
        "Orchestration & Cloud (Kestra, AWS, Azure) "
    ],
    "2005 - 2022 : L'ère de l'Entrepreneuriat & Support": [
        "Gestion d'infrastructures multi-sites (Miléade) ",
        "Automatisation de flux (Python, VBA, PHP) ",
        "Création et gestion d'entreprise IT (Aude-Line) "
    ],
    "1990 - 2003 : Fondations & Direction": [
        "Directeur des Opérations (IDEM SA) - Management de 25 pers ",
        "Responsable Informatique Régional (Calberson) ",
        "Maîtrise des systèmes critiques (AS400, SAP, DB2) "
    ]
}

for era, skills in eras.items():
    with st.expander(f"**{era}**"):
        for skill in skills:
            st.write(f"- {skill}")

st.divider()
st.button("Découvrir mon projet phare : Puls-Events 🚀") # Redirige vers page 1