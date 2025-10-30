"""
Système de filtrage de contenu pour détecter les commentaires inappropriés
Utilise l'API Gemini AI pour une détection intelligente
"""
import re
import google.generativeai as genai
import os

# Configuration Gemini
genai.configure(api_key='AIzaSyBFo_IkHcOzYFtLlzZKRcT7frmdcuvwB38')

class ContentFilter:
    """
    Classe pour détecter le contenu inapproprié dans les commentaires
    """
    
    def __init__(self):
        # Initialiser le modèle Gemini
        try:
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            self.use_ai = True
        except Exception as e:
            print(f"Erreur lors de l'initialisation de Gemini: {e}")
            self.use_ai = False
        
        # Liste de mots interdits (backup si l'API échoue)
        self.bad_words = [
            # Mots grossiers français
            'merde', 'putain', 'con', 'connard', 'salope', 'pute', 'enculé', 'enculer',
            'bordel', 'foutre', 'chier', 'pisser', 'bite', 'chatte', 'cul',
            'nique', 'niquer', 'baiser', 'baise',
            
            # Mots grossiers anglais
            'fuck', 'fucking', 'shit', 'bitch', 'ass', 'asshole', 'damn',
            'crap', 'piss', 'dick', 'cock', 'pussy', 'cunt', 'whore',
            
            # Insultes graves
            'nazi', 'hitler', 'pédé', 'pédale', 'tapette', 'gouine',
            'mongol', 'retardé', 'débile',
            
            # Violence et menaces
            'tuer', 'mort', 'suicide', 'bombe', 'attentat', 'terroriste',
            'viol', 'violer', 'torture', 'massacre',
        ]
        
        # Patterns de contenu suspect
        self.suspicious_patterns = [
            r'\b\d{10,}\b',  # Numéros de téléphone
            r'http[s]?://',  # URLs
            r'www\.',        # Sites web
        ]
    
    def check_content_with_ai(self, text):
        """
        Vérifie le contenu avec l'API Gemini AI
        
        Args:
            text (str): Le texte à analyser
            
        Returns:
            dict: Résultat de l'analyse AI
        """
        try:
            prompt = f"""Analysez le texte suivant et déterminez s'il contient du contenu inapproprié pour un avis sur une plateforme éducative.

Critères à vérifier:
1. Langage grossier, vulgaire ou offensant
2. Insultes, discrimination ou harcèlement
3. Violence, menaces ou contenu dangereux
4. Spam, publicité ou liens suspects
5. Contenu hors sujet ou non pertinent

Texte à analyser: "{text}"

Répondez UNIQUEMENT au format JSON suivant (sans markdown, sans ```json):
{{
    "is_appropriate": true/false,
    "severity": "low/medium/high",
    "issues": ["liste des problèmes détectés"],
    "message": "message d'explication court",
    "suggestions": ["suggestions pour améliorer le texte"]
}}"""

            response = self.model.generate_content(prompt)
            response_text = response.text.strip()
            
            # Nettoyer la réponse (enlever les balises markdown si présentes)
            response_text = response_text.replace('```json', '').replace('```', '').strip()
            
            # Parser la réponse JSON
            import json
            result = json.loads(response_text)
            
            return {
                'is_appropriate': result.get('is_appropriate', True),
                'score': 0 if result.get('is_appropriate', True) else (
                    30 if result.get('severity') == 'high' else 
                    20 if result.get('severity') == 'medium' else 10
                ),
                'issues': result.get('issues', []),
                'message': result.get('message', ''),
                'bad_words_found': [],
                'suspicious_found': [],
                'suggestions': result.get('suggestions', [])
            }
        except Exception as e:
            print(f"Erreur lors de l'analyse AI: {e}")
            return None
    
    def check_content_basic(self, text):
        """
        Vérification basique sans AI (fallback)
        
        Args:
            text (str): Le texte à analyser
            
        Returns:
            dict: Résultat de l'analyse basique
        """
        text_lower = text.lower().strip()
        issues = []
        score = 0
        
        # Vérifier les mots interdits
        bad_words_found = []
        for word in self.bad_words:
            if word in text_lower:
                bad_words_found.append(word)
                score += 10
        
        if bad_words_found:
            issues.append(f"Mots inappropriés détectés")
        
        # Vérifier les patterns suspects
        suspicious_found = []
        for pattern in self.suspicious_patterns:
            matches = re.findall(pattern, text)
            if matches:
                suspicious_found.extend(matches)
                score += 5
        
        if suspicious_found:
            issues.append(f"Contenu suspect détecté")
        
        # Déterminer si le contenu est approprié
        is_appropriate = score < 10
        
        # Générer le message d'erreur
        if not is_appropriate:
            if bad_words_found:
                message = "Votre message contient des mots inappropriés. Veuillez utiliser un langage respectueux."
            elif suspicious_found:
                message = "Votre message contient du contenu suspect (liens, numéros de téléphone)."
            else:
                message = "Votre message ne respecte pas nos règles de publication."
        else:
            message = ""
        
        return {
            'is_appropriate': is_appropriate,
            'score': score,
            'issues': issues,
            'message': message,
            'bad_words_found': bad_words_found,
            'suspicious_found': suspicious_found
        }
    
    def check_content(self, text):
        """
        Vérifie si le contenu contient des éléments inappropriés
        Utilise l'AI en priorité, puis fallback sur la méthode basique
        
        Args:
            text (str): Le texte à analyser
            
        Returns:
            dict: Résultat de l'analyse avec score et détails
        """
        if not text or not text.strip():
            return {
                'is_appropriate': True,
                'score': 0,
                'issues': [],
                'message': '',
                'bad_words_found': [],
                'suspicious_found': []
            }
        
        # Essayer d'abord avec l'AI
        if self.use_ai:
            ai_result = self.check_content_with_ai(text)
            if ai_result:
                return ai_result
        
        # Fallback sur la méthode basique
        return self.check_content_basic(text)
    
    def get_suggestions(self, text):
        """
        Fournit des suggestions pour améliorer le contenu
        
        Args:
            text (str): Le texte à analyser
            
        Returns:
            list: Liste de suggestions
        """
        suggestions = []
        
        # Suggérer des alternatives pour les mots interdits
        alternatives = {
            'merde': 'zut',
            'putain': 'mince',
            'con': 'personne',
            'connard': 'personne',
            'salope': 'personne',
            'fuck': 'zut',
            'shit': 'mince',
            'bitch': 'personne',
        }
        
        text_lower = text.lower()
        for bad_word, alternative in alternatives.items():
            if bad_word in text_lower:
                suggestions.append(f"Remplacer '{bad_word}' par '{alternative}'")
        
        # Suggérer d'éviter les répétitions
        words = text_lower.split()
        word_counts = {}
        for word in words:
            if len(word) > 3:
                word_counts[word] = word_counts.get(word, 0) + 1
        
        for word, count in word_counts.items():
            if count > 2:
                suggestions.append(f"Éviter de répéter '{word}' trop souvent")
        
        return suggestions


# Instance globale du filtre
content_filter = ContentFilter()
