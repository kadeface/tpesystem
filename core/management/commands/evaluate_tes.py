"""
使用TES模式进行增值评价的管理命令
"""
import pandas as pd 
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Score, School, Student, Subject, Semester, ValueAddedEvaluation, ValueAddedConfig, Exam
from core.algorithms.evaluation_models import SimpleDifferenceModel

class Command(BaseCommand):
    help = '使用TES模式进行增值评价'

    def add_arguments(self, parser):
        parser.add_argument('--base-semester', type=str, required=True, help='基线学期ID，例如：2023-2024-1')
        parser.add_argument('--current-semester', type=str, required=True, help='当前学期ID，例如：2023-2024-2')
        parser.add_argument('--subject', type=str, required=True, help='学科ID，例如：CHN')
        parser.add_argument('--base-exam', type=str, help='基线考试ID，例如：202310-FINAL')
        parser.add_argument('--current-exam', type=str, help='当前考试ID，例如：202320-FINAL')
        parser.add_argument('--school', type=str, help='学校ID（可选）')
        parser.add_argument('--config', type=str, help='配置ID（可选）')
        parser.add_argument('--no-save', action='store_true', help='不保存结果到数据库')
        parser.add_argument('--exam-type', type=str, help='考试类型(如果未指定具体考试ID)，例如：FINAL,MID')

    def handle(self, *args, **options):
        base_semester_id = options['base_semester']
        current_semester_id = options['current_semester']
        subject_id = options['subject']
        school_id = options.get('school')
        config_id = options.get('config')
        save_results = not options.get('no_save', False)
        base_exam_id = options.get('base_exam')
        current_exam_id = options.get('current_exam') 
        exam_type = options.get('exam_type')
        
        self.stdout.write(f"开始执行TES增值评价...")
        self.stdout.write(f"基线学期: {base_semester_id}")
        self.stdout.write(f"当前学期: {current_semester_id}")
        self.stdout.write(f"学科: {subject_id}")
        
        # 如果提供了考试类型但没有指定具体考试ID，则查找相应类型的考试
        if exam_type and (not base_exam_id or not current_exam_id):
            self.stdout.write(f"正在查找考试类型: {exam_type}")
            
            # 查找基线学期的考试
            if not base_exam_id:
                base_exams = Exam.objects.filter(
                    semester_id=base_semester_id, 
                    exam_type=exam_type
                ).order_by('-exam_date')
                
                if base_exams.exists():
                    base_exam_id = base_exams.first().exam_id
                    self.stdout.write(f"自动选择基线考试: {base_exam_id}")
                else:
                    self.stdout.write(self.style.WARNING(f"未找到基线学期的{exam_type}类型考试"))
            
            # 查找当前学期的考试
            if not current_exam_id:
                current_exams = Exam.objects.filter(
                    semester_id=current_semester_id, 
                    exam_type=exam_type
                ).order_by('-exam_date')
                
                if current_exams.exists():
                    current_exam_id = current_exams.first().exam_id
                    self.stdout.write(f"自动选择当前考试: {current_exam_id}")
                else:
                    self.stdout.write(self.style.WARNING(f"未找到当前学期的{exam_type}类型考试"))
        
        if base_exam_id:
            self.stdout.write(f"基线考试ID: {base_exam_id}")
        
        if current_exam_id:
            self.stdout.write(f"当前考试ID: {current_exam_id}")
        
        # 获取模型参数
        if config_id:
            try:
                config = ValueAddedConfig.objects.get(config_id=config_id)
                self.stdout.write(f"使用配置: {config.config_name}")
                tes_params = config.parameters
                tes_params['mode'] = 'tes'  # 确保使用TES模式
            except ValueAddedConfig.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"配置 {config_id} 不存在"))
                return
        else:
            # 使用默认参数
            tes_params = {
                'mode': 'tes',
                'current_weight': 0.4,
                'progress_weight': 0.6,
                'score_fields': ['raw_score', 'standard_score'],
                'raw_score_weight': 0.3,
                'standard_score_weight': 0.7,  # 给标准分更高权重
                'special_schools': []
            }
            
            # 获取学科字段映射
            subject_name = Subject.objects.get(subject_id=subject_id).subject_name
            if subject_name == '语文':
                tes_params['score_fields'] = ['raw_score', 'standard_score']
            elif subject_name == '数学':
                tes_params['score_fields'] = ['raw_score', 'standard_score']
            else:
                tes_params['score_fields'] = ['raw_score', 'standard_score']
        
        self.stdout.write(f"使用评价字段: {tes_params.get('score_fields', ['raw_score'])}")
        
        # 创建TES评价模型
        model = SimpleDifferenceModel(tes_params)
        
        # 获取基线学期数据
        base_query = Score.objects.filter(
            semester_id=base_semester_id,
            subject_id=subject_id,
            status='COMPLETE'
        )
        
        # 如果指定了基线考试ID，则添加过滤条件
        if base_exam_id:
            base_query = base_query.filter(exam_id=base_exam_id)
        
        # 获取当前学期数据
        current_query = Score.objects.filter(
            semester_id=current_semester_id,
            subject_id=subject_id,
            status='COMPLETE'
        )
        
        # 如果指定了当前考试ID，则添加过滤条件
        if current_exam_id:
            current_query = current_query.filter(exam_id=current_exam_id)
        
        # 根据学校过滤
        if school_id:
            school = School.objects.get(school_id=school_id)
            self.stdout.write(f"学校筛选: {school.school_name}")
            
            # 获取学校的学生ID列表
            school_students = Student.objects.filter(
                current_school_id=school_id
            ).values_list('student_id', flat=True)
            
            base_query = base_query.filter(student_id__in=school_students)
            current_query = current_query.filter(student_id__in=school_students)
        
        # 检查数据量
        base_count = base_query.count()
        current_count = current_query.count()
        
        self.stdout.write(f"基线学期数据量: {base_count}")
        self.stdout.write(f"当前学期数据量: {current_count}")
        
        if base_count == 0 or current_count == 0:
            self.stdout.write(self.style.ERROR("数据量不足，无法进行评价"))
            return
        
        # 转换为DataFrame
        self.stdout.write("加载并转换数据...")
        base_df = pd.DataFrame(list(base_query.values(
            'student_id', 'raw_score', 'standard_score', 'percentile', 'exam_id'
        )))
        
        # 检查并获取学生所属学校
        if 'special_schools' in tes_params and tes_params['special_schools']:
            student_schools = Student.objects.filter(
                student_id__in=base_df['student_id'].tolist()
            ).values('student_id', 'current_school_id')
            
            student_school_map = {s['student_id']: s['current_school_id'] for s in student_schools}
            base_df['school_id'] = base_df['student_id'].map(student_school_map)
        
        current_df = pd.DataFrame(list(current_query.values(
            'student_id', 'raw_score', 'standard_score', 'percentile', 'exam_id'
        )))
        
        # 检查并获取学生所属学校
        if 'special_schools' in tes_params and tes_params['special_schools']:
            if not 'school_id' in base_df.columns:
                student_schools = Student.objects.filter(
                    student_id__in=current_df['student_id'].tolist()
                ).values('student_id', 'current_school_id')
                
                student_school_map = {s['student_id']: s['current_school_id'] for s in student_schools}
                current_df['school_id'] = current_df['student_id'].map(student_school_map)
        
        # 找出基线和当前数据集中都有的学生
        common_students = set(base_df['student_id']).intersection(set(current_df['student_id']))
        self.stdout.write(f"两个数据集共有学生: {len(common_students)}人")
        
        if len(common_students) == 0:
            self.stdout.write(self.style.ERROR("没有共同学生，无法进行配对比较"))
            return
        
        # 过滤只保留共同的学生
        base_df = base_df[base_df['student_id'].isin(common_students)]
        current_df = current_df[current_df['student_id'].isin(common_students)]
        
        # 执行评价
        self.stdout.write("执行TES增值评价...")
        results = model.evaluate({
            'baseline': base_df,
            'current': current_df
        })
        
        # 输出结果摘要
        self.stdout.write(f"评价完成，共 {len(results)} 条结果")
        self.stdout.write("\n评价结果摘要:")
        self.stdout.write(f"平均增值分: {results['value_added'].mean():.2f}")
        self.stdout.write(f"最大增值分: {results['value_added'].max():.2f}")
        self.stdout.write(f"最小增值分: {results['value_added'].min():.2f}")
        
        # 生成批次ID，包含考试ID信息
        batch_id = f"TES_{subject_id}"
        if base_exam_id and current_exam_id:
            batch_id = f"{batch_id}_{base_exam_id}_{current_exam_id}"
        else:
            batch_id = f"{batch_id}_{base_semester_id}_{current_semester_id}"
        
        # 保存结果到数据库
        if save_results:
            self.stdout.write("保存结果到数据库...")
            with transaction.atomic():
                records_saved = 0
                
                for _, row in results.iterrows():
                    student_id = row['student_id']
                    
                    # 按要求生成评价ID: 学期_考试ID_科目
                    exam_id_part = current_exam_id if current_exam_id else "ALL"
                    eval_id = f"{student_id}_{current_semester_id}_{exam_id_part}_{subject_id}"
                    
                    # 确保ID不超过110个字符（考虑到您已将字段长度增加到120）
                    if len(eval_id) > 110:
                        eval_id = eval_id[:110]
                    
                    ValueAddedEvaluation.objects.update_or_create(
                        eval_id=eval_id,
                        defaults={
                            'target_type': 'STUDENT',
                            'target_id': student_id,
                            'subject_id': subject_id,
                            'semester_id': current_semester_id,
                            'base_score': row.get(f'raw_score_base', 0),
                            'current_score': row.get(f'raw_score_current', 0),
                            'added_value': row.get('value_added', 0),
                            'factors': {
                                'current_total_score': float(row.get('current_total_score', 0)),
                                'progress_total_score': float(row.get('progress_total_score', 0)),
                                'current_rank': int(row.get('current_rank', 0)),
                                'progress_rank': int(row.get('progress_rank', 0)),
                                'value_added_rank': int(row.get('value_added_rank', 0)),
                                'method': 'tes',
                                'batch_id': batch_id,
                                'base_exam_id': base_exam_id or '',
                                'current_exam_id': current_exam_id or ''
                            },
                            'status': 'COMPLETE'
                        }
                    )
                    
                    records_saved += 1
                
                self.stdout.write(self.style.SUCCESS(f"已保存 {records_saved} 条评价记录"))
        
        self.stdout.write(self.style.SUCCESS("评价任务完成！")) 