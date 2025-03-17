# core/analytics/report_generator.py
import pandas as pd
import numpy as np
from .data_access import StudentDataAccess
from .processors import StudentDataProcessor
from .algorithms import TrendAnalysisAlgorithm, StabilityIndexAlgorithm

class StudentGrowthAnalysisReport:
    """学生成长分析报告生成器"""
    
    def __init__(self, student_id):
        self.student_id = student_id
        self.processor = StudentDataProcessor(student_id)
        self.algorithms = {
            'trend': TrendAnalysisAlgorithm(),
            'stability': StabilityIndexAlgorithm()
        }
        
    def generate(self):
        """生成完整的学生成长分析报告"""
        # 准备分析数据
        data = self.processor.prepare_analysis_data()
        
        # 创建时间序列特征
        time_series = self.processor.create_time_series_features(
            data['historical_scores']
        )
        
        # 计算学科进步情况
        progress = self.processor.calculate_subject_progress(
            data['historical_scores']
        )
        
        # 执行趋势分析
        trends = self.algorithms['trend'].calculate(time_series)
        
        # 计算稳定性指数
        stability = self.algorithms['stability'].calculate(
            data['historical_scores']
        )
        
        # 生成综合评估指标
        indicators = self._generate_comprehensive_indicators(
            data, trends, progress, stability
        )
        
        # 计算相对班级表现
        class_performance = self._calculate_class_relative_performance(
            data['historical_scores'], data['class_averages']
        )
        
        # 构建报告
        return {
            'student_info': {
                'student_id': data['student_info'].student_id,
                'name': data['student_info'].name,
                'gender': data['student_info'].gender,
                'current_school': data['student_info'].current_school.school_name,
                'current_grade': data['student_info'].current_grade.grade_name,
                'current_class': data['student_info'].current_class.class_name
            },
            'academic_analysis': {
                'trends': trends,
                'progress': progress.to_dict('records') if not progress.empty else [],
                'stability': stability
            },
            'comprehensive_indicators': indicators,
            'class_performance': class_performance,
            'value_added': self._format_value_added_data(data['value_added'])
        }
    
    def _generate_comprehensive_indicators(self, data, trends, progress, stability):
        """生成综合评估指标"""
        indicators = {}
        
        # 1. 学业均衡指数
        subjects = data['historical_scores']['subject_name'].unique()
        if len(subjects) > 0:
            # 最近一个学期的成绩
            latest_semester = data['historical_scores']['semester_id'].max()
            latest_scores = data['historical_scores'][
                data['historical_scores']['semester_id'] == latest_semester
            ]
            
            if not latest_scores.empty:
                # 计算学科间分数标准差
                subject_avg = latest_scores.groupby('subject_name')['raw_score'].mean()
                # 标准差除以最高分，得到变异系数
                balance_index = 100 * (1 - (subject_avg.std() / subject_avg.max() if subject_avg.max() > 0 else 0))
                indicators['balance_index'] = min(100, max(0, balance_index))
            else:
                indicators['balance_index'] = 50  # 默认中等
        else:
            indicators['balance_index'] = 50  # 默认中等
            
        # 2. 学习稳定性指数
        if stability:
            avg_stability = np.mean([s['stability_index'] for s in stability.values()])
            indicators['stability_index'] = avg_stability
        else:
            indicators['stability_index'] = 50  # 默认中等
            
        # 3. 学业进步指数
        if not progress.empty:
            recent_progress = progress.sort_values('to_semester', ascending=False)
            # 各科进步平均值
            avg_progress_pct = recent_progress['progress_percentage'].mean()
            # 转换为0-100的指数
            progress_index = 50 + (avg_progress_pct * 2)  # 基准50，±25%对应±50分
            indicators['progress_index'] = min(100, max(0, progress_index))
        else:
            indicators['progress_index'] = 50  # 默认中等
            
        # 4. 发展潜力指数
        if trends:
            # 正向趋势的学科占比
            up_trend_count = sum(1 for t in trends.values() if t['direction'] == 'up')
            up_trend_ratio = up_trend_count / len(trends) if len(trends) > 0 else 0
            
            # 增长斜率平均值
            avg_slope = np.mean([t['slope'] for t in trends.values()])
            
            # 潜力指数计算
            potential_index = 50 + (up_trend_ratio * 25) + (min(10, avg_slope) * 2.5)
            indicators['potential_index'] = min(100, max(0, potential_index))
        else:
            indicators['potential_index'] = 50  # 默认中等
            
        return indicators
    
    def _calculate_class_relative_performance(self, student_scores, class_averages):
        """计算学生相对班级的表现"""
        if student_scores.empty or class_averages.empty:
            return {}
            
        # 合并学生成绩和班级平均
        merged = pd.merge(
            student_scores,
            class_averages,
            on=['semester_id', 'subject_name'],
            how='inner'
        )
        
        if merged.empty:
            return {}
            
        # 计算相对表现
        merged['relative_performance'] = merged['raw_score'] - merged['avg_score']
        merged['percentile_in_class'] = merged.apply(
            lambda x: stats.percentileofscore(
                np.linspace(x['min_score'], x['max_score'], 100),
                x['raw_score']
            ),
            axis=1
        )
        
        # 按学科和学期分组
        grouped = merged.groupby(['subject_name', 'semester_id']).agg({
            'relative_performance': 'mean',
            'percentile_in_class': 'mean'
        }).reset_index()
        
        # 转换为字典格式
        result = {}
        for _, row in grouped.iterrows():
            subject = row['subject_name']
            semester = row['semester_id']
            
            if subject not in result:
                result[subject] = {}
                
            result[subject][semester] = {
                'relative_score': row['relative_performance'],
                'percentile': row['percentile_in_class']
            }
            
        return result
    
    def _format_value_added_data(self, value_added):
        """格式化增值评价数据"""
        result = {}
        
        for evaluation in value_added:
            subject = evaluation.subject.subject_name
            semester = evaluation.semester.semester_id
            
            if subject not in result:
                result[subject] = {}
                
            result[subject][semester] = {
                'base_score': evaluation.base_score,
                'current_score': evaluation.current_score,
                'added_value': evaluation.added_value,
                'factors': evaluation.factors
            }
            
        return result