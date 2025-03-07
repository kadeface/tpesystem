from django.urls import path
from . import views

urlpatterns = [
    path('task-status/', views.task_status, name='task_status'),
] 