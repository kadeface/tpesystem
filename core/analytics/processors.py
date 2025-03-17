# core/analytics/processors.py
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from scipy import stats
from .data_access import StudentDataAccess

class StudentDataProcessor:
    """学生数据处理器"""
    
    def __init__(self, student_id):
        self.student_id = student_id
        self.data_access = StudentDataAccess()
    
    def prepare_analysis_data(self):
        """准备分析所需的数据"""
        # 获取学生基本信息
        student = self.data_access.get_student_profile(self.student_id)
        
        # 获取历史成绩
        historical_scores = self.data_access.get_historical_scores(self.student_id)
        
        # 获取班级历史
        class_history = self.data_access.get_class_history(self.student_id)
        
        # 准备班级上下文数据
        class_ids = [h.class_field_id for h in class_history]
        semesters = [h.semester_id for h in class_history]
        
        # 获取班级平均成绩
        class_averages = self.data_access.get_class_average_scores(class_ids, semesters)
        
        # 获取增值评价
        value_added = self.data_access.get_value_added_evaluations(self.student_id)
        
        # 整合数据
        return {
            'student_info': student,
            'historical_scores': historical_scores,
            'class_history': class_history,
            'class_averages': pd.DataFrame(list(class_averages)),
            'value_added': value_added
        }
    
    def create_time_series_features(self, historical_scores):
        """创建时间序列特征"""
        if historical_scores.empty:
            return pd.DataFrame()
            
        # 按学期和学科分组计算各类统计指标
        grouped = historical_scores.groupby(['semester_id', 'subject_name'])
        
        # 提取关键指标
        aggregated = grouped.agg({
            'raw_score': ['mean', 'max', 'min', 'std'],
            'standard_score': ['mean', 'max', 'min', 'std'],
            'percentile': ['mean', 'max', 'min']
        }).reset_index()
        
        # 压平多级索引
        aggregated.columns = ['_'.join(col).strip('_') for col in aggregated.columns.values]
        
        return aggregated
    
    def calculate_subject_progress(self, scores_df):
        """计算各学科进步情况"""
        if scores_df.empty:
            return pd.DataFrame()
            
        # 按学科分组
        subjects = scores_df['subject_name'].unique()
        semesters = sorted(scores_df['semester_id'].unique())
        
        if len(semesters) < 2:
            return pd.DataFrame()  # 需要至少两个学期的数据
        
        progress_data = []
        
        for subject in subjects:
            subject_scores = scores_df[scores_df['subject_name'] == subject]
            
            for i in range(1, len(semesters)):
                prev_sem = semesters[i-1]
                curr_sem = semesters[i]
                
                # 获取前后学期的平均分
                prev_avg = subject_scores[
                    subject_scores['semester_id'] == prev_sem
                ]['raw_score'].mean()
                
                curr_avg = subject_scores[
                    subject_scores['semester_id'] == curr_sem
                ]['raw_score'].mean()
                
                # 计算进步值
                if not (np.isnan(prev_avg) or np.isnan(curr_avg)):
                    progress = curr_avg - prev_avg
                    progress_pct = (progress / prev_avg) * 100 if prev_avg > 0 else np.nan
                    
                    progress_data.append({
                        'subject': subject,
                        'from_semester': prev_sem,
                        'to_semester': curr_sem,
                        'progress_value': progress,
                        'progress_percentage': progress_pct
                    })
        
        return pd.DataFrame(progress_data)