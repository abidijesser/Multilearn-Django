"""
Script de test pour le système de filtrage de contenu avec AI
"""
import os
import sys
import django

# Configuration Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'scriptmaster.settings')
django.setup()

from myapp.content_filter import content_filter

# Tests
test_cases = [
    {
        "text": "MultiLearn est une excellente plateforme d'apprentissage. J'adore les cours proposés!",
        "expected": "appropriate"
    },
    {
        "text": "Cette plateforme est merde, je déteste tout!",
        "expected": "inappropriate"
    },
    {
        "text": "Les cours sont bien mais il y a des bugs à corriger.",
        "expected": "appropriate"
    },
    {
        "text": "Fuck this shit, c'est de la merde!",
        "expected": "inappropriate"
    },
    {
        "text": "Visitez mon site www.spam.com pour gagner de l'argent facilement!",
        "expected": "inappropriate"
    },
    {
        "text": "J'apprécie vraiment la qualité des contenus et l'interface utilisateur.",
        "expected": "appropriate"
    }
]

print("=" * 80)
print("TEST DU SYSTÈME DE FILTRAGE DE CONTENU AVEC AI")
print("=" * 80)
print()

for i, test in enumerate(test_cases, 1):
    print(f"Test #{i}")
    print(f"Texte: {test['text']}")
    print(f"Attendu: {test['expected']}")
    
    result = content_filter.check_content(test['text'])
    
    status = "✓ PASS" if (
        (test['expected'] == 'appropriate' and result['is_appropriate']) or
        (test['expected'] == 'inappropriate' and not result['is_appropriate'])
    ) else "✗ FAIL"
    
    print(f"Résultat: {'Approprié' if result['is_appropriate'] else 'Inapproprié'}")
    print(f"Score: {result['score']}")
    print(f"Message: {result.get('message', 'N/A')}")
    
    if result.get('issues'):
        print(f"Problèmes: {', '.join(result['issues'])}")
    
    if result.get('suggestions'):
        print(f"Suggestions: {', '.join(result['suggestions'])}")
    
    print(f"Statut: {status}")
    print("-" * 80)
    print()

print("=" * 80)
print("FIN DES TESTS")
print("=" * 80)
