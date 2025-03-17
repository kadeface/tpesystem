"""
增值评价服务接口，提供各种评价计算服务。
"""
import pandas as pd
from django.db import transaction
from core.models import (
    Score, Student, Teacher, Class, School, Subject, Semester,
    ValueAddedEvaluation, TeacherHistory
)
from core.algorithms.evaluation_models import (
    SimpleDifferenceModel, PredictedDifferenceModel,
    HLMModel, MLModel
)


class EvaluationService:
    """
    增值评价服务类，封装评价计算逻辑和数据访问。

    Args:
        method: 评价方法名称
        parameters: 评价参数字典

    Returns:
        评价服务实例
    """
    
    def __init__(self, method='simple_difference', parameters=None):
        """
        初始化评价服务。

        Args:
            method: 评价方法名称，可选值：
                'simple_difference': 简单差值法
                'predicted_difference': 预测差值法
                'hlm': 多层线性模型
                'ml_random_forest': 随机森林机器学习模型
                'ml_neural_network': 神经网络机器学习模型
            parameters: 评价参数字典
        """
        self.method = method
        self.parameters = parameters or {}
        self.model = self._create_model()
    
    def _create_model(self):
        """
        创建评价模型实例。

        Returns:
            评价模型实例
        """
        if self.method == 'simple_difference':
            return SimpleDifferenceModel(self.parameters)
        elif self.method == 'predicted_difference':
            return PredictedDifferenceModel(self.parameters)
        elif self.method == 'hlm':
            return HLMModel(self.parameters)
        elif self.method.startswith('ml_'):
            self.parameters['method'] = self.method.split('_', 1)[1]
            return MLModel(self.parameters)
        else:
            raise ValueError(f"不支持的评价方法: {self.method}")
    
    def prepare_student_data(self, base_semester_id, current_semester_id, subject_id, filters=None):
        """
        准备学生评价数据。

        Args:
            base_semester_id: 基线学期ID
            current_semester_id: 当前学期ID
            subject_id: 学科ID
            filters: 额外的过滤条件，如school_id, class_id, base_exam_id, current_exam_id等

        Returns:
            准备好的评价数据字典
        """
        filters = filters or {}
        
        # 获取基线分数
        base_query = Score.objects.filter(
            semester_id=base_semester_id,
            subject_id=subject_id,
            status='COMPLETE'
        )
        
        # 获取当前分数
        current_query = Score.objects.filter(
            semester_id=current_semester_id,
            subject_id=subject_id,
            status='COMPLETE'
        )
        
        # 应用额外过滤条件
        for key, value in filters.items():
            if key == 'school_id':
                base_query = base_query.filter(student__current_school_id=value)
                current_query = current_query.filter(student__current_school_id=value)
            elif key == 'class_id':
                base_query = base_query.filter(student__current_class_id=value)
                current_query = current_query.filter(student__current_class_id=value)
            elif key == 'base_exam_id':
                base_query = base_query.filter(exam_id=value)
            elif key == 'current_exam_id':
                current_query = current_query.filter(exam_id=value)
        
        # 转换为DataFrame
        base_df = pd.DataFrame(list(base_query.values('student_id', 'raw_score', 'standard_score', 'percentile', 'exam_id')))
        current_df = pd.DataFrame(list(current_query.values('student_id', 'raw_score', 'standard_score', 'percentile', 'exam_id')))
        
        # 找出基线和当前数据集中都有的学生
        if not base_df.empty and not current_df.empty:
            common_students = set(base_df['student_id']).intersection(set(current_df['student_id']))
            base_df = base_df[base_df['student_id'].isin(common_students)]
            current_df = current_df[current_df['student_id'].isin(common_students)]
        
        # 如果需要协变量（对于预测差值法和机器学习方法）
        covariates = None
        if self.method in ['predicted_difference', 'ml_random_forest', 'ml_neural_network']:
            # 获取学生信息作为协变量
            students = Student.objects.filter(
                student_id__in=base_df['student_id'].tolist()
            )
            covariates = pd.DataFrame(list(students.values(
                'student_id', 'gender', 'current_school', 'current_grade', 'current_class'
            )))
            
            # 添加其他可能的协变量，如家庭背景等
            
        return {
            'baseline': base_df,
            'current': current_df,
            'covariates': covariates
        }
    
    def evaluate_students(self, base_semester_id, current_semester_id, subject_id, filters=None, save=True):
        """
        执行学生增值评价。

        Args:
            base_semester_id: 基线学期ID
            current_semester_id: 当前学期ID
            subject_id: 学科ID
            filters: 额外的过滤条件
            save: 是否保存评价结果到数据库

        Returns:
            评价结果
        """
        # 准备评价数据
        data = self.prepare_student_data(base_semester_id, current_semester_id, subject_id, filters)
        
        # 执行评价
        results = self.model.evaluate(data)
        
        # 保存结果
        if save:
            with transaction.atomic():
                self.model.save_results('STUDENT', 'BATCH', subject_id, current_semester_id)
        
        return results
    
    def evaluate_teachers(self, base_semester_id, current_semester_id, subject_id, filters=None, save=True):
        """
        执行教师增值评价。

        Args:
            base_semester_id: 基线学期ID
            current_semester_id: 当前学期ID
            subject_id: 学科ID
            filters: 额外的过滤条件
            save: 是否保存评价结果到数据库

        Returns:
            评价结果
        """
        # 获取学生数据
        student_data = self.prepare_student_data(base_semester_id, current_semester_id, subject_id, filters)
        
        # 获取教师数据
        teachers = Teacher.objects.filter(
            teaching_assignments__subject_id=subject_id,
            teaching_assignments__semester_id=current_semester_id
        )
        teacher_df = pd.DataFrame(list(teachers.values('teacher_id', 'name', 'qualification', 'teaching_years')))
        
        # 准备评价数据
        if self.method == 'hlm':
            # 对于HLM，我们需要将学生数据与班级、教师关联
            student_df = pd.merge(
                student_data['current'],
                student_data['baseline'],
                on='student_id',
                suffixes=('_current', '_base')
            )
            
            # 添加学生-班级-教师关联
            student_class = pd.DataFrame(list(Student.objects.filter(
                student_id__in=student_df['student_id']
            ).values('student_id', 'current_class_id')))
            
            teacher_class = pd.DataFrame(list(TeacherHistory.objects.filter(
                subject_id=subject_id,
                semester_id=current_semester_id
            ).values('teacher', 'class_field', 'school', 'subject')))
            
            # 合并数据
            student_df = pd.merge(student_df, student_class, on='student_id')
            student_df = pd.merge(
                student_df, 
                teacher_class.rename(columns={'class_field': 'current_class_id'}),
                on='current_class_id'
            )
            
            data = {
                'student_data': student_df,
                'teacher_data': teacher_df
            }
        else:
            # 为每个教师准备数据并计算增值
            teacher_results = []
            
            for _, teacher in teacher_df.iterrows():
                teacher_id = teacher['teacher_id']
                
                # 获取该教师教授的班级
                teacher_classes = TeacherHistory.objects.filter(
                    teacher=teacher_id,
                    subject_id=subject_id,
                    semester_id=current_semester_id
                ).values_list('class_field', flat=True)
                
                # 获取这些班级的学生
                teacher_students = Student.objects.filter(
                    current_class_id__in=teacher_classes
                ).values_list('student_id', flat=True)
                
                # 过滤学生数据
                teacher_base_df = student_data['baseline'][student_data['baseline']['student_id'].isin(teacher_students)]
                teacher_current_df = student_data['current'][student_data['current']['student_id'].isin(teacher_students)]
                
                if len(teacher_base_df) > 0 and len(teacher_current_df) > 0:
                    teacher_result = self.model.evaluate({
                        'baseline': teacher_base_df,
                        'current': teacher_current_df,
                        'covariates': student_data.get('covariates')
                    })
                    
                    # 计算教师级别的综合指标
                    if isinstance(teacher_result, dict) and 'scores' in teacher_result:
                        teacher_va = teacher_result['scores']['value_added'].mean()
                    else:
                        teacher_va = teacher_result['value_added'].mean()
                    
                    teacher_results.append({
                        'teacher_id': teacher_id,
                        'value_added': teacher_va
                    })
            
            data = pd.DataFrame(teacher_results)
        
        # 执行评价
        results = self.model.evaluate(data)
        
        # 保存结果
        if save:
            with transaction.atomic():
                for _, row in results.iterrows():
                    ValueAddedEvaluation.objects.create(
                        eval_id=f"TEACHER_{row['teacher_id']}_{subject_id}_{current_semester_id}",
                        target_type='TEACHER',
                        target_id=row['teacher_id'],
                        subject_id=subject_id,
                        semester_id=current_semester_id,
                        base_score=0,  # 需要计算基础分数
                        current_score=0,  # 需要计算当前分数
                        added_value=row['value_added'],
                        factors={},
                        status='DRAFT'
                    )
        
        return results

    def evaluate_schools(self, base_semester_id, current_semester_id, subject_id, region_id=None, save=True):
        """
        执行学校增值评价。

        Args:
            base_semester_id: 基线学期ID
            current_semester_id: 当前学期ID
            subject_id: 学科ID
            region_id: 区域ID，用于过滤学校
            save: 是否保存评价结果到数据库

        Returns:
            评价结果
        """
        # 获取学校列表
        schools_query = School.objects.all()
        if region_id:
            schools_query = schools_query.filter(region_id=region_id)
        
        schools = pd.DataFrame(list(schools_query.values('school_id', 'school_name', 'school_type')))
        
        # 为每个学校计算增值
        school_results = []
        
        for _, school in schools.iterrows():
            school_id = school['school_id']
            
            # 准备该学校的学生数据
            school_data = self.prepare_student_data(
                base_semester_id, current_semester_id, subject_id,
                filters={'school_id': school_id}
            )
            
            # 如果有足够的数据进行计算
            if len(school_data['baseline']) > 0 and len(school_data['current']) > 0:
                # 执行评价
                school_result = self.model.evaluate(school_data)
                
                # 计算学校级别的综合指标
                if isinstance(school_result, dict) and 'scores' in school_result:
                    school_va = school_result['scores']['value_added'].mean()
                else:
                    school_va = school_result['value_added'].mean()
                
                school_results.append({
                    'school_id': school_id,
                    'school_name': school['school_name'],
                    'value_added': school_va
                })
        
        results = pd.DataFrame(school_results)
        
        # 保存结果
        if save and not results.empty:
            with transaction.atomic():
                for _, row in results.iterrows():
                    ValueAddedEvaluation.objects.create(
                        eval_id=f"SCHOOL_{row['school_id']}_{subject_id}_{current_semester_id}",
                        target_type='SCHOOL',
                        target_id=row['school_id'],
                        subject_id=subject_id,
                        semester_id=current_semester_id,
                        base_score=0,  # 需要计算基础分数
                        current_score=0,  # 需要计算当前分数
                        added_value=row['value_added'],
                        factors={},
                        status='DRAFT'
                    )
        
        return results

    def evaluate_with_tes(self, base_semester_id, current_semester_id, subject_id, 
                          base_exam_id=None, current_exam_id=None,
                          score_fields=None, special_schools=None, filters=None, save=True):
        """
        使用TES模式执行增值评价。

        Args:
            base_semester_id: 基线学期ID
            current_semester_id: 当前学期ID
            subject_id: 学科ID
            base_exam_id: 基线考试ID (可选)
            current_exam_id: 当前考试ID (可选)
            score_fields: 评价指标字段列表，如['raw_score', 'percentile']
            special_schools: 特殊学校ID列表
            filters: 额外的过滤条件
            save: 是否保存评价结果到数据库

        Returns:
            评价结果
        """
        # 设置TES模式参数
        tes_params = {
            'mode': 'tes',
            'current_weight': 0.4,
            'progress_weight': 0.6,
            'score_fields': score_fields or ['raw_score'],
            'special_schools': special_schools or []
        }
        
        # 创建TES评价模型
        model = SimpleDifferenceModel(tes_params)
        
        # 准备过滤条件
        filters = filters or {}
        
        # 添加考试ID过滤
        if base_exam_id:
            filters['base_exam_id'] = base_exam_id
        if current_exam_id:
            filters['current_exam_id'] = current_exam_id
        
        # 准备评价数据
        data = self.prepare_student_data(base_semester_id, current_semester_id, subject_id, filters)
        
        # 如果需要学校数据进行特殊处理
        if special_schools:
            # 获取学生所属学校
            student_ids = data['baseline']['student_id'].tolist() + data['current']['student_id'].tolist()
            student_ids = list(set(student_ids))  # 去重
            
            student_schools = list(Student.objects.filter(
                student_id__in=student_ids
            ).values('student_id', 'current_school_id'))
            
            student_school_map = {s['student_id']: s['current_school_id'] for s in student_schools}
            
            # 将学校ID添加到基线和当前数据中
            data['baseline']['school_id'] = data['baseline']['student_id'].map(student_school_map)
            data['current']['school_id'] = data['current']['student_id'].map(student_school_map)
        
        # 执行评价
        results = model.evaluate(data)
        
        # 生成批次ID，包含考试ID信息
        batch_id = f"TES_{subject_id}"
        if base_exam_id and current_exam_id:
            batch_id = f"{batch_id}_{base_exam_id}_{current_exam_id}"
        else:
            batch_id = f"{batch_id}_{base_semester_id}_{current_semester_id}"
        
        # 保存结果
        if save:
            with transaction.atomic():
                for _, row in results.iterrows():
                    student_id = row['student_id']
                    
                    # 创建评价ID
                    eval_id = f"STUDENT_{student_id}_{subject_id}_{current_semester_id}"
                    if current_exam_id:
                        eval_id = f"{eval_id}_{current_exam_id}"
                    
                    ValueAddedEvaluation.objects.update_or_create(
                        eval_id=eval_id,
                        defaults={
                            'target_type': 'STUDENT',
                            'target_id': student_id,
                            'subject_id': subject_id,
                            'semester_id': current_semester_id,
                            'base_score': row.get(f'{score_fields[0]}_base', 0) if score_fields else row.get('raw_score_base', 0),
                            'current_score': row.get(f'{score_fields[0]}_current', 0) if score_fields else row.get('raw_score_current', 0),
                            'added_value': row['value_added'],
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
        
        return results 