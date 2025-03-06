"""
导入学生考试成绩数据的管理命令。

此命令从Excel文件中读取学生考试成绩数据，并将其导入系统数据库。
支持同时导入学校、年级、班级、学生和成绩数据，实现一站式数据导入。
"""

import pandas as pd
import numpy as np
from datetime import datetime, date, time, timedelta
import os
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Student, Subject, Exam, Score, School, Grade, Class, Teacher, Semester, TeacherSubject, Region, Family, StudentHistory
import uuid
import hashlib
# 导入所需模块
from core.models import Score, Student, School, StudentHistory, Exam, Subject, Grade, Class, Semester
from datetime import datetime, timedelta
import pandas as pd
from scipy import stats as scipy_stats
from core.utils.progress_tracker import ProgressTracker

class Command(BaseCommand):
    """
    导入学生考试成绩数据的Django管理命令。
    
    从Excel文件导入学生、班级、年级、学校和成绩数据，实现一站式数据导入。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    
    Raises:
        CommandError: 当文件不存在或格式不正确时抛出
    """
    
    help = '从Excel文件导入学生考试成绩数据（包括学校、年级、班级、学生和成绩信息）'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('--file_path', type=str, required=True, help='成绩数据文件路径')
        parser.add_argument('--exam_id', type=str, help='考试ID', required=True)
        parser.add_argument('--exam_name', type=str, help='考试名称', required=True)
        parser.add_argument('--exam_type', type=str, help='考试类型(MIDTERM/FINAL/ENTRANCE)', default='MIDTERM')
        parser.add_argument('--semester', type=str, help='学期ID', required=True)
        parser.add_argument('--teacher_id', type=str, help='默认教师ID', default='T001')
        parser.add_argument('--sheet', type=str, help='Excel工作表名称', default='Sheet1')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        parser.add_argument('--skip_teacher', action='store_true', help='不关联教师（将教师字段设为空）')
        parser.add_argument('--smart_match', action='store_true', help='智能匹配教师（尝试多种匹配方式）')
        parser.add_argument('--region_id', type=str, help='默认区域ID', default='REG001')
        parser.add_argument('--create_students', action='store_true', help='自动创建不存在的学生记录')
        parser.add_argument('--update_students', action='store_true', help='更新已存在的学生信息')
        parser.add_argument('--force', action='store_true', help='强制导入，不进行数据检查')
        parser.add_argument('--task_id', type=str, help='任务ID，用于进度跟踪')

    def _extract_id_info(self, id_number):
        """
        从身份证号提取出生日期和性别信息。
        
        Args:
            id_number: 身份证号码
            
        Returns:
            (birth_date, gender): 出生日期和性别元组
        """
        try:
            # 提取出生日期 (YYYYMMDD格式在第7-14位)
            birth_year = int(id_number[6:10])
            birth_month = int(id_number[10:12])
            birth_day = int(id_number[12:14])
            birth_date = date(birth_year, birth_month, birth_day)
            
            # 提取性别 (第17位，奇数为男，偶数为女)
            gender = 'M' if int(id_number[16:17]) % 2 == 1 else 'F'
            
            return birth_date, gender
        except:
            # 如果解析失败，返回默认值
            return date(2000, 1, 1), 'M'

    def _import_schools(self, df, region_id, debug=False):
        """
        导入学校数据。
        
        Args:
            df: 数据DataFrame
            region_id: 默认区域ID
            debug: 是否启用调试模式
            
        Returns:
            dict: 学校ID到学校对象的映射
        """
        self.stdout.write("步骤1: 导入学校数据...")
        schools = {}
        
        # 获取唯一的学校信息
        unique_schools = df[['学校代码', '学校名称']].drop_duplicates()
        
        # 确保区域存在
        region, _ = Region.objects.get_or_create(
            region_id=region_id,
            defaults={
                'region_name': '默认区域',
                'level': 'CITY',
                'description': '导入数据时自动创建的默认区域'
            }
        )
        
        school_count = 0
        for _, row in unique_schools.iterrows():
            school_id = str(row['学校代码'])
            school_name = row['学校名称']
            
            school, created = School.objects.get_or_create(
                school_id=school_id,
                defaults={
                    'school_name': school_name,
                    'school_type': 'JUNIOR',  # 默认为初中
                    'school_nature': 'PUBLIC',  # 默认为公立
                    'address': '',
                    'phone': '',
                    'email': '',
                    'principal': '',
                    'region': region,
                    'status': 'ACTIVE'
                }
            )
            
            schools[school_id] = school
            if created:
                school_count += 1
                if debug:
                    self.stdout.write(f"  创建学校: {school_name} (ID: {school_id})")
        
        self.stdout.write(self.style.SUCCESS(f"  完成学校导入: 新建 {school_count} 所学校"))
        return schools, school_count

    def _import_grades(self, df, schools, semester, debug=False):
        """
        导入年级数据。
        
        Args:
            df: 数据DataFrame
            schools: 学校字典
            semester: 学期对象
            debug: 是否启用调试模式
            
        Returns:
            dict: (学校ID, 年级) 到年级对象的映射
        """
        self.stdout.write("步骤2: 导入年级数据...")
        grades = {}
        
        # 获取唯一的学校和年级组合
        unique_grades = df[['学校代码', '年级']].drop_duplicates()
        
        grade_count = 0
        for _, row in unique_grades.iterrows():
            school_id = str(row['学校代码'])
            grade_level = str(row['年级'])
            
            school = schools.get(school_id)
            if not school:
                continue
                
            grade_id = f"{school_id}_{grade_level}"
            grade, created = Grade.objects.get_or_create(
                grade_id=grade_id,
                defaults={
                    'grade_name': f'{grade_level}年级',
                    'school': school,
                    'grade_level': grade_level,
                    'semester': semester
                }
            )
            
            grades[(school_id, grade_level)] = grade
            if created:
                grade_count += 1
                if debug:
                    self.stdout.write(f"  创建年级: {school.school_name} - {grade_level}年级")
        
        self.stdout.write(self.style.SUCCESS(f"  完成年级导入: 新建 {grade_count} 个年级"))
        return grades, grade_count

    def _import_classes(self, df, grades, default_teacher_id, debug=False):
        """
        导入班级数据。
        
        Args:
            df: 数据DataFrame
            grades: 年级字典
            default_teacher_id: 默认教师ID
            debug: 是否启用调试模式
            
        Returns:
            dict: (学校ID, 年级, 班级) 到班级对象的映射
        """
        self.stdout.write("步骤3: 导入班级数据...")
        classes = {}
        
        # 获取唯一的学校、年级和班级组合
        unique_classes = df[['学校代码', '年级', '班别']].drop_duplicates()
        
        # 确保默认教师ID有值
        if not default_teacher_id or default_teacher_id == 'None':
            default_teacher_id = 'T001'  # 使用一个安全的默认值
            self.stdout.write(self.style.WARNING(f"  未提供有效的默认教师ID，使用默认值：{default_teacher_id}"))
            
            # 确保该教师ID存在于数据库中
            from core.models import Teacher
            teacher, created = Teacher.objects.get_or_create(
                teacher_id=default_teacher_id,
                defaults={
                    'name': '默认教师',
                    'gender': 'M',
                    'status': 'ACTIVE'
                }
            )
            if created:
                self.stdout.write(self.style.WARNING(f"  自动创建默认教师：{default_teacher_id}"))
        
        class_count = 0
        for _, row in unique_classes.iterrows():
            school_id = str(row['学校代码'])
            grade_level = str(row['年级'])
            class_name = str(row['班别'])
            
            grade = grades.get((school_id, grade_level))
            if not grade:
                continue
                
            class_id = f"{grade.grade_id}_{class_name}"
            class_obj, created = Class.objects.get_or_create(
                class_id=class_id,
                defaults={
                    'class_name': f'{grade_level}年级{class_name}班',
                    'grade': grade,
                    'teacher_id': default_teacher_id,  # 确保使用有效的教师ID
                    'capacity': 50  # 默认容量
                }
            )
            
            classes[(school_id, grade_level, class_name)] = class_obj
            if created:
                class_count += 1
                if debug:
                    self.stdout.write(f"  创建班级: {grade.school.school_name} - {grade_level}年级{class_name}班")
        
        self.stdout.write(self.style.SUCCESS(f"  完成班级导入: 新建 {class_count} 个班级"))
        return classes, class_count

    def _import_students(self, df, schools, grades, classes, create_students=False, update_students=False, region_id='REG001', debug=False):
        """
        导入学生数据。
        
        Args:
            df: 数据DataFrame
            schools: 学校字典
            grades: 年级字典
            classes: 班级字典
            create_students: 是否自动创建不存在的学生
            update_students: 是否更新已存在的学生信息
            region_id: 默认区域ID
            debug: 是否启用调试模式
            
        Returns:
            dict: 学生ID到学生对象的映射
        """
        self.stdout.write("步骤4: 导入学生数据...")
        students = {}
        created_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        # 自动创建默认家庭记录
        default_family, created = Family.objects.get_or_create(
            family_id="F0001",
            defaults={
                'family_name': "默认家庭",
                'address': "",
                'phone': "",
                'email': "",
                'status': "ACTIVE"
            }
        )
        if created and debug:
            self.stdout.write(f"  创建默认家庭记录 (ID: F0001)")
        
        # 确保区域存在
        region, _ = Region.objects.get_or_create(
            region_id=region_id,
            defaults={
                'region_name': '默认区域',
                'level': 'CITY',
                'description': '导入数据时自动创建的默认区域'
            }
        )
        
        for _, row in df.iterrows():
            # 对每个学生使用单独的子事务（savepoint）
            try:
                with transaction.atomic():
                    # 获取基本信息
                    exam_number = str(row['考生号'])  # 考生号
                    name = row['姓名']
                    id_number = str(row['身份证号'])
                    school_student_id = str(row['学籍号'])
                    
                    # 从身份证号提取信息
                    birth_date, gender = self._extract_id_info(id_number)
                    
                    # 获取关联信息
                    school_id = str(row['学校代码'])
                    grade_level = str(row['年级'])
                    class_name = str(row['班别'])
                    
                    school = schools.get(school_id)
                    grade = grades.get((school_id, grade_level))
                    class_obj = classes.get((school_id, grade_level, class_name))
                    
                    if not school or not grade or not class_obj:
                        skipped_count += 1
                        if debug:
                            self.stdout.write(f"  跳过学生: {name} - 缺少学校/年级/班级信息")
                        continue
                    
                    # 在创建历史记录前，优先使用身份证号和学籍号查找学生
                    try:
                        # 首先尝试通过身份证号查找
                        if id_number:
                            student = Student.objects.get(id_number=id_number)
                            if debug:
                                masked_id = id_number[:6] + '*' * (len(id_number) - 10) + id_number[-4:] if len(id_number) >= 10 else id_number
                                self.stdout.write(f"通过身份证号找到学生: {student.name}, 身份证号: {masked_id}")
                        else:
                            # 强制进入except块
                            raise Student.DoesNotExist()
                    except Student.DoesNotExist:
                        try:
                            # 其次尝试通过学籍号查找
                            if school_student_id:
                                student = Student.objects.get(school_student_id=school_student_id)
                                if debug:
                                    self.stdout.write(f"通过学籍号找到学生: {student.name}")
                            else:
                                # 强制进入except块
                                raise Student.DoesNotExist()
                        except Student.DoesNotExist:
                            # 如果都找不到，创建新学生，并从身份证号提取性别
                            gender = 'U'  # 默认未知
                            if id_number:
                                # 从身份证号提取性别 (第17位为奇数是男性，偶数是女性)
                                try:
                                    if len(id_number) == 18:
                                        gender = 'M' if int(id_number[16]) % 2 == 1 else 'F'
                                    elif len(id_number) == 15:  # 兼容15位老身份证
                                        gender = 'M' if int(id_number[14]) % 2 == 1 else 'F'
                                except (ValueError, IndexError):
                                    # 如果身份证号格式不正确，保持默认性别
                                    self.stdout.write(self.style.WARNING(
                                        f"无法从身份证号 '{id_number}' 提取性别信息，使用默认值 'U'"
                                    ))
                            
                            # 在创建学生前增加从身份证号提取出生日期的代码
                            birth_date = None
                            if id_number:
                                # 从身份证号提取出生日期
                                if len(id_number) == 18:  # 18位身份证号
                                    try:
                                        birth_year = int(id_number[6:10])
                                        birth_month = int(id_number[10:12])
                                        birth_day = int(id_number[12:14])
                                        from datetime import date
                                        birth_date = date(birth_year, birth_month, birth_day)
                                    except (ValueError, IndexError):
                                        birth_date = date(2000, 1, 1)  # 默认日期
                                elif len(id_number) == 15:  # 15位身份证号
                                    try:
                                        birth_year = int('19' + id_number[6:8])
                                        birth_month = int(id_number[8:10])
                                        birth_day = int(id_number[10:12])
                                        from datetime import date
                                        birth_date = date(birth_year, birth_month, birth_day)
                                    except (ValueError, IndexError):
                                        birth_date = date(2000, 1, 1)  # 默认日期
                                else:
                                    from datetime import date
                                    birth_date = date(2000, 1, 1)  # 默认日期
                            else:
                                from datetime import date
                                birth_date = date(2000, 1, 1)  # 默认日期
                            
                            student = Student.objects.create(
                                student_id=id_number if id_number else (school_student_id if school_student_id else f"S{uuid.uuid4().hex[:8]}"),
                                name=name,
                                gender=gender,
                                birth_date=birth_date,
                                id_number=id_number,
                                school_student_id=school_student_id,
                                exam_number=exam_number,
                                current_class=class_obj,
                                current_grade=grade,
                                current_school=school,
                                family_id="F0001",
                                region_id=6,
                                phone='',
                                email='',
                                status='ACTIVE'
                            )
                            
                            students[student.student_id] = student
                            created_count += 1
                            if debug and created_count % 100 == 0:
                                self.stdout.write(f"  已创建 {created_count} 名学生...")
                    except Exception as e:
                        error_count += 1
                        if debug:
                            self.stdout.write(self.style.ERROR(f"  处理学生 {row.get('姓名', '未知')} 数据错误: {str(e)}"))
                        skipped_count += 1
                        continue
            except Exception as e:
                error_count += 1
                if debug:
                    self.stdout.write(self.style.ERROR(f"  处理学生 {row.get('姓名', '未知')} 数据错误: {str(e)}"))
                skipped_count += 1
                continue
        
        self.stdout.write(self.style.SUCCESS(
            f"  完成学生导入: 新建 {created_count} 名学生, 更新 {updated_count} 名学生, "
            f"跳过 {skipped_count} 名学生, 错误 {error_count} 条记录"
        ))
        return students

    def _create_exams(self, subject_mapping, exam_id, exam_name, exam_type, grades, semester_id, debug=False):
        """
        创建考试记录。
        
        Args:
            subject_mapping: 学科映射字典
            exam_id: 考试ID
            exam_name: 考试名称
            exam_type: 考试类型
            grades: 年级字典
            semester_id: 学期ID字符串
            debug: 是否启用调试模式
        """
        self.stdout.write("步骤5: 创建考试记录...")
        exams = {}
        
        # 先获取学期对象，以便后续使用
        try:
            semester = Semester.objects.get(semester_id=semester_id)
        except Semester.DoesNotExist:
            self.stdout.write(self.style.WARNING(f"学期ID {semester_id} 不存在，将尝试创建"))
            # 创建默认学期（如有必要）
            semester = Semester.objects.create(
                semester_id=semester_id,
                year=semester_id.split('-')[0],
                term=semester_id.split('-')[1],
                start_date=date(2023, 1, 1),
                end_date=date(2023, 12, 31)
            )
        
        # 获取当前日期时间作为考试时间
        now = datetime.now()
        exam_date = now.date()
        start_time = datetime.combine(exam_date, time(8, 0))
        end_time = datetime.combine(exam_date, time(10, 0))
        
        for subject_key, (subject_id, subject_name) in subject_mapping.items():
            subject = Subject.objects.get(subject_id=subject_id)
            
            for grade_key, grade in grades.items():
                school_id = grade.school.school_id
                grade_level = grade.grade_name.replace('年级', '')
                
                # 修改考试ID的生成方式，使用更短的格式
                short_school_id = school_id[-4:] if len(school_id) > 4 else school_id
                exam_full_id = f"{exam_id}_{subject_id}_{short_school_id}"
                
                try:
                    exam, created = Exam.objects.update_or_create(
                        exam_id=exam_full_id,
                        defaults={
                            'exam_name': f"{exam_name}_{subject_name}_{grade_level}年级",
                            'exam_type': exam_type,
                            'subject': subject,
                            'grade': grade,
                            'semester': semester,  # 使用semester对象而不是semester_id
                            'start_time': start_time,
                            'end_time': end_time,
                            'total_score': 100.0,
                            'status': 'ACTIVE',
                            'grade_id': grade.grade_id,
                            'subject_id': subject_id,
                            'semester_id': semester_id  # 保留这个字段以保持兼容性
                        }
                    )
                    
                    if created and debug:
                        self.stdout.write(f"  创建考试: {exam.exam_name} (ID: {exam.exam_id})")
                    
                    exams[f"{subject_id}_{grade_key}"] = exam
                
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"  创建考试失败: {str(e)}"))
                    self.stdout.write(self.style.ERROR(f"  尝试创建的考试ID: {exam_full_id} (长度: {len(exam_full_id)})"))
                    raise
        
        self.stdout.write(self.style.SUCCESS(f"  完成考试创建: 共 {len(exams)} 个考试记录"))
        return exams

    def _import_scores(self, df, students, exams, subject_mapping, teacher_id, skip_teacher, debug=False):
        """
        导入成绩数据。
        
        Args:
            df: 数据DataFrame
            students: 学生字典
            exams: 考试字典
            subject_mapping: 科目映射
            teacher_id: 教师ID字符串 (不是Teacher对象)
            skip_teacher: 是否跳过教师关联
            debug: 是否启用调试模式
        
        Returns:
            tuple: (created_count, updated_count)
        """
        self.stdout.write("步骤6: 导入成绩数据...")
        created_count = 0
        updated_count = 0
        
        # 获取Teacher对象（如果不跳过教师）
        teacher = None
        if not skip_teacher and teacher_id:
            try:
                teacher = Teacher.objects.get(teacher_id=teacher_id)
            except Teacher.DoesNotExist:
                if debug:
                    self.stdout.write(self.style.WARNING(f"  未找到教师: ID={teacher_id}，成绩将不关联教师"))
        
        # 添加：初始化subject_scores
        subject_scores = {}
        
        # 添加：收集每个科目的所有分数
        for _, row in df.iterrows():
            for subject_key, (subject_id, subject_name) in subject_mapping.items():
                if subject_key in row and pd.notna(row[subject_key]):
                    try:
                        score_value = float(row[subject_key])
                        if subject_id not in subject_scores:
                            subject_scores[subject_id] = []
                        subject_scores[subject_id].append(score_value)
                    except (ValueError, TypeError):
                        continue
        
        # 添加调试信息
        if debug:
            self.stdout.write(f"Excel中的列名: {df.columns.tolist()}")
            self.stdout.write(f"检测到的学科映射: {subject_mapping}")
            self.stdout.write(f"第一行数据示例: {df.iloc[0].to_dict()}")
        
        # 处理每个学生的成绩
        for _, row in df.iterrows():
            # 优先使用身份证号查找学生，其次使用学籍号，最后才考虑考生号
            student = None
            id_number = str(row['身份证号'])
            
            # 先查找身份证号对应的学生
            for s_id, s in students.items():
                if s.id_number == id_number:
                    student = s
                    break
            
            # 如果找不到，尝试用学籍号查找
            if student is None and '学籍号' in row and pd.notna(row['学籍号']):
                registration_no = str(row['学籍号'])
                for s_id, s in students.items():
                    if hasattr(s, 'registration_no') and s.registration_no == registration_no:
                        student = s
                        break
            
            # 最后才考虑考生号
            if student is None:
                exam_number = str(row['考生号'])
                if exam_number in students:
                    student = students[exam_number]
            
            # 如果仍找不到学生，跳过
            if student is None:
                if debug:
                    self.stdout.write(f"无法找到学生: ID号={id_number}, 考生号={row['考生号']}")
                continue
            
            school_id = str(row['学校代码'])
            grade_level = str(row['年级'])
            
            # 处理每个科目的成绩
            for subject_key, (subject_id, subject_name) in subject_mapping.items():
                # 如果列不存在或值为空，跳过
                if subject_key not in row or pd.isna(row[subject_key]):
                    continue
                    
                try:
                    score_value = float(row[subject_key])
                except (ValueError, TypeError):
                    if debug:
                        self.stdout.write(f"  跳过学生 {student.student_id} 的 {subject_key} 成绩 (非数字值: {row[subject_key]})")
                    continue
                    
                # 查找对应的考试记录
                # 使用修改后的exam_key格式匹配_create_exams中的逻辑
                short_school_id = school_id[-4:] if len(school_id) > 4 else school_id
                exam_key = f"{subject_id}_{short_school_id}"
                
                matching_exam = None
                for key, exam in exams.items():
                    if exam.exam_id.endswith(exam_key):
                        matching_exam = exam
                        break
                    
                if not matching_exam:
                    if debug:
                        self.stdout.write(f"  未找到匹配的考试: 学生={student.name}, 学科={subject_name}, 学校={school_id}")
                    continue
                    
                # 处理成绩等级
                score_grade = 'C'  # 默认成绩等级
                if score_value >= 90:
                    score_grade = 'A'
                elif score_value >= 80:
                    score_grade = 'B'
                elif score_value >= 60:
                    score_grade = 'C'
                else:
                    score_grade = 'D'
                    
                # 创建或更新成绩记录
                score_id = hashlib.md5(f"{student.student_id}_{matching_exam.exam_id}_{subject_id}".encode()).hexdigest()[:20]
                
                try:
                    score, score_created = Score.objects.update_or_create(
                        score_id=score_id,
                        defaults={
                            'student': student,
                            'exam': matching_exam,
                            'subject': matching_exam.subject,
                            'teacher': None if skip_teacher else teacher,
                            'raw_score': score_value,
                            'standard_score': score_value,  # 添加标准分，默认与原始分相同
                            'percentile': scipy_stats.percentileofscore(subject_scores[subject_id], score_value) if subject_id in subject_scores else 50,
                            'grade': score_grade,
                            'status': 'ACTIVE'
                        }
                    )
                    
                    if score_created:
                        created_count += 1
                        if debug:
                            self.stdout.write(f"  创建成绩: {student.name} - {subject_name} - {score_value}")
                    else:
                        updated_count += 1
                        if debug:
                            self.stdout.write(f"  更新成绩: {student.name} - {subject_name} - {score_value}")
                        
                except Exception as e:
                    if debug:
                        self.stdout.write(self.style.ERROR(f"  创建成绩记录失败: {str(e)}"))
                    
        self.stdout.write(self.style.SUCCESS(f"  完成成绩导入: 新建 {created_count} 条成绩记录, 更新 {updated_count} 条成绩记录"))
        return created_count, updated_count

    def handle(self, *args, **options):
        """
        命令入口点，处理成绩数据导入。
        
        Args:
            *args: 位置参数
            **options: 关键字参数
            
        Raises:
            CommandError: 当导入过程出错时抛出
        """
        # 获取任务ID
        task_id = options.get('task_id')
        
        # 初始化进度跟踪器（如果提供了任务ID）
        self.tracker = None
        if task_id:
            from core.utils.progress_tracker import ProgressTracker
            self.tracker = ProgressTracker(task_id)
            self.tracker.update(message='开始加载数据文件...')
        
        file_path = options.get('file_path')
        exam_id = options['exam_id']
        exam_name = options['exam_name']
        exam_type = options['exam_type']
        semester_id = options['semester']
        teacher_id = options['teacher_id']
        sheet_name = options['sheet']
        debug = options['debug']
        skip_teacher = options['skip_teacher']
        smart_match = options['smart_match']
        region_id = options['region_id']
        create_students = options['create_students']
        update_students = options['update_students']
        force = options['force']
        
        # 添加文件路径验证
        if not file_path or not os.path.exists(file_path):
            self.stderr.write(self.style.ERROR(f'错误: 文件路径"{file_path}"不存在或无效'))
            return
        
        try:
            # 显示导入开始信息
            self.stdout.write("="*80)
            self.stdout.write(self.style.SUCCESS(f"开始从 {file_path} 导入数据"))
            self.stdout.write(f"考试ID: {exam_id}, 考试名称: {exam_name}, 学期: {semester_id}")
            self.stdout.write("="*80)
            
            # 检查并创建学期（如果不存在）
            try:
                semester_id = self.convert_semester_format(semester_id)
                semester = Semester.objects.get(semester_id=semester_id)
            except Semester.DoesNotExist:
                current_year = int(semester_id.split('-')[0])
                term = semester_id.split('-')[1]
                
                if term == '1':
                    start_date = date(current_year, 9, 1)
                    end_date = date(current_year + 1, 1, 31)
                else:
                    start_date = date(current_year, 2, 1)
                    end_date = date(current_year, 7, 31)
                
                semester = Semester.objects.create(
                    semester_id=semester_id,
                    year=f'{current_year}-{current_year+1}',
                    term=term,
                    start_date=start_date,
                    end_date=end_date
                )
                self.stdout.write(self.style.SUCCESS(f'自动创建学期: {semester_id}'))
            
            # 检查教师是否存在
            teacher = None
            if not skip_teacher and teacher_id:
                try:
                    teacher = Teacher.objects.get(teacher_id=teacher_id)
                    self.stdout.write(f'使用指定教师: {teacher.name} (ID: {teacher_id})')
                except Teacher.DoesNotExist:
                    self.stdout.write(self.style.WARNING(f'未找到指定教师 (ID: {teacher_id})，成绩将不关联教师'))
            
            # 读取Excel文件
            try:
                # 先尝试使用指定的sheet_name
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                self.stdout.write(f'成功读取工作表"{sheet_name}"，共 {len(df)} 条记录')
            except Exception as e:
                if "not found" in str(e):
                    # 如果指定的工作表未找到，尝试读取第一个工作表
                    try:
                        # 读取所有工作表的名称
                        xl = pd.ExcelFile(file_path)
                        available_sheets = xl.sheet_names
                        
                        if len(available_sheets) > 0:
                            first_sheet = available_sheets[0]
                            df = pd.read_excel(file_path, sheet_name=first_sheet)
                            self.stdout.write(self.style.WARNING(
                                f'未找到工作表"{sheet_name}"，已自动使用第一个工作表"{first_sheet}"，共 {len(df)} 条记录'
                            ))
                        else:
                            raise CommandError(f'Excel文件中没有任何工作表')
                    except Exception as inner_e:
                        raise CommandError(f'读取Excel文件失败: {str(inner_e)}')
                else:
                    raise CommandError(f'读取Excel文件失败: {str(e)}')
            
            # 验证数据列
            required_columns = ['考生号', '姓名', '年级', '班别', 
                              '学校代码', '学校名称', '身份证号', '学籍号']
            
            for col in required_columns:
                if col not in df.columns:
                    raise CommandError(f'缺少必要列: {col}')
            
            # 定义全部可能的学科映射
            ALL_SUBJECT_MAPPINGS = {
                # 通用学科（各学段都有）
                '语文': ('CHN', '语文'),
                '数学': ('MATH', '数学'),
                '英语': ('ENG', '英语'),
                
                # 小学学科
                '科学': ('SCI', '科学'),
                '品德': ('MOR_P', '品德与生活'),
                '美术': ('ART_P', '美术'),
                '音乐': ('MUS_P', '音乐'),
                '体育': ('PE_P', '体育'),
                
                # 初中学科
                '物理': ('PHY', '物理'),
                '化学': ('CHEM', '化学'),
                '生物': ('BIO', '生物'),
                '地理': ('GEO', '地理'),
                '历史': ('HIS', '历史'),
                '道法': ('MOR', '道德与法治'),
                '信息技术': ('IT_M', '信息技术'),
                '体育与健康': ('PE_M', '体育与健康'),
                
                # 高中学科
                '数学(文)': ('MATH_L', '数学(文科)'),
                '数学(理)': ('MATH_S', '数学(理科)'),
                '物理(选修)': ('PHY_E', '物理(选修)'),
                '化学(选修)': ('CHEM_E', '化学(选修)'),
                '生物(选修)': ('BIO_E', '生物(选修)'),
                '政治(选修)': ('POL', '政治'),
                '历史(选修)': ('HIS_E', '历史(选修)'),
                '地理(选修)': ('GEO_E', '地理(选修)'),
                '通用技术': ('TECH', '通用技术'),
                
                # 其他可能的学科名称变体
                '思想政治': ('POL', '政治'),
                '思政': ('POL', '政治'),
                '品德与生活': ('MOR_P', '品德与生活'),
                '品德与社会': ('MOR_P', '品德与社会'),
                '道德与法治': ('MOR', '道德与法治'),
                '自然': ('SCI', '科学'),
                
                # 总分和平均分
                '总分': ('TOTAL', '总分'),
                '平均分': ('AVG', '平均分')
            }
            
            # 动态生成当前Excel表使用的学科映射
            subject_mapping = {}
            for column in df.columns:
                subject = self._match_subject(column)
                if subject:
                    subject_mapping[column] = (subject.subject_id, subject.subject_name)
                    if debug:
                        self.stdout.write(f'检测到学科: {column} -> {subject.subject_name}')
            
            # 如果没有检测到任何学科，给出警告
            if not subject_mapping:
                self.stdout.write(self.style.WARNING('未检测到任何匹配的学科列，请检查Excel表格式'))
                return
            else:
                self.stdout.write(f'共检测到 {len(subject_mapping)} 个学科')
            
            # 确保所有学科记录存在
            for subject_key, (subject_id, subject_name) in subject_mapping.items():
                Subject.objects.get_or_create(
                    subject_id=subject_id,
                    defaults={
                        'subject_name': subject_name,
                        'subject_type': 'MAIN',
                        'description': f'{subject_name}学科'
                    }
                )
            
            # 检查学期状态
            try:
                semester = Semester.objects.get(semester_id=semester_id)
                is_active_semester = semester.status == 'ACTIVE'
                
                if not is_active_semester:
                    self.stdout.write(self.style.WARNING(f"警告：学期 {semester_id} 不是活跃状态，将直接导入到历史记录。"))
                    
                with transaction.atomic():
                    # 根据学期状态选择不同的导入逻辑
                    if is_active_semester:
                        # 正常导入到当前数据表
                        self._standard_import(df, exam_id, exam_name, exam_type, semester_id, teacher_id, region_id, 
                                            create_students, update_students, skip_teacher, smart_match, debug)
                    else:
                        # 直接导入到历史记录表
                        self._historical_import(
                            df=df, 
                            semester_id=semester_id, 
                            exam_id=exam_id, 
                            exam_name=exam_name, 
                            exam_type=exam_type, 
                            teacher_id=teacher_id, 
                            skip_teacher=skip_teacher, 
                            region_id=region_id, 
                            create_students=create_students, 
                            update_students=update_students, 
                            force=force, 
                            debug=debug
                        )
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"处理学期数据时出错: {str(e)}"))
                raise e  # 重新抛出异常，让外层处理
            
            # 处理完成后输出优化的统计结果
            #self._print_import_summary(import_stats)
            
            # 在处理过程中更新进度
            # 例如，在处理学校前：
            if self.tracker:
                self.tracker.update(current=1, total=6, message='正在导入学校数据...')
            
            # 在处理年级前：
            if self.tracker:
                self.tracker.update(current=2, total=6, message='正在导入年级数据...')
            
            # 以此类推...
            
            # 完成时：
            if self.tracker:
                self.tracker.complete('导入成功完成！')
            
        except Exception as e:
            raise CommandError(f'导入过程出错: {str(e)}')

    def _standard_import(self, df, exam_id, exam_name, exam_type, semester_id, teacher_id, region_id, 
                        create_students, update_students, skip_teacher, smart_match, debug):
        """标准导入逻辑，用于活跃学期"""
        # 获取学期对象
        try:
            semester = Semester.objects.get(semester_id=semester_id)
        except Semester.DoesNotExist:
            raise CommandError(f"找不到学期: {semester_id}")
        
        # 定义subject_mapping
        subject_mapping = {}
        for column in df.columns:
            subject = self._match_subject(column)
            if subject:
                subject_mapping[column] = (subject.subject_id, subject.subject_name)
        
        if debug:
            self.stdout.write(f"检测到以下学科: {list(subject_mapping.keys())}")
        
        # 导入步骤...
        schools, school_count = self._import_schools(df, region_id, debug)
        
        # 使用semester对象而不是semester_id字符串
        grades, grade_count = self._import_grades(df, schools, semester, debug)
        
        classes, class_count = self._import_classes(df, grades, teacher_id, debug)
        
        students = self._import_students(df, schools, grades, classes, create_students, update_students, region_id, debug)
        
        # 使用semester_id字符串
        exams = self._create_exams(subject_mapping, exam_id, exam_name, exam_type, grades, semester_id, debug)
        
        # 导入成绩
        scores_created, scores_updated = self._import_scores(df, students, exams, subject_mapping, teacher_id, skip_teacher, debug)
        
        return {
            'schools': school_count,
            'grades': grade_count,
            'classes': class_count,
            'students_created': 0,  # 后续需要完善
            'students_updated': 0,  # 后续需要完善
            'scores_created': scores_created,
            'scores_updated': scores_updated
        }

    def _historical_import(self, df, semester_id, exam_id, exam_name, exam_type, teacher_id, skip_teacher, region_id, create_students, update_students, force=False, debug=False):
        """历史数据导入逻辑，用于非活跃学期"""
        self.stdout.write("使用历史记录导入模式...")
        
        # 初始化进度跟踪
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="开始历史数据导入...", current=0, total=6)
        
        # 初始化统计计数器
        stats = {
            'schools_created': 0,
            'grades_created': 0,
            'classes_created': 0,
            'students_created': 0,
            'students_found': 0,
            'scores_created': 0,
            'scores_updated': 0,
            'errors': 0
        }
        
        # 尝试转换学期格式
        #semester_id = self.convert_semester_format(semester_id)
        
        # 获取学期对象
        try:
            semester = Semester.objects.get(semester_id=semester_id)
        except Semester.DoesNotExist:
            # 尝试查找匹配的学期
            semesters = Semester.objects.all()
            # 尝试智能匹配...
            raise CommandError(f"无法找到学期: {semester_id}")
        
        # 添加此代码 - 在方法内部定义subject_mapping
        subject_mapping = {}
        for column in df.columns:
            subject = self._match_subject(column)
            if subject:
                subject_mapping[column] = (subject.subject_id, subject.subject_name)
        
        # 第1步：从Excel收集所有学校信息并创建
        self.stdout.write("步骤1: 导入学校数据...")
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="步骤1: 导入学校数据...", current=1, total=6)
        
        school_map = {}  # 存储学校ID到School对象的映射
        if '学校代码' in df.columns and '学校名称' in df.columns:
            school_groups = df.groupby(['学校代码', '学校名称'])
            
            for (school_id, school_name), _ in school_groups:
                school_id = str(school_id).strip()
                school_name = str(school_name).strip()
                
                # 获取或创建学校
                school, created = School.objects.get_or_create(
                    school_id=school_id,
                    defaults={
                        'school_name': school_name, 
                        'status': 'ACTIVE',
                        'region_id': region_id
                    }
                )
                school_map[school_id] = school
                
                if created:
                    stats['schools_created'] += 1
                    if debug and stats['schools_created'] <= 3:  # 只显示前3个创建的学校
                        self.stdout.write(f"  创建学校: {school_name} (ID: {school_id})")
        
        self.stdout.write(self.style.SUCCESS(f"  完成学校导入: 新建 {stats['schools_created']} 所学校"))
        
        # 第2步：创建年级记录
        self.stdout.write("步骤2: 导入年级数据...")
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="步骤2: 导入年级数据...", current=2, total=6)
        
        grade_map = {}  # 存储(学校ID, 年级级别) -> Grade对象的映射
        if '年级' in df.columns and '学校代码' in df.columns:
            # 按学校和年级分组
            grade_groups = df.groupby(['学校代码', '年级'])
            
            for (school_id, grade_level), _ in grade_groups:
                school_id = str(school_id).strip()
                grade_level = str(grade_level).strip()
                
                school = school_map.get(school_id)
                if not school:
                    if debug:
                        self.stdout.write(self.style.WARNING(f"  跳过年级创建: 找不到学校 {school_id}"))
                    continue
                
                # 创建一个简短但唯一的grade_id
                semester_short = semester_id.replace("-", "")[-3:]  # 例如 "2022-2023-1" 变为 "231"
                grade_id = f"G{school_id[:3]}_{grade_level}_{semester_short}"
                if len(grade_id) > 10:
                    grade_id = grade_id[:10]  # 截断以符合长度限制
                
                # 获取或创建年级
                grade, created = Grade.objects.get_or_create(
                    grade_id=grade_id,
                    defaults={
                        'grade_name': f"{grade_level}年级",
                        'school': school,
                        'grade_level': grade_level,
                        'semester_id': semester_id
                    }
                )
                
                # 存储映射关系
                grade_map[(school_id, grade_level)] = grade
                
                if created:
                    stats['grades_created'] += 1
                    if debug and stats['grades_created'] <= 3:  # 只显示前3个创建的年级
                        self.stdout.write(f"  创建年级: {grade.grade_name} (ID: {grade_id})")
        
        self.stdout.write(self.style.SUCCESS(f"  完成年级导入: 新建 {stats['grades_created']} 个年级"))
        
        # 第3步：创建班级记录
        self.stdout.write("步骤3: 导入班级数据...")
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="步骤3: 导入班级数据...", current=3, total=6)
        
        class_map = {}  # 存储(学校ID, 年级级别, 班别) -> Class对象的映射
        if '班别' in df.columns and '年级' in df.columns and '学校代码' in df.columns:
            # 按学校、年级和班级分组
            class_groups = df.groupby(['学校代码', '年级', '班别'])
            
            for (school_id, grade_level, class_name), _ in class_groups:
                school_id = str(school_id).strip()
                grade_level = str(grade_level).strip()
                class_name = str(class_name).strip()
                
                # 获取年级对象
                grade = grade_map.get((school_id, grade_level))
                if not grade:
                    continue
                
                # 创建一个简短但唯一的class_id
                semester_short = semester_id.replace("-", "")[-3:]
                class_id = f"C{school_id[:2]}_{grade_level}{class_name}_{semester_short}"
                if len(class_id) > 10:
                    class_id = class_id[:10]  # 截断以符合长度限制
                
                # 获取或创建班级
                class_obj, created = Class.objects.get_or_create(
                    class_id=class_id,
                    defaults={
                        'class_name': f"{grade_level}年级{class_name}班",
                        'grade': grade,
                        'semester': semester,  # 关联学期
                        'capacity': 60,  # 默认容量
                        'status': 'COMPLETE'
                    }
                )
                
                # 存储映射关系
                class_map[(school_id, grade_level, class_name)] = class_obj
                
                if created:
                    stats['classes_created'] += 1
                    if debug and stats['classes_created'] <= 3:  # 只显示前3个创建的班级
                        self.stdout.write(f"  创建班级: {class_obj.class_name} (ID: {class_id})")
        
        self.stdout.write(self.style.SUCCESS(f"  完成班级导入: 新建 {stats['classes_created']} 个班级"))
        
        # 第4步：创建考试记录（现在已确保年级存在）
        self.stdout.write("步骤4: 创建考试记录...")
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="步骤4: 创建考试记录...", current=4, total=6)

        # 如果有年级记录，使用第一个年级作为默认关联
        default_grade_id = 'G0001'  # 默认值
        if grade_map:
            # 从已创建的年级中选择第一个作为默认关联
            first_grade = list(grade_map.values())[0]
            default_grade_id = first_grade.grade_id       
        
        exam, created = Exam.objects.get_or_create(
            exam_id=exam_id,
            defaults={
                'exam_name': exam_name,
                'exam_type': exam_type,
                'semester_id': semester_id,
                'start_time': semester.start_date,
                'end_time': semester.end_date + timedelta(days=1),
                'total_score': 750.0,
                'status': 'COMPLETE',
                'grade_id': default_grade_id,  # 使用固定的默认年级ID
                'subject_id': 'TOTAL'
            }
        )
        if created:
            self.stdout.write(f"  创建考试: {exam_name} (ID: {exam_id})")
        
        # 第5步之前，先收集所有科目的分数用于计算Z分
        self.stdout.write("步骤4.5: 计算各科目Z分...")
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="步骤4.5: 计算各科目Z分...", current=4.5, total=6)
        
        subject_scores = {}
        
        # 首先收集每个科目的所有原始分数
        for idx, row in df.iterrows():
            for subject_col, subject_info in subject_mapping.items():
                if subject_col in row and pd.notna(row[subject_col]):
                    subject_id, _ = subject_info
                    score_value = float(row[subject_col])
                    
                    if subject_id not in subject_scores:
                        subject_scores[subject_id] = []
                    
                    subject_scores[subject_id].append(score_value)
        
        # 计算每个科目的均值和标准差
        subject_stats = {}
        for subject_id, scores in subject_scores.items():
            if len(scores) > 1:  # 确保有足够的数据计算标准差
                mean = np.mean(scores)
                std = np.std(scores, ddof=1)  # 使用样本标准差
                subject_stats[subject_id] = (mean, std)
                if debug:
                    self.stdout.write(f"  科目 {subject_id}: 均值={mean:.2f}, 标准差={std:.2f}, 样本数={len(scores)}")
        
        # 第5步：导入学生记录和成绩
        self.stdout.write("步骤5: 导入学生和成绩数据...")
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message="步骤5: 导入学生和成绩数据...", current=5, total=6)
        
        historical_count = 0
        
        # 进度显示变量
        total_records = len(df)
        progress_step = max(1, total_records // 10)  # 每10%显示一次进度
        
        for idx, row in df.iterrows():
            # 显示进度
            if idx % progress_step == 0 and idx > 0:
                progress_percent = (idx / total_records) * 100
                self.stdout.write(f"  处理进度: {progress_percent:.1f}% ({idx}/{total_records})")
                
                # 更新进度跟踪器
                if hasattr(self, 'tracker') and self.tracker:
                    sub_progress = 5 + (idx / total_records)  # 5到6之间的值
                    self.tracker.update(
                        message=f"正在处理学生和成绩数据... {progress_percent:.1f}% ({idx}/{total_records})",
                        current=sub_progress,
                        total=6
                    )
            
            # 获取学生基本信息
            student_id = str(row.get('考生号', '')).strip()
            name = str(row.get('姓名', '')).strip()
            id_number = str(row.get('身份证号', '')).strip()
            student_number = str(row.get('学籍号', '')).strip()
            
            # 获取学校、年级、班级信息
            school_id = str(row.get('学校代码', '')).strip()
            grade_level = str(row.get('年级', '')).strip()
            class_name = str(row.get('班别', '')).strip()
            
            # 获取相关对象
            school = school_map.get(school_id)
            grade = grade_map.get((school_id, grade_level))
            class_obj = class_map.get((school_id, grade_level, class_name))
            
            # 在创建历史记录前，优先使用身份证号和学籍号查找学生
            try:
                # 首先尝试通过身份证号查找
                if id_number:
                    student = Student.objects.get(id_number=id_number)
                    stats['students_found'] += 1
                else:
                    # 强制进入except块
                    raise Student.DoesNotExist()
            except Student.DoesNotExist:
                try:
                    # 其次尝试通过学籍号查找
                    if student_number:
                        student = Student.objects.get(school_student_id=student_number)
                        stats['students_found'] += 1
                    else:
                        # 强制进入except块
                        raise Student.DoesNotExist()
                except Student.DoesNotExist:
                    # 如果都找不到，创建新学生，并从身份证号提取性别
                    gender = 'U'  # 默认未知
                    if id_number:
                        # 从身份证号提取性别 (第17位为奇数是男性，偶数是女性)
                        try:
                            if len(id_number) == 18:
                                gender = 'M' if int(id_number[16]) % 2 == 1 else 'F'
                            elif len(id_number) == 15:  # 兼容15位老身份证
                                gender = 'M' if int(id_number[14]) % 2 == 1 else 'F'
                        except (ValueError, IndexError):
                            pass
                    
                    # 在创建学生前增加从身份证号提取出生日期的代码
                    birth_date = None
                    if id_number:
                        # 从身份证号提取出生日期
                        if len(id_number) == 18:  # 18位身份证号
                            try:
                                birth_year = int(id_number[6:10])
                                birth_month = int(id_number[10:12])
                                birth_day = int(id_number[12:14])
                                from datetime import date
                                birth_date = date(birth_year, birth_month, birth_day)
                            except (ValueError, IndexError):
                                birth_date = date(2000, 1, 1)  # 默认日期
                        elif len(id_number) == 15:  # 15位身份证号
                            try:
                                birth_year = int('19' + id_number[6:8])
                                birth_month = int(id_number[8:10])
                                birth_day = int(id_number[10:12])
                                from datetime import date
                                birth_date = date(birth_year, birth_month, birth_day)
                            except (ValueError, IndexError):
                                birth_date = date(2000, 1, 1)  # 默认日期
                        else:
                            from datetime import date
                            birth_date = date(2000, 1, 1)  # 默认日期
                    else:
                        from datetime import date
                        birth_date = date(2000, 1, 1)  # 默认日期
                    
                    student = Student.objects.create(
                        student_id=id_number if id_number else (student_number if student_number else f"S{uuid.uuid4().hex[:8]}"),
                        name=name,
                        gender=gender,
                        birth_date=birth_date,
                        id_number=id_number,
                        school_student_id=student_number,
                        exam_number=student_id,
                        current_class=class_obj,
                        current_grade=grade,
                        current_school=school,
                        family_id="F0001",
                        region_id=6,
                        phone='',
                        email='',
                        status='ACTIVE'
                    )
                    stats['students_created'] += 1
            
            # 现在可以安全地创建学生历史记录了
            try:
                history, history_created = StudentHistory.objects.update_or_create(
                    student=student,
                    semester=semester,
                    defaults={
                        'grade': grade,
                        'class_field': class_obj,
                        'school': school,
                        'start_date': semester.start_date,
                        'status': 'ACTIVE'
                    }
                )
            except Exception as e:
                stats['errors'] += 1
                if debug and stats['errors'] <= 5:  # 只显示前5个错误
                    self.stdout.write(self.style.ERROR(f"  创建学生历史记录失败: {str(e)}"))
                continue
            
            # 处理学生成绩
            # 从Excel中提取成绩数据并存储
            for subject_col, subject_info in subject_mapping.items():
                if subject_col in row and pd.notna(row[subject_col]):
                    try:
                        subject_id, subject_name = subject_info
                        score_value = float(row[subject_col])
                        
                        # 计算Z分（标准分）
                        z_score = score_value  # 默认值与原始分相同
                        
                        if subject_id in subject_stats:
                            mean, std = subject_stats[subject_id]
                            if std > 0:  # 避免除以零
                                # 计算Z分: (原始分 - 均值) / 标准差
                                z_score = (score_value - mean) / std
                                # 转换为更易读的分数，例如转换到均值70，标准差10的分布
                                standard_score = 70 + (z_score * 10)
                                # 限制分数范围，避免极端值
                                standard_score = max(0, min(100, standard_score))
                            else:
                                standard_score = score_value  # 如果标准差为0，使用原始分
                        else:
                            standard_score = score_value  # 如果没有统计信息，使用原始分
                        
                        # 生成唯一的成绩ID (使用哈希值)
                        score_id = hashlib.md5(f"{student.student_id}_{exam.exam_id}_{subject_id}".encode()).hexdigest()[:20]
                        
                        # 创建成绩记录
                        score, score_created = Score.objects.update_or_create(
                            score_id=score_id,
                            defaults={
                                'student': student,
                                'exam': exam,
                                'subject_id': subject_id,
                                'raw_score': score_value,
                                'standard_score': standard_score,  # 使用计算的标准分
                                'percentile': scipy_stats.percentileofscore(subject_scores[subject_id], score_value) if subject_id in subject_scores else 50,
                                'status': 'COMPLETE',
                                'semester_id': semester_id
                            }
                        )
                        
                        if score_created:
                            stats['scores_created'] += 1
                        else:
                            stats['scores_updated'] += 1
                    except Exception as e:
                        stats['errors'] += 1
                        if debug and stats['errors'] <= 5:  # 只显示前5个错误
                            self.stdout.write(self.style.ERROR(f"  创建成绩记录失败: {str(e)}"))
            
            historical_count += 1
            if historical_count % 1000 == 0 and debug:
                self.stdout.write(f"  已处理 {historical_count} 条记录...")

        # 输出统计结果
        self.stdout.write("\n" + "="*30 + " 历史导入结果统计 " + "="*30)
        self.stdout.write(f"学校数量: {stats['schools_created']} 所")
        self.stdout.write(f"年级数量: {stats['grades_created']} 个")
        self.stdout.write(f"班级数量: {stats['classes_created']} 个")
        self.stdout.write(f"学生记录: 新建 {stats['students_created']} 名, 找到 {stats['students_found']} 名")
        self.stdout.write(f"成绩记录: 新建 {stats['scores_created']} 条, 更新 {stats['scores_updated']} 条")
        if stats['errors'] > 0:
            self.stdout.write(self.style.ERROR(f"错误数量: {stats['errors']} 条"))
        else:
            self.stdout.write(f"错误数量: 0 条")
        self.stdout.write("="*80)
        
        self.stdout.write(self.style.SUCCESS(f"历史导入完成，共处理 {historical_count} 条记录"))
        
        # 完成导入，更新进度跟踪器
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(
                message=f"导入完成！共处理 {historical_count} 条记录，创建 {stats['scores_created']} 条成绩",
                current=6,
                total=6
            )
        
        return stats

    def _match_subject(self, column_name):
        """
        将Excel列名映射到系统中的学科对象。
        
        Args:
            column_name: Excel中的列名
            
        Returns:
            Subject对象或None（如果没有匹配）
        """
        # 定义全部可能的学科映射
        ALL_SUBJECT_MAPPINGS = {
            # 通用学科（各学段都有）
            '语文': ('CHN', '语文'),
            '数学': ('MATH', '数学'),
            '英语': ('ENG', '英语'),
            
            # 小学学科
            '科学': ('SCI', '科学'),
            '品德': ('MOR_P', '品德与生活'),
            '美术': ('ART_P', '美术'),
            '音乐': ('MUS_P', '音乐'),
            '体育': ('PE_P', '体育'),
            
            # 初中学科
            '物理': ('PHY', '物理'),
            '化学': ('CHEM', '化学'),
            '生物': ('BIO', '生物'),
            '地理': ('GEO', '地理'),
            '历史': ('HIS', '历史'),
            '道法': ('MOR', '道德与法治'),
            '信息技术': ('IT_M', '信息技术'),
            '体育与健康': ('PE_M', '体育与健康'),
            
            # 高中学科
            '数学(文)': ('MATH_L', '数学(文科)'),
            '数学(理)': ('MATH_S', '数学(理科)'),
            '物理(选修)': ('PHY_E', '物理(选修)'),
            '化学(选修)': ('CHEM_E', '化学(选修)'),
            '生物(选修)': ('BIO_E', '生物(选修)'),
            '政治(选修)': ('POL', '政治'),
            '历史(选修)': ('HIS_E', '历史(选修)'),
            '地理(选修)': ('GEO_E', '地理(选修)'),
            '通用技术': ('TECH', '通用技术'),
            
            # 其他可能的学科名称变体
            '思想政治': ('POL', '政治'),
            '思政': ('POL', '政治'),
            '品德与生活': ('MOR_P', '品德与生活'),
            '品德与社会': ('MOR_P', '品德与社会'),
            '道德与法治': ('MOR', '道德与法治'),
            '自然': ('SCI', '科学'),
            
            # 总分和平均分
            '总分': ('TOTAL', '总分'),
            '平均分': ('AVG', '平均分')
        }
        
        # 检查列名是否在映射中
        if column_name in ALL_SUBJECT_MAPPINGS:
            subject_id, subject_name = ALL_SUBJECT_MAPPINGS[column_name]
            
            # 获取或创建学科
            from core.models import Subject
            subject, created = Subject.objects.get_or_create(
                subject_id=subject_id,
                defaults={
                    'subject_name': subject_name,
                    'subject_type': 'MAIN',
                    'description': f'{subject_name}学科'
                }
            )
            return subject
        
        return None

    def _validate_import_data(self, df, debug=False):
        """
        验证导入数据的格式正确性。
        
        Args:
            df: 导入的DataFrame
            debug: 是否启用调试模式
            
        Returns:
            tuple: (是否有效, 错误信息列表)
        """
        errors = []
        warnings = []
        
        # 检查必填列是否存在
        required_columns = ['姓名', '身份证号', '学籍号', '班别', '年级', '学校代码']
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            errors.append(f"缺少必要列: {', '.join(missing_columns)}")
        
        # 验证身份证号格式
        if '身份证号' in df.columns:
            # 检查是否有超长的身份证号
            for idx, id_num in enumerate(df['身份证号']):
                if not pd.isna(id_num):
                    id_num = str(id_num).strip()
                    
                    # 大陆身份证号验证(18位)
                    if len(id_num) > 18 and id_num[0].isdigit():
                        student_name = df.iloc[idx]['姓名'] if '姓名' in df.columns else f"第{idx+1}行"
                        errors.append(f"学生 {student_name} 的身份证号 '{id_num[:6]}...' 长度错误: {len(id_num)}位，应为18位")
                    
                    # 港澳台证件号格式验证
                    if id_num.startswith(('H', 'M', 'T')) and len(id_num) > 25:
                        student_name = df.iloc[idx]['姓名'] if '姓名' in df.columns else f"第{idx+1}行"
                        errors.append(f"学生 {student_name} 的港澳台证件号 '{id_num[:6]}...' 超过最大允许长度25位")
        
        # 验证学籍号格式
        if '学籍号' in df.columns:
            for idx, student_num in enumerate(df['学籍号']):
                if not pd.isna(student_num):
                    student_num = str(student_num).strip()
                    if len(student_num) > 19:
                        student_name = df.iloc[idx]['姓名'] if '姓名' in df.columns else f"第{idx+1}行"
                        errors.append(f"学生 {student_name} 的学籍号 '{student_num[:6]}...' 长度错误: {len(student_num)}位，应为19位")
        
        # 检查姓名是否为空
        if '姓名' in df.columns:
            empty_names = df[df['姓名'].isna() | (df['姓名'] == '')].index.tolist()
            if empty_names:
                errors.append(f"第 {', '.join(str(i+1) for i in empty_names)} 行的姓名为空")
        
        valid = len(errors) == 0
        
        # 输出验证结果
        if debug:
            if valid:
                self.stdout.write(self.style.SUCCESS("数据验证通过!"))
            else:
                self.stdout.write(self.style.ERROR("数据验证失败:"))
                for err in errors:
                    self.stdout.write(self.style.ERROR(f" - {err}"))
            if warnings:
                self.stdout.write(self.style.WARNING("警告:"))
                for warn in warnings:
                    self.stdout.write(self.style.WARNING(f" - {warn}"))
        
        return valid, errors, warnings

    def convert_semester_format(self, display_format):
        """将显示格式转换为数据库格式"""
        if "学年第" in display_format and "学期" in display_format:
            # 例如："2022-2023学年第2学期" -> "2022-2023-2"
            year_part = display_format.split("学年第")[0]  # "2022-2023"
            term_part = display_format.split("学年第")[1].replace("学期", "")  # "2"
            return f"{year_part}-{term_part}"
        return display_format  # 如果不匹配预期格式，返回原始值 

    def _print_import_summary(self, stats):
        """
        打印导入统计摘要。
        
        Args:
            stats: 包含各种统计数据的字典
        """
        self.stdout.write("\n" + "="*30 + " 导入结果统计 " + "="*30)
        self.stdout.write(f"学校数量: {stats.get('schools', 0)} 所")
        self.stdout.write(f"年级数量: {stats.get('grades', 0)} 个")
        self.stdout.write(f"班级数量: {stats.get('classes', 0)} 个")
        self.stdout.write(f"学生记录: 新建 {stats.get('students_created', 0)} 名, 更新 {stats.get('students_updated', 0)} 名")
        self.stdout.write(f"成绩记录: 新建 {stats.get('scores_created', 0)} 条, 更新 {stats.get('scores_updated', 0)} 条")
        if stats.get('errors', 0) > 0:
            self.stdout.write(self.style.ERROR(f"错误数量: {stats.get('errors', 0)} 条"))
        else:
            self.stdout.write(f"错误数量: 0 条")
        self.stdout.write("="*80)     # 重写输出方法，将输出同时发送到控制台和进度跟踪器
    def stdout_write(self, message, style=None):
        if style:
            styled_message = getattr(self.style, style)(message)
            self.stdout.write(styled_message)
        else:
            self.stdout.write(message)
        
        # 如果有进度跟踪器，也更新进度消息
        if hasattr(self, 'tracker') and self.tracker:
            self.tracker.update(message=message) 

