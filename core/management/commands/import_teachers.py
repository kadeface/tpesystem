from django.core.management.base import BaseCommand
from core.models import School, Teacher, Region
import csv
import pandas as pd
from datetime import datetime
import os

class Command(BaseCommand):
    """
    导入教师数据的Django管理命令。

    从Excel或CSV文件中读取教师信息并导入到系统中。

    Args:
        file_path: 包含教师数据的文件路径

    Returns:
        None

    Raises:
        FileNotFoundError: 如果指定的文件不存在
        ValidationError: 如果数据不符合要求格式
    """

    help = '从Excel或CSV文件导入教师数据'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='文件路径（支持.xlsx, .xls, .csv）')
        parser.add_argument('--debug', action='store_true', help='启用调试模式')
        parser.add_argument('--delimiter', type=str, default='tab', 
                           help='CSV文件的字段分隔符（默认为tab表示制表符，可选comma表示逗号）')
        parser.add_argument('--sheet', type=str, default='Sheet1', 
                           help='Excel文件的工作表名（默认为Sheet1）')
        parser.add_argument('--show-errors', action='store_true', help='显示详细错误信息')

    def handle(self, *args, **options):
        file_path = options['file_path']
        debug = options.get('debug', False)
        show_errors = options.get('show_errors', False)
        delimiter_option = options.get('delimiter', 'tab')
        sheet_name = options.get('sheet', 'Sheet1')
        
        # 处理分隔符选项
        if delimiter_option == 'tab':
            delimiter = '\t'
        elif delimiter_option == 'comma':
            delimiter = ','
        else:
            delimiter = delimiter_option
            
        if len(delimiter) != 1 and not file_path.lower().endswith(('.xlsx', '.xls')):
            self.stdout.write(self.style.ERROR(f'错误: CSV分隔符必须是单个字符，当前值: "{delimiter}"'))
            return
        
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f'错误: 文件 "{file_path}" 不存在'))
            return
            
        # 检查学校数据
        schools = School.objects.all()
        if not schools.exists():
            self.stdout.write(self.style.WARNING('警告: 系统中没有学校记录，请先导入学校数据'))
        else:
            self.stdout.write(self.style.NOTICE(f'系统中存在 {schools.count()} 条学校记录'))
            for school in schools[:5]:
                self.stdout.write(self.style.NOTICE(f'  - {school.school_id}: {school.school_name}'))
        
        # 检查区域数据
        regions = Region.objects.all()
        if not regions.exists():
            self.stdout.write(self.style.WARNING('警告: 系统中没有区域记录，将使用默认区域'))
            # 创建默认区域
            Region.objects.create(
                region_id='REG001',
                region_name='默认区域',
                level='CITY'
            )
            self.stdout.write(self.style.SUCCESS('已创建默认区域 REG001'))
        else:
            self.stdout.write(self.style.NOTICE(f'系统中存在 {regions.count()} 条区域记录'))
        
        # 存储错误信息
        error_details = []
        
        try:
            # 根据文件扩展名判断文件类型
            file_ext = os.path.splitext(file_path)[1].lower()
            
            if file_ext in ['.xlsx', '.xls']:
                self.stdout.write(self.style.NOTICE(f'检测到Excel文件: {file_path}'))
                self._process_excel_file(file_path, sheet_name, debug, error_details)
            else:
                self.stdout.write(self.style.NOTICE(f'检测到CSV文件: {file_path}'))
                # 尝试使用UTF-8编码
                try:
                    with open(file_path, 'r', encoding='utf-8') as file:
                        self._process_csv_file(file, debug, delimiter, error_details)
                except UnicodeDecodeError:
                    # 如果UTF-8失败，尝试GBK编码
                    self.stdout.write(self.style.WARNING('UTF-8编码失败，尝试使用GBK编码'))
                    with open(file_path, 'r', encoding='gbk') as file:
                        self._process_csv_file(file, debug, delimiter, error_details)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'导入过程中出错: {str(e)}'))
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
        
        # 显示详细错误信息
        if show_errors and error_details:
            self.stdout.write(self.style.ERROR('\n详细错误信息:'))
            for i, (row_num, error) in enumerate(error_details[:20], 1):  # 只显示前20条
                self.stdout.write(self.style.ERROR(f"{i}. 行 {row_num}: {error}"))
            
            if len(error_details) > 20:
                self.stdout.write(self.style.ERROR(f"... 还有 {len(error_details) - 20} 条错误信息未显示"))
            
            # 错误类型统计
            error_types = {}
            for _, error in error_details:
                error_type = str(error).split(':')[0] if ':' in str(error) else str(error)
                error_types[error_type] = error_types.get(error_type, 0) + 1
            
            self.stdout.write(self.style.ERROR('\n错误类型统计:'))
            for error_type, count in sorted(error_types.items(), key=lambda x: x[1], reverse=True):
                self.stdout.write(self.style.ERROR(f"- {error_type}: {count}条"))
    
    def _process_excel_file(self, file_path, sheet_name, debug, error_details):
        """处理Excel文件导入"""
        try:
            # 使用pandas读取Excel文件
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            if debug:
                self.stdout.write(self.style.NOTICE('Excel文件预览:'))
                self.stdout.write(self.style.NOTICE(str(df.head())))
                self.stdout.write(self.style.NOTICE(f'列名: {df.columns.tolist()}'))
            
            # 将DataFrame转换为字典列表
            records = df.to_dict('records')
            
            # 处理记录
            self._process_records(records, debug, error_details)
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'处理Excel文件时出错: {str(e)}'))
            raise
    
    def _process_csv_file(self, file, debug, delimiter, error_details):
        """处理CSV文件导入"""
        # 预览文件内容
        if debug:
            file_content = file.read(500)
            self.stdout.write(self.style.NOTICE('文件内容预览:'))
            self.stdout.write(self.style.NOTICE(file_content))
            file.seek(0)  # 重置文件指针
        
        reader = csv.DictReader(file, delimiter=delimiter)
        if debug:
            self.stdout.write(self.style.NOTICE(f'标题行: {reader.fieldnames}'))
        
        # 处理记录
        self._process_records(reader, debug, error_details)
    
    def _process_records(self, records, debug, error_details):
        """处理数据记录（通用方法，适用于CSV和Excel）"""
        success_count = 0
        error_count = 0
        skipped_count = 0
        total_count = 0
        
        for row in records:
            total_count += 1
            if debug:
                self.stdout.write(self.style.NOTICE(f'处理第{total_count}条记录'))
                self.stdout.write(self.style.NOTICE(f'行数据: {row}'))
            
            try:
                # 提取必需字段
                teacher_data = {}
                
                # 姓名是必需的
                if '姓名' not in row or pd.isna(row['姓名']):
                    self.stdout.write(self.style.WARNING(f'警告: 第{total_count}行没有姓名，跳过'))
                    skipped_count += 1
                    continue
                
                # 生成唯一的教师ID
                name = str(row['姓名'])
                teacher_id = f"T{total_count:04d}"
                
                # 查找或创建学校
                school_name = str(row.get('学校名称', '')) if not pd.isna(row.get('学校名称', '')) else ''
                if not school_name:
                    self.stdout.write(self.style.WARNING(f'警告: 第{total_count}行没有学校名称，跳过'))
                    skipped_count += 1
                    continue
                
                schools = School.objects.filter(school_name=school_name)
                if schools.exists():
                    # 使用第一条记录，同时记录警告
                    school = schools.first()
                    if schools.count() > 1:
                        self.stdout.write(self.style.WARNING(
                            f"警告: 找到多个名为 '{school_name}' 的学校（共{schools.count()}个），使用ID为 {school.school_id} 的记录"
                        ))
                else:
                    # 创建一个临时学校ID
                    school_id = f"SCH{total_count:04d}"
                    self.stdout.write(self.style.WARNING(
                        f"警告: 找不到名称为 '{school_name}' 的学校，创建临时记录"
                    ))
                    
                    # 获取默认区域
                    try:
                        default_region = Region.objects.first()
                    except:
                        # A如果没有区域，创建默认区域
                        default_region = Region.objects.create(
                            region_id='REG001',
                            region_name='默认区域',
                            level='CITY'
                        )
                    
                    # 创建学校记录，使用默认值
                    school = School.objects.create(
                        school_id=school_id,
                        school_name=school_name,
                        school_type='PRIMARY',  # 默认小学
                        school_nature='PUBLIC',  # 默认公立
                        address='',
                        phone='',
                        email='',
                        principal='',
                        region=default_region  # 使用默认区域
                    )
                
                # 处理可能的NaN值
                def get_str_value(row, key, default=''):
                    value = row.get(key, default)
                    return str(value) if not pd.isna(value) else default
                
                # 提取其他字段
                # 性别处理（从身份证提取）
                id_number = get_str_value(row, '身份证号')
                if len(id_number) >= 18:
                    gender = 'F' if int(id_number[16]) % 2 == 0 else 'M'
                else:
                    gender = 'M'  # 默认男性
                
                # 提取出生日期（从身份证提取）
                birth_date = None
                if len(id_number) >= 18:
                    try:
                        birth_date = datetime.strptime(id_number[6:14], '%Y%m%d').date()
                    except ValueError:
                        birth_date = datetime.now().date()
                else:
                    birth_date = datetime.now().date()
                
                # 职称等级映射
                title = get_str_value(row, '职称')
                qualification = 'JUNIOR'  # 默认初级
                if '高级' in title:
                    qualification = 'SENIOR'
                elif '中级' in title:
                    qualification = 'MIDDLE'
                
                # 是否班主任（从职务判断）
                admin_position = get_str_value(row, '职务')
                is_class_teacher = '班主任' in admin_position
                
                # 教龄处理
                teaching_years = 0
                try:
                    teaching_years_str = get_str_value(row, '教龄', '0')
                    teaching_years = int(float(teaching_years_str)) if teaching_years_str.replace('.', '', 1).isdigit() else 0
                except:
                    teaching_years = 0
                
                # 创建教师记录
                defaults = {
                    'name': name,
                    'gender': gender,
                    'birth_date': birth_date,
                    'id_number': id_number,
                    'phone': get_str_value(row, '联系电话'),
                    'email': f"{name}@example.com",  # 默认邮箱
                    'education': get_str_value(row, '最高学历'),
                    'graduate_school': get_str_value(row, '毕业学校'),
                    'major': get_str_value(row, '专业'),
                    'cert_number': '',  # 无证书编号
                    'title': title,
                    'current_school': school,
                    'qualification': qualification,
                    'teaching_years': teaching_years,
                    'entry_date': None,  # 无入职日期
                    'main_subject': get_str_value(row, '任教科目'),
                    'secondary_subject': get_str_value(row, '兼任科目'),
                    'is_class_teacher': is_class_teacher,
                    'admin_position': admin_position,
                    'status': 'ACTIVE'
                }
                
                if debug:
                    self.stdout.write(self.style.NOTICE(f'将创建/更新教师: {teacher_id}'))
                    self.stdout.write(self.style.NOTICE(f'数据: {defaults}'))
                
                teacher, created = Teacher.objects.update_or_create(
                    teacher_id=teacher_id,
                    defaults=defaults
                )
                
                action = "创建" if created else "更新"
                self.stdout.write(self.style.SUCCESS(
                    f"成功{action}教师: {name} (ID: {teacher_id})"
                ))
                success_count += 1
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(
                    f"处理第{total_count}行时出错: {str(e)}"
                ))
                # 添加错误详情
                error_details.append((total_count, str(e)))
                error_count += 1
                import traceback
                if debug:
                    self.stdout.write(self.style.ERROR(traceback.format_exc()))
        
        self.stdout.write(self.style.SUCCESS(
            f'教师数据导入完成！总记录: {total_count}, 成功: {success_count}, '
            f'跳过: {skipped_count}, 错误: {error_count}'
        )) 