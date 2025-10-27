from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
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
    # ==================== Événements ====================

path('events/', views.event_list, name='event_list'),
path('events/create/', views.event_create, name='event_create'),
path('events/<int:event_id>/', views.event_detail, name='event_detail'),
path('events/<int:event_id>/edit/', views.event_edit, name='event_edit'),
path('events/<int:event_id>/delete/', views.event_delete, name='event_delete'),
 path('dashboard/events/', views.events_admin, name='events_admin'),  # Changed from admin/events/
    path('dashboard/events/create/', views.event_create, name='event_create'),
    path('dashboard/events/<int:event_id>/edit/', views.event_edit, name='event_edit'),
    path('dashboard/events/<int:event_id>/delete/', views.event_delete, name='event_delete'),
# Participation
path('events/<int:event_id>/participate/', views.participate_event, name='participate_event'),
path('dashboard/events/<int:event_id>/participants/', views.event_participants, name='event_participants'),
path('dashboard/events/<int:event_id>/participants/<int:user_id>/update/', views.update_participation_status, name='update_participation_status'),
]
