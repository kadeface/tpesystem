# 新建一个用于测试非线性潜力评估的命令

import numpy as np
import pandas as pd
import os
import logging
from django.core.management.base import BaseCommand

from core.value_added_models import (
    ValueAddedDataProcessor,
    NonlinearStudentPotentialEvaluator
)

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = '使用非线性模型评估学生学习潜力'
    
    def add_arguments(self, parser):
        # 参数设置...
        parser.add_argument('--exams', nargs='+', type=str, required=True, help='考试ID列表')
        parser.add_argument('--subject', type=str, required=True, help='学科ID')
        parser.add_argument('--output', default='results/student_potential/', help='输出目录')
        parser.add_argument('--student-id', type=str, help='指定要分析的学生ID')
        
    def handle(self, *args, **options):
        try:
            # 1. 准备数据
            processor = ValueAddedDataProcessor()
            processor.load_exam_data(options['exams'], options['subject'])
            
            # 2. 获取模型数据
            model_data = processor.prepare_model_data()
            
            # 3. 创建非线性学习潜力评估器并准备数据
            evaluator = NonlinearStudentPotentialEvaluator(data=model_data)
            
            try:
                # 准备数据时会自动过滤掉考试记录不足的学生
                prepared_data = evaluator.prepare_data()
                logger.info(f"找到{prepared_data['student_id'].nunique()}名有足够考试记录的学生")
            except ValueError as e:
                self.stdout.write(self.style.ERROR(f"数据准备失败: {str(e)}"))
                return
            
            # 4. 评估潜力
            potential_scores = evaluator.evaluate_potential()
            
            # 5. 分析成长模式
            growth_patterns = evaluator.analyze_growth_patterns()
            
            # 6. 处理输出
            output_dir = options['output']
            os.makedirs(output_dir, exist_ok=True)
            
            # 7. 保存结果
            potential_scores.to_csv(os.path.join(output_dir, 'potential_scores.csv'), index=False)
            growth_patterns.to_csv(os.path.join(output_dir, 'growth_patterns.csv'), index=False)
            
            # 8. 如果指定了学生ID，输出详细报告
            if options.get('student_id'):
                student_id = options['student_id']
                student_report = evaluator.get_student_report(student_id)
                
                if 'error' in student_report:
                    self.stdout.write(self.style.ERROR(student_report['error']))
                else:
                    self.stdout.write(self.style.SUCCESS(f"学生 {student_id} 潜力评估报告:"))
                    for key, value in student_report.items():
                        if key not in ['scores_history', 'velocity_history', 'phase_recommendations']:
                            self.stdout.write(f"- {key}: {value}")
                            
                    self.stdout.write("学习阶段建议:")
                    for rec in student_report['phase_recommendations']:
                        self.stdout.write(f"  * {rec}")
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"评估失败: {str(e)}"))
            logger.exception("非线性潜力评估过程中发生错误") 