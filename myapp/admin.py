from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Course, Enrollment, Quiz, Question, QuizResult, PlatformFeedback, EventFeedback, Event, Participation, Reclamation 

# ==================== GESTION DES UTILISATEURS ====================

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['username', 'email', 'role', 'first_name', 'last_name', 'is_staff']
    list_filter = ['role', 'is_staff', 'is_superuser', 'is_active']
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Informations supplémentaires', {'fields': ('role', 'phone', 'bio', 'profile_picture')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('Informations supplémentaires', {'fields': ('role', 'phone', 'email')}),
    )

# ==================== GESTION DES COURS ====================

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'teacher', 'status', 'level', 'student_count', 'created_at']
    list_filter = ['status', 'level', 'created_at']
    search_fields = ['title', 'description', 'teacher__username']
    date_hierarchy = 'created_at'
    
    def student_count(self, obj):
        return obj.students.count()
    student_count.short_description = 'Étudiants inscrits'


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ['student', 'course', 'progress', 'completed', 'enrolled_at', 'last_accessed']
    list_filter = ['completed', 'enrolled_at']
    search_fields = ['student__username', 'course__title']
    readonly_fields = ['enrolled_at', 'last_accessed']

# ==================== GESTION DES QUIZ ====================

class QuestionInline(admin.TabularInline):
    model = Question
    extra = 2
    fields = ['question_text', 'question_type', 'choices', 'correct_answer', 'points', 'order']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'course', 'quiz_type', 'passing_score', 'max_attempts', 'question_count', 'created_at']
    list_filter = ['quiz_type', 'course', 'created_at']
    search_fields = ['title', 'description', 'course__title']
    inlines = [QuestionInline]
    date_hierarchy = 'created_at'
    
    def question_count(self, obj):
        return obj.questions.count()
    question_count.short_description = 'Questions'


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['question_text_short', 'quiz', 'question_type', 'points', 'order']
    list_filter = ['question_type', 'quiz']
    search_fields = ['question_text']
    list_editable = ['order']
    
    def question_text_short(self, obj):
        return obj.question_text[:60] + '...' if len(obj.question_text) > 60 else obj.question_text
    question_text_short.short_description = 'Question'


@admin.register(QuizResult)
class QuizResultAdmin(admin.ModelAdmin):
    list_display = ['student', 'quiz', 'score', 'passed', 'attempt_number', 'graded', 'submitted_at']
    list_filter = ['passed', 'graded', 'quiz', 'submitted_at']
    search_fields = ['student__username', 'quiz__title']
    readonly_fields = ['submitted_at', 'student', 'quiz', 'score', 'answers']
    date_hierarchy = 'submitted_at'
    
    fieldsets = (
        ('Informations', {
            'fields': ('student', 'quiz', 'attempt_number', 'submitted_at')
        }),
        ('Résultats', {
            'fields': ('score', 'passed', 'answers')
        }),
        ('Correction', {
            'fields': ('graded', 'teacher_feedback', 'graded_at')
        }),
    )


# ==================== GESTION DES FEEDBACKS PLATEFORME ====================

@admin.register(PlatformFeedback)
class PlatformFeedbackAdmin(admin.ModelAdmin):
    list_display = ['display_username', 'display_email', 'message_short', 'is_approved', 'created_at']
    list_filter = ['is_approved', 'created_at']
    search_fields = ['username', 'email', 'message', 'user__username', 'user__email']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    def display_username(self, obj):
        return obj.display_name
    display_username.short_description = 'Utilisateur'
    
    def display_email(self, obj):
        return obj.display_email
    display_email.short_description = 'Email'
    
    def message_short(self, obj):
        return obj.message[:50] + '...' if len(obj.message) > 50 else obj.message
    message_short.short_description = 'Message'
    
    fieldsets = (
        ('Informations', {
            'fields': ('user', 'username', 'email', 'created_at')
        }),
        ('Contenu', {
            'fields': ('message',)
        }),
        ('Modération', {
            'fields': ('is_approved',)
        }),
    )

# ==================== GESTION DES FEEDBACKS ÉVÉNEMENTS ====================

@admin.register(EventFeedback)
class EventFeedbackAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'rating', 'sentiment_score', 'created_at']
    list_filter = ['rating', 'created_at', 'event']
    search_fields = ['user__username', 'event__title', 'comment']
    readonly_fields = ['created_at', 'sentiment_score']
    date_hierarchy = 'created_at'
    
    def comment_short(self, obj):
        return obj.comment[:50] + '...' if obj.comment and len(obj.comment) > 50 else obj.comment
    comment_short.short_description = 'Commentaire'

# ==================== GESTION DES ÉVÉNEMENTS ====================

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ['title', 'start_time', 'end_time', 'location', 'is_online', 'created_by', 'created_at']
    list_filter = ['is_online', 'start_time', 'end_time', 'created_at']
    search_fields = ['title', 'description', 'location', 'created_by__username']
    date_hierarchy = 'start_time'


@admin.register(Participation)
class ParticipationAdmin(admin.ModelAdmin):
    list_display = ['user', 'event', 'status', 'registered_at']
    list_filter = ['status', 'registered_at']
    search_fields = ['user__username', 'event__title']
    readonly_fields = ['registered_at']

# ==================== GESTION DES RÉCLAMATIONS ====================

@admin.register(Reclamation)
class ReclamationAdmin(admin.ModelAdmin):
    list_display = ['sujet', 'student', 'type_reclamation', 'statut', 'priorite', 'created_at', 'traite_par']
    list_filter = ['statut', 'type_reclamation', 'priorite', 'created_at']
    search_fields = ['sujet', 'description', 'student__username', 'student__email']
    readonly_fields = ['created_at', 'updated_at', 'date_resolution']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Informations de base', {
            'fields': ('student', 'sujet', 'type_reclamation', 'description')
        }),
        ('Statut et traitement', {
            'fields': ('statut', 'priorite', 'traite_par', 'reponse_admin')
        }),
        ('Dates', {
            'fields': ('created_at', 'updated_at', 'date_resolution')
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('student', 'traite_par')
