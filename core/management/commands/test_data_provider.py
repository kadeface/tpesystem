"""
测试教育数据提供器

用于验证和展示EducationDataProvider的功能
"""

import pandas as pd
import logging
from pathlib import Path
from django.core.management.base import BaseCommand
from django.conf import settings
from core.management.commands.education_data_provider import EducationDataProvider

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """测试教育数据提供器"""
    
    help = "测试教育数据提供器功能"
    
    def add_arguments(self, parser):
        parser.add_argument('-e', '--exam',
                          help='指定考试ID，多个用逗号分隔')
        parser.add_argument('-s', '--subject',
                          help='指定学科ID')
        parser.add_argument('-st', '--student',
                          help='指定学生ID，多个用逗号分隔')
        parser.add_argument('-o', '--output', type=Path,
                          default=settings.BASE_DIR / 'results' / 'data_provider_test')
    
    def handle(self, *args, **options):
        try:
            # 解析参数
            exam_ids = None
            if options.get('exam'):
                exam_ids = [e.strip() for e in options['exam'].split(',')]
                
            subject_id = options.get('subject')
            
            student_ids = None
            if options.get('student'):
                student_ids = [s.strip() for s in options['student'].split(',')]
            
            self.stdout.write(f"测试教育数据提供器：考试={exam_ids}, 学科={subject_id}, 学生={student_ids}")
            
            # 初始化数据提供器
            data_provider = EducationDataProvider(
                exam_ids=exam_ids,
                subject_id=subject_id,
                student_ids=student_ids
            )
            
            # 获取数据
            self.stdout.write("获取并处理数据...")
            data = data_provider.get_data()
            
            # 获取数据摘要
            self.stdout.write("\n数据摘要：")
            self.stdout.write(f"记录数: {len(data)}")
            self.stdout.write(f"学生数: {data['student_id'].nunique()}")
            
            if 'school_id' in data.columns:
                self.stdout.write(f"学校数: {data['school_id'].nunique()}")
                
            if 'class_id' in data.columns:
                self.stdout.write(f"班级数: {data['class_id'].nunique()}")
            
            # 获取班级摘要
            class_summary = data_provider.get_class_summary()
            if not class_summary.empty:
                self.stdout.write(f"\n班级摘要 ({len(class_summary)}个班级):")
                self.stdout.write(f"平均人数: {class_summary['student_count'].mean():.1f}")
                self.stdout.write(f"平均标准分: {class_summary['mean_score'].mean():.1f}")
            
            # 获取学校摘要
            school_summary = data_provider.get_school_summary()
            if not school_summary.empty:
                self.stdout.write(f"\n学校摘要 ({len(school_summary)}所学校):")
                self.stdout.write(f"平均班级数: {school_summary['class_count'].mean():.1f}")
                self.stdout.write(f"平均学生数: {school_summary['student_count'].mean():.1f}")
            
            # 准备建模数据
            model_data = data_provider.prepare_for_modeling()
            self.stdout.write(f"\n建模数据准备完成: {len(model_data)}条记录")
            
            # 保存结果
            output_dir = options['output']
            output_dir.mkdir(parents=True, exist_ok=True)
            
            data.to_csv(output_dir / 'processed_data.csv', index=False)
            class_summary.to_csv(output_dir / 'class_summary.csv', index=False)
            school_summary.to_csv(output_dir / 'school_summary.csv', index=False)
            
            self.stdout.write(self.style.SUCCESS(f"测试完成！数据已保存至：{output_dir}"))
            
        except Exception as e:
            logger.exception("数据提供器测试失败")
            self.stderr.write(self.style.ERROR(f"执行失败: {str(e)}")) 