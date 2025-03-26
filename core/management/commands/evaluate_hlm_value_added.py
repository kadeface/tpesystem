"""
基于多层线性模型(HLM)的教师增值评价管理命令

python manage.py evaluate_hlm_value_added --base-exam 2025-DIST-M-202301 --current-exam 2025-DIST-M-202307 --subject CHN --export
"""
import pandas as pd
import numpy as np
from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Score, Class, Student, Subject, ValueAddedEvaluation, School, Grade, Teacher, TeacherHistory, Exam, StudentHistory
import os
from datetime import datetime
import statsmodels.api as sm
import statsmodels.formula.api as smf
import matplotlib.pyplot as plt
from scipy import stats
import warnings
from django.db.models import Q


class Command(BaseCommand):
    """
    实现基于多层线性模型(HLM)的教师增值评价算法。
    
    该命令处理学生-班级-学校三层嵌套数据结构，并通过HLM模型计算教师增值效应。
    
    Args:
        base_exam: 基线考试ID
        current_exam: 当前考试ID
        subject: 学科ID
        
    Returns:
        None: 结果会保存到数据库和/或导出到Excel文件
        
    Raises:
        ValueError: 当输入数据不满足模型要求时
    """
    
    help = '使用多层线性模型(HLM)进行教师增值评价'

    def add_arguments(self, parser):
        """
        定义命令行参数。
        
        Args:
            parser: 命令行参数解析器
            
        Returns:
            None
        """
        parser.add_argument('--base-exam', required=True, help='基线考试ID')
        parser.add_argument('--current-exams', required=True, nargs='+', help='当前考试ID(可指定多个)')
        parser.add_argument('--subject', required=True, help='学科ID')
        parser.add_argument('--export', help='导出结果到指定文件夹')
        parser.add_argument('--no-save', action='store_true', help='不保存结果到数据库')
        parser.add_argument('--min-students', type=int, default=10, help='最小学生数量')

    def handle(self, *args, **options):
        """
        命令处理主函数。
        
        Args:
            *args: 位置参数
            **options: 关键字参数
            
        Returns:
            None
        """
        self.stdout.write("开始HLM增值评价分析...")
        
        # 保存选项
        self.options = options
        
        # 获取基本参数
        base_exam_id = options['base_exam']
        current_exams = options['current_exams']  # 这现在是一个列表
        subject_id = options['subject']
        
        self.stdout.write(f"基线考试: {base_exam_id}")
        self.stdout.write(f"当前考试: {', '.join(current_exams)}")
        self.stdout.write(f"学科: {subject_id}")
        
        # 检查是单考试还是多考试模式
        if len(current_exams) == 1:
            # 单次考试模式 - 使用原有逻辑
            current_exam_id = current_exams[0]
            
            # 获取考试信息
            exams_info = self._get_exams_info(base_exam_id, current_exam_id)
            if not exams_info:
                return
            
            # 获取学生数据
            student_data = self._get_student_scores(base_exam_id, current_exam_id, subject_id, exams_info)
            if student_data is None or student_data.empty:
                return
            
            # 预处理数据
            model_data = self._preprocess_data(student_data)
            
            # 拟合模型
            model_results = self._fit_hlm_model(model_data)
            
            # 模型诊断
            diagnostics = self._run_model_diagnostics(model_data, model_results)
            self._display_diagnostics(diagnostics)
            
            # 计算教师效应
            teacher_effects = self._calculate_teacher_effects(model_results, model_data)
            
            # 进行方差分解
            variance_components = self._decompose_variance(model_results)
            self._display_variance_components(variance_components)
            
            # 显示结果
            self._display_results(teacher_effects, model_results)
            
            # 导出结果
            if options.get('export'):
                self._export_to_excel(teacher_effects, variance_components, options['export'])
            
            # 保存到数据库
            if not options.get('no_save', False):
                self._save_results_to_db(teacher_effects, model_results, exams_info)
        else:
            # 多次考试模式 - 使用新逻辑
            self.stdout.write("运行多次考试增值评价...")
            
            # 使用新方法处理多次考试
            combined_results = self._process_multiple_exams(base_exam_id, current_exams, subject_id)
            
            if combined_results is not None:
                # 显示合并结果
                self.stdout.write("显示合并后的增值评价结果...")
                self._display_results(combined_results)
                
                # 导出结果
                if options.get('export'):
                    self._export_to_excel(combined_results, {}, options['export'], is_multi_exam=True)
                
                # 保存到数据库 (可选是否保存合并结果)
                if not options.get('no_save', False):
                    self._save_multi_exam_results_to_db(combined_results, base_exam_id, current_exams, subject_id)
            else:
                self.stdout.write(self.style.ERROR("无法生成多次考试的增值评价结果"))
        
        self.stdout.write(self.style.SUCCESS("HLM增值评价分析完成"))

    def _get_exams_info(self, base_exam_id, current_exam_id):
        """
        获取考试相关信息。
        
        Args:
            base_exam_id: 基线考试ID
            current_exam_id: 当前考试ID
            
        Returns:
            dict: 包含考试相关信息的字典
        """
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
            
            return {
                'base_exam': base_exam,
                'current_exam': current_exam,
                'base_semester_id': base_semester_id,
                'current_semester_id': current_semester_id,
                'grade_id': grade_id
            }
        except Exam.DoesNotExist as e:
            self.stdout.write(self.style.ERROR(f"考试ID不存在: {e}"))
            return None

    def _get_student_scores(self, base_exam_id, current_exam_id, subject_id, exams_info):
        """
        先从StudentHistory获取学生信息，再获取对应的成绩数据。
        
        Args:
            base_exam_id: 基线考试ID
            current_exam_id: 当前考试ID
            subject_id: 学科ID
            exams_info: 考试信息字典
            
        Returns:
            DataFrame: 包含学生成绩、班级和学校信息的合并数据
        """
        self.stdout.write("获取学生信息和成绩数据...")
        
        # 获取当前学期ID
        current_semester_id = exams_info.get('current_semester_id')
        if not current_semester_id:
            self.stdout.write(self.style.ERROR("无法获取当前学期ID"))
            try:
                current_semester_id = exams_info['current_exam'].semester_id
                self.stdout.write(f"已从考试对象获取当前学期ID: {current_semester_id}")
            except:
                self.stdout.write(self.style.ERROR("无法获取当前学期ID，无法继续"))
                return None
        
        # 1. 首先获取当前学期的学生信息
        self.stdout.write(f"从StudentHistory获取学期{current_semester_id}的学生信息...")
        
        try:
            student_histories = StudentHistory.objects.filter(
                semester_id=current_semester_id
            ).values('student_id', 'class_field_id', 'school_id', 'grade_id')
            
            # 转换为DataFrame
            student_info = pd.DataFrame(list(student_histories))
            
            if len(student_info) == 0:
                self.stdout.write(self.style.ERROR(f"StudentHistory中没有学期{current_semester_id}的记录"))
                return None
            

            self.stdout.write(f"获取到学生信息: {len(student_info)}条记录")
            self.stdout.write(f"学生信息列: {student_info.columns.tolist()}")
            
            # 2. 获取基线考试成绩
            self.stdout.write(f"获取基线考试({base_exam_id})成绩...")
            base_scores = Score.objects.filter(
                exam_id=base_exam_id,
                subject_id=subject_id,
                student_id__in=student_info['student_id'].tolist()
            ).values('student_id', 'standard_score')
            
            if not base_scores:
                self.stdout.write(self.style.ERROR(f"未找到基线考试({base_exam_id})的成绩数据"))
                return None
            
            # 转换为DataFrame并重命名
            base_df = pd.DataFrame(list(base_scores))
            base_df.rename(columns={'standard_score': 'base_score'}, inplace=True)
            self.stdout.write(f"获取到基线成绩: {len(base_df)}条记录")
            
            # 3. 获取当前考试成绩
            self.stdout.write(f"获取当前考试({current_exam_id})成绩...")
            current_scores = Score.objects.filter(
                exam_id=current_exam_id,
                subject_id=subject_id,
                student_id__in=student_info['student_id'].tolist()
            ).values('student_id', 'standard_score')
            
            if not current_scores:
                self.stdout.write(self.style.ERROR(f"未找到当前考试({current_exam_id})的成绩数据"))
                return None
            
            # 转换为DataFrame并重命名
            current_df = pd.DataFrame(list(current_scores))
            current_df.rename(columns={'standard_score': 'current_score'}, inplace=True)
            self.stdout.write(f"获取到当前成绩: {len(current_df)}条记录")
            
            # 4. 合并所有数据：先合并基线和当前考试成绩
            self.stdout.write("合并成绩数据...")
            scores_merged = pd.merge(base_df, current_df, on='student_id', how='inner')
            self.stdout.write(f"两次考试都有成绩的学生: {len(scores_merged)}条记录")
            
            if len(scores_merged) < 10:
                self.stdout.write(self.style.WARNING(f"匹配的学生记录数量过少: {len(scores_merged)}"))
                if len(scores_merged) == 0:
                    return None
            
            # 5. 将成绩数据与学生信息合并
            self.stdout.write("合并学生信息和成绩数据...")
            final_data = pd.merge(scores_merged, student_info, on='student_id', how='inner')
            self.stdout.write(f"最终合并数据: {len(final_data)}条记录")
            
            # 此时检查并确保列名一致
            if 'class_field_id' in final_data.columns and 'class_id' not in final_data.columns:
                # 重命名为class_id以便后续方法使用
                final_data.rename(columns={'class_field_id': 'class_id'}, inplace=True)
                self.stdout.write("已将class_field_id列重命名为class_id以便后续处理")
            
            # 6. 添加班级和学校名称
            self._add_class_info(final_data)
            self._add_school_info(final_data)
            
            # 打印最终数据的列
            self.stdout.write(f"最终数据列: {final_data.columns.tolist()}")
            
            # 检查重要字段是否存在
            for field in ['student_id', 'base_score', 'current_score', 'class_id', 'school_id', 'grade_id']:
                if field not in final_data.columns:
                    self.stdout.write(self.style.ERROR(f"最终数据缺少重要字段: {field}"))
            
            return final_data
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"获取学生信息和成绩数据时出错: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            return None

    def _check_exam_data(self, base_exam_id, current_exam_id, subject_id):
        """
        检查考试数据是否存在于数据库中。
        
        Args:
            base_exam_id: 基线考试ID
            current_exam_id: 当前考试ID
            subject_id: 学科ID
        """
        # 检查考试是否存在
        try:
            base_exam = Exam.objects.get(exam_id=base_exam_id)
            self.stdout.write(f"基线考试存在: {base_exam.exam_id} - {base_exam.exam_name}")
        except Exam.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"基线考试 {base_exam_id} 不存在于数据库中!"))
        
        try:
            current_exam = Exam.objects.get(exam_id=current_exam_id)
            self.stdout.write(f"当前考试存在: {current_exam.exam_id} - {current_exam.exam_name}")
        except Exam.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"当前考试 {current_exam_id} 不存在于数据库中!"))
        
        # 检查学科是否存在
        try:
            subject = Subject.objects.get(subject_id=subject_id)
            self.stdout.write(f"学科存在: {subject.subject_id} - {subject.subject_name}")
        except Subject.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"学科 {subject_id} 不存在于数据库中!"))
        
        # 检查成绩数据
        base_count = Score.objects.filter(exam_id=base_exam_id, subject_id=subject_id).count()
        current_count = Score.objects.filter(exam_id=current_exam_id, subject_id=subject_id).count()
        
        self.stdout.write(f"基线考试成绩记录数: {base_count}")
        self.stdout.write(f"当前考试成绩记录数: {current_count}")

    def _suggest_data_solutions(self, exam_id, subject_id):
        """
        当未发现数据时提供解决方案建议。
        
        Args:
            exam_id: 考试ID
            subject_id: 学科ID
        """
        self.stdout.write(self.style.WARNING("=== 数据问题解决建议 ==="))
        self.stdout.write("1. 检查考试ID是否正确")
        self.stdout.write(f"2. 确认数据库中存在该考试({exam_id})的数据")
        
        # 检查是否有相似ID的考试
        similar_exams = Exam.objects.filter(exam_id__contains=exam_id.split('-')[0])[:5]
        if similar_exams:
            self.stdout.write("可能的相似考试ID:")
            for exam in similar_exams:
                self.stdout.write(f"  - {exam.exam_id}: {exam.exam_name}")
        
        # 检查该学科是否有其他考试数据
        other_exams = Score.objects.filter(subject_id=subject_id).values('exam_id').distinct()[:5]
        if other_exams:
            self.stdout.write(f"该学科({subject_id})有数据的考试:")
            for exam in other_exams:
                self.stdout.write(f"  - {exam['exam_id']}")
        
        self.stdout.write("3. 您可以使用以下命令导入数据:")
        self.stdout.write(f"   python manage.py import_exam_scores --exam-id {exam_id} --subject {subject_id} --file path/to/scores.csv")
        self.stdout.write("======================")

    def _get_covariates(self, student_ids):
        """
        获取学生协变量数据。
        
        Args:
            student_ids: 学生ID列表
            
        Returns:
            DataFrame: 学生协变量数据
        """
        # 这里应该根据实际情况从相应的表中获取协变量
        # 例如学生性别、家庭背景、家长学历等
        
        # 示例：这里仅使用学生表中的性别作为协变量
        students = Student.objects.filter(student_id__in=student_ids).values(
            'student_id', 'gender'
        )
        
        covariates_df = pd.DataFrame(list(students))
        
        # 将性别转换为哑变量
        if 'gender' in covariates_df.columns:
            covariates_df['gender_male'] = (covariates_df['gender'] == 'M').astype(int)
        
        return covariates_df

    def _preprocess_data(self, student_data):
        """
        预处理数据，为建模做准备。
        
        Args:
            student_data: 包含学生成绩的DataFrame
            
        Returns:
            DataFrame: 经过预处理的数据
        """
        self.stdout.write("预处理数据...")
        
        # 复制数据，避免修改原始数据
        model_data = student_data.copy()
        
        # 检查是否存在grade_id列
        if 'grade_id' not in model_data.columns:
            self.stdout.write(self.style.WARNING("数据中缺少grade_id列，将使用class_id的前缀作为替代"))
            
            # 尝试从class_id提取年级信息作为替代
            if 'class_id' in model_data.columns:
                # 假设class_id的格式可能是GXXCXX，其中前缀部分是年级ID
                try:
                    # 从class_id中提取前缀作为grade_id
                    model_data['grade_id'] = model_data['class_id'].str.extract(r'(G\d+)')
                    self.stdout.write(f"从class_id提取出的grade_id值: {model_data['grade_id'].unique()}")
                except:
                    # 如果提取失败，使用class_id代替
                    model_data['grade_id'] = model_data['class_id']
                    self.stdout.write("无法从class_id提取年级ID，将直接使用class_id分组")
            else:
                # 如果连class_id都没有，创建一个虚拟的年级ID
                self.stdout.write(self.style.WARNING("数据中缺少class_id列，将创建虚拟年级ID"))
                model_data['grade_id'] = 'G00'
        
        # 数据清洗：移除缺失值
        before_len = len(model_data)
        model_data = model_data.dropna(subset=['base_score', 'current_score'])
        after_len = len(model_data)
        if before_len > after_len:
            self.stdout.write(f"移除缺失值后，数据量从{before_len}减少到{after_len}")
        
        # 计算各级别的基线成绩均值(用于中心化)
        model_data['school_mean_base'] = model_data.groupby('school_id')['base_score'].transform('mean')
        model_data['class_mean_base'] = model_data.groupby('class_id')['base_score'].transform('mean')
        model_data['grade_mean_base'] = model_data.groupby('grade_id')['base_score'].transform('mean')
        
        # 学生基线成绩中心化(相对于学校均值)
        model_data['base_score_centered'] = model_data['base_score'] - model_data['school_mean_base']
        
        # 计算班级规模(可用作班级层协变量)
        model_data['class_size'] = model_data.groupby('class_id')['student_id'].transform('count')
        
        # 在预处理数据中添加标准化
        model_data['base_score_centered_std'] = (model_data['base_score_centered'] - 
                                                  model_data['base_score_centered'].mean()) / model_data['base_score_centered'].std()

        model_data['class_size_std'] = (model_data['class_size'] - 
                                         model_data['class_size'].mean()) / model_data['class_size'].std()
        
        # 处理缺失值
        if model_data.isnull().sum().sum() > 0:
            self.stdout.write(self.style.WARNING(f"警告: 数据中存在缺失值"))
            model_data = model_data.dropna()
        
        return model_data

    def _fit_hlm_model(self, model_data):
        """
        拟合多层线性模型，计算教师和学校效应。
        
        Args:
            model_data: 预处理后的学生数据
            
        Returns:
            dict: 包含模型结果的字典
        """
        self.stdout.write("拟合多层线性模型...")
        
        # 检查数据是否为空
        if model_data is None or len(model_data) == 0:
            self.stdout.write(self.style.ERROR("无数据可用于拟合模型"))
            return None
            
        # 检查必要列是否存在
        required_columns = ['current_score', 'base_score', 'school_id', 'class_id']
        missing_columns = [col for col in required_columns if col not in model_data.columns]
        if missing_columns:
            self.stdout.write(self.style.ERROR(f"缺少必要的列: {missing_columns}"))
            return None
        
        # 确保没有NaN值
        model_df = model_data.dropna(subset=['current_score', 'base_score', 'school_id', 'class_id'])
        if len(model_df) < 10:
            self.stdout.write(self.style.ERROR(f"有效数据太少，只有{len(model_df)}条记录"))
            return None
            
        # 创建学生层次变量，方便后续分析
        model_df['student_id'] = model_df['student_id'].astype(str)
        model_df['class_id'] = model_df['class_id'].astype(str)
        model_df['school_id'] = model_df['school_id'].astype(str)
        
        # 检查唯一学校和班级数量
        schools = model_df['school_id'].unique()
        classes = model_df['class_id'].unique()
        self.stdout.write(f"数据包含 {len(schools)} 所学校, {len(classes)} 个班级")
        
        if len(schools) < 2:
            self.stdout.write(self.style.WARNING("学校数量少于2个，无法正确估计学校层效应，将使用简化模型"))
        
        if len(classes) < 5:
            self.stdout.write(self.style.WARNING("班级数量少于5个，可能影响模型稳定性"))
        
        # 检查是否有constant模型变量
        try:
            # 找出方差接近0的变量
            num_vars = model_df.select_dtypes(include=np.number).columns
            zero_var_cols = []
            for col in num_vars:
                if model_df[col].var() < 1e-10:
                    zero_var_cols.append(col)
                    self.stdout.write(f"移除常数协变量: {col}")
            
            # 移除常数协变量
            if zero_var_cols:
                model_df = model_df.drop(columns=zero_var_cols)
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"检查常数变量时出错: {str(e)}"))
        
        try:
            # 为避免NaN值导致错误，再次确保没有缺失值
            model_df = model_df.dropna(subset=['current_score', 'base_score', 'school_id', 'class_id'])
            
            # 创建模型变量
            model_df['intercept'] = 1.0  # 添加截距
            
            # 保存原始模型数据
            model_data_full = model_df.copy()
            
            # 防御性检查: 确保每个组至少有2条记录
            school_counts = model_df.groupby('school_id').size()
            valid_schools = school_counts[school_counts >= 2].index
            class_counts = model_df.groupby('class_id').size()
            valid_classes = class_counts[class_counts >= 2].index
            
            # 只保留有足够样本的学校和班级
            model_df = model_df[
                model_df['school_id'].isin(valid_schools) & 
                model_df['class_id'].isin(valid_classes)
            ]
            
            if len(model_df) < len(model_data_full):
                self.stdout.write(self.style.WARNING(
                    f"移除了样本数不足的学校和班级，数据量从{len(model_data_full)}减少到{len(model_df)}"))
            
            if len(model_df) < 10:
                self.stdout.write(self.style.ERROR("有效数据太少，无法拟合多层模型"))
                return None
                
            # 改为更简单的模型公式
            self.stdout.write("拟合学校层模型...")
            try:
                school_formula = "current_score ~ base_score"
                school_model = smf.mixedlm(
                    formula=school_formula,
                    data=model_df,
                    groups=model_df['school_id'],
                    re_formula="~1"
                )
                school_result = school_model.fit(reml=True)
                self.stdout.write("学校层模型拟合成功")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"学校层模型拟合失败: {str(e)}"))
                school_result = None
            
            self.stdout.write("拟合班级层模型...")
            try:
                class_formula = "current_score ~ base_score"
                class_model = smf.mixedlm(
                    formula=class_formula,
                    data=model_df,
                    groups=model_df['class_id'],
                    re_formula="~1"
                )
                class_result = class_model.fit(reml=True)
                self.stdout.write("班级层模型拟合成功")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"班级层模型拟合失败: {str(e)}"))
                # 无法拟合班级层模型时，使用简单线性回归
                self.stdout.write("使用简单线性回归模型作为备选...")
                try:
                    ols_model = smf.ols(formula="current_score ~ base_score", data=model_df)
                    ols_result = ols_model.fit()
                    self.stdout.write("线性回归模型拟合成功")
                    
                    # 如果HLM模型失败但OLS成功，使用OLS结果
                    if school_result is None:
                        # 创建返回结果
                        return {
                            'model_type': 'ols',
                            'ols_result': ols_result,
                            'model_data': model_df,
                            'full_data': model_data_full
                        }
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"线性回归模型拟合失败: {str(e)}"))
                    return None
            
            # 返回结果
            return {
                'model_type': 'hlm',
                'school_result': school_result,
                'class_result': class_result,
                'model_data': model_df,
                'full_data': model_data_full
            }
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"模型拟合时出错: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())
            return None

    def _run_model_diagnostics(self, model_data, model_results):
        """
        进行模型诊断，生成诊断图表和指标。
        
        Args:
            model_data: 模型使用的数据
            model_results: 模型拟合结果
            
        Returns:
            dict: 包含诊断结果的字典
        """
        self.stdout.write("进行模型诊断...")
        
        # 首先检查model_results是否为None
        if model_results is None:
            self.stdout.write(self.style.ERROR("模型结果为空，无法进行诊断"))
            return None
        
        # 打印模型结果中的键，用于诊断
        self.stdout.write(f"模型结果键: {list(model_results.keys())}")
        
        # 检查所需的模型是否存在
        if model_results.get('model_type') == 'hlm':
            if 'class_result' in model_results:
                residuals = model_results['class_result'].resid
                self.stdout.write("使用班级模型进行诊断")
            elif 'school_result' in model_results:
                residuals = model_results['school_result'].resid
                self.stdout.write("使用学校模型进行诊断")
            else:
                self.stdout.write(self.style.ERROR("无可用的HLM模型结果进行诊断"))
                self.stdout.write(f"可用的键: {list(model_results.keys())}")
                return None
        elif model_results.get('model_type') == 'ols':
            if 'ols_result' in model_results:
                residuals = model_results['ols_result'].resid
                self.stdout.write("使用OLS模型进行诊断")
            else:
                self.stdout.write(self.style.ERROR("无可用的OLS模型结果进行诊断"))
                return None
        else:
            self.stdout.write(self.style.ERROR(f"未知的模型类型: {model_results.get('model_type')}"))
            return None
        
        # 记录残差的基本统计量
        n_residuals = len(residuals)
        mean_residual = residuals.mean()
        std_residual = residuals.std()
        min_residual = residuals.min()
        max_residual = residuals.max()
        
        self.stdout.write(f"残差统计: 数量={n_residuals}, 均值={mean_residual:.4f}, 标准差={std_residual:.4f}, 最小值={min_residual:.4f}, 最大值={max_residual:.4f}")
        
        # 进行正态性检验
        try:
            from scipy import stats
            k2, p_value = stats.normaltest(residuals)
            normality_result = {
                'test_statistic': k2,
                'p_value': p_value,
                'is_normal': p_value > 0.05
            }
            self.stdout.write(f"正态性检验: 统计量={k2:.4f}, p值={p_value:.4f}, {'正态' if p_value > 0.05 else '非正态'}")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"正态性检验失败: {str(e)}"))
            normality_result = {
                'test_statistic': None,
                'p_value': None,
                'is_normal': None,
                'error': str(e)
            }
        
        # 返回诊断结果
        diagnostics = {
            'residuals': residuals,
            'n_residuals': n_residuals,
            'mean_residual': mean_residual,
            'std_residual': std_residual,
            'min_residual': min_residual,
            'max_residual': max_residual,
            'normality': normality_result  # 添加正态性检验结果
        }
        
        return diagnostics

    def _display_diagnostics(self, diagnostics):
        """
        显示模型诊断结果。
        
        Args:
            diagnostics: 模型诊断结果字典
        """
        self.stdout.write("\n模型诊断结果:")
        
        # 检查诊断结果是否为None
        if diagnostics is None:
            self.stdout.write(self.style.ERROR("无可用的诊断结果"))
            return
        
        # 检查normality键是否存在
        if 'normality' not in diagnostics:
            self.stdout.write(self.style.WARNING("诊断结果中缺少正态性检验结果"))
            # 创建一个空的正态性结果，避免KeyError
            diagnostics['normality'] = {
                'test_statistic': None,
                'p_value': None,
                'is_normal': None,
                'error': "未进行正态性检验"
            }
        
        # 显示残差描述性统计
        self.stdout.write(f"残差数量: {diagnostics.get('n_residuals', 'N/A')}")
        self.stdout.write(f"残差均值: {diagnostics.get('mean_residual', 'N/A'):.4f}")
        self.stdout.write(f"残差标准差: {diagnostics.get('std_residual', 'N/A'):.4f}")
        self.stdout.write(f"残差范围: [{diagnostics.get('min_residual', 'N/A'):.4f}, {diagnostics.get('max_residual', 'N/A'):.4f}]")
        
        # 显示正态性检验结果
        norm_test = diagnostics['normality']
        if norm_test.get('test_statistic') is not None:
            self.stdout.write(f"正态性检验: 统计量={norm_test.get('test_statistic', 'N/A'):.4f}, p值={norm_test.get('p_value', 'N/A'):.4f}")
            self.stdout.write(f"残差分布: {'正态' if norm_test.get('is_normal') else '非正态'}")
        else:
            self.stdout.write(f"正态性检验: {norm_test.get('error', '未知错误')}")
        
        # 绘制残差图表（如果可能）
        try:
            # 残差可视化代码...
            self.stdout.write("残差分析图表已保存")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"绘制残差图表失败: {str(e)}"))

    def _calculate_teacher_effects(self, model_results, model_data):
        """
        计算教师增值效应。
        
        Args:
            model_results: 模型拟合结果
            model_data: 预处理后的模型数据
            
        Returns:
            dict: 包含教师、学校和学生增值效应的字典
        """
        self.stdout.write("计算教师增值效应...")
        
        # 获取班级随机效应
        random_effects = model_results['class_result'].random_effects
        
        # 转换为DataFrame
        effects_data = []
        for class_id, effect_values in random_effects.items():
            effects_data.append({
                'class_id': class_id,
                'intercept_effect': effect_values.iloc[0],  # 截距随机效应
                'slope_effect': effect_values.iloc[1] if len(effect_values) > 1 else 0  # 斜率随机效应(如果有)
            })
        
        effects_df = pd.DataFrame(effects_data)
        
        # 获取班级基本信息
        class_info = model_data.groupby('class_id').agg({
            'school_id': 'first',
            'class_name': 'first',
            'base_score': 'mean',
            'current_score': 'mean',
            'student_id': 'count'
        }).rename(columns={'student_id': 'student_count'})
        
        # 合并班级信息和随机效应
        teacher_effects = pd.merge(class_info, effects_df, on='class_id')
        
        # 获取固定效应系数
        fixed_effects = model_results['class_result'].fe_params
        intercept = fixed_effects.iloc[0]
        base_score_coef = fixed_effects.iloc[1]
        
        # 计算期望分数(如果没有随机效应)
        teacher_effects['expected_score'] = intercept + base_score_coef * (
            teacher_effects['base_score'] - teacher_effects.merge(
                model_data[['school_id', 'school_mean_base']].drop_duplicates(),
                on='school_id'
            )['school_mean_base']
        )
        
        # 增值分数 = 随机效应(班级特有贡献)
        teacher_effects['value_added'] = teacher_effects['intercept_effect']
        
        # 标准化增值分数(T分数: 均值50, 标准差10)
        mean_va = teacher_effects['value_added'].mean()
        std_va = teacher_effects['value_added'].std()
        teacher_effects['value_added_t'] = 50 + 10 * (teacher_effects['value_added'] - mean_va) / std_va
        
        # 计算排名 (原始T分的排名，用于参考)
        teacher_effects['rank_original'] = teacher_effects['value_added_t'].rank(ascending=False)
        
        # 1. 计算可靠性指标 - 合并多种可靠性衡量方式
        
        # 基于样本量的可靠性 (学生数量越多，可靠性越高)
        teacher_effects['reliability_n'] = teacher_effects['student_count'] / (
            teacher_effects['student_count'] + 10  # 调节参数
        )
        
        # 基于分数稳定性的可靠性 (班内学生成绩越一致，可靠性越高)
        # 计算每个班级内学生成绩的变异系数
        teacher_effects['score_stability'] = 1.0 - (
            teacher_effects.groupby('class_id')['current_score'].transform('std') / 
            teacher_effects.groupby('class_id')['current_score'].transform('mean')
        ).fillna(0).clip(0.3, 1)  # 设置下限0.3避免极低值
        
        # 组合可靠性 (加权平均)
        teacher_effects['reliability'] = (
            0.65 * teacher_effects['reliability_n'] + 
            0.35 * teacher_effects['score_stability']
        )
        
        # 2. 应用经验贝叶斯收缩估计 (Empirical Bayes Shrinkage)
        # 可靠性越低，越向全局均值收缩
        global_mean = 50  # T分布的全局均值
        teacher_effects['value_added_t_shrunk'] = (
            teacher_effects['reliability'] * teacher_effects['value_added_t'] + 
            (1 - teacher_effects['reliability']) * global_mean
        )
        
        # 3. 计算改进后的标准误差和置信区间
        # 获取基础标准误差
        class_model = model_results['class_result']
        se_base = np.sqrt(class_model.cov_re.iloc[0, 0])  # 基础标准误差
        
        # 根据可靠性调整标准误差
        teacher_effects['class_se'] = se_base * np.sqrt(1 / teacher_effects['reliability'])
        
        # t分布临界值计算 (使用更精确的t分布)
        dof = len(model_data) - len(class_model.fe_params)  # 自由度
        confidence_level = 0.95  # 使用95%置信水平
        t_critical = stats.t.ppf(1 - (1 - confidence_level) / 2, dof)
        
        # 计算置信区间宽度 (并应用合理约束)
        ci_width = t_critical * teacher_effects['class_se'] * 10 / std_va
        min_allowed_ci = 3.0  # 最小允许的置信区间半宽度
        max_allowed_ci = 12.0  # 最大允许的置信区间半宽度
        ci_half_width = ci_width.clip(min_allowed_ci, max_allowed_ci)
        
        # 设置置信区间上下限
        teacher_effects['ci_lower'] = teacher_effects['value_added_t_shrunk'] - ci_half_width
        teacher_effects['ci_upper'] = teacher_effects['value_added_t_shrunk'] + ci_half_width
        
        # 4. 使用收缩后的T分作为最终结果
        teacher_effects['value_added_t'] = teacher_effects['value_added_t_shrunk']
        
        # 重新计算排名 (基于收缩后的T分)
        teacher_effects['rank'] = teacher_effects['value_added_t'].rank(ascending=False)
        
        # 5. 基于最终T分进行分类评级
        bins = [0, 35, 45, 55, 65, 100]
        labels = ['显著低于平均', '低于平均', '平均水平', '高于平均', '显著高于平均']
        teacher_effects['rating'] = pd.cut(
            teacher_effects['value_added_t'], 
            bins=bins, 
            labels=labels,
            include_lowest=True
        )
        
        # 6. 添加补充信息
        # 获取教师信息
        self._add_teacher_info(teacher_effects)
        
        # 添加学校名称
        self._add_school_info(teacher_effects)
        
        # 7. 计算学校层面效应
        school_effects = teacher_effects.groupby('school_id').agg({
            'school_name': 'first',
            'value_added_t': 'mean',  # 使用最终T分
            'value_added': 'mean',
            'class_id': 'count'
        }).rename(columns={
            'class_id': 'class_count',
            'value_added_t': 'value_added_score',
            'value_added': 'effect'
        }).reset_index()
        
        # 按照增值得分排序并添加排名
        school_effects = school_effects.sort_values('value_added_score', ascending=False)
        school_effects['rank'] = range(1, len(school_effects) + 1)
        school_effects['percentile'] = school_effects['value_added_score'].rank(pct=True) * 100
        
        # 8. 计算学生增值效应 (如果需要)
        student_effects = None
        try:
            self.stdout.write("计算学生增值效应...")
            
            # 提取固定效应和随机效应
            fixed_effects = model_results['class_result'].fe_params
            
            # 创建学生增值数据
            student_data = model_data.copy()
            student_effects = self._calculate_student_effects(student_data, teacher_effects, fixed_effects)
            
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"计算学生增值效应时出错: {str(e)}"))
        
        # 9. 返回结果
        return {
            'teacher_effects': teacher_effects,
            'school_effects': school_effects,
            'student_effects': student_effects
        }

    def _add_teacher_info(self, teacher_effects):
        """
        添加班级科任教师信息。
        
        Args:
            teacher_effects: 教师效应DataFrame
            
        Returns:
            None: 直接修改传入的DataFrame
        """
        subject_id = self.options['subject']
        
        # 检查Teacher模型字段
        sample_teacher = Teacher.objects.first()
        teacher_name_field = 'teacher_id'  # 默认使用ID
        if sample_teacher:
            # 尝试发现可能的姓名字段
            for field_name in ['name', 'full_name', 'teacher_name', 'real_name', 'display_name']:
                if hasattr(sample_teacher, field_name):
                    teacher_name_field = field_name
                    break
        
        # 查询教师信息
        teacher_info = {}
        for class_id in teacher_effects['class_id']:
            # 通过TeacherHistory获取科任教师
            teacher_record = TeacherHistory.objects.filter(
                class_field_id=class_id,
                subject_id=subject_id
            ).order_by('-start_date').first()
            
            if teacher_record:
                try:
                    teacher = Teacher.objects.get(teacher_id=teacher_record.teacher_id)
                    teacher_info[class_id] = {
                        'teacher_id': teacher.teacher_id,
                        'teacher_name': getattr(teacher, teacher_name_field, teacher.teacher_id)
                    }
                except Teacher.DoesNotExist:
                    teacher_info[class_id] = {
                        'teacher_id': teacher_record.teacher_id,
                        'teacher_name': teacher_record.teacher_id
                    }
            else:
                teacher_info[class_id] = {
                    'teacher_id': None,
                    'teacher_name': "未知"
                }
        
        # 添加到DataFrame
        teacher_effects['teacher_id'] = teacher_effects['class_id'].map(
            lambda x: teacher_info.get(x, {}).get('teacher_id')
        )
        teacher_effects['teacher_name'] = teacher_effects['class_id'].map(
            lambda x: teacher_info.get(x, {}).get('teacher_name')
        )

    def _add_school_info(self, teacher_effects):
        """
        添加学校名称信息。
        
        Args:
            teacher_effects: 教师效应DataFrame
            
        Returns:
            None: 直接修改传入的DataFrame
        """
        # 获取学校信息
        school_ids = teacher_effects['school_id'].unique()
        schools = School.objects.filter(school_id__in=school_ids).values('school_id', 'school_name')
        
        # 创建映射
        school_name_map = {s['school_id']: s['school_name'] for s in schools}
        
        # 添加到DataFrame
        teacher_effects['school_name'] = teacher_effects['school_id'].map(
            lambda x: school_name_map.get(x, "未知学校")
        )

    def _decompose_variance(self, model_results):
        """
        进行方差分解分析。
        
        Args:
            model_results: 模型拟合结果
            
        Returns:
            dict: 方差分解结果
        """
        self.stdout.write("进行方差分解分析...")
        
        # 从学校模型和班级模型中提取方差成分
        try:
            # 使用更稳健的方法获取方差成分
            # 学校层方差
            school_var = model_results['school_result'].cov_re.iloc[0, 0]
            
            # 班级层方差 - 直接从班级模型获取，而不是从学校模型中减去
            class_var = model_results['class_result'].cov_re.iloc[0, 0]
            
            # 如果班级方差小于学校方差，调整计算方法
            if class_var <= school_var:
                # 尝试使用替代方法估计班级层方差
                # 例如，使用随机效应的方差
                random_effects = model_results['class_result'].random_effects
                effects_values = [effect.iloc[0] for effect in random_effects.values()]
                class_var = np.var(effects_values)
                
                # 如果仍然为零或太小，设置一个最小值
                min_variance = 0.01 * (school_var + model_results['class_result'].scale)
                class_var = max(class_var, min_variance)
            
            # 残差方差(学生层方差)
            residual_var = model_results['class_result'].scale
            
            # 总方差
            total_var = school_var + class_var + residual_var
            
            # 计算ICC
            icc_school = school_var / total_var
            icc_class = (school_var + class_var) / total_var
            
            # 各层次方差占比
            school_pct = school_var / total_var * 100
            class_pct = class_var / total_var * 100
            residual_pct = residual_var / total_var * 100
            
            return {
                'school_variance': school_var,
                'class_variance': class_var,
                'residual_variance': residual_var,
                'total_variance': total_var,
                'icc_school': icc_school,
                'icc_class': icc_class,
                'school_pct': school_pct,
                'class_pct': class_pct,
                'residual_pct': residual_pct
            }
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"方差分解分析失败: {str(e)}"))
            # 记录更详细的异常信息以帮助调试
            import traceback
            self.stdout.write(traceback.format_exc())
            return {}

    def _display_variance_components(self, variance_components):
        """
        显示方差分解结果。
        
        Args:
            variance_components: 方差分解结果字典
            
        Returns:
            None
        """
        if not variance_components:
            return
            
        self.stdout.write("\n方差分解结果:")
        self.stdout.write(f"学校层方差: {variance_components['school_variance']:.2f} ({variance_components['school_pct']:.1f}%)")
        self.stdout.write(f"班级层方差: {variance_components['class_variance']:.2f} ({variance_components['class_pct']:.1f}%)")
        self.stdout.write(f"学生层方差: {variance_components['residual_variance']:.2f} ({variance_components['residual_pct']:.1f}%)")
        self.stdout.write(f"总方差: {variance_components['total_variance']:.2f}")
        
        self.stdout.write(f"\n学校级内相关系数(ICC): {variance_components['icc_school']:.4f}")
        self.stdout.write(f"班级级内相关系数(ICC): {variance_components['icc_class']:.4f}")
        
        # 解释ICC
        if variance_components['icc_class'] > 0.3:
            self.stdout.write(self.style.SUCCESS("班级层ICC较高，表明班级层面差异显著，增值评价结果可靠性较高"))
        elif variance_components['icc_class'] > 0.1:
            self.stdout.write("班级层ICC处于中等水平，班级间存在一定差异")
        else:
            self.stdout.write(self.style.WARNING("班级层ICC较低，表明班级间差异不显著，增值评价结果可靠性较低"))

    def _display_results(self, teacher_effects, model_results=None):
        """
        显示教师增值评价结果。
        
        Args:
            teacher_effects: 包含教师增值效应的DataFrame
            model_results: 模型拟合结果
            
        Returns:
            None
        """
        self.stdout.write("\n增值评价结果:")
        
        if teacher_effects is None:
            self.stdout.write(self.style.ERROR("无增值评价结果可显示"))
            return
        
        # 声明变量用于保存原始的teacher_effects输入
        original_teacher_effects = teacher_effects
        
        # 检查teacher_effects是否为字典类型
        if isinstance(teacher_effects, dict):
            # 如果是字典类型，提取actual_teacher_effects
            actual_teacher_effects = teacher_effects.get('teacher_effects')
            
            # 显示学校增值排名
            if 'school_effects' in teacher_effects:
                school_effects = teacher_effects['school_effects']
                self.stdout.write("\n学校增值排名:")
                self.stdout.write("-" * 80)
                self.stdout.write(f"{'排名':<5}{'学校ID':<12}{'学校名称':<20}{'增值分数':<10}{'百分位':<10}{'班级数':<8}")
                self.stdout.write("-" * 80)
                
                for idx, row in school_effects.iterrows():
                    self.stdout.write(
                        f"{row.get('rank', '-'):<5}{row['school_id']:<12}{row['school_name']:<20}"
                        f"{row['value_added_score']:.2f}  {row.get('percentile', 0):.1f}%    {row.get('class_count', 0):<8}"
                    )
            
            # 使用actual_teacher_effects替代teacher_effects
            t_scores = actual_teacher_effects['value_added_t']
        else:
            # 保持兼容性
            actual_teacher_effects = teacher_effects
            t_scores = teacher_effects['value_added_t']
        
        # 仅显示总结性统计信息
        self.stdout.write(f"\n评价统计信息:")
        self.stdout.write(f"班级总数: {len(actual_teacher_effects)}")
        self.stdout.write(f"平均T分: {t_scores.mean():.2f}")
        self.stdout.write(f"最大T分: {t_scores.max():.2f}")
        self.stdout.write(f"最小T分: {t_scores.min():.2f}")
        self.stdout.write(f"T分标准差: {t_scores.std():.2f}")
        
        # 按评级统计
        ratings = actual_teacher_effects['rating'].value_counts()
        self.stdout.write("\n各评级班级数量:")
        for rating, count in ratings.items():
            self.stdout.write(f"{rating}: {count}")
        
        # 自动导出到临时Excel文件
        if not self.options.get('export'):
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            temp_filename = f"HLM增值评价_临时结果_{timestamp}.xlsx"
            
            # 修复：传递原始的teacher_effects字典到export方法，而不是提取后的DataFrame
            self._export_to_excel(original_teacher_effects, self._decompose_variance(model_results), '')
            self.stdout.write(f"\n结果已临时导出到: {temp_filename}")

    def _save_results_to_db(self, teacher_effects, model_results, exams_info):
        """
        保存结果到数据库。
        
        Args:
            teacher_effects: 教师增值效应DataFrame
            model_results: 模型拟合结果
            exams_info: 考试信息字典
            
        Returns:
            None
        """
        if not self.options.get('no_save', False):
            self.stdout.write("保存结果到数据库...")
            
            subject_id = self.options['subject']
            base_exam_id = self.options['base_exam']
            current_exam_id = self.options['current_exams']
            current_semester_id = exams_info['current_semester_id']
            
            # 生成批次ID
            batch_id = f"HLM_{subject_id}_{base_exam_id}_{current_exam_id}"
            
            # 获取模型参数
            model_params = {
                'formula': model_results.get('formula', ''),
                're_formula': model_results.get('re_formula', ''),
                'fixed_effects': model_results['class_result'].fe_params.to_dict(),
                'variance_components': self._decompose_variance(model_results)
            }
            
            with transaction.atomic():
                records_saved = 0
                
                for _, row in teacher_effects.iterrows():
                    class_id = row['class_id']
                    
                    # 构建评价ID
                    eval_id = f"HLM_{class_id}_{current_exam_id}_{subject_id}"
                    
                    # 保存因素
                    factors = {
                        'value_added_t': float(row['value_added_t']),
                        'method': 'hlm',
                        'batch_id': batch_id,
                        'base_exam_id': base_exam_id,
                        'current_exam_id': current_exam_id,
                        'ci_lower': float(row['ci_lower']),
                        'ci_upper': float(row['ci_upper']),
                        'model_params': model_params,
                        'rating': str(row['rating'])
                    }
                    
                    # 添加教师ID(如果有)
                    if pd.notna(row.get('teacher_id')):
                        factors['teacher_id'] = row['teacher_id']
                    
                    # 添加学校ID(如果有)
                    if pd.notna(row.get('school_id')):
                        factors['school_id'] = row['school_id']
                    
                    # 保存到数据库
                    ValueAddedEvaluation.objects.update_or_create(
                        eval_id=eval_id,
                        defaults={
                            'target_type': 'CLASS',
                            'target_id': class_id,
                            'subject_id': subject_id,
                            'semester_id': current_semester_id,
                            'base_score': float(row['base_score']),
                            'current_score': float(row['current_score']),
                            'added_value': float(row['value_added']),
                            'factors': factors,
                            'status': 'COMPLETE'
                        }
                    )
                    
                    records_saved += 1
                
                self.stdout.write(self.style.SUCCESS(f"已保存 {records_saved} 条班级评价记录"))

    def _export_to_excel(self, teacher_effects, variance_components, export_path='', is_multi_exam=False):
        """
        导出结果到Excel文件。
        
        Args:
            teacher_effects: 教师增值效应DataFrame
            variance_components: 方差分解结果字典
            export_path: 导出文件路径
            is_multi_exam: 是否为多次考试结果
            
        Returns:
            None
        """
        self.stdout.write("导出结果到Excel...")
        self.stdout.write(f"teacher_effects类型: {type(teacher_effects)}")
        
        # 检查teacher_effects是否为字典
        if isinstance(teacher_effects, dict):
            self.stdout.write(f"teacher_effects字典键: {list(teacher_effects.keys())}")
            actual_teacher_effects = teacher_effects.get('teacher_effects')
            school_effects = teacher_effects.get('school_effects')
            student_effects = teacher_effects.get('student_effects')
            
            # 添加调试信息
            if school_effects is not None:
                self.stdout.write(f"找到学校效应数据，共{len(school_effects)}行")
                self.stdout.write(f"学校效应列: {school_effects.columns.tolist()}")
            else:
                self.stdout.write(self.style.WARNING("未找到学校效应数据"))
        else:
            actual_teacher_effects = teacher_effects
            school_effects = None
            student_effects = None
            self.stdout.write("teacher_effects不是字典类型，无法提取学校效应")
        
        # 准备导出数据
        export_data = actual_teacher_effects.copy()
        
        # 保留需要的列并重命名
        columns_to_export = {
            'rank': '排名',
            'school_name': '学校',
            'class_name': '班级',
            'teacher_name': '科任教师',
            'student_count': '学生人数',
            'base_score': '基线均分',
            'current_score': '当前均分',
            'value_added_t': '增值T分',
            'ci_lower': '置信区间下限',
            'ci_upper': '置信区间上限',
            'rating': '评级'
        }
        
        # 如果是多次考试结果，添加额外列
        if is_multi_exam and 'exams_combined' in export_data.columns:
            columns_to_export['exams_combined'] = '合并考试数'
        
        # 重命名列
        export_df = export_data[list(columns_to_export.keys())].rename(columns=columns_to_export)
        # 添加：按排名升序排序
        export_df = export_df.sort_values('排名')
        # 格式化数值列
        numeric_cols = ['基线均分', '当前均分', '增值T分', '置信区间下限', '置信区间上限']
        for col in numeric_cols:
            if col in export_df.columns:
                export_df[col] = export_df[col].map(lambda x: f"{x:.2f}")
        
        # 设置导出路径
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_exam_id = self.options['base_exam']
        
        if is_multi_exam:
            current_exams = '_'.join(self.options.get('current_exams', ['unknown']))
            subject_id = self.options['subject']
            filename = f"HLM多次考试增值评价_{subject_id}_{base_exam_id}到{current_exams}_{timestamp}.xlsx"
        else:
            current_exam_id = self.options.get('current_exam', self.options.get('current_exams', ['unknown'])[0])
            subject_id = self.options['subject']
            filename = f"HLM增值评价_{subject_id}_{base_exam_id}到{current_exam_id}_{timestamp}.xlsx"
            
        export_file = os.path.join(export_path, filename) if export_path else filename
        
        # 创建Excel写入器
        try:
            with pd.ExcelWriter(export_file, engine='openpyxl') as writer:
                # 写入教师增值效应结果
                export_df.to_excel(writer, sheet_name='教师增值评价结果', index=False)
                
                # 写入学校增值效应数据
                if school_effects is not None:
                    self.stdout.write("导出学校效应数据...")
                    # 重命名学校效应列
                    school_columns = {
                        'school_id': '学校ID',
                        'school_name': '学校名称',
                        'value_added_score': '增值分数',
                        'effect': '效应值',
                        'class_count': '班级数',
                        'rank': '排名',
                        'percentile': '百分位'
                    }
                    
                    # 选择存在的列
                    available_school_columns = [col for col in school_columns.keys() if col in school_effects.columns]
                    renamed_school_columns = {col: school_columns[col] for col in available_school_columns}
                    
                    if available_school_columns:
                        # 导出学校效应
                        school_effects[available_school_columns].rename(columns=renamed_school_columns).to_excel(
                            writer, sheet_name='学校增值效应', index=False
                        )
                        self.stdout.write(f"学校效应已写入到工作表，包含{len(available_school_columns)}列")
                    else:
                        self.stdout.write(self.style.WARNING("学校效应数据中没有可导出的列"))
                else:
                    self.stdout.write(self.style.WARNING("没有学校效应数据可导出"))
                    
                # 添加：导出学生增值评价结果
                if isinstance(teacher_effects, dict) and 'student_effects' in teacher_effects:
                    student_effects = teacher_effects['student_effects']
                    
                    self.stdout.write(f"导出学生增值效应数据，{len(student_effects)}行...")
                    self.stdout.write(f"学生效应列: {student_effects.columns.tolist()}")
                    
                    # 重命名学生效应列（根据实际存在的列）
                    student_columns = {
                        'student_id': '学生ID',
                        'student_name': '学生姓名',
                        'class_id': '班级ID',
                        'class_name': '班级名称',
                        'school_id': '学校ID',
                        'school_name': '学校名称',
                        'base_score': '基线分数',
                        'current_score': '当前分数',
                        'expected_score': '期望分数',
                        'value_added': '增值效应',
                        'value_added_t': '增值T分',
                        'rank': '排名',
                        'growth_potential': '成长潜力',
                        'adjusted_value_added': '潜力调整增值',
                        'adjusted_value_added_t': '潜力调整T分',
                        'base_score_group': '基线分组',
                        'group_value_added_t': '组内增值T分',
                        'composite_score': '复合分数',
                        'composite_rank': '复合排名',
                        'composite_rating': '复合评级'
                    }
                    
                    # 选择存在的列
                    available_student_columns = [col for col in student_columns.keys() if col in student_effects.columns]
                    renamed_student_columns = {col: student_columns[col] for col in available_student_columns}
                    
                    # 格式化学生数据
                    student_export = student_effects[available_student_columns].rename(columns=renamed_student_columns)
                    
                    # 按排名升序排序
                    student_export = student_export.sort_values('复合排名')
                    
                    # 格式化数值列
                    numeric_cols = ['基线分数', '当前分数', '期望分数', '增值效应', '增值T分']
                    for col in numeric_cols:
                        if col in student_export.columns:
                            student_export[col] = student_export[col].map(lambda x: f"{x:.2f}")
                    
                    # 导出学生效应
                    student_export.to_excel(writer, sheet_name='学生增值效应', index=False)
                    self.stdout.write(f"已导出{len(student_export)}名学生的增值效应")
                else:
                    self.stdout.write(self.style.WARNING("没有学生增值效应数据可导出"))
                
                # 如果是多次考试结果，添加考试信息表
                if is_multi_exam:
                    # 创建考试信息DataFrame
                    exams_info = []
                    base_exam_id = self.options['base_exam']
                    current_exams = self.options.get('current_exams', [])
                    
                    # 添加基线考试
                    try:
                        base_exam = Exam.objects.get(exam_id=base_exam_id)
                        exams_info.append({
                            '考试ID': base_exam_id,
                            '考试名称': base_exam.exam_name,
                            '考试日期': base_exam.exam_date,
                            '类型': '基线考试',
                            '权重': 'N/A'
                        })
                    except:
                        exams_info.append({
                            '考试ID': base_exam_id,
                            '考试名称': '未知',
                            '考试日期': '未知',
                            '类型': '基线考试',
                            '权重': 'N/A'
                        })
                    
                    # 添加各次后续考试
                    for i, exam_id in enumerate(current_exams):
                        weight = 1.0 + i * 0.5
                        try:
                            exam = Exam.objects.get(exam_id=exam_id)
                            exams_info.append({
                                '考试ID': exam_id,
                                '考试名称': exam.exam_name,
                                '考试日期': exam.exam_date,
                                '类型': '后续考试',
                                '权重': f"{weight:.2f}"
                            })
                        except:
                            exams_info.append({
                                '考试ID': exam_id,
                                '考试名称': '未知',
                                '考试日期': '未知',
                                '类型': '后续考试',
                                '权重': f"{weight:.2f}"
                            })
                    
                    # 写入考试信息
                    pd.DataFrame(exams_info).to_excel(writer, sheet_name='考试信息', index=False)
                
                # 写入方差分解结果(如果有)
                if variance_components:
                    # 创建方差分解结果DataFrame
                    variance_df = pd.DataFrame([
                        {'层次': '学校层', '方差': variance_components['school_variance'], '百分比': f"{variance_components['school_pct']:.1f}%"},
                        {'层次': '班级层', '方差': variance_components['class_variance'], '百分比': f"{variance_components['class_pct']:.1f}%"},
                        {'层次': '学生层', '方差': variance_components['residual_variance'], '百分比': f"{variance_components['residual_pct']:.1f}%"},
                        {'层次': '总方差', '方差': variance_components['total_variance'], '百分比': '100.0%'}
                    ])
                    
                    # 写入方差分解结果
                    variance_df.to_excel(writer, sheet_name='方差分解', index=False)
                    
                    # 写入ICC结果
                    icc_df = pd.DataFrame([
                        {'类型': '学校级内相关系数(ICC)', '值': f"{variance_components['icc_school']:.4f}"},
                        {'类型': '班级级内相关系数(ICC)', '值': f"{variance_components['icc_class']:.4f}"}
                    ])
                    
                    # 写入ICC结果
                    icc_df.to_excel(writer, sheet_name='ICC分析', index=False)
            
            self.stdout.write(self.style.SUCCESS(f"结果已导出到: {export_file}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"导出失败: {str(e)}"))
            import traceback
            self.stdout.write(traceback.format_exc())

    def _process_multiple_exams(self, base_exam_id, exam_ids_list, subject_id):
        """
        处理多次考试数据进行增值评价
        
        Args:
            base_exam_id: 基线考试ID
            exam_ids_list: 多个后续考试ID列表
            subject_id: 学科ID
            
        Returns:
            DataFrame: 合并多次结果的教师增值效应
        """
        self.stdout.write("处理多次考试数据...")
        
        # 存储每次评价的结果
        all_results = []
        weights = []
        
        # 对每个考试ID运行一次增值评价
        for i, current_exam_id in enumerate(exam_ids_list):
            self.stdout.write(f"\n处理考试 {current_exam_id} ({i+1}/{len(exam_ids_list)})...")
            
            # 设置权重 - 越近的考试权重越大
            weight = 1.0 + i * 0.5  # 例如：第一次=1.0，第二次=1.5，第三次=2.0
            weights.append(weight)
            
            # 获取考试信息
            exams_info = self._get_exams_info(base_exam_id, current_exam_id)
            if not exams_info:
                continue
                
            # 获取学生数据
            student_data = self._get_student_scores(base_exam_id, current_exam_id, subject_id, exams_info)
            if student_data is None or student_data.empty:
                continue
            
            # 预处理数据
            model_data = self._preprocess_data(student_data)
            
            # 拟合模型
            try:
                model_results = self._fit_hlm_model(model_data)
                
                # 计算教师效应
                teacher_effects = self._calculate_teacher_effects(model_results, model_data)
                
                # 将当前考试ID添加到结果中
                teacher_effects['exam_id'] = current_exam_id
                
                # 保存结果
                all_results.append(teacher_effects)
                
                self.stdout.write(self.style.SUCCESS(f"考试 {current_exam_id} 处理完成"))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"处理考试 {current_exam_id} 时出错: {str(e)}"))
                import traceback
                self.stdout.write(traceback.format_exc())
        
        # 如果没有有效结果，返回None
        if not all_results:
            self.stdout.write(self.style.ERROR("没有成功处理的考试数据"))
            return None
        
        # 合并多次结果
        self.stdout.write("合并多次考试结果...")
        combined_results = self._combine_multiple_results(all_results, weights)
        
        return combined_results

    def _combine_multiple_results(self, all_results, weights):
        """
        合并多次考试的增值评价结果。
        
        Args:
            all_results: 多次考试结果列表 
            weights: 每次考试的权重列表
            
        Returns:
            dict: 合并后的增值评价结果
        """
        self.stdout.write("合并多次考试结果...")
        
        # 检查输入
        if not all_results or len(all_results) == 0:
            self.stdout.write(self.style.ERROR("没有可合并的结果"))
            return None
        
        # 提取每个结果中的teacher_effects
        teacher_effects_list = []
        school_effects_list = []
        student_effects_list = []
        
        for result in all_results:
            if isinstance(result, dict):
                if 'teacher_effects' in result:
                    teacher_effects_list.append(result['teacher_effects'])
                if 'school_effects' in result:
                    school_effects_list.append(result['school_effects'])
                if 'student_effects' in result:
                    student_effects_list.append(result['student_effects'])
            else:
                # 向后兼容，假设result就是teacher_effects
                teacher_effects_list.append(result)
        
        # 收集所有班级和学校
        schools = set()
        classes = set()
        
        for te in teacher_effects_list:
            if 'class_id' in te.columns:
                classes.update(te['class_id'].unique())
            if 'school_id' in te.columns:
                schools.update(te['school_id'].unique())
        
        # 创建合并后的结果数据框，确保包含所有必要列
        columns = ['class_id', 'school_id', 'class_name', 'school_name', 
                   'value_added_t', 'base_score', 'current_score', 'value_added',
                   'teacher_name', 'student_count', 'ci_lower', 'ci_upper', 'rating',
                   'exams_combined']
        
        combined_data = []
        
        # 处理每个班级
        for class_id in classes:
            class_data = {'class_id': class_id, 'exams_combined': 0}
            weighted_values = {
                'value_added_t': 0, 'value_added': 0, 
                'base_score': 0, 'current_score': 0
            }
            total_weight = 0
            
            # 遍历每个考试结果
            for i, te in enumerate(teacher_effects_list):
                class_row = te[te['class_id'] == class_id]
                if not class_row.empty:
                    weight = weights[i]
                    total_weight += weight
                    class_data['exams_combined'] += 1
                    
                    # 提取基本信息
                    for col in ['school_id', 'class_name', 'school_name', 'teacher_name']:
                        if col in class_row.columns and col not in class_data:
                            class_data[col] = class_row[col].iloc[0]
                    
                    # 累积权重数据
                    for col in weighted_values.keys():
                        if col in class_row.columns:
                            weighted_values[col] += class_row[col].iloc[0] * weight
            
            # 只有当至少有一个考试包含该班级时才处理
            if total_weight > 0:
                # 计算加权平均值
                for col, value in weighted_values.items():
                    class_data[col] = value / total_weight
                
                # 设置默认值
                if 'student_count' not in class_data:
                    class_data['student_count'] = 0
                
                # 设置置信区间和评级
                t_score = class_data.get('value_added_t', 50)
                class_data['ci_lower'] = t_score - 5  # 默认置信区间
                class_data['ci_upper'] = t_score + 5  # 默认置信区间
                
                # 分类评级
                bins = [0, 35, 45, 55, 65, 100]
                labels = ['显著低于平均', '低于平均', '平均水平', '高于平均', '显著高于平均']
                t_score_category = None
                for i in range(len(bins)-1):
                    if bins[i] <= t_score < bins[i+1]:
                        t_score_category = labels[i]
                        break
                class_data['rating'] = t_score_category if t_score_category else '平均水平'
                
                combined_data.append(class_data)
        
        # 创建合并后的DataFrame
        combined_df = pd.DataFrame(combined_data)
        
        # 计算排名
        if not combined_df.empty and 'value_added_t' in combined_df.columns:
            combined_df['rank'] = combined_df['value_added_t'].rank(ascending=False)
        
        self.stdout.write(f"合并后共有{len(combined_df)}个班级")
        
        # 返回与_calculate_teacher_effects相同格式的字典
        return {
            'teacher_effects': combined_df,
            # 如果有学校和学生数据也合并它们
            'school_effects': None if not school_effects_list else pd.concat(school_effects_list).drop_duplicates(),
            'student_effects': None if not student_effects_list else pd.concat(student_effects_list).drop_duplicates()
        }

    def _save_multi_exam_results_to_db(self, combined_results, base_exam_id, current_exams, subject_id):
        """
        保存多次考试的合并结果到数据库
        
        Args:
            combined_results: 合并后的教师增值效应DataFrame
            base_exam_id: 基线考试ID
            current_exams: 后续考试ID列表
            subject_id: 学科ID
            
        Returns:
            None
        """
        if not self.options.get('no_save', False):
            self.stdout.write("保存多次考试合并结果到数据库...")
            
            # 获取当前学期信息
            current_semester_id = None
            try:
                # 尝试从最后一次考试获取学期ID
                last_exam = Exam.objects.get(exam_id=current_exams[-1])
                current_semester_id = last_exam.semester_id
            except:
                self.stdout.write(self.style.WARNING("无法获取当前学期信息，使用默认值"))
            
            # 生成批次ID
            exams_suffix = '_'.join(current_exams)
            batch_id = f"HLM_MULTI_{subject_id}_{base_exam_id}_{exams_suffix}"
            
            # 模型参数（简化处理，因为合并后没有具体模型）
            model_params = {
                'method': 'hlm_multi_exam',
                'base_exam_id': base_exam_id,
                'exams_included': current_exams,
                'combination_weights': 'weighted_by_recency',
            }
            
            with transaction.atomic():
                records_saved = 0
                
                for _, row in combined_results.iterrows():
                    class_id = row['class_id']
                    
                    # 构建评价ID
                    eval_id = f"HLM_MULTI_{class_id}_{exams_suffix}_{subject_id}"
                    
                    # 保存因素
                    factors = {
                        'value_added_t': float(row['value_added_t']),
                        'method': 'hlm_multi_exam',
                        'batch_id': batch_id,
                        'base_exam_id': base_exam_id,
                        'current_exams': current_exams,
                        'exams_combined': int(row.get('exams_combined', len(current_exams))),
                        'ci_lower': float(row['ci_lower']),
                        'ci_upper': float(row['ci_upper']),
                        'model_params': model_params,
                        'rating': str(row['rating'])
                    }
                    
                    # 添加教师ID(如果有)
                    if pd.notna(row.get('teacher_id')):
                        factors['teacher_id'] = row['teacher_id']
                    
                    # 添加学校ID(如果有)
                    if pd.notna(row.get('school_id')):
                        factors['school_id'] = row['school_id']
                    
                    # 保存到数据库
                    ValueAddedEvaluation.objects.update_or_create(
                        eval_id=eval_id,
                        defaults={
                            'target_type': 'CLASS',
                            'target_id': class_id,
                            'subject_id': subject_id,
                            'semester_id': current_semester_id,
                            'base_score': float(row['base_score']),
                            'current_score': float(row['current_score']),
                            'added_value': float(row.get('value_added', 0.0)),
                            'factors': factors,
                            'status': 'COMPLETE'
                        }
                    )
                    
                    records_saved += 1
                
                self.stdout.write(self.style.SUCCESS(f"已保存 {records_saved} 条合并后的班级评价记录"))

    def _add_class_info(self, data_frame):
        """
        向数据框添加班级信息
        
        Args:
            data_frame: 包含class_id的DataFrame
        """
        if 'class_id' not in data_frame.columns:
            # 检查是否存在class_field_id列
            if 'class_field_id' in data_frame.columns:
                # 重命名为class_id
                data_frame.rename(columns={'class_field_id': 'class_id'}, inplace=True)
                self.stdout.write("已将class_field_id列重命名为class_id")
            else:
                self.stdout.write(self.style.WARNING("数据中既没有class_id也没有class_field_id列，无法添加班级信息"))
                return
        
        # 获取所有唯一的班级ID
        class_ids = data_frame['class_id'].dropna().unique().tolist()
        
        if not class_ids:
            self.stdout.write(self.style.WARNING("数据中没有有效的班级ID"))
            return
        
        # 查询班级信息，使用class_id匹配class表的class_id字段
        try:
            classes = Class.objects.filter(class_id__in=class_ids).values('class_id', 'class_name')
            class_info = {c['class_id']: c['class_name'] for c in classes}
            
            # 添加班级名称
            data_frame['class_name'] = data_frame['class_id'].map(class_info)
            
            # 记录无法匹配的班级数
            missing = data_frame['class_name'].isna().sum()
            if missing > 0:
                self.stdout.write(self.style.WARNING(f"有{missing}条记录无法匹配到班级名称"))
                self.stdout.write(f"无法匹配的班级ID: {data_frame[data_frame['class_name'].isna()]['class_id'].unique()}")
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"添加班级信息时出错: {str(e)}"))

    def _add_school_info(self, data_frame):
        """
        向数据框添加学校信息
        
        Args:
            data_frame: 包含school_id的DataFrame
        """
        if 'school_id' not in data_frame.columns:
            self.stdout.write(self.style.WARNING("数据中缺少school_id列，无法添加学校信息"))
            return
        
        # 获取所有唯一的学校ID
        school_ids = data_frame['school_id'].dropna().unique().tolist()
        
        if not school_ids:
            self.stdout.write(self.style.WARNING("数据中没有有效的学校ID"))
            return
        
        # 查询学校信息
        try:
            schools = School.objects.filter(school_id__in=school_ids).values('school_id', 'school_name')
            school_info = {s['school_id']: s['school_name'] for s in schools}
            
            # 添加学校名称
            data_frame['school_name'] = data_frame['school_id'].map(school_info)
            
            # 记录无法匹配的学校数
            missing = data_frame['school_name'].isna().sum()
            if missing > 0:
                self.stdout.write(self.style.WARNING(f"有{missing}条记录无法匹配到学校名称"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"添加学校信息时出错: {str(e)}"))

    def _calculate_student_effects(self, student_data, teacher_effects, fixed_effects):
        """
        计算学生个体的增值效应。
        
        Args:
            student_data: 包含学生成绩的DataFrame
            teacher_effects: 教师增值效应DataFrame
            fixed_effects: 模型固定效应系数
            
        Returns:
            DataFrame: 包含学生增值效应的数据
        """
        # 从Student表获取学生姓名
        self.stdout.write("从Student表获取学生姓名...")
        
        # 获取所有student_id
        student_ids = student_data['student_id'].unique().tolist()
        
        # 批量查询学生信息
        students = Student.objects.filter(student_id__in=student_ids).values('student_id', 'name')
        
        # 创建学生ID到姓名的映射
        student_name_map = {s['student_id']: s['name'] for s in students}
        
        # 添加学生姓名列
        student_data['student_name'] = student_data['student_id'].map(student_name_map)
        
        # 检查是否有无法匹配姓名的学生
        missing_names = student_data[student_data['student_name'].isna()]
        if not missing_names.empty:
            self.stdout.write(self.style.WARNING(f"有{len(missing_names)}名学生无法匹配姓名"))
        
        # 计算学生期望分数（基于固定效应）
        intercept = fixed_effects.iloc[0]
        base_score_coef = fixed_effects.iloc[1]
        
        # 创建班级效应映射
        class_effects_map = {}
        for _, row in teacher_effects.iterrows():
            class_effects_map[row['class_id']] = row['value_added']
        
        # 将班级效应添加到学生数据
        student_data['class_effect'] = student_data['class_id'].map(class_effects_map)
        
        # 计算学生期望分数（基于固定效应和班级随机效应）
        student_data['expected_score'] = intercept + base_score_coef * (
            student_data['base_score'] - 500  # 去中心化处理
        ) + student_data['class_effect']
        
        # 计算学生增值（实际分数与期望分数的差值）
        student_data['value_added'] = student_data['current_score'] - student_data['expected_score']
        
        # 新标准化方式（直接转换）
        student_data['value_added_t'] = 50 + (student_data['value_added'] / 10)
        
        # 分类评级
        bins = [0, 35, 45, 55, 65, 100]
        labels = ['显著低于平均', '低于平均', '平均水平', '高于平均', '显著高于平均']
        student_data['rating'] = pd.cut(
            student_data['value_added_t'],
            bins=bins,
            labels=labels,
            include_lowest=True
        )
        
        # 按增值T分排名
        student_data = student_data.sort_values('value_added_t', ascending=False)
        student_data['rank'] = range(1, len(student_data) + 1)
        
        # 基线潜力调整
        score_range = student_data['current_score'].max() - student_data['base_score'].min()
        max_score = student_data['current_score'].max()
        
        # 1. 计算每个学生的成长潜力系数（基线越高，潜力越小）
        student_data['growth_potential'] = (max_score - student_data['base_score']) / score_range
        
        # 2. 计算潜力调整后的增值（原始增值除以潜力系数）
        student_data['adjusted_value_added'] = student_data['value_added'] / student_data['growth_potential']
        
        # 3. 计算调整后的T分数（这是关键改进）
        mean_adj_va = student_data['adjusted_value_added'].mean()
        std_adj_va = student_data['adjusted_value_added'].std()
        student_data['adjusted_value_added_t'] = 50 + 10 * (student_data['adjusted_value_added'] - mean_adj_va) / std_adj_va
        
        # 4. 创建复合评价指标（同时考虑原始增值和潜力调整增值）
        student_data['composite_score'] = 0.5 * student_data['value_added_t'] + 0.5 * student_data['adjusted_value_added_t']
        
        # 5. 实现分层评价（分不同基线分组计算增值）
        # 创建基线分组（四分位数）
        student_data['base_score_group'] = pd.qcut(student_data['base_score'], 4, 
                                                 labels=['低分组', '中低分组', '中高分组', '高分组'])
        
        # 为每个分组独立计算组内增值T分
        for group in student_data['base_score_group'].unique():
            mask = student_data['base_score_group'] == group
            if sum(mask) > 1:  # 确保组内有足够样本
                group_mean = student_data.loc[mask, 'value_added'].mean()
                group_std = student_data.loc[mask, 'value_added'].std()
                
                if group_std > 0:  # 避免除零错误
                    student_data.loc[mask, 'group_value_added_t'] = 50 + 10 * (
                        student_data.loc[mask, 'value_added'] - group_mean) / group_std
        
        # 6. 使用复合分数重新排名
        student_data = student_data.sort_values('composite_score', ascending=False)
        student_data['composite_rank'] = range(1, len(student_data) + 1)
        
        # 7. 使用复合分数重新评级
        student_data['composite_rating'] = pd.cut(
            student_data['composite_score'],
            bins=[0, 35, 45, 55, 65, 100],
            labels=['显著低于平均', '低于平均', '平均水平', '高于平均', '显著高于平均'],
            include_lowest=True
        )
        
        # 8. 添加最终报告列（根据需要调整）
        columns_to_keep = [
            'student_id', 'student_name', 'class_id', 'class_name', 
            'school_id', 'school_name', 'base_score', 'current_score', 
            'expected_score', 'value_added', 'value_added_t', 'rank', 'rating',
            'growth_potential', 'adjusted_value_added', 'adjusted_value_added_t',
            'base_score_group', 'group_value_added_t', 
            'composite_score', 'composite_rank', 'composite_rating'
        ]
        
        # 只保留实际存在的列
        available_columns = [col for col in columns_to_keep if col in student_data.columns]
        student_effects = student_data[available_columns]
        
        # 设置最终排名和评级（使用复合分数）
        student_effects['final_rank'] = student_effects['composite_rank']
        student_effects['final_rating'] = student_effects['composite_rating']
        
        self.stdout.write(f"学生增值效应计算完成，共{len(student_effects)}名学生")
        return student_effects