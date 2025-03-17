from django.db import models

class Region(models.Model):
    """
    区域模型，存储区域层级信息。

    Attributes:
        region_id: 区域编号，主键
        region_name: 区域名称
        parent_id: 上级区域ID，自关联
        level: 区域级别
        description: 区域描述
    """
    region_id = models.CharField(max_length=10, primary_key=True)
    region_name = models.CharField(max_length=100)
    parent_id = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    level = models.CharField(max_length=20)
    description = models.TextField()

    def __str__(self):
        return self.region_name

    class Meta:
        verbose_name = '区域'
        verbose_name_plural = '区域管理'

class Semester(models.Model):
    """
    学年学期模型，存储学期信息。

    Args:
        semester_id: 学期编号，主键
        year: 学年
        term: 学期
        start_date: 开始日期
        end_date: 结束日期
        status: 状态

    Returns:
        学期模型实例
    """
    semester_id = models.CharField(max_length=20, primary_key=True)
    year = models.CharField(max_length=9)  # 格式：2023-2024
    term = models.CharField(max_length=1, choices=[('1','第一学期'),('2','第二学期')])
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, default='ACTIVE')

    def __str__(self):
        return f"{self.year}学年第{self.term}学期"

    class Meta:
        verbose_name = '学期'
        verbose_name_plural = '学期管理'

class School(models.Model):
    """
    学校模型，存储学校基本信息。

    Args:
        school_id: 学校编号，主键
        school_name: 学校名称
        school_type: 学校类型
        school_nature: 学校性质
        address: 学校地址
        phone: 联系电话
        principal: 校长姓名
        region_id: 所属区域ID
        status: 状态

    Returns:
        学校模型实例
    """
    school_id = models.CharField(max_length=10, primary_key=True)
    school_name = models.CharField(max_length=100)
    school_type = models.CharField(max_length=10, choices=[
        ('PRIMARY', '小学'), 
        ('JUNIOR', '初中'), 
        ('HIGH', '高中')
    ])
    school_nature = models.CharField(max_length=10, choices=[
        ('PUBLIC', '公立'), 
        ('PRIVATE', '私立')
    ])
    address = models.CharField(max_length=200)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    principal = models.CharField(max_length=50)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, default='ACTIVE')

    def __str__(self):
        return self.school_name 

    class Meta:
        verbose_name = '学校'
        verbose_name_plural = '学校管理'

class Grade(models.Model):
    """
    年级模型，存储年级基本信息。

    Args:
        grade_id: 年级编号，主键
        grade_name: 年级名称
        school: 所属学校
        grade_level: 年级级别
        semester: 学期

    Returns:
        年级模型实例
    """
    grade_id = models.CharField(max_length=10, primary_key=True)
    grade_name = models.CharField(max_length=50)
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    grade_level = models.CharField(max_length=2)  # 年级级别(1-12)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.school.school_name}-{self.grade_name}"

    class Meta:
        verbose_name = '年级'
        verbose_name_plural = '年级管理'

class Class(models.Model):
    """
    班级模型，存储班级基本信息。

    Args:
        class_id: 班级编号，主键
        class_name: 班级名称
        grade: 所属年级
        teacher_id: 班主任ID
        capacity: 班级容量
        status: 状态

    Returns:
        班级模型实例
    """
    class_id = models.CharField(max_length=20, primary_key=True, help_text="班级唯一标识")
    class_name = models.CharField(max_length=50)
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    teacher_id = models.CharField(max_length=10)  # 临时字段，之后会替换为ForeignKey
    capacity = models.IntegerField()
    status = models.CharField(max_length=10, default='ACTIVE')
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='classes', null=True)

    def __str__(self):
        return f"{self.grade.school.school_name}-{self.grade.grade_name}-{self.class_name}" 

    class Meta:
        verbose_name = '班级'
        verbose_name_plural = '班级管理'
        unique_together = ('grade', 'class_name', 'semester')

class Teacher(models.Model):
    """
    教师模型，存储教师基本信息。

    Args:
        teacher_id: 教师编号，主键
        name: 教师姓名
        gender: 性别，M表示男，F表示女
        birth_date: 出生日期
        id_number: 身份证号
        phone: 联系电话
        email: 电子邮箱
        education: 最高学历
        graduate_school: 毕业院校
        major: 专业背景
        cert_number: 教师资格证编号
        title: 职称
        current_school: 当前所在学校
        qualification: 教师职称等级
        teaching_years: 教龄
        entry_date: 入职日期
        main_subject: 主要任教学科
        secondary_subject: 次要任教学科
        is_class_teacher: 是否班主任
        admin_position: 行政职务
        status: 在职状态

    Returns:
        教师模型实例
    """
    teacher_id = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=50)
    gender = models.CharField(max_length=1, choices=[('M', '男'), ('F', '女')])
    birth_date = models.DateField()
    id_number = models.CharField(max_length=18, blank=True, null=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    education = models.CharField(max_length=20, blank=True, null=True)
    graduate_school = models.CharField(max_length=100, blank=True, null=True)
    major = models.CharField(max_length=50, blank=True, null=True)
    cert_number = models.CharField(max_length=20, blank=True, null=True)
    title = models.CharField(max_length=100, blank=True, null=True)
    current_school = models.ForeignKey(School, on_delete=models.CASCADE)
    qualification = models.CharField(max_length=10, choices=[
        ('JUNIOR', '初级'), 
        ('MIDDLE', '中级'), 
        ('SENIOR', '高级')
    ])
    teaching_years = models.IntegerField(default=0)
    entry_date = models.DateField(blank=True, null=True)
    main_subject = models.CharField(max_length=50, blank=True, null=True)
    secondary_subject = models.CharField(max_length=50, blank=True, null=True)
    is_class_teacher = models.BooleanField(default=False)
    admin_position = models.CharField(max_length=100, blank=True, null=True)
    status = models.CharField(max_length=10, default='ACTIVE')
    classes = models.ManyToManyField(Class, related_name='teachers', blank=True)

    def __str__(self):
        return f"{self.name}({self.teacher_id})" 

    class Meta:
        verbose_name = '教师'
        verbose_name_plural = '教师管理'

class Family(models.Model):
    """
    家庭模型，存储学生家庭信息。
    """
    family_id = models.CharField(max_length=20, primary_key=True)
    family_name = models.CharField(max_length=50)
    address = models.CharField(max_length=200, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    status = models.CharField(max_length=10, default='ACTIVE')

    class Meta:
        verbose_name = '家庭'
        verbose_name_plural = '家庭管理'

class Student(models.Model):
    """
    学生模型，存储学生基本信息。

    Args:
        student_id: 学生编号，主键
        name: 学生姓名
        gender: 性别
        birth_date: 出生日期
        phone: 联系电话
        email: 电子邮箱
        family: 所属家庭
        current_school: 当前所在学校
        current_grade: 当前年级
        current_class: 当前班级
        region: 所属区域
        status: 状态

    Returns:
        学生模型实例
    """
    student_id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=50)
    gender = models.CharField(max_length=1, choices=[('M', '男'), ('F', '女')])
    birth_date = models.DateField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    family = models.ForeignKey(Family, on_delete=models.CASCADE)
    current_school = models.ForeignKey(School, on_delete=models.CASCADE)
    current_grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    current_class = models.ForeignKey(Class, on_delete=models.CASCADE)
    region = models.ForeignKey(Region, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, default='ACTIVE')
    id_number = models.CharField(max_length=18, unique=True, null=True, blank=True)
    school_student_id = models.CharField(max_length=20, null=True, blank=True)
    exam_number = models.CharField(max_length=20, null=True, blank=True)  # 添加考生号字段

    def __str__(self):
        return f"{self.name}({self.student_id})" 

    def masked_id_number(self):
        """返回脱敏后的身份证号"""
        if not self.id_number or len(self.id_number) < 8:
            return self.id_number
        return self.id_number[:6] + '*' * (len(self.id_number) - 10) + self.id_number[-4:]
    
    def masked_school_student_id(self):
        """返回脱敏后的学籍号"""
        if not self.school_student_id or len(self.school_student_id) < 8:
            return self.school_student_id
        return self.school_student_id[:4] + '*' * (len(self.school_student_id) - 8) + self.school_student_id[-4:]
    
    # 后台管理界面展示时使用
    def admin_id_number(self):
        return self.masked_id_number()
    admin_id_number.short_description = '身份证号'

    @staticmethod
    def validate_id_number(id_number):
        """
        验证身份证号格式。
        
        Args:
            id_number: 身份证号码
            
        Returns:
            tuple: (是否有效, 错误信息)
        """
        if not id_number:
            return True, ""  # 允许空值
        
        # 大陆身份证验证
        if id_number[0].isdigit():
            if len(id_number) != 18 and len(id_number) != 15:
                return False, f"大陆身份证号长度必须为18位(或15位旧证), 当前为{len(id_number)}位"
            
        # 港澳居民居住证 (H+10位数字)
        elif id_number.startswith('H'):
            if len(id_number) < 11 or not id_number[1:11].isdigit():
                return False, "香港居民居住证格式应为H+10位数字"
            
        # 澳门居民居住证 (M+10位数字)
        elif id_number.startswith('M'):
            if len(id_number) < 11 or not id_number[1:11].isdigit():
                return False, "澳门居民居住证格式应为M+10位数字"
            
        # 台湾居民居住证 (T+10位数字)
        elif id_number.startswith('T'):
            if len(id_number) < 11 or not id_number[1:11].isdigit():
                return False, "台湾居民居住证格式应为T+10位数字"
            
        else:
            return False, "未知的证件类型"
        
        return True, ""

    class Meta:
        verbose_name = '学生'
        verbose_name_plural = '学生管理'

class TeacherTeam(models.Model):
    """
    教师团队模型，存储教师团队信息。

    Args:
        team_id: 团队编号，主键
        team_name: 团队名称
        leader: 团队负责人
        school: 所属学校
        subject: 负责学科
        create_date: 创建日期
        status: 状态

    Returns:
        教师团队模型实例
    """
    team_id = models.CharField(max_length=10, primary_key=True)
    team_name = models.CharField(max_length=100)
    leader = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='led_teams')
    school = models.ForeignKey(School, on_delete=models.CASCADE)
    subject = models.ForeignKey('Subject', on_delete=models.CASCADE)
    create_date = models.DateField()
    status = models.CharField(max_length=10, default='ACTIVE') 

    class Meta:
        verbose_name = '教师团队'
        verbose_name_plural = '教师团队管理'

class Subject(models.Model):
    """
    学科模型，存储学科基本信息。

    Args:
        subject_id: 学科编号，主键
        subject_name: 学科名称
        subject_type: 学科类型
        description: 学科描述
        status: 状态

    Returns:
        学科模型实例
    """
    subject_id = models.CharField(max_length=10, primary_key=True)
    subject_name = models.CharField(max_length=50)
    subject_type = models.CharField(max_length=10, choices=[
        ('MAIN', '主课'), 
        ('MINOR', '副课')
    ])
    description = models.TextField()
    status = models.CharField(max_length=10, default='ACTIVE') 

    class Meta:
        verbose_name = '学科'
        verbose_name_plural = '学科管理'

class Exam(models.Model):
    """
    考试模型，存储考试基本信息。

    Args:
        exam_id: 考试编号，主键
        exam_name: 考试名称
        exam_type: 考试类型
        subject: 考试科目
        grade: 考试年级
        semester: 所属学期
        start_time: 开始时间
        end_time: 结束时间
        total_score: 总分值
        status: 状态

    Returns:
        考试模型实例
    """
    exam_id = models.CharField(max_length=30, primary_key=True)
    exam_name = models.CharField(max_length=100)
    exam_type = models.CharField(max_length=10, choices=[
        ('MIDTERM', '期中考试'), 
        ('FINAL', '期末考试'),
        ('ENTRANCE', '入学考试')
    ])
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    total_score = models.FloatField()
    status = models.CharField(max_length=10, default='PLANNED') 

    def __str__(self):
        return f"{self.exam_name} - {self.subject.subject_name}"

    class Meta:
        verbose_name = '考试'
        verbose_name_plural = '考试管理'

class EvaluationMetrics(models.Model):
    """
    评价指标模型，存储评价指标定义。

    Args:
        metric_id: 指标编号，主键
        metric_name: 指标名称
        metric_type: 指标类型
        weight: 权重
        formula: 计算公式
        description: 指标描述
        status: 状态

    Returns:
        评价指标模型实例
    """
    metric_id = models.CharField(max_length=60, primary_key=True)
    metric_name = models.CharField(max_length=100)
    metric_type = models.CharField(max_length=10, choices=[
        ('GROWTH', '成长型'), 
        ('LEVEL', '水平型')
    ])
    weight = models.FloatField()
    formula = models.TextField()
    description = models.TextField()
    status = models.CharField(max_length=10, default='ACTIVE') 

    class Meta:
        verbose_name = '评价指标'
        verbose_name_plural = '评价指标管理'

def get_default_semester():
    from core.models import Semester
    # 获取最新的学期
    try:
        return Semester.objects.filter(status='ACTIVE').first().semester_id
    except:
        return "UNKNOWN"

class Score(models.Model):
    """
    成绩模型，存储学生考试成绩信息。
    
    Args:
        score_id: 成绩编号，主键
        student: 学生
        exam: 考试
        subject: 学科
        teacher: 教师
        raw_score: 原始分数
        standard_score: 标准分
        percentile: 百分位
        grade: 等级
        status: 状态
        semester_id: 学期编号
        
    Returns:
        成绩模型实例
    """
    score_id = models.CharField(max_length=25, primary_key=True)  
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)
    raw_score = models.FloatField()
    standard_score = models.FloatField()
    percentile = models.FloatField()
    grade = models.CharField(max_length=2)  # A, B, C, D, F等
    status = models.CharField(max_length=10, default='DRAFT')
    semester_id = models.CharField(max_length=20, db_index=True, default=get_default_semester)
    
    def save(self, *args, **kwargs):
        # 确保semester_id与exam的学期一致
        if self.exam and not self.semester_id:
            self.semester_id = self.exam.semester_id
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = '成绩'
        verbose_name_plural = '成绩管理'
        indexes = [models.Index(fields=['semester_id'])]
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'exam', 'subject'],
                name='unique_score_record'
            )
        ]

class SubjectRelation(models.Model):
    """
    学科关联模型，存储学科间的关联关系。

    Args:
        relation_id: 关联编号，主键
        subject1: 关联学科1
        subject2: 关联学科2
        relation_type: 关联类型
        description: 关联描述

    Returns:
        学科关联模型实例
    """
    relation_id = models.CharField(max_length=60, primary_key=True)
    subject1 = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='related_from')
    subject2 = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='related_to')
    relation_type = models.CharField(max_length=15, choices=[
        ('PREREQUISITE', '先修课程'),
        ('RELATED', '相关课程')
    ])
    description = models.TextField()

    class Meta:
        verbose_name = '学科关联'
        verbose_name_plural = '学科关联管理'

class ValueAddedEvaluation(models.Model):
    """
    增值评价模型，存储增值评价结果。

    Args:
        eval_id: 评价编号，主键
        target_type: 评价对象类型
        target_id: 评价对象ID
        subject: 评价学科
        semester: 评价学期
        base_score: 基础分数
        current_score: 当前分数
        added_value: 增值分数
        factors: 影响因素
        status: 状态

    Returns:
        增值评价模型实例
    """
    eval_id = models.CharField(max_length=60, primary_key=True)
    target_type = models.CharField(max_length=10, choices=[
        ('SCHOOL', '学校'),
        ('TEACHER', '教师'),
        ('STUDENT', '学生')
    ])
    target_id = models.CharField(max_length=60)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    base_score = models.FloatField()
    current_score = models.FloatField()
    added_value = models.FloatField()
    factors = models.JSONField(default=dict)
    status = models.CharField(max_length=10, default='DRAFT') 

    class Meta:
        verbose_name = '增值评价'
        verbose_name_plural = '增值评价管理'

class TeacherSubject(models.Model):
    """
    教师学科关联模型，存储教师与学科的关联关系。
    
    Args:
        teacher: 教师
        subject: 学科
        is_main: 是否为主教学科目
        start_date: 开始教授日期
        end_date: 结束教授日期
        status: 状态
    
    Returns:
        教师学科关联模型实例
    """
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='teaching_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teachers')
    is_main = models.BooleanField(default=True)  # 是否为主教学科目
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, default='ACTIVE')
    
    class Meta:
        verbose_name = '教师学科关联'
        verbose_name_plural = '教师学科关联管理'
        unique_together = ('teacher', 'subject')  # 一个教师同一个学科只能有一条记录 

class TeacherSubjectClass(models.Model):
    """
    教师-学科-班级关联模型，记录教师教授的学科和班级。
    """
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE)
    class_field = models.ForeignKey(Class, on_delete=models.CASCADE)
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    
    class Meta:
        unique_together = [['teacher', 'subject', 'class_field', 'semester']]

class DataImportTool(models.Model):
    """
    数据导入工具模型（仅用于Admin界面）。
    
    创建一个实际的模型以便在Admin中显示。
    """
    name = models.CharField(max_length=100, default="数据导入工具")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = '数据导入工具'
        verbose_name_plural = '数据导入工具'

class StudentHistory(models.Model):
    """
    学生历史记录模型，记录学生班级和年级变更历史。
    
    Args:
        id: 自增主键
        student: 关联的学生
        grade: 当时所在年级
        class_field: 当时所在班级
        school: 当时所在学校
        semester: 关联学期
        start_date: 开始日期
        end_date: 结束日期
        status: 记录状态
        
    Returns:
        学生历史记录实例
    """
    id = models.AutoField(primary_key=True)
    student = models.ForeignKey('Student', on_delete=models.CASCADE)
    grade = models.ForeignKey('Grade', on_delete=models.SET_NULL, null=True)
    class_field = models.ForeignKey('Class', on_delete=models.SET_NULL, null=True)
    school = models.ForeignKey('School', on_delete=models.SET_NULL, null=True)
    semester = models.ForeignKey('Semester', on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, default='ACTIVE')
    
    class Meta:
        verbose_name = '学生历史记录'
        verbose_name_plural = '学生历史记录管理'

class TeacherHistory(models.Model):
    """
    教师历史记录模型，记录教师在不同学期的任教情况。
    
    跟踪记录教师历史任教的学校、学科、班级等信息，支持教师教学轨迹分析。
    """
    history_id = models.AutoField(primary_key=True)
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE, related_name='history')
    school = models.ForeignKey('School', on_delete=models.PROTECT)
    semester = models.ForeignKey('Semester', on_delete=models.PROTECT)
    subject = models.ForeignKey('Subject', on_delete=models.PROTECT)
    grade = models.ForeignKey('Grade', on_delete=models.PROTECT, null=True, blank=True)
    class_field = models.ForeignKey('Class', on_delete=models.PROTECT, null=True, blank=True)
    is_class_teacher = models.BooleanField(default=False, verbose_name='是否班主任')
    admin_position = models.CharField(max_length=100, blank=True, null=True, verbose_name='行政职务')
    start_date = models.DateField(verbose_name='开始日期')
    end_date = models.DateField(null=True, blank=True, verbose_name='结束日期')
    status = models.CharField(max_length=20, choices=[
        ('ACTIVE', '在任'), 
        ('COMPLETED', '已结束'),
        ('SUSPENDED', '暂停')
    ], default='ACTIVE')
    
    class Meta:
        verbose_name = '教师历史记录'
        verbose_name_plural = '教师历史记录'
        unique_together = [['teacher', 'school', 'semester', 'subject', 'class_field']]
        
    def __str__(self):
        semester_display = self.semester.semester_id.replace('-', '学年第') + '学期'
        return f"{self.teacher.name} - {self.school.school_name} - {semester_display} - {self.subject.subject_name}" 

class ValueAddedConfig(models.Model):
    """
    增值评价配置模型，存储不同评价场景的配置。
    
    Args:
        config_id: 配置编号，主键
        config_name: 配置名称
        target_type: 评价对象类型
        method: 评价方法
        parameters: 评价参数
        description: 配置描述
        status: 状态
        
    Returns:
        增值评价配置模型实例
    """
    config_id = models.CharField(max_length=60, primary_key=True)
    config_name = models.CharField(max_length=100)
    target_type = models.CharField(max_length=10, choices=[
        ('SCHOOL', '学校'),
        ('TEACHER', '教师'),
        ('STUDENT', '学生')
    ])
    method = models.CharField(max_length=60, choices=[
        ('simple_difference', '简单差值法'),
        ('simple_difference_tes', 'TES差值法'),
        ('predicted_difference', '预测差值法'),
        ('hlm', '多层线性模型'),
        ('ml_random_forest', '随机森林'),
        ('ml_neural_network', '神经网络')
    ])
    parameters = models.JSONField(default=dict)
    description = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=10, default='ACTIVE') 

    class Meta:
        verbose_name = '增值评价配置'
        verbose_name_plural = '增值评价配置管理'
        
    def __str__(self):
        return f"{self.config_name} ({self.target_type})" 