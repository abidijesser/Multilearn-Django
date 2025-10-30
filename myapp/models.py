from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone
from transformers import pipeline
# ==================== GESTION DES UTILISATEURS ====================

class User(AbstractUser):
    """
    Modèle utilisateur simplifié avec gestion des rôles
    """
    ROLE_CHOICES = [
        ('ADMIN', 'Administrateur'),
        ('TEACHER', 'Enseignant'),
        ('STUDENT', 'Étudiant'),
    ]
    
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='STUDENT')
    phone = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'users'
        verbose_name = 'Utilisateur'
        verbose_name_plural = 'Utilisateurs'
    
    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"


# ==================== GESTION DES COURS ====================

class Course(models.Model):
    """
    Modèle simplifié pour les cours avec contenu intégré
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Brouillon'),
        ('PUBLISHED', 'Publié'),
        ('ARCHIVED', 'Archivé'),
    ]
    
    # Informations de base
    title = models.CharField(max_length=200)
    description = models.TextField()
    teacher = models.ForeignKey(User, on_delete=models.CASCADE, related_name='courses_taught')
    
    # Contenu du cours (fusionné avec chapitres)
    content = models.TextField(help_text="Contenu complet du cours (texte, liens, etc.)")
    files = models.FileField(upload_to='courses/files/', blank=True, null=True, help_text="Fichiers du cours (PDF, ZIP, etc.)")
    
    # Métadonnées
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    level = models.CharField(max_length=50, blank=True, null=True)
    duration_hours = models.IntegerField(blank=True, null=True)
    cover_image = models.ImageField(upload_to='courses/', blank=True, null=True)
    
    # Étudiants inscrits (relation Many-to-Many simplifiée)
    students = models.ManyToManyField(User, through='Enrollment', related_name='enrolled_courses')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'courses'
        verbose_name = 'Cours'
        verbose_name_plural = 'Cours'
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title


class Enrollment(models.Model):
    """
    Table intermédiaire pour l'inscription avec suivi de progression
    """
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    
    # Progression
    progress = models.FloatField(default=0.0, validators=[MinValueValidator(0.0), MaxValueValidator(100.0)])
    completed = models.BooleanField(default=False)
    
    # Dates
    enrolled_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    last_accessed = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'enrollments'
        verbose_name = 'Inscription'
        verbose_name_plural = 'Inscriptions'
        unique_together = ['student', 'course']
    
    def __str__(self):
        return f"{self.student.username} - {self.course.title} ({self.progress}%)"


# ==================== GESTION DES QUIZ ====================

class Quiz(models.Model):
    """
    Modèle simplifié pour les quiz avec questions intégrées sous forme JSON
    """
    QUIZ_TYPE_CHOICES = [
        ('PRACTICE', 'Exercice'),
        ('EXAM', 'Examen'),
    ]
    
    # Relations
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='quizzes')
    
    # Informations de base
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    quiz_type = models.CharField(max_length=15, choices=QUIZ_TYPE_CHOICES, default='PRACTICE')
    
    # Configuration
    duration_minutes = models.IntegerField(blank=True, null=True)
    passing_score = models.FloatField(default=50.0)
    max_attempts = models.IntegerField(default=3, help_text="0 = illimité")
    show_answers = models.BooleanField(default=True, help_text="Afficher les corrections")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'quizzes'
        verbose_name = 'Quiz'
        verbose_name_plural = 'Quizzes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.course.title} - {self.title}"


class Question(models.Model):
    """
    Questions de quiz avec réponses intégrées
    """
    QUESTION_TYPE_CHOICES = [
        ('MCQ', 'QCM'),
        ('TRUE_FALSE', 'Vrai/Faux'),
        ('TEXT', 'Texte libre'),
    ]
    
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    
    # Contenu
    question_text = models.TextField()
    question_type = models.CharField(max_length=15, choices=QUESTION_TYPE_CHOICES)
    
    # Réponses (stockées sous forme de texte séparé par des virgules pour MCQ)
    # Format: "réponse1|réponse2|réponse3|réponse4"
    choices = models.TextField(blank=True, help_text="Réponses séparées par '|' (pour MCQ/Vrai-Faux)")
    correct_answer = models.TextField(help_text="Réponse correcte ou index (0,1,2...) pour MCQ")
    
    # Points et ordre
    points = models.FloatField(default=1.0)
    order = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'questions'
        verbose_name = 'Question'
        verbose_name_plural = 'Questions'
        ordering = ['quiz', 'order']
    
    def __str__(self):
        return f"{self.quiz.title} - Q{self.order}: {self.question_text[:50]}"
    
    def get_choices_list(self):
        """Retourne les choix sous forme de liste"""
        if self.choices:
            return self.choices.split('|')
        return []


class QuizResult(models.Model):
    """
    Résultats simplifiés des tentatives de quiz
    """
    # Relations
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_results')
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='results')
    
    # Score et statut
    score = models.FloatField(default=0.0)
    passed = models.BooleanField(default=False)
    attempt_number = models.IntegerField(default=1)
    
    # Réponses (stockées en JSON-like: "1:a,2:b,3:c" où 1,2,3 sont les IDs des questions)
    answers = models.TextField(help_text="Format: question_id:réponse,question_id:réponse")
    
    # Feedback enseignant (pour questions texte)
    teacher_feedback = models.TextField(blank=True, null=True)
    graded = models.BooleanField(default=False, help_text="Corrigé par l'enseignant")
    
    # Dates
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(blank=True, null=True)
    
    class Meta:
        db_table = 'quiz_results'
        verbose_name = 'Résultat de quiz'
        verbose_name_plural = 'Résultats de quiz'
        ordering = ['-submitted_at']
    
    def __str__(self):
        return f"{self.student.username} - {self.quiz.title}: {self.score}% (Tentative {self.attempt_number})"
    
    def get_answers_dict(self):
        """Retourne les réponses sous forme de dictionnaire"""
        if not self.answers:
            return {}
        result = {}
        for pair in self.answers.split(','):
            if ':' in pair:
                q_id, answer = pair.split(':', 1)
                result[int(q_id)] = answer
        return result


# ==================== GESTION DES FEEDBACKS PLATEFORME ====================

class PlatformFeedback(models.Model):
    """
    Modèle pour les avis généraux des utilisateurs sur la plateforme
    """
    # Utilisateur connecté (optionnel pour permettre les avis anonymes)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='platform_feedbacks', null=True, blank=True, help_text="Utilisateur connecté (optionnel)")
    
    # Informations de base (pour les avis anonymes)
    username = models.CharField(max_length=150, blank=True, null=True, help_text="Nom d'utilisateur (pour avis anonymes)")
    email = models.EmailField(blank=True, null=True, help_text="Adresse email (pour avis anonymes)")
    
    # Message obligatoire
    message = models.TextField(help_text="Message de feedback")
    
    def clean(self):
        """Validation personnalisée du modèle"""
        from django.core.exceptions import ValidationError
        
        if self.message and len(self.message.strip()) < 3:
            raise ValidationError('Le message doit contenir au moins 3 caractères.')
        
        # Vérifier qu'au moins un des deux est rempli (user OU username/email)
        if not self.user and not (self.username and self.email):
            raise ValidationError('Vous devez être connecté ou fournir un nom d\'utilisateur et un email.')
    
    def save(self, *args, **kwargs):
        """Override save pour appliquer la validation"""
        self.clean()
        super().save(*args, **kwargs)
    
    # Date de création
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Statut (optionnel pour modération)
    is_approved = models.BooleanField(default=True, help_text="Feedback approuvé")
    
    class Meta:
        db_table = 'platform_feedbacks'
        verbose_name = 'Platform Feedback'
        verbose_name_plural = 'Platform Feedbacks'
        ordering = ['-created_at']
    
    def __str__(self):
        if self.user:
            return f"Feedback de {self.user.username} ({self.created_at.strftime('%d/%m/%Y')})"
        else:
            return f"Feedback de {self.username} ({self.created_at.strftime('%d/%m/%Y')})"
    
    @property
    def display_name(self):
        """Retourne le nom d'affichage (utilisateur connecté ou nom saisi)"""
        if self.user:
            return self.user.get_full_name() or self.user.username
        return self.username
    
    @property
    def display_email(self):
        """Retourne l'email d'affichage (utilisateur connecté ou email saisi)"""
        if self.user:
            return self.user.email
        return self.email
# ==================== GESTION DES ÉVÉNEMENTS ====================

class Event(models.Model):
    """
    Modèle pour la gestion des événements (compétitions, hackathons, etc.)
    """
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    location = models.CharField(max_length=255, blank=True, null=True)
    is_online = models.BooleanField(default=False)
    image = models.ImageField(upload_to='events/', blank=True, null=True)
    max_participants = models.PositiveIntegerField(blank=True, null=True, help_text="Nombre maximum de participants (laisser vide pour illimité)")
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='events_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    

    class Meta:
        db_table = 'events'
        verbose_name = 'Événement'
        verbose_name_plural = 'Événements'
        ordering = ['-start_time']

def __str__(self):
    return self.title

@property
def duration(self):
    """Calcule la durée de l'événement"""
    if self.start_time and self.end_time:
        duration = self.end_time - self.start_time
        hours = duration.total_seconds() // 3600
        minutes = (duration.total_seconds() % 3600) // 60
        
        if hours > 0:
            return f"{int(hours)}h{int(minutes):02d}"
        else:
            return f"{int(minutes)} min"
    return "Non définie"

@property
def is_full(self):
    if self.max_participants is None:
        return False
    return self.participants.count() >= self.max_participants

class Participation(models.Model):
    STATUS_CHOICES = [
        ('REGISTERED', 'Inscrit'),
        ('CONFIRMED', 'Confirmé'),
        ('CANCELLED', 'Annulé'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='participations')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='participants')
    registered_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='REGISTERED')
    class Meta:
        db_table = 'participations'
        unique_together = ['user', 'event']

    def __str__(self):
        return f"{self.user.username} -> {self.event.title} ({self.get_status_display()})"

class EventFeedback(models.Model):
    event = models.ForeignKey('Event', on_delete=models.CASCADE, related_name='feedbacks')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    rating = models.PositiveSmallIntegerField(choices=[(i,i) for i in range(1,6)], null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sentiment_score = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'event_feedbacks'
        verbose_name = 'Event Feedback'
        verbose_name_plural = 'Event Feedbacks'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.comment and not self.sentiment_score:
            try:
                sentiment_analyzer = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")
                result = sentiment_analyzer(self.comment[:512])[0]
                self.sentiment_score = float(result.get('score', 0.5))
            except Exception:
                self.sentiment_score = 0.5
        super().save(*args, **kwargs)


    def __str__(self):
        return f"{self.user} - {self.event} - {self.rating} ⭐"
 # ---- NOUVELLES MÉTHODES POUR LES AVIS ----
    def average_rating(self):
        """Moyenne des notes"""
        return round(self.feedbacks.aggregate(avg=Avg('rating'))['avg'] or 0, 1)

    def feedback_count(self):
        """Nombre total d'avis"""
        return self.feedbacks.count()

    def positive_feedbacks(self):
        """Nombre d'avis positifs"""
        return self.feedbacks.filter(sentiment_score__gte=0.6).count()

    def neutral_feedbacks(self):
        """Nombre d'avis neutres"""
        return self.feedbacks.filter(sentiment_score__gte=0.4, sentiment_score__lt=0.6).count()

    def negative_feedbacks(self):
        """Nombre d'avis négatifs"""
        return self.feedbacks.filter(sentiment_score__lt=0.4).count()

# Keep Feedback as an alias for backwards compatibility
Feedback = EventFeedback
