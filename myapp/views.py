from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.utils import timezone
from .models import User, Course, Enrollment, Quiz, Question, QuizResult
import json
import re
import google.generativeai as genai

# Configuration Gemini
genai.configure(api_key='AIzaSyBFo_IkHcOzYFtLlzZKRcT7frmdcuvwB38')
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# ============= Fonctions IA pour recommandations =============

def analyze_bio_and_recommend_courses(user):
    """
    Analyse la biographie avec Gemini AI et recommande des cours
    """
    if not user.bio:
        return []
    
    try:
        if user.role == 'STUDENT':
            # Récupérer TOUS les cours disponibles
            enrolled_ids = list(user.enrollments.values_list('course_id', flat=True))
            all_courses = Course.objects.filter(status='PUBLISHED').exclude(id__in=enrolled_ids)
            
            if not all_courses.exists():
                return []
            
            # Créer la liste complète des cours avec ID et titre uniquement
            courses_list = "\n".join([
                f"{c.id}. {c.title}"
                for c in all_courses
            ])
            
            # Prompt simplifié pour Gemini
            prompt = f"""Tu es un conseiller d'orientation. Analyse cette biographie d'étudiant et recommande les 5 cours les PLUS compatibles parmi TOUS les cours disponibles.

BIOGRAPHIE DE L'ÉTUDIANT:
{user.bio}

LISTE COMPLÈTE DES COURS DISPONIBLES:
{courses_list}

INSTRUCTIONS:
- Analyse la biographie pour comprendre les compétences, intérêts et objectifs de l'étudiant
- Compare avec TOUS les titres de cours
- Recommande les 5 cours les plus pertinents et compatibles
- Réponds UNIQUEMENT avec les numéros des cours, séparés par des virgules
- Format de réponse: 3,7,12,5,19 (juste les numéros, rien d'autre)"""
            
            response = gemini_model.generate_content(prompt)
            
            # Extraire les IDs des cours recommandés
            response_text = response.text.strip()
            course_ids = []
            for item in response_text.replace(' ', '').split(','):
                if item.isdigit():
                    course_ids.append(int(item))
            
            # Récupérer les cours recommandés
            recommended = []
            for cid in course_ids[:5]:
                try:
                    course = Course.objects.get(id=cid, status='PUBLISHED')
                    if course.id not in enrolled_ids:
                        recommended.append(course)
                except Course.DoesNotExist:
                    continue
            
            return recommended
        
        elif user.role == 'TEACHER':
            # Suggestions pour enseignants
            existing_titles = ", ".join([c.title for c in user.courses_taught.all()])
            
            prompt = f"""Tu es un conseiller pédagogique. Analyse cette biographie d'enseignant et suggère 5 cours qu'il pourrait créer.

BIOGRAPHIE DE L'ENSEIGNANT:
{user.bio}

COURS DÉJÀ CRÉÉS:
{existing_titles if existing_titles else "Aucun cours créé pour le moment"}

INSTRUCTIONS:
- Analyse les compétences et expertises de l'enseignant
- Suggère 5 nouveaux cours différents de ceux déjà créés
- Format: Titre du cours | Domaine
- Exemple:
Python Avancé | Programmation
Web Development avec React | Développement Web
Data Science Pratique | Analyse de données"""
            
            response = gemini_model.generate_content(prompt)
            suggestions = []
            for line in response.text.strip().split('\n'):
                line = line.strip()
                if '|' in line:
                    parts = line.split('|')
                    if len(parts) >= 2:
                        suggestions.append({
                            'title': parts[0].strip(),
                            'domain': parts[1].strip(),
                            'suggestion': parts[0].strip()
                        })
            
            return suggestions[:5]
    
    except Exception as e:
        print(f"Erreur Gemini: {e}")
        return []
    
    return []

# ============= Pages publiques =============

def home(request):
    """Page d'accueil publique"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    courses = Course.objects.filter(status='PUBLISHED')[:6]
    stats = {
        'total_courses': Course.objects.filter(status='PUBLISHED').count(),
        'total_students': User.objects.filter(role='STUDENT').count(),
        'total_teachers': User.objects.filter(role='TEACHER').count(),
    }
    
    context = {
        'courses': courses,
        'stats': stats,
    }
    return render(request, 'home.html', context)


# ============= Authentification =============

def register_view(request):
    """Page d'inscription"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        password_confirm = request.POST.get('password_confirm')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        role = request.POST.get('role', 'STUDENT')
        
        # Validation
        if password != password_confirm:
            messages.error(request, 'Les mots de passe ne correspondent pas.')
            return render(request, 'register.html')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Ce nom d\'utilisateur existe déjà.')
            return render(request, 'register.html')
        
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Cet email est déjà utilisé.')
            return render(request, 'register.html')
        
        # Créer l'utilisateur
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            role=role
        )
        
        messages.success(request, 'Compte créé avec succès ! Vous pouvez maintenant vous connecter.')
        return redirect('login')
    
    return render(request, 'register.html')


def login_view(request):
    """Page de connexion"""
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            login(request, user)
            messages.success(request, f'Bienvenue {user.get_full_name() or user.username} !')
            
            # Rediriger selon le paramètre 'next' ou vers le dashboard
            next_url = request.GET.get('next', 'dashboard')
            return redirect(next_url)
        else:
            messages.error(request, 'Nom d\'utilisateur ou mot de passe incorrect.')
    
    return render(request, 'login.html')


def logout_view(request):
    """Déconnexion"""
    logout(request)
    messages.info(request, 'Vous avez été déconnecté.')
    return redirect('home')


@login_required
def profile_view(request):
    """Page de profil utilisateur"""
    user = request.user
    
    if request.method == 'POST':
        # Mise à jour du profil
        user.first_name = request.POST.get('first_name', user.first_name)
        user.last_name = request.POST.get('last_name', user.last_name)
        user.email = request.POST.get('email', user.email)
        user.bio = request.POST.get('bio', user.bio)
        
        # Gestion de la photo de profil
        if 'profile_picture' in request.FILES:
            user.profile_picture = request.FILES['profile_picture']
        
        user.save()
        messages.success(request, 'Profil mis à jour avec succès !')
        return redirect('profile')
    
    # Statistiques selon le rôle
    context = {'user': user}
    
    # Recommandations IA basées sur la biographie
    if user.bio:
        ai_recommendations = analyze_bio_and_recommend_courses(user)
        context['ai_recommendations'] = ai_recommendations
    
    if user.role == 'STUDENT':
        context['enrollments'] = user.enrollments.select_related('course').all()
        context['completed_quizzes'] = QuizResult.objects.filter(student=user).count()
    elif user.role == 'TEACHER':
        context['courses'] = user.courses_taught.annotate(
            student_count=Count('enrollments')
        ).all()
        context['total_students'] = Enrollment.objects.filter(
            course__teacher=user
        ).values('student').distinct().count()
    
    return render(request, 'profile.html', context)


# ============= Dashboard =============

@login_required
def dashboard(request):
    """Dashboard selon le rôle de l'utilisateur"""
    user = request.user
    context = {'user': user}
    
    if user.role == 'ADMIN':
        # Dashboard Admin
        context.update({
            'total_users': User.objects.count(),
            'total_courses': Course.objects.count(),
            'total_enrollments': Enrollment.objects.count(),
            'total_quizzes': Quiz.objects.count(),
            'recent_users': User.objects.order_by('-date_joined')[:5],
            'recent_courses': Course.objects.order_by('-created_at')[:5],
        })
        return render(request, 'dashboard_admin.html', context)
    
    elif user.role == 'TEACHER':
        # Dashboard Enseignant
        courses = user.courses_taught.annotate(
            student_count=Count('enrollments')
        ).all()
        
        context.update({
            'courses': courses,
            'total_courses': courses.count(),
            'total_students': Enrollment.objects.filter(
                course__teacher=user
            ).values('student').distinct().count(),
            'total_quizzes': Quiz.objects.filter(course__teacher=user).count(),
        })
        return render(request, 'dashboard_teacher.html', context)
    
    else:  # STUDENT
        # Dashboard Étudiant
        enrollments = user.enrollments.select_related('course').all()
        
        context.update({
            'enrollments': enrollments,
            'total_courses': enrollments.count(),
            'avg_progress': enrollments.aggregate(Avg('progress'))['progress__avg'] or 0,
            'completed_quizzes': QuizResult.objects.filter(student=user).count(),
            'available_courses': Course.objects.filter(
                status='PUBLISHED'
            ).exclude(
                id__in=enrollments.values_list('course_id', flat=True)
            )[:6],
        })
        return render(request, 'dashboard_student.html', context)


# ============= Cours =============

def course_list(request):
    """Liste de tous les cours"""
    courses = Course.objects.filter(status='PUBLISHED').annotate(
        student_count=Count('enrollments')
    ).order_by('-created_at')
    
    # Filtres
    level = request.GET.get('level')
    search = request.GET.get('search')
    
    if level:
        courses = courses.filter(level=level)
    
    if search:
        courses = courses.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search)
        )
    
    context = {
        'courses': courses,
        'levels': ['Débutant', 'Intermédiaire', 'Avancé', 'Expert'],
    }
    return render(request, 'course_list.html', context)


def course_detail(request, course_id):
    """Détails d'un cours"""
    course = get_object_or_404(Course, id=course_id)
    
    # Vérifier si l'utilisateur est inscrit
    is_enrolled = False
    enrollment = None
    if request.user.is_authenticated:
        try:
            enrollment = Enrollment.objects.get(student=request.user, course=course)
            is_enrolled = True
        except Enrollment.DoesNotExist:
            pass
    
    # Quizzes du cours
    quizzes = course.quizzes.all()
    
    context = {
        'course': course,
        'is_enrolled': is_enrolled,
        'enrollment': enrollment,
        'quizzes': quizzes,
        'student_count': course.enrollments.count(),
    }
    return render(request, 'course_detail.html', context)


@login_required
def course_enroll(request, course_id):
    """Inscription à un cours"""
    course = get_object_or_404(Course, id=course_id)
    
    if request.user.role != 'STUDENT':
        messages.error(request, 'Seuls les étudiants peuvent s\'inscrire aux cours.')
        return redirect('course_detail', course_id=course_id)
    
    # Vérifier si déjà inscrit
    if Enrollment.objects.filter(student=request.user, course=course).exists():
        messages.warning(request, 'Vous êtes déjà inscrit à ce cours.')
        return redirect('course_detail', course_id=course_id)
    
    # Créer l'inscription
    Enrollment.objects.create(student=request.user, course=course)
    messages.success(request, f'Vous êtes maintenant inscrit au cours "{course.title}" !')
    
    return redirect('course_detail', course_id=course_id)


@login_required
def course_create(request):
    """Créer un nouveau cours (enseignants uniquement)"""
    if request.user.role != 'TEACHER':
        messages.error(request, 'Seuls les enseignants peuvent créer des cours.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        content = request.POST.get('content')
        level = request.POST.get('level', 'Débutant')
        duration_hours = request.POST.get('duration_hours', 0)
        status = request.POST.get('status', 'DRAFT')
        
        course = Course.objects.create(
            teacher=request.user,
            title=title,
            description=description,
            content=content,
            level=level,
            duration_hours=duration_hours,
            status=status
        )
        
        # Gestion de l'image de couverture
        if 'cover_image' in request.FILES:
            course.cover_image = request.FILES['cover_image']
            course.save()
        
        messages.success(request, f'Cours "{title}" créé avec succès !')
        return redirect('course_detail', course_id=course.id)
    
    return render(request, 'course_create.html')


@login_required
def course_edit(request, course_id):
    """Éditer un cours existant"""
    course = get_object_or_404(Course, id=course_id)
    
    # Vérifier que l'utilisateur est le propriétaire
    if course.teacher != request.user:
        messages.error(request, 'Vous ne pouvez modifier que vos propres cours.')
        return redirect('course_detail', course_id=course_id)
    
    if request.method == 'POST':
        course.title = request.POST.get('title', course.title)
        course.description = request.POST.get('description', course.description)
        course.content = request.POST.get('content', course.content)
        course.level = request.POST.get('level', course.level)
        course.duration_hours = request.POST.get('duration_hours', course.duration_hours)
        course.status = request.POST.get('status', course.status)
        
        if 'cover_image' in request.FILES:
            course.cover_image = request.FILES['cover_image']
        
        course.save()
        messages.success(request, 'Cours mis à jour avec succès !')
        return redirect('course_detail', course_id=course.id)
    
    context = {'course': course}
    return render(request, 'course_edit.html', context)


# ============= Quiz =============

def quiz_list(request, course_id):
    """Liste des quiz d'un cours"""
    course = get_object_or_404(Course, id=course_id)
    quizzes = course.quizzes.annotate(
        question_count=Count('questions')
    ).all()
    
    # Vérifier l'inscription
    is_enrolled = False
    if request.user.is_authenticated and request.user.role == 'STUDENT':
        is_enrolled = Enrollment.objects.filter(
            student=request.user, 
            course=course
        ).exists()
    
    context = {
        'course': course,
        'quizzes': quizzes,
        'is_enrolled': is_enrolled,
    }
    return render(request, 'quiz_list.html', context)


@login_required
def quiz_create(request, course_id):
    """Créer un nouveau quiz pour un cours"""
    course = get_object_or_404(Course, id=course_id)
    
    # Vérifier que l'utilisateur est l'enseignant du cours
    if request.user != course.teacher:
        messages.error(request, "Vous n'êtes pas autorisé à créer un quiz pour ce cours.")
        return redirect('course_detail', course_id=course_id)
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        duration_minutes = request.POST.get('duration_minutes')
        passing_score = request.POST.get('passing_score')
        max_attempts = request.POST.get('max_attempts')
        quiz_type = request.POST.get('quiz_type')
        show_answers = request.POST.get('show_answers') == 'on'
        questions_data = request.POST.get('questions_data')
        
        # Validation
        if not all([title, description, duration_minutes, passing_score, max_attempts, quiz_type]):
            messages.error(request, 'Veuillez remplir tous les champs obligatoires.')
            return render(request, 'quiz_create.html', {'course': course})
        
        # Créer le quiz
        quiz = Quiz.objects.create(
            course=course,
            title=title,
            description=description,
            duration_minutes=int(duration_minutes),
            passing_score=int(passing_score),
            max_attempts=int(max_attempts),
            quiz_type=quiz_type,
            show_answers=show_answers
        )
        
        # Créer les questions si fournies
        if questions_data:
            try:
                questions = json.loads(questions_data)
                for q_data in questions:
                    # Préparer les choix au format attendu par le modèle (séparés par |)
                    choices_text = '|'.join(q_data['options']) if q_data['options'] else ''
                    
                    Question.objects.create(
                        quiz=quiz,
                        question_type=q_data['question_type'],
                        question_text=q_data['question_text'],
                        points=q_data['points'],
                        correct_answer=q_data['correct_answer'],
                        choices=choices_text,
                        order=q_data['order']
                    )
                messages.success(request, f'Le quiz "{title}" a été créé avec {len(questions)} question(s)!')
            except Exception as e:
                messages.warning(request, f'Le quiz "{title}" a été créé, mais il y a eu une erreur lors de l\'ajout des questions: {str(e)}')
        else:
            messages.success(request, f'Le quiz "{title}" a été créé avec succès!')
        
        return redirect('quiz_detail', quiz_id=quiz.id)
    
    context = {
        'course': course,
    }
    return render(request, 'quiz_create.html', context)


@login_required
def quiz_detail(request, quiz_id):
    """Détails d'un quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Vérifier l'accès
    can_take = False
    attempts_left = 0
    is_enrolled = False
    
    if request.user.role == 'STUDENT':
        is_enrolled = Enrollment.objects.filter(
            student=request.user,
            course=quiz.course
        ).exists()
        
        if is_enrolled:
            attempts_count = QuizResult.objects.filter(
                student=request.user,
                quiz=quiz
            ).count()
            
            attempts_left = quiz.max_attempts - attempts_count
            can_take = attempts_left > 0
    
    # Résultats précédents
    previous_results = []
    if request.user.is_authenticated:
        previous_results = QuizResult.objects.filter(
            student=request.user,
            quiz=quiz
        ).order_by('-submitted_at')
    
    context = {
        'quiz': quiz,
        'can_take': can_take,
        'attempts_left': attempts_left,
        'is_enrolled': is_enrolled,
        'previous_results': previous_results,
        'question_count': quiz.questions.count(),
    }
    return render(request, 'quiz_detail.html', context)


@login_required
def quiz_take(request, quiz_id):
    """Passer un quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Vérifications
    if request.user.role != 'STUDENT':
        messages.error(request, 'Seuls les étudiants peuvent passer les quiz.')
        return redirect('quiz_detail', quiz_id=quiz_id)
    
    is_enrolled = Enrollment.objects.filter(
        student=request.user,
        course=quiz.course
    ).exists()
    
    if not is_enrolled:
        messages.error(request, 'Vous devez être inscrit au cours pour passer ce quiz.')
        return redirect('course_detail', course_id=quiz.course.id)
    
    # Vérifier le nombre de tentatives
    attempts_count = QuizResult.objects.filter(
        student=request.user,
        quiz=quiz
    ).count()
    
    if attempts_count >= quiz.max_attempts:
        messages.error(request, 'Vous avez atteint le nombre maximum de tentatives.')
        return redirect('quiz_detail', quiz_id=quiz_id)
    
    # Récupérer les questions
    questions = quiz.questions.order_by('order')
    
    context = {
        'quiz': quiz,
        'questions': questions,
        'attempt_number': attempts_count + 1,
    }
    return render(request, 'quiz_take.html', context)


@login_required
def quiz_submit(request, quiz_id):
    """Soumettre les réponses d'un quiz"""
    if request.method != 'POST':
        return redirect('quiz_detail', quiz_id=quiz_id)
    
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Récupérer les réponses
    answers = {}
    for key, value in request.POST.items():
        if key.startswith('question_'):
            question_id = key.replace('question_', '')
            answers[question_id] = value
    
    # Calculer le score
    questions = quiz.questions.all()
    total_points = sum(q.points for q in questions)
    earned_points = 0
    
    for question in questions:
        student_answer = answers.get(str(question.id), '').strip()
        correct_answer = question.correct_answer.strip()
        
        if question.question_type in ['MCQ', 'TRUE_FALSE']:
            choices = question.get_choices_list()
            
            # Convertir l'index de l'étudiant en texte si c'est un chiffre
            if student_answer.isdigit():
                answer_index = int(student_answer)
                if 0 <= answer_index < len(choices):
                    student_answer_text = choices[answer_index]
                else:
                    student_answer_text = student_answer
            else:
                student_answer_text = student_answer
            
            # Convertir l'index de la réponse correcte en texte si c'est un chiffre
            if correct_answer.isdigit():
                correct_index = int(correct_answer)
                if 0 <= correct_index < len(choices):
                    correct_answer_text = choices[correct_index]
                else:
                    correct_answer_text = correct_answer
            else:
                correct_answer_text = correct_answer
            
            # Comparer les deux textes
            if student_answer_text == correct_answer_text:
                earned_points += question.points
    
    # Calculer le pourcentage
    score = (earned_points / total_points * 100) if total_points > 0 else 0
    passed = score >= quiz.passing_score
    
    # Sauvegarder le résultat
    result = QuizResult.objects.create(
        student=request.user,
        quiz=quiz,
        score=score,
        answers=json.dumps(answers),
        passed=passed
    )
    
    messages.success(request, f'Quiz soumis ! Score: {score:.1f}%')
    return redirect('quiz_result_detail', result_id=result.id)


@login_required
def quiz_results(request, quiz_id):
    """Tous les résultats d'un quiz (pour les enseignants)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Vérifier que l'utilisateur est l'enseignant du cours
    if quiz.course.teacher != request.user:
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    results = QuizResult.objects.filter(quiz=quiz).select_related('student').order_by('-submitted_at')
    
    context = {
        'quiz': quiz,
        'results': results,
        'avg_score': results.aggregate(Avg('score'))['score__avg'] or 0,
        'pass_rate': results.filter(passed=True).count() / results.count() * 100 if results.count() > 0 else 0,
    }
    return render(request, 'quiz_results.html', context)


@login_required
def quiz_result_detail(request, result_id):
    """Détails d'un résultat de quiz"""
    result = get_object_or_404(QuizResult, id=result_id)
    
    # Vérifier l'accès
    if result.student != request.user and result.quiz.course.teacher != request.user:
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    # Parser les réponses
    answers = json.loads(result.answers) if result.answers else {}
    
    # Récupérer les questions avec les réponses de l'étudiant
    questions_data = []
    for question in result.quiz.questions.order_by('order'):
        student_answer = answers.get(str(question.id), '')
        choices = question.get_choices_list()
        
        questions_data.append({
            'question': question,
            'student_answer': student_answer,
            'student_answer_text': choices[int(student_answer)] if student_answer.isdigit() and int(student_answer) < len(choices) else student_answer,
            'correct_answer_text': choices[int(question.correct_answer)] if question.correct_answer.isdigit() and int(question.correct_answer) < len(choices) else question.correct_answer,
            'is_correct': student_answer == question.correct_answer,
        })
    
    # Gestion du feedback enseignant
    if request.method == 'POST' and result.quiz.course.teacher == request.user:
        result.teacher_feedback = request.POST.get('feedback', '')
        result.save()
        messages.success(request, 'Feedback ajouté avec succès !')
        return redirect('quiz_result_detail', result_id=result_id)
    
    context = {
        'result': result,
        'questions_data': questions_data,
        'is_teacher': request.user == result.quiz.course.teacher,
    }
    return render(request, 'quiz_result_detail.html', context)
