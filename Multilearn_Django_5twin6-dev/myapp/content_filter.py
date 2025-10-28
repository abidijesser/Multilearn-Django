"""
Système de filtrage de contenu pour détecter les commentaires inappropriés
"""
import re

class ContentFilter:
    """
    Classe pour détecter le contenu inapproprié dans les commentaires
    """
    
    def __init__(self):
        # Liste de mots interdits (français et anglais)
        self.bad_words = [
            # Mots grossiers français
            'merde', 'putain', 'con', 'connard', 'salope', 'pute', 'enculé', 'enculer',
            'bordel', 'foutre', 'chier', 'pisser', 'bite', 'chatte', 'cul', 'foutre',
            'nique', 'niquer', 'baiser', 'baise', 'baiseur', 'baiseuse',
            
            # Mots grossiers anglais
            'fuck', 'fucking', 'shit', 'bitch', 'ass', 'asshole', 'damn', 'hell',
            'crap', 'piss', 'pissed', 'dick', 'cock', 'pussy', 'cunt', 'whore',
            
            # Insultes et discriminations
            'nazi', 'hitler', 'juif', 'juive', 'arabe', 'noir', 'blanc', 'chinois',
            'pédé', 'pédale', 'tapette', 'gouine', 'lesbienne', 'homo', 'trans',
            'handicapé', 'mongol', 'retardé', 'débile', 'crétin', 'idiot',
            
            # Violence et menaces
            'tuer', 'mort', 'suicide', 'bombe', 'attentat', 'terroriste', 'violence',
            'agression', 'viol', 'violer', 'torture', 'massacre', 'génocide',
            
            # Spam et publicité
            'spam', 'pub', 'publicité', 'promo', 'offre', 'gratuit', 'gagner',
            'argent', 'bitcoin', 'crypto', 'investissement', 'trading',
        ]
        
        # Patterns de contenu suspect
        self.suspicious_patterns = [
            r'\b\d{4,}\b',  # Nombres de 4 chiffres ou plus (téléphones, codes)
            r'http[s]?://',  # URLs
            r'www\.',        # Sites web
            r'@\w+',         # Mentions
            r'#\w+',         # Hashtags
            r'\b[A-Z]{3,}\b', # Mots en majuscules
        ]
    
    def check_content(self, text):
        """
        Vérifie si le contenu contient des éléments inappropriés
        
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
                'message': ''
            }
        
        text_lower = text.lower().strip()
        issues = []
        score = 0
        
        # Vérifier les mots interdits
        bad_words_found = []
        for word in self.bad_words:
            if word in text_lower:
                bad_words_found.append(word)
                score += 10  # +10 points par mot interdit
        
        if bad_words_found:
            issues.append(f"Mots inappropriés détectés: {', '.join(bad_words_found[:3])}")
        
        # Vérifier les patterns suspects
        suspicious_found = []
        for pattern in self.suspicious_patterns:
            matches = re.findall(pattern, text)
            if matches:
                suspicious_found.extend(matches)
                score += 5  # +5 points par pattern suspect
        
        if suspicious_found:
            issues.append(f"Contenu suspect détecté: {', '.join(suspicious_found[:3])}")
        
        # Vérifier la répétition excessive
        words = text_lower.split()
        if len(words) > 0:
            word_counts = {}
            for word in words:
                if len(word) > 3:  # Ignorer les mots courts
                    word_counts[word] = word_counts.get(word, 0) + 1
            
            # Si un mot apparaît plus de 3 fois
            for word, count in word_counts.items():
                if count > 3:
                    score += 5
                    issues.append(f"Répétition excessive du mot '{word}' ({count} fois)")
                    break
        
        # Vérifier la longueur excessive (spam potentiel)
        if len(text) > 1000:
            score += 5
            issues.append("Message très long (spam potentiel)")
        
        # Déterminer si le contenu est approprié
        is_appropriate = score < 15  # Seuil de tolérance
        
        # Générer le message d'erreur
        if not is_appropriate:
            if bad_words_found:
                message = "Votre message contient des mots inappropriés. Veuillez modifier votre texte."
            elif suspicious_found:
                message = "Votre message contient du contenu suspect. Veuillez le réviser."
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
