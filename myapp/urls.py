from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from .views import generate_quiz_view

urlpatterns =[
    # Pages publiques
    path('', views.home, name='home'),
    
    # Authentification
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    
    # Dashboard
    path('dashboard/', views.dashboard, name='dashboard'),
    
    # Cours
    path('courses/', views.course_list, name='course_list'),
    path('courses/<int:course_id>/', views.course_detail, name='course_detail'),
    path('courses/create/', views.course_create, name='course_create'),
    path('courses/<int:course_id>/edit/', views.course_edit, name='course_edit'),
    path('courses/<int:course_id>/enroll/', views.course_enroll, name='course_enroll'),
    
    # Quiz
    path('courses/<int:course_id>/quizzes/', views.quiz_list, name='quiz_list'),
    path('courses/<int:course_id>/quiz/create/', views.quiz_create, name='quiz_create'),
    path('quiz/<int:quiz_id>/', views.quiz_detail, name='quiz_detail'),
    path('quiz/<int:quiz_id>/take/', views.quiz_take, name='quiz_take'),
    path('quiz/<int:quiz_id>/submit/', views.quiz_submit, name='quiz_submit'),
    path('quiz/<int:quiz_id>/results/', views.quiz_results, name='quiz_results'),
    path('quiz/result/<int:result_id>/', views.quiz_result_detail, name='quiz_result_detail'),
path('generate-quiz/', generate_quiz_view, name='generate_quiz'),
path('courses/<int:course_id>/quiz/generate_ai/', views.generate_quiz_view, name='generate_quiz_ai'),
# urls.py
path('courses/<int:course_id>/quiz/generate_ai_pdf/', views.generate_quiz_ai_pdf, name='generate_quiz_ai_pdf'),
path('generate-quiz/', generate_quiz_view, name='generate_quiz'),
path('courses/<int:course_id>/quiz/generate_ai/', generate_quiz_view, name='generate_quiz'),

    # Feedback
    path('feedback/', views.feedback_list, name='feedback_list'),
    path('feedback/create/', views.feedback_create, name='feedback_create'),
    path('feedback/<int:feedback_id>/edit/', views.feedback_edit, name='feedback_edit'),
    path('feedback/<int:feedback_id>/delete/', views.feedback_delete, name='feedback_delete'),
    path('feedback/admin/', views.feedback_admin, name='feedback_admin'),
    path('feedback/<int:feedback_id>/approve/', views.feedback_approve, name='feedback_approve'),
    path('feedback/<int:feedback_id>/reject/', views.feedback_reject, name='feedback_reject'),
    
    # API pour détection de contenu
    path('api/check-content/', views.check_content_api, name='check_content_api'),
]