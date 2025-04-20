from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RegionViewSet, GradeViewSet, SubjectViewSet, 
    ExamViewSet, SchoolViewSet
)

router = DefaultRouter()
router.register(r'regions', RegionViewSet)
router.register(r'grades', GradeViewSet)
router.register(r'subjects', SubjectViewSet)
router.register(r'exams', ExamViewSet)
router.register(r'schools', SchoolViewSet)

urlpatterns = [
    path('', include(router.urls)),
] 