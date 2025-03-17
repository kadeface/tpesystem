# core/analytics/data_access.py
from core.models import Student, Score, StudentHistory, TeacherHistory, ValueAddedEvaluation
from django.db.models import Avg, Max, Min, StdDev, F, Q, Count
import pandas as pd

class StudentDataAccess:
    """学生数据访问层，封装所有数据库查询操作"""
    
    @staticmethod
    def get_student_profile(student_id):
        """获取学生基本资料"""
        return Student.objects.select_related(
            'current_school', 'current_class', 'current_grade'
        ).get(student_id=student_id)
    
    @staticmethod
    def get_historical_scores(student_id, semesters=None):
        """获取学生历史成绩数据
        
        Args:
            student_id: 学生ID
            semesters: 学期列表，如果为None则获取所有学期数据
            
        Returns:
            pandas.DataFrame: 包含学生所有历史成绩的数据框
        """
        query = Score.objects.filter(student_id=student_id)
        
        if semesters:
            query = query.filter(semester_id__in=semesters)
            
        query = query.select_related(
            'subject', 'exam'
        ).order_by('semester_id', 'exam__exam_date')
        
        # 转换为pandas DataFrame便于后续分析
        scores_data = []
        for score in query:
            scores_data.append({
                'semester_id': score.semester_id,
                'exam_id': score.exam.exam_id,
                'exam_date': score.exam.exam_date,
                'exam_type': score.exam.exam_type,
                'subject_id': score.subject.subject_id,
                'subject_name': score.subject.subject_name,
                'raw_score': score.raw_score,
                'standard_score': score.standard_score,
                'percentile': score.percentile,
                'grade': score.grade
            })
        
        return pd.DataFrame(scores_data)
    
    @staticmethod
    def get_class_history(student_id):
        """获取学生班级变更历史"""
        return StudentHistory.objects.filter(
            student_id=student_id
        ).select_related(
            'grade', 'class_field', 'school', 'semester'
        ).order_by('semester__start_date')
    
    @staticmethod
    def get_class_average_scores(class_ids, semesters, subjects=None):
        """获取班级平均成绩"""
        query = Score.objects.filter(
            student__studenthistory__class_field_id__in=class_ids,
            semester_id__in=semesters
        )
        
        if subjects:
            query = query.filter(subject_id__in=subjects)
            
        return query.values(
            'semester_id', 'subject__subject_name'
        ).annotate(
            avg_score=Avg('raw_score'),
            max_score=Max('raw_score'),
            min_score=Min('raw_score'),
            std_dev=StdDev('raw_score')
        )
    
    @staticmethod
    def get_value_added_evaluations(student_id):
        """获取学生增值评价记录"""
        return ValueAddedEvaluation.objects.filter(
            target_type='STUDENT',
            target_id=student_id
        ).select_related('subject', 'semester')