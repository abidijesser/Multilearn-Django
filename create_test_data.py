"""
Script simplifié pour créer des données de test pour MultiLearn
Usage: python manage.py shell < create_test_data.py
"""

from myapp.models import User, Course, Enrollment, Quiz, Question, QuizResult
from django.contrib.auth.hashers import make_password

print("🚀 Création des données de test pour MultiLearn (Version Simplifiée)...")
print("=" * 70)

# ==================== UTILISATEURS ====================
print("\n👥 Création des utilisateurs...")

# Administrateur
admin, created = User.objects.get_or_create(
    username='admin',
    defaults={
        'email': 'admin@multilearn.com',
        'first_name': 'Admin',
        'last_name': 'System',
        'role': 'ADMIN',
        'password': make_password('admin123'),
        'is_staff': True,
        'is_superuser': True,
        'bio': 'Administrateur système',
    }
)
print("✅ Admin: admin / admin123" if created else "ℹ️  Admin existe déjà")

# Enseignant
teacher, created = User.objects.get_or_create(
    username='prof_martin',
    defaults={
        'email': 'martin@multilearn.com',
        'first_name': 'Jean',
        'last_name': 'Martin',
        'role': 'TEACHER',
        'password': make_password('password123'),
        'bio': 'Expert en Python et développement web',
        'phone': '+33 6 12 34 56 78',
    }
)
print("✅ Enseignant: prof_martin / password123" if created else "ℹ️  Enseignant existe déjà")

# Étudiants
students = []
students_data = [
    ('etudiant_marie', 'Marie', 'Dupont', 'marie@multilearn.com'),
    ('etudiant_pierre', 'Pierre', 'Bernard', 'pierre@multilearn.com'),
]

for username, first_name, last_name, email in students_data:
    student, created = User.objects.get_or_create(
        username=username,
        defaults={
            'email': email,
            'first_name': first_name,
            'last_name': last_name,
            'role': 'STUDENT',
            'password': make_password('password123'),
        }
    )
    students.append(student)
    print(f"✅ Étudiant: {username} / password123" if created else f"ℹ️  {username} existe déjà")

# ==================== COURS ====================
print("\n📚 Création des cours...")

# Cours Python
course_python, created = Course.objects.get_or_create(
    title='Introduction à Python',
    defaults={
        'description': 'Apprenez les bases de Python: variables, types, conditions, boucles, fonctions et plus.',
        'teacher': teacher,
        'content': '''
# Chapitre 1: Les Bases
- Variables et types de données (int, float, str, bool)
- Opérateurs arithmétiques et logiques
- Entrées/sorties avec input() et print()

# Chapitre 2: Structures de Contrôle
- Conditions (if, elif, else)
- Boucles (for, while)
- Break et continue

# Chapitre 3: Fonctions
- Définir des fonctions avec def
- Paramètres et valeurs de retour
- Portée des variables

# Chapitre 4: Structures de Données
- Listes, tuples, dictionnaires
- Méthodes de manipulation
- Compréhensions de listes
        ''',
        'status': 'PUBLISHED',
        'level': 'Débutant',
        'duration_hours': 20,
    }
)
print(f"✅ Cours: {course_python.title}" if created else f"ℹ️  Cours existe déjà")

# Cours Web
course_web, created = Course.objects.get_or_create(
    title='Développement Web Complet',
    defaults={
        'description': 'HTML, CSS, JavaScript - Créez des sites web professionnels.',
        'teacher': teacher,
        'content': '''
# Module 1: HTML5
- Structure d'une page HTML
- Balises sémantiques
- Formulaires et tableaux

# Module 2: CSS3
- Sélecteurs et propriétés
- Flexbox et Grid
- Animations et transitions
- Responsive design

# Module 3: JavaScript
- Manipulation du DOM
- Événements
- AJAX et fetch API
- ES6+ (let, const, arrow functions, promises)
        ''',
        'status': 'PUBLISHED',
        'level': 'Débutant',
        'duration_hours': 40,
    }
)
print(f"✅ Cours: {course_web.title}" if created else f"ℹ️  Cours existe déjà")



# ==================== INSCRIPTIONS ====================
print("\n✍️  Inscription des étudiants aux cours...")

# Inscrire les étudiants
for i, student in enumerate(students):
    # Au cours Python
    enrollment, created = Enrollment.objects.get_or_create(
        student=student,
        course=course_python,
        defaults={
            'progress': 30.0 if i == 0 else 15.0,
        }
    )
    if created:
        print(f"  ✅ {student.username} → {course_python.title}")
    
    # Au cours Web (seulement le premier étudiant)
    if i == 0:
        enrollment2, created = Enrollment.objects.get_or_create(
            student=student,
            course=course_web,
            defaults={'progress': 10.0}
        )
        if created:
            print(f"  ✅ {student.username} → {course_web.title}")

# ==================== QUIZ ====================
print("\n🎯 Création des quiz...")

# Quiz Python
quiz_python, created = Quiz.objects.get_or_create(
    course=course_python,
    title='Quiz Python - Les Bases',
    defaults={
        'description': 'Testez vos connaissances sur les bases de Python',
        'quiz_type': 'PRACTICE',
        'duration_minutes': 20,
        'passing_score': 60.0,
        'max_attempts': 3,
        'show_answers': True,
    }
)

if created:
    print(f"✅ Quiz: {quiz_python.title}")
    
    # Question 1 - MCQ
    Question.objects.create(
        quiz=quiz_python,
        question_text='Quel est le type de la variable x = 5 en Python?',
        question_type='MCQ',
        choices='int|float|str|bool',
        correct_answer='0',  # Index de la bonne réponse (int est à l'index 0)
        points=2.0,
        order=1
    )
    
    # Question 2 - Vrai/Faux
    Question.objects.create(
        quiz=quiz_python,
        question_text='Python est un langage compilé.',
        question_type='TRUE_FALSE',
        choices='Vrai|Faux',
        correct_answer='1',  # Faux est correct (index 1)
        points=1.0,
        order=2
    )
    
    # Question 3 - MCQ
    Question.objects.create(
        quiz=quiz_python,
        question_text='Quelle fonction permet d\'afficher du texte en Python?',
        question_type='MCQ',
        choices='print()|display()|show()|write()',
        correct_answer='0',  # print() est correct
        points=1.0,
        order=3
    )
    
    # Question 4 - Texte libre
    Question.objects.create(
        quiz=quiz_python,
        question_text='Quel est le résultat de: 2 + 2 * 2 ?',
        question_type='TEXT',
        choices='',
        correct_answer='6',
        points=2.0,
        order=4
    )
    
    print("  ✅ 4 questions créées")
else:
    print(f"ℹ️  Quiz existe déjà")

# Quiz Web
quiz_web, created = Quiz.objects.get_or_create(
    course=course_web,
    title='Quiz HTML & CSS',
    defaults={
        'description': 'Évaluez vos connaissances en HTML et CSS',
        'quiz_type': 'EXAM',
        'duration_minutes': 30,
        'passing_score': 70.0,
        'max_attempts': 2,
        'show_answers': False,
    }
)

if created:
    print(f"✅ Quiz: {quiz_web.title}")
    
    Question.objects.create(
        quiz=quiz_web,
        question_text='Quelle balise HTML est utilisée pour créer un paragraphe?',
        question_type='MCQ',
        choices='<p>|<para>|<paragraph>|<text>',
        correct_answer='0',
        points=1.0,
        order=1
    )
    
    Question.objects.create(
        quiz=quiz_web,
        question_text='CSS signifie Cascading Style Sheets.',
        question_type='TRUE_FALSE',
        choices='Vrai|Faux',
        correct_answer='0',
        points=1.0,
        order=2
    )
    
    print("  ✅ 2 questions créées")
else:
    print(f"ℹ️  Quiz existe déjà")

# ==================== RÉSUMÉ ====================
print("\n" + "=" * 70)
print("✅ BASE DE DONNÉES SIMPLIFIÉE CRÉÉE AVEC SUCCÈS!")
print("=" * 70)

print("\n📊 Statistiques:")
print(f"  • Utilisateurs: {User.objects.count()}")
print(f"    - Admins: {User.objects.filter(role='ADMIN').count()}")
print(f"    - Enseignants: {User.objects.filter(role='TEACHER').count()}")
print(f"    - Étudiants: {User.objects.filter(role='STUDENT').count()}")
print(f"  • Cours: {Course.objects.count()}")
print(f"  • Inscriptions: {Enrollment.objects.count()}")
print(f"  • Quiz: {Quiz.objects.count()}")
print(f"  • Questions: {Question.objects.count()}")

print("\n🗄️  Tables dans la base de données:")
print("  1. users (utilisateurs avec rôles)")
print("  2. courses (cours avec contenu intégré)")
print("  3. enrollments (inscriptions + progression)")
print("  4. quizzes (quiz avec configuration)")
print("  5. questions (questions avec réponses intégrées)")
print("  6. quiz_results (résultats simplifiés)")

print("\n🔐 Identifiants de connexion:")
print("  • Admin:       admin / admin123")
print("  • Enseignant:  prof_martin / password123")
print("  • Étudiant:    etudiant_marie / password123")

print("\n🌐 Accédez à l'interface:")
print("  http://127.0.0.1:8000/admin/")

print("\n✨ Avantages de la structure simplifiée:")
print("  ✅ Seulement 6 tables principales (au lieu de 13)")
print("  ✅ Contenu des cours intégré (pas de tables séparées)")
print("  ✅ Questions avec réponses en format texte")
print("  ✅ Résultats de quiz simplifiés")
print("  ✅ Même fonctionnalités, structure plus claire")
print("=" * 70)
