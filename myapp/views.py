from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count, Avg, Q
from django.utils import timezone
from .models import User, Course, Enrollment, Quiz
from django.http import JsonResponse
import json
import re
import os
import logging
import requests

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404

from .models import Course

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY = getattr(settings, "GROQ_API_KEY", None)

# -------------------------
# Utilitaires
# -------------------------
def chunk_text(text, max_chars=1000):
    """Découpe le texte en chunks cohérents."""
    if not text:
        return []
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
    if not paragraphs:
        paragraphs = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) + 2 < max_chars:
            current = f"{current}\n\n{para}" if current else para
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    if not chunks and text:
        chunks = [text[:max_chars]]
    return chunks

def find_relevant_chunks(question, chunks, top_k=3):
    """Score simple par overlap lexical et retourne les meilleurs chunks."""
    q_words = set(re.findall(r'\w+', question.lower()))
    scored = []
    for i, chunk in enumerate(chunks):
        cw = set(re.findall(r'\w+', chunk.lower()))
        common = len(q_words & cw)
        # léger bonus pour premiers chunks
        score = common + (1 if i < 2 else 0)
        if score > 0:
            scored.append((score, chunk))
    if not scored:
        return chunks[:top_k]
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]

def compute_confidence(question, context, method):
    """Retourne un score 0..1 basé sur overlap simple + méthode."""
    q_words = set(re.findall(r'\w+', question.lower()))
    ctx_words = set(re.findall(r'\w+', context.lower()))
    if not q_words:
        return 0.45 if method == "fallback" else 0.75
    overlap = len(q_words & ctx_words) / len(q_words)
    if method == "groq":
        score = 0.6 + 0.35 * overlap
    else:
        score = 0.25 + 0.5 * overlap
    score = max(0.1, min(score, 0.98))
    return round(score, 2)

# -------------------------
# Llamas / Groq
# -------------------------
def ask_groq(question, context, mode="strict"):
    """
    Appel Groq. mode currently ignored (kept for extensibilité).
    Retour: (answer_str or None, success_bool)
    """
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY non configurée.")
        return None, False

    # Prompt : on demande au modèle d'utiliser le contexte (strict)
    prompt = (
        "Tu es un assistant pédagogique expert. Réponds en français, de façon claire et concise.\n"
        "Utilise d'abord le CONTENU DU COURS fourni. Si la réponse n'est pas dans le contenu, "
        "dis clairement que l'information n'est pas disponible dans le cours.\n\n"
        f"CONTENU DU COURS:\n{context}\n\nQUESTION:\n{question}\n\nRÉPONSE:"
    )

    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": "Tu es un assistant pédagogique expert."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 600,
        "top_p": 0.9
    }

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=30
        )
    except requests.exceptions.Timeout:
        logger.exception("Groq timeout")
        return None, False
    except requests.exceptions.RequestException as e:
        logger.exception("Erreur réseau Groq: %s", e)
        return None, False

    if resp.status_code != 200:
        logger.error("Groq returned %s: %s", resp.status_code, resp.text)
        return None, False

    try:
        data = resp.json()
    except ValueError:
        logger.error("Groq returned non-json")
        return None, False

    # parsing robuste
    answer = None
    try:
        choices = data.get("choices")
        if choices and len(choices) > 0:
            choice = choices[0]
            msg = choice.get("message") or {}
            if isinstance(msg, dict) and msg.get("content"):
                answer = msg.get("content")
            elif choice.get("text"):
                answer = choice.get("text")
            else:
                # trouver première valeur string non vide
                for v in choice.values():
                    if isinstance(v, str) and v.strip():
                        answer = v
                        break
    except Exception as e:
        logger.exception("Erreur parsing Groq response: %s", e)
        return None, False

    if not answer:
        logger.error("Aucune réponse trouvée dans payload Groq")
        return None, False

    return answer.strip(), True

# -------------------------
# Endpoint Q&A
# -------------------------
@csrf_exempt
def course_qa(request, course_id):
    """
    POST JSON: { "question": "..." }
    Retour JSON: { question, answer, method, confidence, sources }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Méthode non autorisée"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse({"error": "Format JSON invalide."}, status=400)

    question = (payload.get("question") or "").strip()
    if not question:
        return JsonResponse({"error": "Aucune question reçue."}, status=400)
    if len(question) > 1500:
        return JsonResponse({"error": "Question trop longue (max 1500 caractères)."}, status=400)

    course = get_object_or_404(Course, id=course_id)
    context = (course.description or "") + "\n\n" + (course.content or "")

    # chunks & recherche simple pour produire sources
    chunks = chunk_text(context, max_chars=1200)
    relevant = find_relevant_chunks(question, chunks, top_k=3)
    if not relevant:
        relevant = chunks[:2] if chunks else [context[:1200]]

    context_for_llm = "\n\n".join(relevant)
    if len(context_for_llm) > 3500:
        context_for_llm = context_for_llm[:3500] + "\n\n[...]"

    answer, success = ask_groq(question, context_for_llm)
    if not success or not answer:
        answer = generate_fallback(question=question, context=context_for_llm)
        method = "fallback"
    else:
        method = "groq"

    # préparer sources (aperçus)
    sources = []
    for c in relevant[:3]:
        preview = c[:300] + "..." if len(c) > 300 else c
        sources.append({"text": preview})

    confidence = compute_confidence(question, context_for_llm, method)

    logger.info("Q&A course=%s method=%s success=%s", course_id, method, success)

    return JsonResponse({
        "question": question,
        "answer": answer,
        "method": method,
        "confidence": confidence,
        "sources": sources
    })

# fallback generator réutilisable
def generate_fallback(question, context):
    """Génère un fallback à partir du contexte (phrases les plus pertinentes)."""
    if not context:
        return "❌ Je n’ai pas trouvé cette information dans le cours."

    sentences = re.split(r'(?<=[.!?])\s+', context.strip())
    q_words = set(re.findall(r'\w+', question.lower()))
    scored = []
    for s in sentences:
        s_clean = s.strip()
        if len(s_clean) < 30 or len(s_clean) > 600:
            continue
        s_words = set(re.findall(r'\w+', s_clean.lower()))
        score = len(q_words & s_words)
        if score > 0:
            scored.append((score, s_clean))
    if not scored:
        # retourner quelques extraits si rien de pertinent
        fallback_list = [s for s in sentences if 40 <= len(s) <= 300][:2]
        if fallback_list:
            return "📝 Extraits du cours pertinents :\n\n" + "\n\n".join(f"• {s}" for s in fallback_list)
        return "❌ Je n’ai pas trouvé cette information dans le cours."
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [s for _, s in scored[:2]]
    return "📝 Extraits du cours pertinents :\n\n" + "\n\n".join(f"• {s}" for s in top)






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
@login_required
def course_delete(request, course_id):
    """Supprimer un cours (enseignants uniquement)"""
    course = get_object_or_404(Course, id=course_id)
    
    # Vérifier que l'utilisateur est bien le propriétaire du cours
    if course.teacher != request.user:
        messages.error(request, "Vous n'êtes pas autorisé à supprimer ce cours.")
        return redirect('course_detail', course_id=course.id)
    
    if request.method == 'POST':
        title = course.title
        course.delete()
        messages.success(request, f'Le cours "{title}" a été supprimé avec succès.')
        return redirect('dashboard')
    
    # Page de confirmation (optionnelle)
    return render(request, 'course_delete_confirm.html', {'course': course})


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
