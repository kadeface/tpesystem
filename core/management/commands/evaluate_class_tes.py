"""
计算班级科目TES增值评价的管理命令 - 优化版

python manage.py evaluate_class_tes --base-exam 2025-DIST-M-202301 --current-exam 2025-DIST-M-202307 --subject CHN --export
"""
import pandas as pd 
from django.core.management.base import BaseCommand
from django.db import transaction, models
from core.models import Score, Class, Student, Semester, Subject, ValueAddedEvaluation, School, Grade, Teacher, TeacherHistory, Exam
from core.algorithms.value_added import aggregate_student_to_class_t_score, calculate_class_value_added
from django.db.models import F
import os
from datetime import datetime

class Command(BaseCommand):
    help = '计算班级科目的增值评价 (基于考试ID)'

    def add_arguments(self, parser):
        parser.add_argument('--base-exam', type=str, required=True, help='基线考试ID，例如：202310-FINAL')
        parser.add_argument('--current-exam', type=str, required=True, help='当前考试ID，例如：202320-FINAL')
        parser.add_argument('--subject', type=str, required=True, help='学科ID，例如：CHN')
        parser.add_argument('--no-save', action='store_true', help='不保存结果到数据库')
        parser.add_argument('--export', action='store_true', help='导出结果到Excel文件')
        parser.add_argument('--export-path', type=str, help='导出Excel的路径，不指定则使用当前目录')

    def handle(self, *args, **options):
        base_exam_id = options['base_exam']
        current_exam_id = options['current_exam']
        subject_id = options['subject']
        save_results = not options.get('no_save', False)
        
        self.stdout.write(f"开始执行班级科目增值评价...")
        self.stdout.write(f"基线考试: {base_exam_id}")
        self.stdout.write(f"当前考试: {current_exam_id}")
        self.stdout.write(f"学科: {subject_id}")
        
        # 1. 从考试ID获取相关信息(学期、年级等)
        try:
            base_exam = Exam.objects.get(exam_id=base_exam_id)
            current_exam = Exam.objects.get(exam_id=current_exam_id)
            
            base_semester_id = base_exam.semester_id
            current_semester_id = current_exam.semester_id
            grade_id = base_exam.grade_id
            
            # 验证考试信息的一致性
            if base_exam.grade_id != current_exam.grade_id:
                self.stdout.write(self.style.WARNING(f"警告：基线考试年级({base_exam.grade_id})与当前考试年级({current_exam.grade_id})不一致"))
            
            self.stdout.write(f"基线学期: {base_semester_id}")
            self.stdout.write(f"当前学期: {current_semester_id}")
            self.stdout.write(f"年级: {grade_id}")
        except Exam.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"考试ID不存在: {e}"))
            return
        
        # 2. 获取考试成绩数据
        base_query = Score.objects.filter(
            exam_id=base_exam_id,
            subject_id=subject_id,
            status='COMPLETE'
        )
        
        current_query = Score.objects.filter(
            exam_id=current_exam_id,
            subject_id=subject_id,
            status='COMPLETE'
        )
        
        # 检查数据量
        base_count = base_query.count()
        current_count = current_query.count()
        
        self.stdout.write(f"基线考试数据量: {base_count}")
        self.stdout.write(f"当前考试数据量: {current_count}")
        
        if base_count == 0 or current_count == 0:
            self.stdout.write(self.style.ERROR("数据量不足，无法进行评价"))
            return
        
        # 3. 获取相关班级列表
        class_list = Class.objects.filter(
            grade_id=grade_id  # 修正为单个grade_id
        ).values_list('class_id', flat=True)
        
        self.stdout.write(f"找到相关班级数量: {len(class_list)}")
        
        # 4. 准备数据处理
        # 获取分数数据
        base_scores = list(base_query.values(
            'student_id', 'raw_score', 'standard_score', 'exam_id'
        ))
        
        current_scores = list(current_query.values(
            'student_id', 'raw_score', 'standard_score', 'exam_id'
        ))
        
        # 获取学生对应的班级信息 - 从Student表
        student_ids = set([s['student_id'] for s in base_scores]) | set([s['student_id'] for s in current_scores])
        students = Student.objects.filter(student_id__in=student_ids).values('student_id', 'current_class_id')
        
        student_class_map = {}
        for student in students:
            student_class_map[student['student_id']] = student['current_class_id']
        
        # 5. 构建DataFrame
        base_df = pd.DataFrame(base_scores)
        base_df['class_id'] = base_df['student_id'].map(student_class_map)
        base_df = base_df.dropna(subset=['class_id'])  # 移除没有班级信息的记录
        
        current_df = pd.DataFrame(current_scores)
        current_df['class_id'] = current_df['student_id'].map(student_class_map)
        current_df = current_df.dropna(subset=['class_id'])  # 移除没有班级信息的记录
        
        # 报告有效数据量
        self.stdout.write(f"基线有效数据量: {len(base_df)}")
        self.stdout.write(f"当前有效数据量: {len(current_df)}")
        
        if len(base_df) == 0 or len(current_df) == 0:
            self.stdout.write(self.style.ERROR("有效数据量不足，无法进行评价"))
            return
        
        # 添加subject_id字段
        base_df['subject_id'] = subject_id
        current_df['subject_id'] = subject_id
        
        # 6. 计算班级T分数和增值
        self.stdout.write("计算班级T分数...")
        base_class_scores = aggregate_student_to_class_t_score(base_df, exam_field='exam_id')
        current_class_scores = aggregate_student_to_class_t_score(current_df, exam_field='exam_id')
        
        self.stdout.write("计算班级增值分数...")
        class_va_results = calculate_class_value_added(base_class_scores, current_class_scores)
        class_va_results = class_va_results.sort_values(by='comprehensive_score', ascending=False)
        
        # 7. 获取科任教师信息 - 从TeacherHistory表
        self.stdout.write("获取班级科任教师信息...")
        class_subject_teachers = {}
        
        # 检查Teacher模型字段
        sample_teacher = Teacher.objects.first()
        teacher_name_field = 'teacher_id'  # 默认使用ID
        if sample_teacher:
            # 尝试发现可能的姓名字段
            for field_name in ['name', 'full_name', 'teacher_name', 'real_name', 'display_name']:
                if hasattr(sample_teacher, field_name):
                    teacher_name_field = field_name
                    self.stdout.write(f"使用'{field_name}'作为教师姓名字段")
                    break

        # 查询教师信息
        for class_id in class_va_results['class_id'].unique():
            # 通过TeacherHistory获取科任教师
            teacher_record = TeacherHistory.objects.filter(
                class_field_id=class_id,
                subject_id=subject_id,
                grade_id=grade_id
            ).order_by('-start_date').first()
            
            if not teacher_record:
                # 放宽条件
                teacher_record = TeacherHistory.objects.filter(
                    class_field_id=class_id, 
                    subject_id=subject_id
                ).order_by('-start_date').first()
            
            if teacher_record:
                try:
                    teacher = Teacher.objects.get(teacher_id=teacher_record.teacher_id)
                    class_subject_teachers[class_id] = getattr(teacher, teacher_name_field, teacher.teacher_id)
                except Teacher.DoesNotExist:
                    class_subject_teachers[class_id] = teacher_record.teacher_id
            else:
                class_subject_teachers[class_id] = "未知"
        
        # 8. 获取学校信息
        class_school_map = {}
        for class_id in class_va_results['class_id'].unique():
            try:
                class_obj = Class.objects.get(class_id=class_id)
                if hasattr(class_obj, 'grade_id') and class_obj.grade_id:
                    grade = Grade.objects.get(grade_id=class_obj.grade_id)
                    if hasattr(grade, 'school_id') and grade.school_id:
                        school = School.objects.get(school_id=grade.school_id)
                        class_school_map[class_id] = school.school_name
            except Exception:
                pass
            
            if class_id not in class_school_map:
                class_school_map[class_id] = "未知学校"
        
        # 9. 输出结果
        self.stdout.write("\n班级增值评价结果 (按综合得分降序排列):")
        self.stdout.write(f"{'排名':<5} {'学校':<15} {'班级':<15} {'科任教师':<10} {'学科':<8} {'基线T分':<10} {'当前T分':<10} {'增值分':<10} {'标准增值':<10} {'综合得分':<10}")
        
        rank = 1
        for _, row in class_va_results.iterrows():
            class_id = row['class_id']
            try:
                class_obj = Class.objects.get(class_id=class_id)
                class_name = class_obj.class_name
            except Class.DoesNotExist:
                class_name = class_id
            
            school_name = class_school_map.get(class_id, "未知学校")
            teacher_name = class_subject_teachers.get(class_id, "未知")
            
            self.stdout.write(
                f"{rank:<5} {school_name:<15} {class_name:<15} {teacher_name:<10} {subject_id:<8} "
                f"{row['t_score_base']:<10.2f} {row['t_score_current']:<10.2f} "
                f"{row['added_value']:<10.2f} {row['added_value_scaled']:<10.2f} {row['comprehensive_score']:<10.2f}"
            )
            rank += 1
        
        # 10. 保存结果到数据库
        if save_results:
            self.stdout.write("保存结果到数据库...")
            batch_id = f"CLASS_TES_{subject_id}_{base_exam_id}_{current_exam_id}"
            
            with transaction.atomic():
                records_saved = 0
                
                for _, row in class_va_results.iterrows():
                    class_id = row['class_id']
                    
                    # 获取学校ID和教师ID用于保存
                    school_id = None
                    teacher_id = None
                    
                    try:
                        class_obj = Class.objects.get(class_id=class_id)
                        if hasattr(class_obj, 'grade_id') and class_obj.grade_id:
                            grade = Grade.objects.get(grade_id=class_obj.grade_id)
                            if hasattr(grade, 'school_id'):
                                school_id = grade.school_id
                        
                        # 获取教师ID
                        teacher_record = TeacherHistory.objects.filter(
                            class_field_id=class_id,
                            subject_id=subject_id,
                            grade_id=grade_id
                        ).order_by('-start_date').first()
                        
                        if teacher_record:
                            teacher_id = teacher_record.teacher_id
                    except:
                        pass
                    
                    # 生成评价ID
                    eval_id = f"CLASS_{class_id}_{current_exam_id}_{subject_id}"
                    
                    # 保存因素
                    factors = {
                        'comprehensive_score': float(row['comprehensive_score']),
                        'method': 't_score_diff',
                        'batch_id': batch_id,
                        'base_exam_id': base_exam_id,
                        'current_exam_id': current_exam_id,
                        'added_value_scaled': float(row['added_value_scaled'])
                    }
                    
                    if school_id:
                        factors['school_id'] = school_id
                        
                    if teacher_id:
                        factors['teacher_id'] = teacher_id
                    
                    ValueAddedEvaluation.objects.update_or_create(
                        eval_id=eval_id,
                        defaults={
                            'target_type': 'CLASS',
                            'target_id': class_id,
                            'subject_id': subject_id,
                            'semester_id': current_semester_id,
                            'base_score': row['t_score_base'],
                            'current_score': row['t_score_current'],
                            'added_value': row['added_value'],
                            'factors': factors,
                            'status': 'COMPLETE'
                        }
                    )
                    
                    records_saved += 1
                
                self.stdout.write(self.style.SUCCESS(f"已保存 {records_saved} 条班级评价记录"))
        
        self.stdout.write(self.style.SUCCESS("班级科目增值评价任务完成！"))

        # 导出结果到Excel
        if options.get('export'):
            self.stdout.write("导出结果到Excel...")
            
            # 准备导出数据
            export_data = []
            for _, row in class_va_results.iterrows():
                class_id = row['class_id']
                
                try:
                    class_obj = Class.objects.get(class_id=class_id)
                    class_name = class_obj.class_name
                except Class.DoesNotExist:
                    class_name = class_id
                
                school_name = class_school_map.get(class_id, "未知学校")
                teacher_name = class_subject_teachers.get(class_id, "未知")
                
                export_data.append({
                    '学校': school_name,
                    '班级': class_name,
                    '科任教师': teacher_name,
                    '学科': subject_id,
                    '基线T分': round(row['t_score_base'], 2),
                    '当前T分': round(row['t_score_current'], 2),
                    '增值分': round(row['added_value'], 2),
                    '标准增值': round(row['added_value_scaled'], 2),
                    '综合得分': round(row['comprehensive_score'], 2)
                })
            
            # 转换为DataFrame
            export_df = pd.DataFrame(export_data)
            
            # 设置导出路径
            export_path = options.get('export_path', '')
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"班级增值评价_{subject_id}_{base_exam_id}到{current_exam_id}_{timestamp}.xlsx"
            export_file = os.path.join(export_path, filename) if export_path else filename
            
            # 导出到Excel
            try:
                export_df.to_excel(export_file, index=False, sheet_name='班级增值评价')
                self.stdout.write(self.style.SUCCESS(f"结果已导出到: {export_file}"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"导出失败: {e}")) 