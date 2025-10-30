from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.utils import timezone
from django import forms
from django.http import JsonResponse
from .models import User, Course, Enrollment, Quiz, Question, QuizResult, Event, Participation, EventFeedback, PlatformFeedback, Reclamation
import json
from django.views.decorators.csrf import csrf_exempt
from transformers import pipeline
import os
import requests
from django.core.files.base import ContentFile
from .content_filter import content_filter
from django.shortcuts import render
from .generate_quiz import generate_quiz_from_text
import re
import google.generativeai as genai

# Configuration Gemini
genai.configure(api_key='AIzaSyBFo_IkHcOzYFtLlzZKRcT7frmdcuvwB38')
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

# ---------- IA Image Generation Helper ----------
def generate_event_image(title: str, description: str):
    """
    Try to generate an image via Hugging Face Inference API using the title/description.
    Returns raw image bytes on success, or None otherwise.
    Requires env var HF_API_TOKEN. Uses a general SD model endpoint.
    """
    api_token = os.getenv('HF_API_TOKEN')
    if not api_token:
        return None
    prompt = f"Event poster, professional, modern, clean, high quality, '{title}'. {description[:200]}"
    try:
        resp = requests.post(
            'https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2',
            headers={'Authorization': f'Bearer {api_token}'},
            json={'inputs': prompt},
            timeout=30
        )
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        return None
    return None

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


# ============= Quiz AI Generation =============

@login_required
def generate_quiz_ai(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    quiz_data = None

    if request.method == "POST":
        course_text = request.POST.get("course_text", "").strip()
        if course_text:
            quiz_data = generate_quiz_from_text(course_text)

    context = {
        "quiz_data": quiz_data,
        "course": course
    }
    return render(request, "quiz/generate_quiz.html", context)

import PyPDF2
from PyPDF2 import PdfReader

@csrf_exempt
def generate_quiz_ai_pdf(request, course_id):
    if request.method == 'POST' and request.FILES.get('pdf'):
        pdf_file = request.FILES['pdf']
        reader = PdfReader(pdf_file)
        text = "".join([page.extract_text() + "\n" for page in reader.pages])
        # Exemple : appel IA pour générer des questions ici
        questions = [
            {
                "question_text": "Exemple question depuis PDF",
                "points": 10,
                "correct_answer": "Réponse 1",
                "options": ["Réponse 1", "Réponse 2", "Réponse 3"],
                "explanation": "Explication"
            }
        ]
        return JsonResponse({"questions": questions})
    return JsonResponse({"error": "Aucun PDF reçu"}, status=400)

@csrf_exempt
def generate_quiz_view(request, course_id):
    """Génération du quiz depuis texte ou PDF."""
    course = Course.objects.get(pk=course_id)

    # Gestion PDF
    if request.FILES.get("pdf"):
        pdf_file = request.FILES["pdf"]
        reader = PdfReader(pdf_file)
        text = "\n".join(page.extract_text() for page in reader.pages)
    else:
        data = json.loads(request.body.decode("utf-8"))
        text = data.get("text", "") or getattr(course, "description", "")

    if not text.strip():
        return JsonResponse({"questions": []})

    quiz_data = generate_quiz_from_text(text)
    return JsonResponse({"questions": quiz_data})

# ============= Content Filter API =============

def check_content_api(request):
    """
    API endpoint pour vérifier le contenu en temps réel
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
    
    try:
        data = json.loads(request.body)
        text = data.get('text', '')
        
        if not text:
            return JsonResponse({
                'is_appropriate': True,
                'score': 0,
                'message': '',
                'suggestions': []
            })
        
        # Analyser le contenu
        result = content_filter.check_content(text)
        
        # Ajouter des suggestions si nécessaire
        suggestions = []
        if not result['is_appropriate']:
            suggestions = content_filter.get_suggestions(text)
        
        return JsonResponse({
            'is_appropriate': result['is_appropriate'],
            'score': result['score'],
            'message': result['message'],
            'issues': result['issues'],
            'suggestions': suggestions,
            'bad_words_found': result['bad_words_found'],
            'suspicious_found': result['suspicious_found']
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Données JSON invalides'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============= Platform Feedback =============

def feedback_list(request):
    """Liste des feedbacks publics de la plateforme"""
    feedbacks = PlatformFeedback.objects.filter(is_approved=True).order_by('-created_at')
    
    context = {
        'feedbacks': feedbacks,
    }
    return render(request, 'feedback_list.html', context)


def feedback_create(request):
    """Créer un nouveau feedback plateforme"""
    if request.method == 'POST':
        message = request.POST.get('message')
        
        # Validation
        if not message:
            messages.error(request, 'Veuillez saisir votre message.')
            return render(request, 'feedback_create.html', {'user': request.user})
        
        if len(message.strip()) < 3:
            messages.error(request, 'Votre message doit contenir au moins 3 caractères.')
            return render(request, 'feedback_create.html', {'user': request.user})
        
        # Vérifier le contenu inapproprié côté serveur
        content_result = content_filter.check_content(message)
        if not content_result['is_appropriate']:
            messages.error(request, f"Contenu inapproprié détecté : {content_result['message']}")
            return render(request, 'feedback_create.html', {'user': request.user})
        
        # Créer le feedback
        if request.user.is_authenticated:
            feedback = PlatformFeedback.objects.create(
                user=request.user,
                message=message
            )
            messages.success(request, 'Merci pour votre feedback ! Il sera publié après modération.')
        else:
            username = request.POST.get('username')
            email = request.POST.get('email')
            
            if not all([username, email]):
                messages.error(request, 'Veuillez remplir tous les champs.')
                return render(request, 'feedback_create.html', {'user': request.user})
            
            feedback = PlatformFeedback.objects.create(
                username=username,
                email=email,
                message=message
            )
            messages.success(request, 'Merci pour votre feedback ! Il sera publié après modération.')
        
        return redirect('feedback_list')
    
    return render(request, 'feedback_create.html', {'user': request.user})


@login_required
def feedback_admin(request):
    """Gestion des feedbacks pour les administrateurs"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    feedbacks = PlatformFeedback.objects.all().order_by('-created_at')
    
    # Filtres
    status = request.GET.get('status')
    if status == 'approved':
        feedbacks = feedbacks.filter(is_approved=True)
    elif status == 'pending':
        feedbacks = feedbacks.filter(is_approved=False)
    
    context = {
        'feedbacks': feedbacks,
        'total_feedbacks': PlatformFeedback.objects.count(),
        'approved_feedbacks': PlatformFeedback.objects.filter(is_approved=True).count(),
        'pending_feedbacks': PlatformFeedback.objects.filter(is_approved=False).count(),
    }
    return render(request, 'feedback_admin.html', context)


@login_required
def feedback_approve(request, feedback_id):
    """Approuver un feedback"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    feedback = get_object_or_404(PlatformFeedback, id=feedback_id)
    feedback.is_approved = True
    feedback.save()
    
    messages.success(request, 'Feedback approuvé avec succès !')
    return redirect('feedback_admin')


@login_required
def feedback_reject(request, feedback_id):
    """Rejeter un feedback"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    feedback = get_object_or_404(PlatformFeedback, id=feedback_id)
    feedback.is_approved = False
    feedback.save()
    
    messages.success(request, 'Feedback rejeté.')
    return redirect('feedback_admin')


@login_required
def feedback_edit(request, feedback_id):
    """Modifier un feedback (propriétaire uniquement)"""
    feedback = get_object_or_404(PlatformFeedback, id=feedback_id)
    
    # Vérifier que l'utilisateur est le propriétaire du feedback
    if feedback.user != request.user:
        messages.error(request, 'Vous ne pouvez modifier que vos propres avis.')
        return redirect('feedback_list')
    
    if request.method == 'POST':
        message = request.POST.get('message')
        
        # Validation
        if not message:
            messages.error(request, 'Veuillez saisir votre message.')
            return render(request, 'feedback_edit.html', {'feedback': feedback})
        
        if len(message.strip()) < 3:
            messages.error(request, 'Votre message doit contenir au moins 3 caractères.')
            return render(request, 'feedback_edit.html', {'feedback': feedback})
        
        # Vérifier le contenu inapproprié côté serveur
        content_result = content_filter.check_content(message)
        if not content_result['is_appropriate']:
            messages.error(request, f"Contenu inapproprié détecté : {content_result['message']}")
            return render(request, 'feedback_edit.html', {'feedback': feedback})
        
        # Mettre à jour le feedback
        feedback.message = message
        feedback.save()
        
        messages.success(request, 'Votre avis a été modifié avec succès !')
        return redirect('feedback_list')
    
    return render(request, 'feedback_edit.html', {'feedback': feedback})


@login_required
def feedback_delete(request, feedback_id):
    """Supprimer un feedback (propriétaire uniquement)"""
    feedback = get_object_or_404(PlatformFeedback, id=feedback_id)
    
    # Vérifier que l'utilisateur est le propriétaire du feedback
    if feedback.user != request.user:
        messages.error(request, 'Vous ne pouvez supprimer que vos propres avis.')
        return redirect('feedback_list')
    
    if request.method == 'POST':
        feedback.delete()
        messages.success(request, 'Votre avis a été supprimé avec succès.')
        return redirect('feedback_list')
    
    return render(request, 'feedback_delete.html', {'feedback': feedback})


# ============= Gestion des événements =============
# ---------- Formulaire d'événement ----------
class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = ['title', 'description', 'start_time', 'end_time', 'location', 'is_online', 'image', 'max_participants']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        now = timezone.now()

        # Autoriser "maintenant" et le futur, interdire le passé
        if start_time and start_time < now:
            self.add_error('start_time', "La date de début ne doit pas être dans le passé.")

        # La date de fin doit être après la date de début
        if start_time and end_time and end_time <= start_time:
            self.add_error('end_time', "La date de fin doit être après la date de début.")

        return cleaned_data



# ---------- Vues pour les événements ----------
def event_list(request):
    """Vue publique qui affiche tous les événements (passés, en cours et futurs)"""
    current_time = timezone.now()
    # Récupérer tous les événements (passés, en cours et futurs)
    events = Event.objects.all().order_by('-start_time')
    
    # Filtres
    event_type = request.GET.get('type')
    search = request.GET.get('search')
    
    if event_type:
        events = events.filter(is_online=(event_type == 'online'))
    
    if search:
        events = events.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(location__icontains=search)
        )
    
    participated_event_ids = []
    if request.user.is_authenticated:
        participated_event_ids = list(
            Participation.objects.filter(user=request.user)
            .values_list('event_id', flat=True)
        )

    # Calcul des statistiques d'avis par événement
    feedback_stats = {}
    if events.exists():
        event_ids = list(events.values_list('id', flat=True))
        feedback_qs = EventFeedback.objects.filter(event_id__in=event_ids)
        # Pré-initialiser
        for eid in event_ids:
            feedback_stats[eid] = {
                'total': 0,
                'avg': 0.0,
                'ratings': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                'ratings_pct': {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0},
                'sentiment': {'pos': 0, 'neu': 0, 'neg': 0},
                'sentiment_pct': {'pos': 0.0, 'neu': 0.0, 'neg': 0.0},
                'breakdown': [],  # list of dicts: {'star': int, 'pct': float}
            }
        # Remplir les comptes par note
        for fb in feedback_qs.values('event_id', 'rating', 'sentiment_score'):
            eid = fb['event_id']
            rating = int(fb['rating']) if fb['rating'] else 0
            feedback_stats[eid]['total'] += 1
            if rating in feedback_stats[eid]['ratings']:
                feedback_stats[eid]['ratings'][rating] += 1
            score = fb.get('sentiment_score')
            if score is not None:
                if score >= 0.6:
                    feedback_stats[eid]['sentiment']['pos'] += 1
                elif score < 0.4:
                    feedback_stats[eid]['sentiment']['neg'] += 1
                else:
                    feedback_stats[eid]['sentiment']['neu'] += 1
        # Moyennes et pourcentages
        for eid, stats in feedback_stats.items():
            total = stats['total']
            if total > 0:
                s = sum(star * count for star, count in stats['ratings'].items())
                stats['avg'] = round(s / total, 1)
                for star, count in stats['ratings'].items():
                    stats['ratings_pct'][star] = round(count * 100.0 / total, 1)
                pos = stats['sentiment']['pos']
                neu = stats['sentiment']['neu']
                neg = stats['sentiment']['neg']
                stats['sentiment_pct']['pos'] = round(pos * 100.0 / total, 1)
                stats['sentiment_pct']['neu'] = round(neu * 100.0 / total, 1)
                stats['sentiment_pct']['neg'] = round(neg * 100.0 / total, 1)
                # Construct ordered breakdown 5 -> 1
                stats['breakdown'] = [
                    {'star': star, 'pct': stats['ratings_pct'][star]}
                    for star in [5,4,3,2,1]
                ]

        # Attacher les stats sur chaque objet event pour un accès simple dans le template
        events_map = {e.id: e for e in events}
        for eid, stats in feedback_stats.items():
            evt = events_map.get(eid)
            if evt is not None:
                setattr(evt, 'feedback_stats', stats)

    context = {
        'events': events,
        'current_filter': event_type,
        'search_query': search,
        'now': current_time,
        'participated_event_ids': participated_event_ids,
        'feedback_stats': feedback_stats,
    }
    return render(request, 'events_front.html', context)

@login_required
def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    participants = event.participants.all()  # ManyToMany via Participation
    return render(request, 'event_detail.html', {'event': event, 'participants': participants})

from django.http import JsonResponse

@login_required
def event_create(request):
    if request.method == 'POST':
        form = EventForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.created_by = request.user
            # Validation: start_time must NOT be in the past (allow now and future)
            if event.start_time < timezone.now():
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'errors': {'start_time': ["La date de début ne doit pas être dans le passé."]}}, status=400)
                messages.error(request, "La date de début ne doit pas être dans le passé.")
                return render(request, 'events_admin.html', {'form': form})

            event.save()
            # Image upload or AI generation
            if 'image' in request.FILES:
                event.image = request.FILES['image']
                event.save(update_fields=['image'])
            else:
                img_bytes = generate_event_image(event.title, event.description or '')
                if img_bytes:
                    event.image.save(f"event_{event.id}.png", ContentFile(img_bytes), save=True)
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'message': 'Événement créé avec succès',
                    'redirect': '/dashboard/events/'
                })
            return redirect('events_admin')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'errors': form.errors
                })
    else:
        form = EventForm()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return render(request, 'event_form.html', {'form': form})
    return render(request, 'events_admin.html', {'form': form})

@login_required
def event_edit(request, event_id):
    event = get_object_or_404(Event, id=event_id)
    
    # Vérifier que l'utilisateur est le créateur ou admin
    if event.created_by != request.user and request.user.role != 'ADMIN':
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'error',
                'message': "Vous n'êtes pas autorisé(e) à modifier cet événement."
            }, status=403)
        messages.error(request, "Vous n'êtes pas autorisé(e) à modifier cet événement.")
        return redirect('event_detail', event_id=event_id)

    if request.method == 'POST':
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            updated = form.save(commit=False)
            if updated.start_time < timezone.now():
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'status': 'error', 'errors': {'start_time': ["La date de début ne doit pas être dans le passé."]}}, status=400)
                messages.error(request, 'La date de début ne doit pas être dans le passé.')
                return render(request, 'event_form.html', {'form': form, 'event': event})
            updated.save()
            if 'image' in request.FILES:
                updated.image = request.FILES['image']
                updated.save(update_fields=['image'])
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'message': 'Événement modifié avec succès',
                    'redirect': '/dashboard/events/'
                })
            
            messages.success(request, 'Événement modifié avec succès')
            return redirect('events_admin')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'error',
                    'errors': form.errors
                })
    
    else:
        # REQUÊTE GET - Retourner le formulaire pré-rempli
        form = EventForm(instance=event)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            # Retourner le formulaire HTML pour AJAX
            return render(request, 'event_form.html', {
                'form': form,
                'event': event
            })
        
        return render(request, 'event_form.html', {'form': form, 'event': event})
@login_required
def event_delete(request, event_id):
    event = get_object_or_404(Event, id=event_id)

    # Vérifier que l'utilisateur est le créateur
    if event.created_by != request.user:
        messages.error(request, "Vous n'êtes pas autorisé(e) à supprimer cet événement.")
        return redirect('event_detail', event_id=event_id)

    event.delete()
    messages.success(request, f'Événement "{event.title}" supprimé avec succès !')
    return redirect('event_list')

@login_required
def participate_event(request, event_id):
    """Gérer la participation à un événement"""
    event = get_object_or_404(Event, id=event_id)
    
    # Vérifier si l'événement n'est pas terminé
    if event.end_time < timezone.now():
        messages.error(request, "Cet événement est déjà terminé.")
        return JsonResponse({
            'status': 'error',
            'message': 'Événement terminé'
        })
    # Vérifier capacité
    if event.max_participants is not None and event.participants.count() >= event.max_participants:
        return JsonResponse({
            'status': 'error',
            'message': 'Événement complet'
        }, status=400)
    
    # Créer la participation si elle n'existe pas
    participation, created = Participation.objects.get_or_create(
        user=request.user,
        event=event
    )
    
    message = "Vous participez maintenant à cet événement!" if created else "Vous êtes déjà inscrit à cet événement."
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'success',
            'message': message,
            'participant_count': event.participants.count()
        })
    
    messages.success(request, message)
    return redirect('event_list')

@login_required
def events_admin(request):
    """Vue pour la gestion des événements dans l'interface admin"""
    # Vérifier que l'utilisateur est admin
    if request.user.role != 'ADMIN':
        messages.error(request, "Vous n'avez pas accès à cette page.")
        return redirect('dashboard')
    
    # Récupérer tous les événements
    events = Event.objects.all().order_by('-start_time')

    # Calculer stats feedback par événement (même logique que front)
    feedback_stats = {}
    if events.exists():
        event_ids = list(events.values_list('id', flat=True))
        feedback_qs = EventFeedback.objects.filter(event_id__in=event_ids)
        for eid in event_ids:
            feedback_stats[eid] = {
                'total': 0,
                'avg': 0.0,
                'ratings': {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
                'ratings_pct': {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0},
                'sentiment': {'pos': 0, 'neu': 0, 'neg': 0},
                'sentiment_pct': {'pos': 0.0, 'neu': 0.0, 'neg': 0.0},
                'breakdown': [],
            }
        for fb in feedback_qs.values('event_id', 'rating', 'sentiment_score'):
            eid = fb['event_id']
            rating = int(fb['rating']) if fb['rating'] else 0
            feedback_stats[eid]['total'] += 1
            if rating in feedback_stats[eid]['ratings']:
                feedback_stats[eid]['ratings'][rating] += 1
            score = fb.get('sentiment_score')
            if score is not None:
                if score >= 0.6:
                    feedback_stats[eid]['sentiment']['pos'] += 1
                elif score < 0.4:
                    feedback_stats[eid]['sentiment']['neg'] += 1
                else:
                    feedback_stats[eid]['sentiment']['neu'] += 1
        for eid, stats in feedback_stats.items():
            total = stats['total']
            if total > 0:
                s = sum(star * count for star, count in stats['ratings'].items())
                stats['avg'] = round(s / total, 1)
                for star, count in stats['ratings'].items():
                    stats['ratings_pct'][star] = round(count * 100.0 / total, 1)
                pos = stats['sentiment']['pos']
                neu = stats['sentiment']['neu']
                neg = stats['sentiment']['neg']
                stats['sentiment_pct']['pos'] = round(pos * 100.0 / total, 1)
                stats['sentiment_pct']['neu'] = round(neu * 100.0 / total, 1)
                stats['sentiment_pct']['neg'] = round(neg * 100.0 / total, 1)
                stats['breakdown'] = [
                    {'star': star, 'pct': stats['ratings_pct'][star]}
                    for star in [5,4,3,2,1]
                ]

        # Attacher sur chaque event
        events_map = {e.id: e for e in events}
        for eid, stats in feedback_stats.items():
            evt = events_map.get(eid)
            if evt is not None:
                setattr(evt, 'feedback_stats', stats)

    return render(request, 'events_admin.html', {
        'events': events,
        'now': timezone.now(),
    })

@login_required
def event_participants(request, event_id):
    """Page de gestion des participants pour un événement"""
    if request.user.role != 'ADMIN':
        messages.error(request, "Accès non autorisé.")
        return redirect('dashboard')
    
    event = get_object_or_404(Event, id=event_id)
    participants = event.participants.select_related('user').all()
    
    # Statistiques
    stats = {
        'total': participants.count(),
        'confirmed': participants.filter(status='CONFIRMED').count(),
        'registered': participants.filter(status='REGISTERED').count(),
        'cancelled': participants.filter(status='CANCELLED').count(),
    }
    
    context = {
        'event': event,
        'participants': participants,
        'stats': stats,
    }
    return render(request, 'event_participants.html', context)

@login_required
def update_participation_status(request, event_id, user_id):
    """Mettre à jour le statut d'un participant"""
    if request.user.role != 'ADMIN':
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    if request.method == 'POST':
        participation = get_object_or_404(Participation, event_id=event_id, user_id=user_id)
        new_status = request.POST.get('status')
        
        if new_status in ['REGISTERED', 'CONFIRMED', 'CANCELLED']:
            participation.status = new_status
            participation.save()
            
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'new_status': new_status})
            
            messages.success(request, f"Statut mis à jour pour {participation.user.username}")
        
        return redirect('event_participants', event_id=event_id)
    
    # Déplacer cette fonction au même niveau que les autres vues (pas à l'intérieur d'une autre fonction)

@login_required
def create_test_finished_event(request):
    """Créer un événement de test déjà terminé et inscrire l'utilisateur courant"""
    now = timezone.now()
    event = Event.objects.create(
        title=f"Événement Test Terminé {now.strftime('%Y-%m-%d %H:%M:%S')}",
        description="Événement de test pour le feedback",
        start_time=now - timezone.timedelta(hours=2),
        end_time=now - timezone.timedelta(minutes=1),
        location="Salle virtuelle",
        is_online=True,
        created_by=request.user,
    )

    # Inscrire l'utilisateur courant comme participant pour afficher le bouton feedback
    Participation.objects.get_or_create(user=request.user, event=event, defaults={'status': 'REGISTERED'})

    messages.success(request, f'Événement de test créé: "{event.title}". Il est déjà terminé. Vous pouvez donner un avis.')
    return redirect('event_list')
@login_required
@csrf_exempt
def submit_feedback(request, event_id):
    if request.method == 'POST':
        try:
            event = Event.objects.get(id=event_id)
        except Event.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Événement introuvable.'}, status=404)

        # Autoriser l'avis si l'utilisateur a participé OU si l'événement est terminé
        has_participated = Participation.objects.filter(user=request.user, event=event, status__in=['REGISTERED', 'CONFIRMED']).exists()
        if not has_participated and event.end_time >= timezone.now():
            return JsonResponse({'status': 'error', 'message': 'Vous pourrez donner un avis à la fin de l\'événement.'}, status=403)

        rating_raw = request.POST.get('rating')
        rating = int(rating_raw) if rating_raw and rating_raw.isdigit() else None
        comment = request.POST.get('comment', '').strip()

        if not comment:
            return JsonResponse({'status': 'error', 'message': 'Veuillez saisir un avis (texte) pour l’analyse IA.'}, status=400)

        # Analyse du sentiment avec Hugging Face (multilingue)
        # Ce modèle retourne: {'label': '5 stars', 'score': 0.xxx} ou {'label': '1 star', 'score': 0.xxx}
        sentiment_score = 0.5  # Par défaut neutre
        if comment:
            try:
                sentiment_analyzer = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")
                sentiment_result = sentiment_analyzer(comment[:512])
                # Le résultat est une liste avec dict: {'label': '5 stars', 'score': 0.xxx}
                if sentiment_result and len(sentiment_result) > 0:
                    result = sentiment_result[0]
                    label = result.get('label', '')
                    score = float(result.get('score', 0.5))
                    
                    # Convertir le label en sentiment_score basé sur les étoiles
                    # 5 stars -> positif (> 0.8), 4 stars -> plutôt positif (> 0.6)
                    # 3 stars -> neutre (0.4-0.6), 2-1 stars -> négatif (< 0.4)
                    if '5 stars' in label:
                        sentiment_score = 0.9
                    elif '4 stars' in label:
                        sentiment_score = 0.7
                    elif '3 stars' in label:
                        sentiment_score = 0.5
                    elif '2 stars' in label:
                        sentiment_score = 0.3
                    elif '1 star' in label:
                        sentiment_score = 0.1
                    else:
                        sentiment_score = score
                    
                    print(f"[DEBUG] Comment: '{comment[:50]}...' | Label: {label} | Score: {sentiment_score} | Original: {score}")
            except Exception as e:
                print(f"[ERROR] Sentiment analysis failed: {e}")
                sentiment_score = 0.5

        EventFeedback.objects.update_or_create(
            user=request.user,
            event=event,
            defaults={'rating': rating, 'comment': comment, 'sentiment_score': sentiment_score}
        )

        return JsonResponse({'status': 'success', 'message': 'Merci pour votre avis !'})

    return JsonResponse({'status': 'error', 'message': 'Méthode non autorisée.'}, status=405)


# ============= GESTION DES RÉCLAMATIONS =============

@login_required
def reclamation_create(request):
    """Créer une nouvelle réclamation (étudiants uniquement)"""
    if request.method == 'POST':
        sujet = request.POST.get('sujet')
        type_reclamation = request.POST.get('type_reclamation')
        description = request.POST.get('description')
        
        # Validation
        if not all([sujet, type_reclamation, description]):
            messages.error(request, 'Veuillez remplir tous les champs.')
            return render(request, 'reclamation_create.html')
        
        if len(description.strip()) < 10:
            messages.error(request, 'La description doit contenir au moins 10 caractères.')
            return render(request, 'reclamation_create.html')
        
        # Créer la réclamation
        reclamation = Reclamation.objects.create(
            student=request.user,
            sujet=sujet,
            type_reclamation=type_reclamation,
            description=description,
            statut='EN_ATTENTE'
        )
        
        messages.success(request, 'Votre réclamation a été soumise avec succès. Nous la traiterons dans les plus brefs délais.')
        return redirect('reclamation_detail', reclamation_id=reclamation.id)
    
    return render(request, 'reclamation_create.html')


@login_required
def reclamation_list(request):
    """Liste des réclamations de l'étudiant connecté"""
    reclamations = Reclamation.objects.filter(student=request.user).order_by('-created_at')
    
    # Filtres
    statut_filter = request.GET.get('statut')
    type_filter = request.GET.get('type')
    
    if statut_filter:
        reclamations = reclamations.filter(statut=statut_filter)
    
    if type_filter:
        reclamations = reclamations.filter(type_reclamation=type_filter)
    
    # Statistiques
    stats = {
        'total': reclamations.count(),
        'en_attente': reclamations.filter(statut='EN_ATTENTE').count(),
        'en_cours': reclamations.filter(statut='EN_COURS').count(),
        'resolues': reclamations.filter(statut='RESOLUE').count(),
        'rejetees': reclamations.filter(statut='REJETEE').count(),
    }
    
    context = {
        'reclamations': reclamations,
        'stats': stats,
    }
    return render(request, 'reclamation_list.html', context)


@login_required
def reclamation_detail(request, reclamation_id):
    """Détail d'une réclamation"""
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    # Vérifier que l'utilisateur a le droit de voir cette réclamation
    if reclamation.student != request.user and request.user.role != 'ADMIN':
        messages.error(request, 'Vous n\'avez pas accès à cette réclamation.')
        return redirect('reclamation_list')
    
    context = {
        'reclamation': reclamation,
    }
    return render(request, 'reclamation_detail.html', context)


@login_required
def reclamation_admin(request):
    """Gestion des réclamations pour les administrateurs"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    reclamations = Reclamation.objects.all().order_by('-created_at')
    
    # Filtres
    statut_filter = request.GET.get('statut')
    type_filter = request.GET.get('type')
    priorite_filter = request.GET.get('priorite')
    
    if statut_filter:
        reclamations = reclamations.filter(statut=statut_filter)
    
    if type_filter:
        reclamations = reclamations.filter(type_reclamation=type_filter)
    
    if priorite_filter:
        reclamations = reclamations.filter(priorite=priorite_filter)
    
    # Statistiques
    stats = {
        'total': Reclamation.objects.count(),
        'en_attente': Reclamation.objects.filter(statut='EN_ATTENTE').count(),
        'en_cours': Reclamation.objects.filter(statut='EN_COURS').count(),
        'resolues': Reclamation.objects.filter(statut='RESOLUE').count(),
        'rejetees': Reclamation.objects.filter(statut='REJETEE').count(),
    }
    
    context = {
        'reclamations': reclamations,
        'stats': stats,
    }
    return render(request, 'reclamation_admin.html', context)


@login_required
def reclamation_traiter(request, reclamation_id):
    """Marquer une réclamation comme en cours de traitement"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    reclamation.marquer_en_cours(request.user)
    
    messages.success(request, 'La réclamation est maintenant en cours de traitement.')
    return redirect('reclamation_admin')


@login_required
def reclamation_resoudre(request, reclamation_id):
    """Résoudre une réclamation"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        reponse = request.POST.get('reponse')
        
        if not reponse:
            messages.error(request, 'Veuillez fournir une réponse.')
            return redirect('reclamation_admin')
        
        reclamation.resoudre(request.user, reponse)
        messages.success(request, 'La réclamation a été résolue avec succès.')
        return redirect('reclamation_admin')
    
    return render(request, 'reclamation_resoudre.html', {'reclamation': reclamation})


@login_required
def reclamation_rejeter(request, reclamation_id):
    """Rejeter une réclamation"""
    if request.user.role != 'ADMIN':
        messages.error(request, 'Accès non autorisé.')
        return redirect('dashboard')
    
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        raison = request.POST.get('raison')
        
        if not raison:
            messages.error(request, 'Veuillez fournir une raison.')
            return redirect('reclamation_admin')
        
        reclamation.rejeter(request.user, raison)
        messages.success(request, 'La réclamation a été rejetée.')
        return redirect('reclamation_admin')
    
    return render(request, 'reclamation_rejeter.html', {'reclamation': reclamation})


@login_required
def reclamation_update_priorite(request, reclamation_id):
    """Mettre à jour la priorité d'une réclamation"""
    if request.user.role != 'ADMIN':
        return JsonResponse({'error': 'Non autorisé'}, status=403)
    
    reclamation = get_object_or_404(Reclamation, id=reclamation_id)
    
    if request.method == 'POST':
        priorite = request.POST.get('priorite')
        if priorite in ['BASSE', 'MOYENNE', 'HAUTE']:
            reclamation.priorite = priorite
            reclamation.save()
            return JsonResponse({'status': 'success', 'message': 'Priorité mise à jour'})
    
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)
