"""
基于连续四次考试的贝叶斯增值评价命令。

该命令执行多时间点基线的增值评价，使用连续多次考试成绩作为基线。
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from django.core.management.base import BaseCommand
from django.conf import settings
from core.models import Student, Score, Exam, School, Class
from core.value_added_models import TimeSeriesBayesianValueAddedModel
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    执行基于连续多次考试的贝叶斯增值评价。
    
    Args:
        baseline_count: 用作基线的考试次数
        target_exam: 目标考试ID
        output: 输出路径
    """
    
    help = "使用连续多次考试成绩作为基线执行贝叶斯增值评价"
    
    def add_arguments(self, parser):
        parser.add_argument('-b', '--baseline_count', type=int, default=4,
                           help='基线考试次数(默认4)')
        parser.add_argument('-t', '--target_exam', 
                           help='目标考试ID')
        parser.add_argument('-o', '--output', type=Path,
                           default=settings.BASE_DIR / 'results' / 'timeseries_value_added')
    
    def handle(self, *args, **options):
        try:
            # 读取数据
            data = self._get_score_data(options['target_exam'], 
                                      options['baseline_count'])
            
            # 初始化模型
            model = TimeSeriesBayesianValueAddedModel(
                baseline_exams_count=options['baseline_count']
            )
            
            # 拟合模型
            results = model.fit(data)
            
            # 保存结果
            self._save_results(results, options['output'])
            
            self.stdout.write(
                self.style.SUCCESS(f"多时间点增值评价完成，结果已保存至{options['output']}")
            )
            
        except Exception as e:
            logger.exception("多时间点增值评价失败")
            self.stderr.write(self.style.ERROR(f"执行失败: {str(e)}"))
    
    def _get_score_data(self, target_exam_id, baseline_count):
        """获取考试成绩数据"""
        # 获取目标考试
        target_exam = Exam.objects.get(id=target_exam_id)
        
        # 获取之前的所有考试
        previous_exams = Exam.objects.filter(
            exam_date__lt=target_exam.exam_date,
            subject=target_exam.subject,
            grade=target_exam.grade
        ).order_by('-exam_date')
        
        if previous_exams.count() < baseline_count:
            raise ValueError(
                f"目标考试前没有足够的考试记录(需要{baseline_count}次，实际{previous_exams.count()}次)"
            )
        
        # 获取相关的考试ID
        exam_ids = [target_exam_id] + [str(e.id) for e in previous_exams[:baseline_count]]
        
        # 查询成绩数据
        scores = Score.objects.select_related('student', 'exam').filter(
            exam_id__in=exam_ids
        )
        
        # 转换为DataFrame
        score_data = []
        for score in scores:
            score_data.append({
                'student_id': score.student_id,
                'class_id': score.student.class_id,
                'school_id': score.student.school_id,
                'exam_id': score.exam_id,
                'exam_date': score.exam.exam_date,
                'standard_score': score.standard_score
            })
        
        return pd.DataFrame(score_data)
    
    def _save_results(self, results, output_dir):
        """保存分析结果"""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存学校效应
        school_effects = []
        for school_id, effect in results['school_effects'].items():
            school = School.objects.get(id=school_id)
            school_effects.append({
                'school_id': school_id,
                'school_name': school.name,
                'effect': round(effect['effect'], 3),
                'ci_lower': round(effect['ci_lower'], 3),
                'ci_upper': round(effect['ci_upper'], 3),
                'significant': effect['significant']
            })
        
        pd.DataFrame(school_effects).to_csv(
            output_dir / 'school_effects.csv', index=False
        )
        
        # 保存班级效应
        class_effects = []
        for class_id, effect in results['class_effects'].items():
            class_obj = Class.objects.get(id=class_id)
            class_effects.append({
                'class_id': class_id,
                'class_name': class_obj.name,
                'school_id': class_obj.school_id,
                'effect': round(effect['effect'], 3),
                'ci_lower': round(effect['ci_lower'], 3),
                'ci_upper': round(effect['ci_upper'], 3),
                'significant': effect['significant']
            })
        
        pd.DataFrame(class_effects).to_csv(
            output_dir / 'class_effects.csv', index=False
        )
        
        # 保存模型摘要
        results['model_summary'].to_csv(output_dir / 'model_summary.csv')
        
        logger.info(f"分析结果已保存至: {output_dir}") 