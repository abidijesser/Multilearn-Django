import json
import re
import google.generativeai as genai

# ⚠️ Clé API directement dans le code
GENAI_API_KEY = "AIzaSyCzz5V9cE05VecdzFrA-RM_6jVlqN8eDEo"  # <-- Remplace par ta vraie clé

# Configure ton API Gemini
genai.configure(api_key=GENAI_API_KEY)

def clean_json_output(response_text: str):
    """Nettoie le texte brut pour extraire un JSON valide."""
    try:
        match = re.search(r'\[.*\]', response_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return []
    except Exception:
        return []

def generate_quiz_from_text(concept: str, quiz_type: str = "Général"):
    """
    Génère des questions de quiz basées uniquement sur le concept ou le type fourni.
    """
    prompt = f"""
Tu es un assistant éducatif spécialisé.
Le concept ou sujet du quiz est : "{concept}".
Le type de quiz est : "{quiz_type}".
Génère 5 à 10 questions pertinentes sur ce concept.
Types de questions possibles : QCM, vrai/faux, courte réponse.
Format JSON attendu :

[
  {{
    "question_type": "MCQ" | "TRUE_FALSE" | "SHORT_ANSWER",
    "question_text": "string",
    "options": ["option1", "option2", "option3", "option4"],
    "correct_answer": "option2",
    "points": 2,
    "order": 1
  }}
]
"""
    try:
        model = genai.GenerativeModel("gemini-2.5-flash")  # Assure-toi d'utiliser un modèle valide
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        return clean_json_output(response_text)
    except Exception as e:
        return [{
            "question_type": "SHORT_ANSWER",
            "question_text": f"Erreur : {str(e)}",
            "options": [],
            "correct_answer": "",
            "points": 0,
            "order": 1
        }]
