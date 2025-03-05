"""
导入教师学科班级关联数据的管理命令。

此命令从Excel文件中读取教师-学科-班级关联数据，并将其导入系统数据库。
建立教师、学科、班级的三方关联关系，对应特定学期的教学安排。
"""

import pandas as pd
from datetime import datetime, date
import os
import logging
import re
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from core.models import Teacher, Subject, Class, School, TeacherSubject, Semester, TeacherSubjectClass, TeacherHistory
import random

# 配置日志
logger = logging.getLogger(__name__)

class Command(BaseCommand):
    """
    导入教师学科班级关联数据的Django管理命令。
    
    从Excel文件导入教师-学科-班级关联数据，建立教师、学科、班级三者的关联关系。
    支持"宽表"格式，即一行数据包含一个班级的多个学科教师。
    
    Args:
        BaseCommand: Django管理命令基类
    
    Returns:
        无
    
    Raises:
        CommandError: 当文件不存在或格式不正确时抛出
    """
    
    help = '从Excel文件导入教师学科班级关联数据'
    
    def add_arguments(self, parser):
        """
        添加命令行参数配置。
        
        Args:
            parser: 参数解析器对象
            
        Returns:
            无
        """
        parser.add_argument('file_path', type=str, help='关联数据Excel文件路径')
        parser.add_argument('--sheet', type=str, help='Excel工作表名称', default='Sheet1')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        parser.add_argument('--update', action='store_true', help='更新现有记录')
        parser.add_argument('--batch-size', type=int, default=100, help='批量处理大小')
        parser.add_argument('--skip-validation', action='store_true', help='跳过数据验证')
        parser.add_argument('--dry-run', action='store_true', help='试运行模式，不实际写入数据库')
        parser.add_argument('--semester-id', type=str, help='学期ID，例如：2023-2024-1', required=True)
        parser.add_argument('--auto-create-teachers', action='store_true', help='自动创建教师')
    
    def validate_data(self, df):
        """
        验证导入数据的有效性。
        
        Args:
            df: DataFrame对象，包含要验证的数据
            
        Returns:
            tuple: (是否有效, 学科列列表)
            
        Raises:
            CommandError: 当数据无效时抛出
        """
        # 打印所有列名，帮助调试
        self.stdout.write("Excel文件中的列名:")
        for col_idx, col_name in enumerate(df.columns):
            self.stdout.write(f"  {col_idx+1}. '{col_name}'")
        
        # 列名映射 - 支持多种可能的列名
        column_mappings = {
            '学校代码': ['学校代码', '学校编号', '校码'],
            '年级': ['年级', '级别', 'Grade'],
            '班级': ['班级', '班别', '班号', '班组', 'Class']
        }
        
        # 初始化列名映射结果
        actual_column_names = {}
        missing_columns = []
        
        # 检查每个所需列，寻找匹配
        for required_col, possible_names in column_mappings.items():
            found = False
            for name in possible_names:
                if name in df.columns:
                    actual_column_names[required_col] = name
                    found = True
                    break
            
            if not found:
                missing_columns.append(required_col)
        
        # 如果有缺失列，抛出错误
        if missing_columns:
            error_msg = f"缺少必要列: {', '.join(missing_columns)}\n可能的列名: {column_mappings}"
            raise CommandError(error_msg)
        
        # 打印识别出的列名
        self.stdout.write("列名匹配结果:")
        for required_col, actual_col in actual_column_names.items():
            self.stdout.write(f"  {required_col} -> '{actual_col}'")
        
        # 确定学科列 - 排除已识别的列和学校名称列
        identified_columns = list(actual_column_names.values()) + ['学校名称']
        subject_columns = [col for col in df.columns if col not in identified_columns]
        
        if not subject_columns:
            raise CommandError('未找到学科教师列')
        
        # 检查空值
        for col in actual_column_names.values():
            null_count = df[col].isna().sum()
            if null_count > 0:
                self.stdout.write(self.style.WARNING(f'警告: {col} 列有 {null_count} 个空值'))
        
        # 数据类型转换和清洗
        for col in actual_column_names.values():
            df[col] = df[col].astype(str)
            df[col] = df[col].str.strip()  # 去除前后空格
        
        # 将实际列名保存到类属性中，供process_row使用
        self.column_map = actual_column_names
        
        return True, subject_columns
    
    def get_subject_id_map(self):
        """
        获取学科名称到学科ID的映射。
        
        Returns:
            dict: 学科名称到学科ID的映射
        """
        # 先打印所有学科供参考
        self.stdout.write("数据库中的所有学科:")
        subjects = Subject.objects.all()
        subject_ids = []
        for subject in subjects:
            self.stdout.write(f"  {subject.subject_name} (ID: {subject.subject_id})")
            subject_ids.append(subject.subject_id)
        
        # 根据实际数据库中的学科ID创建映射
        subject_map = {
            '语文': 'CHN',
            '数学': 'MATH',
            '英语': 'ENG',
            '物理': 'PHY',
            '化学': 'CHEM' if 'CHEM' in subject_ids else None,
            '生物': 'BIO' if 'BIO' in subject_ids else None,
            '政治': 'MOR',  # 注意：政治映射到道德与法治
            '道德与法治': 'MOR',
            '历史': 'HIS',
            '地理': 'GEO' if 'GEO' in subject_ids else None,
            '总分': 'TOTAL'
        }
        
        # 移除映射到不存在学科ID的项
        subject_map = {k: v for k, v in subject_map.items() if v is not None}
        
        # 实际获取数据库中的学科
        self.subject_name_map = {}  # 用于存储ID到名称的映射，便于反查
        
        for subject in subjects:
            # 存储ID到名称的映射
            self.subject_name_map[subject.subject_id] = subject.subject_name
            
            # 生成多种可能的键名以提高匹配率
            key = subject.subject_name
            subject_map[key] = subject.subject_id  # 完整名称
            
            # 简化名称，如"语文"变为"语"
            if len(key) > 1 and '学' in key:
                simple_key = key.replace('学', '')
                subject_map[simple_key] = subject.subject_id
            
            # 处理列名中可能的变体，如"语文科任"
            key_with_suffix = f"{key}科任"
            subject_map[key_with_suffix] = subject.subject_id
            
            # 特殊处理政治/道德与法治
            if subject.subject_id == 'MOR':
                subject_map['政治'] = 'MOR'
                subject_map['政治科任'] = 'MOR'
                subject_map['思政'] = 'MOR'
                subject_map['道法'] = 'MOR'
        
        return subject_map
    
    def get_school_education_level(self, school_id):
        """
        根据学校ID确定教育学段代码。
        
        Args:
            school_id: 学校ID
            
        Returns:
            str: 教育学段代码，如'PRIMARY'、'JUNIOR'、'SENIOR'等
        """
        try:
            # 尝试从数据库中查询学校信息以确定学段
            school = School.objects.get(school_id=school_id)
            
            # 直接通过school_type判断学段
            if hasattr(school, 'school_type') and school.school_type:
                # 假设school_type和qualification使用同样的编码
                return school.school_type
            
            # 如果没有school_type或者为空，再尝试通过名称判断
            if hasattr(school, 'school_name'):
                if '小学' in school.school_name:
                    return 'PRIMARY'
                elif '初中' in school.school_name or '中学' in school.school_name:
                    if '高中' in school.school_name:
                        return 'SENIOR'
                    return 'JUNIOR'
                elif '高中' in school.school_name:
                    return 'SENIOR'
        except School.DoesNotExist:
            # 学校不存在时的处理
            pass
        
        # 通过学校ID前缀判断 - 作为兜底方案
        if school_id.startswith('1'):
            return 'PRIMARY'  # 小学
        elif school_id.startswith('2'):
            return 'JUNIOR'   # 初中
        elif school_id.startswith('3'):
            return 'SENIOR'   # 高中
        
        # 默认值
        return 'SENIOR'  # 默认为高中
    
    def create_teacher_with_defaults(self, teacher_id, teacher_name, school_id, qualification):
        """
        创建教师并提供所有必需字段的默认值
        
        Args:
            teacher_id: 教师ID
            teacher_name: 教师姓名
            school_id: 学校ID
            qualification: 学段信息
            
        Returns:
            Teacher: 创建的教师对象
        """
        # 默认生日设为1980年1月1日
        default_birth_date = date(1980, 1, 1)
        
        # 创建所有字段的默认值
        teacher_data = {
            'teacher_id': teacher_id,
            'name': teacher_name,
            'gender': 'U',  # 默认性别未知
            'birth_date': default_birth_date,  # 提供默认生日
            'phone': '',  # 空字符串而非null
            'email': '',  # 空字符串而非null
            'current_school_id': school_id,
            'status': 'ACTIVE',
            'qualification': qualification
        }
        
        # 创建教师
        teacher = Teacher.objects.create(**teacher_data)
        return teacher
    
    def process_row(self, row, subject_columns, subject_map, semester_id, debug=False, update_existing=False):
        """
        处理单行数据，为每个学科教师创建关联。
        
        Args:
            row: Series对象，包含一行数据
            subject_columns: 学科教师列名列表
            subject_map: 学科名称到学科ID的映射
            semester_id: 学期ID
            debug: 是否启用调试模式
            update_existing: 是否更新现有记录
            
        Returns:
            tuple: (创建数, 更新数, 错误数)
        """
        created_count = 0
        updated_count = 0
        error_count = 0
        
        try:
            # 使用validate_data中识别的列名获取基本数据
            school_id = str(row[self.column_map['学校代码']])
            grade_level = str(row[self.column_map['年级']])
            class_name = str(row[self.column_map['班级']])
            
            # 查找班级
            class_id = f"{school_id}_{grade_level}_{class_name}"
            try:
                class_obj = Class.objects.get(class_id=class_id)
            except Class.DoesNotExist:
                if debug:
                    logger.warning(f"班级不存在: {class_id}")
                return 0, 0, 1
            
            # 获取学期对象
            try:
                semester = Semester.objects.get(semester_id=semester_id)
            except Semester.DoesNotExist:
                if debug:
                    logger.warning(f"学期不存在: {semester_id}")
                return 0, 0, 1
            
            # 处理每个学科教师
            for subject_col in subject_columns:
                if pd.isna(row[subject_col]):
                    continue
                
                teacher_name = str(row[subject_col]).strip()
                if not teacher_name:
                    continue
                
                # 获取学科ID
                subject_id = None
                
                # 1. 直接从映射中查找完整的列名
                if subject_col in subject_map:
                    subject_id = subject_map[subject_col]
                else:
                    # 2. 尝试从映射中查找部分匹配
                    for key, value in subject_map.items():
                        if key in subject_col or subject_col in key:
                            subject_id = value
                            break
                
                if not subject_id:
                    if debug:
                        logger.warning(f"无法识别学科: {subject_col}")
                    error_count += 1
                    continue
                
                # 查找学科
                try:
                    subject = Subject.objects.get(subject_id=subject_id)
                except Subject.DoesNotExist:
                    if debug:
                        logger.warning(f"学科不存在: {subject_id}")
                    error_count += 1
                    continue
                
                # 根据教师姓名查找教师记录
                try:
                    # 记录原始名称以便调试
                    original_name = teacher_name
                    
                    # 清理教师名称（去除空格和特殊字符）
                    teacher_name = teacher_name.strip()
                    
                    # 1. 精确匹配当前学校教师
                    teacher = Teacher.objects.filter(
                        name=teacher_name,
                        current_school__school_id=school_id
                    ).first()
                    
                    # 2. 精确匹配所有教师
                    if not teacher:
                        teacher = Teacher.objects.filter(name=teacher_name).first()
                    
                    # 3. 如果仍未找到，尝试模糊匹配
                    if not teacher and len(teacher_name) > 1:
                        self.stdout.write(f"尝试模糊匹配教师: {original_name}")
                        # 使用包含查询而非精确匹配
                        possible_teachers = Teacher.objects.filter(name__contains=teacher_name[:2])
                        if possible_teachers.exists():
                            self.stdout.write(f"  可能的匹配: {[t.name for t in possible_teachers]}")
                            # 可以选择自动使用第一个匹配项
                            # teacher = possible_teachers.first()
                    
                    # 如果教师不存在，检查是否需要自动创建
                    if not teacher:
                        if self.options.get('auto_create_teachers'):
                            try:
                                # 生成短ID，确保不超过10个字符
                                short_school_id = school_id[-2:] if len(school_id) >= 2 else school_id
                                short_name = teacher_name[:2] if len(teacher_name) >= 2 else teacher_name
                                random_suffix = str(random.randint(100, 999))
                                teacher_id = f"A{short_school_id}{short_name}{random_suffix}"
                                
                                # 确保ID不超过10个字符
                                if len(teacher_id) > 10:
                                    teacher_id = teacher_id[:10]
                                
                                # 检查ID是否已存在
                                while Teacher.objects.filter(teacher_id=teacher_id).exists():
                                    random_suffix = str(random.randint(100, 999))
                                    teacher_id = f"A{short_school_id}{short_name}{random_suffix}"
                                    if len(teacher_id) > 10:
                                        teacher_id = teacher_id[:10]
                                
                                # 确定教师的学段代码
                                qualification = self.get_school_education_level(school_id)
                                
                                # 使用辅助方法创建教师，确保提供所有必需字段的默认值
                                teacher = self.create_teacher_with_defaults(
                                    teacher_id=teacher_id,
                                    teacher_name=teacher_name,
                                    school_id=school_id,
                                    qualification=qualification
                                )
                                
                                self.stdout.write(f"自动创建教师: {teacher_name} (ID: {teacher_id}, 学段: {qualification})")
                            except Exception as e:
                                if debug:
                                    self.stdout.write(self.style.ERROR(f"自动创建教师失败: {str(e)}"))
                                error_count += 1
                                continue
                        else:
                            if debug:
                                logger.warning(f"教师不存在: {original_name} (在学校 {school_id})")
                            error_count += 1
                            continue
                        
                except Exception as e:
                    if debug:
                        logger.error(f"查找教师错误: {str(e)}")
                    error_count += 1
                    continue
                
                # 创建或更新TeacherSubjectClass关联
                try:
                    if update_existing:
                        # 更新现有记录
                        teacher_subject_class, created = TeacherSubjectClass.objects.update_or_create(
                            teacher=teacher,
                            subject=subject,
                            class_obj=class_obj,
                            semester=semester,
                            defaults={
                                'is_main': True,
                                'status': 'ACTIVE',
                                'school': class_obj.grade.school  # 从班级获取学校
                            }
                        )
                    else:
                        # 仅创建新记录
                        teacher_subject_class, created = TeacherSubjectClass.objects.get_or_create(
                            teacher=teacher,
                            subject=subject,
                            class_obj=class_obj,
                            semester=semester,
                            defaults={
                                'is_main': True,
                                'status': 'ACTIVE',
                                'school': class_obj.grade.school  # 从班级获取学校
                            }
                        )
                    
                    # 同时创建或更新TeacherSubject记录
                    teacher_subject, ts_created = TeacherSubject.objects.update_or_create(
                        teacher=teacher,
                        subject=subject,
                        defaults={
                            'is_main': True,
                            'status': 'ACTIVE',
                            'start_date': semester.start_date,
                            'end_date': semester.end_date
                        }
                    )
                    
                    # 关联教师与班级
                    if not teacher.classes.filter(pk=class_obj.pk).exists():
                        teacher.classes.add(class_obj)
                    
                    if created:
                        created_count += 1
                        if debug:
                            logger.info(f"创建教师学科班级关联: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                    else:
                        updated_count += 1
                        if debug:
                            logger.info(f"更新教师学科班级关联: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                            
                    # 如果是更新，先创建历史记录
                    if update_existing and not self.options['dry_run']:
                        existing_tsc = TeacherSubjectClass.objects.filter(
                            teacher=teacher,
                            subject=subject,
                            class_obj=class_obj,
                            semester=semester
                        ).first()
                        
                        if existing_tsc:
                            # 创建历史记录
                            TeacherHistory.objects.create(
                                teacher=teacher,
                                school=class_obj.grade.school,  # 从班级获取学校
                                semester=semester,
                                subject=subject,
                                grade=class_obj.grade,
                                class_field=class_obj,
                                is_class_teacher=teacher.is_class_teacher,
                                admin_position=teacher.admin_position,
                                start_date=semester.start_date,
                                end_date=semester.end_date,
                                status='COMPLETED'
                            )
                            self.stdout.write(f"创建教师历史记录: {teacher.name} - {subject.subject_name} - {class_obj.class_name}")
                            
                except Exception as e:
                    if debug:
                        logger.error(f"创建关联错误: {str(e)}")
                    error_count += 1
                    
        except Exception as e:
            if debug:
                logger.error(f"处理行数据错误: {str(e)}")
            error_count += 1
            
        return created_count, updated_count, error_count
    
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
        # 将选项保存为实例变量，以便在其他方法中访问
        self.options = options
        
        file_path = options['file_path']
        sheet_name = options['sheet']
        debug = options['debug']
        update_existing = options['update']
        batch_size = options['batch_size']
        skip_validation = options['skip_validation']
        dry_run = options['dry_run']
        semester_id = options['semester_id']
        auto_create_teachers = options['auto_create_teachers']
        
        # 配置日志级别
        if debug:
            logger.setLevel(logging.DEBUG)
        
        # 检查文件是否存在
        if not os.path.exists(file_path):
            raise CommandError(f'文件不存在: {file_path}')
        
        try:
            # 显示导入开始信息
            self.stdout.write("="*80)
            self.stdout.write(self.style.SUCCESS(f"开始从 {file_path} 导入教师学科班级关联数据"))
            self.stdout.write(f"使用学期ID: {semester_id}")
            if dry_run:
                self.stdout.write(self.style.WARNING("试运行模式：不会实际写入数据库"))
            self.stdout.write("="*80)
            
            # 读取Excel文件
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                self.stdout.write(f'成功读取文件，共 {len(df)} 条记录')
            except Exception as e:
                raise CommandError(f'读取Excel文件失败: {str(e)}')
            
            # 获取学科映射
            subject_map = self.get_subject_id_map()
            self.stdout.write(f'获取到学科映射: {len(subject_map)} 个学科')
            
            # 数据验证
            if not skip_validation:
                valid, subject_columns = self.validate_data(df)
                if valid:
                    self.stdout.write(self.style.SUCCESS("数据验证通过"))
                    self.stdout.write(f"识别到的学科列: {', '.join(subject_columns)}")
            else:
                # 如果跳过验证，手动设置列名映射
                self.column_map = {
                    '学校代码': '学校代码',
                    '年级': '年级',
                    '班级': '班级'  # 请确保这与Excel中的实际列名匹配
                }
                
                # 尝试自动检测列名
                for col in ['班级', '班别', '班号', '班组']:
                    if col in df.columns:
                        self.column_map['班级'] = col
                        break
                
                # 排除基本列的其余列视为学科列
                identified_columns = list(self.column_map.values()) + ['学校名称']
                subject_columns = [col for col in df.columns if col not in identified_columns]
                self.stdout.write(f"跳过验证，识别到的学科列: {', '.join(subject_columns)}")
            
            created_count = 0
            updated_count = 0
            error_count = 0
            
            # 按批次处理数据
            total_rows = len(df)
            batches = (total_rows + batch_size - 1) // batch_size
            
            for batch_idx in range(batches):
                start_idx = batch_idx * batch_size
                end_idx = min((batch_idx + 1) * batch_size, total_rows)
                
                self.stdout.write(f"处理批次 {batch_idx+1}/{batches} (记录 {start_idx+1}-{end_idx})")
                
                batch_created = 0
                batch_updated = 0
                batch_error = 0
                
                # 为每个批次创建独立的事务
                with transaction.atomic():
                    sid = transaction.savepoint()
                    
                    try:
                        for idx in range(start_idx, end_idx):
                            row = df.iloc[idx]
                            
                            # 为每行创建独立的保存点
                            row_sid = transaction.savepoint()
                            
                            try:
                                row_created, row_updated, row_error = self.process_row(
                                    row, 
                                    subject_columns, 
                                    subject_map, 
                                    semester_id,
                                    debug, 
                                    update_existing
                                )
                                
                                batch_created += row_created
                                batch_updated += row_updated
                                batch_error += row_error
                                
                            except Exception as e:
                                # 如果处理行时出错，回滚到该行的保存点，但继续处理其他行
                                transaction.savepoint_rollback(row_sid)
                                batch_error += 1
                                self.stdout.write(self.style.ERROR(f"处理行 {idx+1} 时出错: {str(e)}"))
                        
                        if dry_run:
                            # 试运行模式下回滚整个批次
                            transaction.savepoint_rollback(sid)
                            self.stdout.write(self.style.WARNING(f"批次 {batch_idx+1} 试运行完成，已回滚更改"))
                    
                    except Exception as e:
                        # 如果批次处理过程中出现未捕获的异常，回滚整个批次
                        transaction.savepoint_rollback(sid)
                        self.stdout.write(self.style.ERROR(f"处理批次 {batch_idx+1} 时发生严重错误: {str(e)}"))
                        batch_error = end_idx - start_idx  # 将整个批次标记为错误
                
                created_count += batch_created
                updated_count += batch_updated
                error_count += batch_error
                
                self.stdout.write(f"批次 {batch_idx+1} 处理完成: 新建 {batch_created}, 更新 {batch_updated}, 错误 {batch_error}")
            
            # 输出导入结果摘要
            self.stdout.write("="*80)
            status_msg = "关联数据试运行完成!" if dry_run else "关联数据导入完成!"
            self.stdout.write(self.style.SUCCESS(status_msg))
            self.stdout.write(f"新建关联: {created_count}")
            self.stdout.write(f"更新关联: {updated_count}")
            self.stdout.write(f"错误记录: {error_count}")
            self.stdout.write("="*80)
        
        except Exception as e:
            raise CommandError(f'导入过程出错: {str(e)}') 

    def import_teacher_subject_class(self, row, semester):
        # 先查询现有记录
        existing = TeacherSubjectClass.objects.filter(...)
        
        # 如果更新现有记录，先创建历史
        if existing:
            TeacherHistory.objects.create(
                teacher=existing.teacher,
                school=existing.teacher.current_school,
                semester=semester,
                subject=existing.subject,
                grade=existing.class_field.grade,
                class_field=existing.class_field,
                is_class_teacher=existing.teacher.is_class_teacher,
                admin_position=existing.teacher.admin_position,
                start_date=semester.start_date,
                end_date=semester.end_date,
                status='COMPLETED'
            ) 