from django import forms
from .models import Semester, Region, Teacher

class ScoresImportForm(forms.Form):
    """
    成绩导入表单。
    
    Args:
        file: 成绩Excel文件
        exam_id: 考试ID
        exam_name: 考试名称
        semester: 学期
        exam_type: 考试类型
        region: 区域
        teacher_id: 教师ID (可选)
    
    Returns:
        验证后的表单
    """
    file = forms.FileField(label='Excel文件')
    exam_id = forms.CharField(label='考试ID', max_length=50)
    exam_name = forms.CharField(label='考试名称', max_length=100)
    semester = forms.ModelChoiceField(
        label='学期',
        queryset=Semester.objects.all(),
        empty_label="请选择学期"
    )
    exam_type = forms.ChoiceField(
        label='考试类型',
        choices=[
            ('monthly', '月考'),
            ('midterm', '期中考试'),
            ('final', '期末考试'),
            ('entrance', '入学考试'),
            ('mock', '模拟考试'),
            ('other', '其他')
        ]
    )
    region = forms.ModelChoiceField(
        label='区域',
        queryset=Region.objects.all(),
        required=False,
        empty_label="请选择区域（可选）"
    )
    teacher_id = forms.ModelChoiceField(
        label='教师ID',
        queryset=Teacher.objects.all(),
        required=False,
        empty_label="请选择教师（可选）"
    )
    sheet_name = forms.CharField(
        label='工作表名称',
        max_length=50,
        required=False,
        help_text='留空将使用第一个工作表'
    )
    create_students = forms.BooleanField(
        label='自动创建学生',
        required=False,
        initial=True,
        help_text='如果学生不存在，自动创建'
    )
    update_students = forms.BooleanField(
        label='更新学生信息',
        required=False,
        initial=True,
        help_text='从Excel中更新学生信息'
    )
    skip_teacher = forms.BooleanField(
        label='跳过教师验证',
        required=False,
        help_text='不检查教师是否存在'
    )
    debug = forms.BooleanField(
        label='调试模式',
        required=False,
        help_text='打印详细信息但不写入数据库'
    )
    smart_match = forms.BooleanField(
        label='智能匹配',
        required=False,
        initial=True,
        help_text='智能匹配学生和科目'
    )
    force = forms.BooleanField(
        label='强制导入',
        required=False,
        help_text='忽略错误继续导入'
    ) 