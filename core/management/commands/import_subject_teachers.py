"""
导入学科任课教师数据的管理命令。

此命令从Excel科任表中读取班级学科教师关联数据，并将其导入系统数据库。
支持横向表格格式，其中每行代表一个班级，各列为不同学科的任课教师。
"""

import pandas as pd
from datetime import datetime, date
import os
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Teacher, Subject, Class, School, TeacherSubject

class Command(BaseCommand):
    """
    导入学科任课教师数据的Django管理命令。
    
    从科任表导入教师-学科-班级关联数据，建立必要的关联关系。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    
    Raises:
        CommandError: 当文件不存在或格式不正确时抛出
    """
    
    help = '从Excel科任表导入学科任课教师数据'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('file_path', type=str, help='科任表Excel文件路径')
        parser.add_argument('--sheet', type=str, help='Excel工作表名称', default='Sheet1')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        parser.add_argument('--update', action='store_true', help='更新现有记录')
        parser.add_argument('--create-teachers', action='store_true', help='自动创建不存在的教师')
        parser.add_argument('--semester', type=str, help='学期ID（用于记录开始和结束日期）', default='')
    
    def _get_subject_mapping(self):
        """
        获取Excel列名到学科ID的映射。
        
        Returns:
            dict: 列名到(学科ID,学科名称)的映射
        """
        # 定义科目列名到学科ID的映射
        return {
            '语文科任': ('CHN', '语文'),
            '数学科任': ('MATH', '数学'),
            '英语科任': ('ENG', '英语'),
            '物理科任': ('PHY', '物理'),
            '化学科任': ('CHEM', '化学'),
            '生物科任': ('BIO', '生物'),
            '政治科任': ('POL', '政治'),
            '历史科任': ('HIS', '历史'),
            '地理科任': ('GEO', '地理'),
            '音乐科任': ('MUS', '音乐'),
            '美术科任': ('ART', '美术'),
            '体育科任': ('PE', '体育'),
            '信息科任': ('IT', '信息技术'),
            # 添加其他可能的学科映射
        }
    
    def _ensure_teacher_exists(self, teacher_name, school, debug=False):
        """
        确保教师记录存在，如果不存在则创建。
        
        Args:
            teacher_name: 教师姓名
            school: 学校对象
            debug: 是否启用调试模式
            
        Returns:
            Teacher: 教师对象
        """
        # 尝试查找该学校中的该教师
        matching_teachers = Teacher.objects.filter(name=teacher_name, current_school=school)
        
        if matching_teachers.exists():
            return matching_teachers.first()
        
        # 如果找不到教师，创建一个新教师
        # 生成一个唯一的教师ID：T + 学校ID后4位 + 随机3位数
        import random
        teacher_id = f"T{school.school_id[-4:]}_{random.randint(100, 999)}"
        
        # 检查ID是否已存在，如果存在则重新生成
        while Teacher.objects.filter(teacher_id=teacher_id).exists():
            teacher_id = f"T{school.school_id[-4:]}_{random.randint(100, 999)}"
        
        teacher = Teacher.objects.create(
            teacher_id=teacher_id,
            name=teacher_name,
            gender='M',  # 默认值，后续可更新
            birth_date=date(1980, 1, 1),  # 默认值，后续可更新
            phone='',
            email='',
            current_school=school,
            qualification='MIDDLE',  # 默认中级
            status='ACTIVE'
        )
        
        if debug:
            self.stdout.write(f"自动创建教师: {teacher_name} (ID: {teacher_id})")
        
        return teacher
    
    def _extract_teacher_id(self, teacher_name, teacher_dict, school, create_teachers, debug):
        """
        从教师姓名提取或查找教师ID。
        
        Args:
            teacher_name: 教师姓名
            teacher_dict: 已查找到的教师字典缓存
            school: 学校对象
            create_teachers: 是否创建不存在的教师
            debug: 是否启用调试模式
            
        Returns:
            Teacher: 教师对象或None
        """
        if not teacher_name or pd.isna(teacher_name):
            return None
        
        # 检查缓存中是否已有此教师
        if teacher_name in teacher_dict:
            return teacher_dict[teacher_name]
        
        # 尝试通过教师姓名查找教师
        teacher = None
        try:
            # 先在当前学校查找
            teacher = Teacher.objects.get(name=teacher_name, current_school=school)
        except Teacher.DoesNotExist:
            try:
                # 如果在当前学校找不到，尝试在全局查找
                teacher = Teacher.objects.get(name=teacher_name)
            except Teacher.DoesNotExist:
                # 如果允许创建教师，则创建一个新教师
                if create_teachers:
                    teacher = self._ensure_teacher_exists(teacher_name, school, debug)
                else:
                    if debug:
                        self.stdout.write(self.style.WARNING(f"教师不存在: {teacher_name}"))
                    return None
            except Teacher.MultipleObjectsReturned:
                # 如果存在多个同名教师，选择第一个
                teacher = Teacher.objects.filter(name=teacher_name).first()
                if debug:
                    self.stdout.write(self.style.WARNING(f"存在多个教师: {teacher_name}，使用ID为{teacher.teacher_id}的教师"))
        
        # 将教师添加到缓存中
        teacher_dict[teacher_name] = teacher
        return teacher
    
    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            *args: 位置参数
            **options: 关键字参数，包含命令行选项
            
        Returns:
            无
            
        Raises:
            CommandError: 当文件不存在或处理过程出错时抛出
        """
        file_path = options['file_path']
        sheet_name = options['sheet']
        debug = options['debug']
        update_existing = options['update']
        create_teachers = options['create_teachers']
        semester_id = options['semester']
        
        # 获取学期开始和结束日期
        start_date = None
        end_date = None
        if semester_id:
            from core.models import Semester
            try:
                semester = Semester.objects.get(semester_id=semester_id)
                start_date = semester.start_date
                end_date = semester.end_date
            except Semester.DoesNotExist:
                if debug:
                    self.stdout.write(self.style.WARNING(f"未找到学期: {semester_id}，不设置开始和结束日期"))
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise CommandError(f'文件不存在: {file_path}')
        
        try:
            # 显示导入开始信息
            self.stdout.write("="*80)
            self.stdout.write(self.style.SUCCESS(f"开始从 {file_path} 导入科任表数据"))
            self.stdout.write("="*80)
            
            # 读取Excel文件
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                self.stdout.write(f'成功读取文件，共 {len(df)} 条记录')
            except Exception as e:
                raise CommandError(f'读取Excel文件失败: {str(e)}')
            
            # 验证数据列
            required_columns = ['学校代码', '学校名称', '年级', '班别']
            
            for col in required_columns:
                if col not in df.columns:
                    raise CommandError(f'缺少必要列: {col}')
            
            # 获取学科映射
            subject_mapping = self._get_subject_mapping()
            
            # 检查哪些学科列存在于表格中
            available_subject_columns = [col for col in subject_mapping.keys() if col in df.columns]
            
            if not available_subject_columns:
                raise CommandError('未找到任何学科列')
            
            # 确保所有学科记录存在于数据库中
            for subject_col in available_subject_columns:
                subject_id, subject_name = subject_mapping[subject_col]
                Subject.objects.get_or_create(
                    subject_id=subject_id,
                    defaults={
                        'subject_name': subject_name,
                        'subject_type': 'MAIN',
                        'description': f'{subject_name}学科'
                    }
                )
            
            # 使用事务确保数据一致性
            with transaction.atomic():
                created_count = 0
                updated_count = 0
                error_count = 0
                
                # 缓存教师对象，避免重复查询
                teacher_cache = {}
                
                for _, row in df.iterrows():
                    try:
                        # 获取班级基本信息
                        school_id = str(row['学校代码'])
                        school_name = row['学校名称']
                        grade_level = str(row['年级'])
                        class_name = str(row['班别']).zfill(2)  # 确保班号是两位数
                        
                        # 尝试获取学校对象
                        try:
                            school = School.objects.get(school_id=school_id)
                        except School.DoesNotExist:
                            if debug:
                                self.stdout.write(self.style.WARNING(f"学校不存在: {school_id} {school_name}"))
                            error_count += 1
                            continue
                        
                        # 获取班级对象
                        class_id = f"{school_id}_{grade_level}_{class_name}"
                        try:
                            class_obj = Class.objects.get(class_id=class_id)
                        except Class.DoesNotExist:
                            if debug:
                                self.stdout.write(self.style.WARNING(f"班级不存在: {class_id}"))
                            error_count += 1
                            continue
                        
                        # 处理每个学科的任课教师
                        for subject_col in available_subject_columns:
                            if subject_col not in row or pd.isna(row[subject_col]):
                                continue
                            
                            teacher_name = str(row[subject_col]).strip()
                            subject_id, _ = subject_mapping[subject_col]
                            
                            # 获取教师对象
                            teacher = self._extract_teacher_id(teacher_name, teacher_cache, school, create_teachers, debug)
                            if not teacher:
                                continue
                            
                            # 获取学科对象
                            subject = Subject.objects.get(subject_id=subject_id)
                            
                            # 创建或更新TeacherSubject关联
                            defaults = {
                                'is_main': True,  # 默认为主教学科目
                                'status': 'ACTIVE'
                            }
                            
                            if start_date:
                                defaults['start_date'] = start_date
                            
                            if end_date:
                                defaults['end_date'] = end_date
                            
                            if update_existing:
                                # 更新现有记录
                                teacher_subject, created = TeacherSubject.objects.update_or_create(
                                    teacher=teacher,
                                    subject=subject,
                                    defaults=defaults
                                )
                            else:
                                # 仅创建新记录
                                teacher_subject, created = TeacherSubject.objects.get_or_create(
                                    teacher=teacher,
                                    subject=subject,
                                    defaults=defaults
                                )
                            
                            # 关联教师与班级
                            if not teacher.classes.filter(pk=class_obj.pk).exists():
                                teacher.classes.add(class_obj)
                            
                            if created:
                                created_count += 1
                                if debug:
                                    self.stdout.write(f"创建教师学科关联: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                            else:
                                updated_count += 1
                                if debug:
                                    self.stdout.write(f"更新教师学科关联: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                    
                    except Exception as e:
                        error_count += 1
                        if debug:
                            self.stdout.write(self.style.ERROR(f"处理数据错误: {str(e)}"))
                        continue
                
                # 输出导入结果摘要
                self.stdout.write("="*80)
                self.stdout.write(self.style.SUCCESS(f"科任表数据导入完成!"))
                self.stdout.write(f"新建关联: {created_count}")
                self.stdout.write(f"更新关联: {updated_count}")
                self.stdout.write(f"错误记录: {error_count}")
                self.stdout.write("="*80)
        
        except Exception as e:
            raise CommandError(f'导入过程出错: {str(e)}') 