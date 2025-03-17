"""
增值评价模型定义模块，封装不同的增值评价计算模型。
"""

class BaseEvaluationModel:
    """
    增值评价基础模型类。

    Args:
        method: 评价方法名称
        parameters: 模型参数字典

    Returns:
        增值评价基础模型实例
    """
    
    def __init__(self, method, parameters=None):
        """
        初始化增值评价模型。

        Args:
            method: 评价方法名称
            parameters: 模型参数字典
        """
        self.method = method
        self.parameters = parameters or {}
        self.results = None
        
    def evaluate(self, data):
        """
        执行评价计算（由子类实现）。

        Args:
            data: 评价所需数据

        Returns:
            评价结果
        """
        raise NotImplementedError("子类必须实现evaluate方法")
    
    def get_results(self):
        """
        获取评价结果。

        Returns:
            评价结果
        """
        return self.results
    
    def save_results(self, target_type, target_id, subject_id, semester_id):
        """
        保存评价结果到数据库。

        Args:
            target_type: 评价对象类型，如'STUDENT'、'TEACHER'、'SCHOOL'
            target_id: 评价对象ID
            subject_id: 学科ID
            semester_id: 学期ID

        Returns:
            保存的评价记录列表
        """
        from core.models import ValueAddedEvaluation, Subject, Semester
        
        if not self.results:
            raise ValueError("还没有执行评价，没有可保存的结果")
        
        eval_records = []
        
        for _, row in self.results.iterrows():
            # 创建评价记录
            eval_record = ValueAddedEvaluation(
                eval_id=f"{target_type}_{target_id}_{subject_id}_{semester_id}",
                target_type=target_type,
                target_id=row.get('id', target_id),
                subject_id=subject_id,
                semester_id=semester_id,
                base_score=row.get('base_score', 0),
                current_score=row.get('current_score', 0),
                added_value=row.get('value_added', 0),
                factors=row.get('factors', {}),
                status='DRAFT'
            )
            eval_record.save()
            eval_records.append(eval_record)
        
        return eval_records


class SimpleDifferenceModel(BaseEvaluationModel):
    """
    简单差值增值评价模型。

    支持两种计算模式：
    1. 基础模式：直接计算前后测试分数差值
    2. TES模式：基于排名分层计算增值分数，支持本期分数与进步分数的加权计算

    Args:
        parameters: 模型参数字典
            mode: 'basic'(基础模式) 或 'tes'(TES模式)
            current_weight: 本期得分权重 (仅TES模式)
            progress_weight: 进步得分权重 (仅TES模式)
            score_fields: 需评价的指标字段列表 (仅TES模式)
            special_schools: 特殊学校ID列表 (仅TES模式)

    Returns:
        简单差值增值评价模型实例
    """
    
    def __init__(self, parameters=None):
        """
        初始化简单差值模型。

        Args:
            parameters: 模型参数字典
        """
        params = parameters or {}
        params.setdefault('mode', 'basic')
        params.setdefault('current_weight', 0.4)
        params.setdefault('progress_weight', 0.6)
        params.setdefault('special_schools', [])
        super().__init__('simple_difference', params)
    
    def evaluate(self, data):
        """
        执行简单差值法评价。

        Args:
            data: 包含基线和当前数据的字典
                data = {
                    'baseline': baseline_df,
                    'current': current_df
                }

        Returns:
            评价结果DataFrame
        """
        from core.algorithms.value_added import simple_difference_method
        
        baseline_df = data['baseline']
        current_df = data['current']
        
        # 根据模式选择计算方法
        if self.parameters['mode'] == 'tes':
            self.results = self._evaluate_tes_mode(baseline_df, current_df)
        else:
            self.results = simple_difference_method(baseline_df, current_df)
            
        return self.results
    
    def calculate_scores_by_percentile(self, ranked, total_students):
        """基于百分位计算分数
        
        Args:
            ranked: 排名序列
            total_students: 总学生数
            
        Returns:
            分数序列
        """
        # 计算每个学生的百分位
        percentile = (total_students - ranked + 1) / total_students * 100
        
        # 基于百分位分配分数
        return percentile.apply(lambda p: 8 if p >= 90 else  # 前10%
                               6 if p >= 75 else  # 10-25%
                               5 if p >= 55 else  # 25-45%
                               4 if p >= 35 else  # 45-65%
                               3 if p >= 15 else  # 65-85%
                               2 if p >= 5 else   # 85-95%
                               0)                 # 后5%
    
    def _rank_and_score(self, df, column, ascending=True):
        """
        根据排名计算得分。

        Args:
            df: 输入的DataFrame
            column: 用于排名的列名
            ascending: 是否升序排序

        Returns:
            包含计算得分的Series
        """
        ranked = df[column].rank(ascending=ascending, method="min")
        scores = self.calculate_scores_by_percentile(ranked, len(ranked))
        return scores
    
    def _evaluate_tes_mode(self, baseline_df, current_df):
        """
        使用TES模式计算增值分数。

        Args:
            baseline_df: 基线分数DataFrame
            current_df: 当前分数DataFrame

        Returns:
            包含增值评价结果的DataFrame
        """
        import pandas as pd
        
        # 确保基线和当前数据使用相同的student_id
        baseline_df_copy = baseline_df.copy()
        current_df_copy = current_df.copy()
        
        # 获取特殊学校的掩码
        special_schools = self.parameters.get('special_schools', [])
        if 'school_id' in current_df_copy.columns:
            special_school_mask = current_df_copy['school_id'].isin(special_schools)
        else:
            special_school_mask = pd.Series(False, index=current_df_copy.index)
        
        # 获取需要评价的指标字段
        score_fields = self.parameters.get('score_fields', ['raw_score'])
        
        # 合并基线和当前数据
        merged_df = pd.merge(
            baseline_df_copy, current_df_copy,
            on='student_id',
            suffixes=('_base', '_current')
        )
        
        # 计算进步值
        progress_df = pd.DataFrame(index=merged_df.index)
        for field in score_fields:
            base_field = f"{field}_base"
            current_field = f"{field}_current"
            progress_df[f"{field}_progress"] = merged_df[current_field] - merged_df[base_field]
        
        # 计算当前得分排名和增值排名
        result_df = merged_df.copy()
        
        # 为每个指标计算本期得分和进步得分
        for field in score_fields:
            current_field = f"{field}_current"
            progress_field = f"{field}_progress"
            
            # 特殊学校的分数调整
            if len(special_schools) > 0:
                # 创建临时列用于排名计算
                result_df[f"{current_field}_adj"] = result_df[current_field].copy()
                result_df.loc[special_school_mask, f"{current_field}_adj"] = \
                    result_df.loc[special_school_mask, current_field] * 1.333
                
                # 根据是否为低分率类指标决定排序方向
                is_low_rate = 'dfl' in field or 'low_rate' in field
                current_asc = True if is_low_rate else False
                
                # 计算本期得分排名
                result_df[f"{current_field}_rank"] = result_df[f"{current_field}_adj"].rank(
                    ascending=current_asc, method="min")
                result_df[f"{current_field}_score"] = self._rank_and_score(
                    result_df, f"{current_field}_rank", ascending=not current_asc)
                
                # 创建临时列用于进步排名计算
                result_df[f"{progress_field}_adj"] = progress_df[progress_field].copy()
                result_df.loc[special_school_mask, f"{progress_field}_adj"] = \
                    progress_df.loc[special_school_mask, progress_field] * 1.333
                
                # 计算进步得分排名
                progress_asc = True if is_low_rate else False
                result_df[f"{progress_field}_rank"] = result_df[f"{progress_field}_adj"].rank(
                    ascending=progress_asc, method="min")
                result_df[f"{progress_field}_score"] = self._rank_and_score(
                    result_df, f"{progress_field}_rank", ascending=not progress_asc)
                
                # 清理临时列
                result_df.drop([f"{current_field}_adj", f"{progress_field}_adj"], axis=1, inplace=True)
            else:
                # 无特殊学校情况
                is_low_rate = 'dfl' in field or 'low_rate' in field
                current_asc = True if is_low_rate else False
                result_df[f"{current_field}_rank"] = result_df[current_field].rank(
                    ascending=current_asc, method="min")
                result_df[f"{current_field}_score"] = self._rank_and_score(
                    result_df, f"{current_field}_rank", ascending=not current_asc)
                
                progress_asc = True if is_low_rate else False
                result_df[f"{progress_field}_rank"] = progress_df[progress_field].rank(
                    ascending=progress_asc, method="min")
                result_df[f"{progress_field}_score"] = self._rank_and_score(
                    result_df, f"{progress_field}_rank", ascending=not progress_asc)
        
        # 计算无低分率的情况下的加成
        for field in score_fields:
            if 'dfl' in field or 'low_rate' in field:
                low_rate_field = f"{field}_current"
                # 找出没有低分率的记录
                no_low_rate_mask = result_df[low_rate_field] == 0
                
                # 为没有低分率的记录提供加成（其他得分乘以1.33）
                for f in score_fields:
                    if f != field:  # 只为非低分率指标提供加成
                        current_score_field = f"{f}_current_score"
                        result_df.loc[no_low_rate_mask, current_score_field] *= 1.33
                        
                        progress_score_field = f"{f}_progress_score"
                        result_df.loc[no_low_rate_mask, progress_score_field] *= 1.33
        
        # 计算总分
        current_score_columns = [f"{field}_current_score" for field in score_fields]
        progress_score_columns = [f"{field}_progress_score" for field in score_fields]
        
        result_df['current_total_score'] = result_df[current_score_columns].sum(axis=1)
        result_df['progress_total_score'] = result_df[progress_score_columns].sum(axis=1)
        
        # 计算综合得分（本期总分权重 * 本期总分 + 进步得分权重 * 进步总分）
        current_weight = self.parameters.get('current_weight', 0.4)
        progress_weight = self.parameters.get('progress_weight', 0.6)
        
        result_df['value_added'] = (result_df['current_total_score'] * current_weight + 
                                   result_df['progress_total_score'] * progress_weight)
        
        # 计算排名
        result_df['current_rank'] = result_df['current_total_score'].rank(method="min", ascending=False)
        result_df['progress_rank'] = result_df['progress_total_score'].rank(method="min", ascending=False)
        result_df['value_added_rank'] = result_df['value_added'].rank(method="min", ascending=False)
        
        return result_df


class PredictedDifferenceModel(BaseEvaluationModel):
    """
    预测差值增值评价模型。

    Args:
        parameters: 模型参数字典，可包含covariates_include列表指定包含哪些协变量

    Returns:
        预测差值增值评价模型实例
    """
    
    def __init__(self, parameters=None):
        """
        初始化预测差值模型。

        Args:
            parameters: 模型参数字典
        """
        super().__init__('predicted_difference', parameters)
    
    def evaluate(self, data):
        """
        执行预测差值法评价。

        Args:
            data: 包含基线、当前数据和协变量的字典
                data = {
                    'baseline': baseline_df,
                    'current': current_df,
                    'covariates': covariates_df  # 可选
                }

        Returns:
            评价结果DataFrame
        """
        from core.algorithms.value_added import predicted_difference_method
        
        baseline_df = data['baseline']
        current_df = data['current']
        covariates_df = data.get('covariates', None)
        
        # 如果参数中指定了要包含的协变量，则过滤协变量DataFrame
        if covariates_df is not None and 'covariates_include' in self.parameters:
            include_cols = ['student_id'] + self.parameters['covariates_include']
            covariates_df = covariates_df[include_cols]
        
        self.results = predicted_difference_method(baseline_df, current_df, covariates_df)
        return self.results


class HLMModel(BaseEvaluationModel):
    """
    多层线性模型(HLM)增值评价模型。

    Args:
        parameters: 模型参数字典

    Returns:
        HLM增值评价模型实例
    """
    
    def __init__(self, parameters=None):
        """
        初始化HLM模型。

        Args:
            parameters: 模型参数字典
        """
        super().__init__('hlm', parameters)
    
    def evaluate(self, data):
        """
        执行HLM评价。

        Args:
            data: 包含所需数据的字典
                data = {
                    'student_data': student_df,
                    'teacher_data': teacher_df,  # 可选
                    'school_data': school_df  # 可选
                }

        Returns:
            评价结果元组(student_results, group_results)
        """
        from core.algorithms.value_added import hlm_value_added
        
        student_df = data['student_data']
        teacher_df = data.get('teacher_data', None)
        school_df = data.get('school_data', None)
        
        student_results, group_results = hlm_value_added(student_df, teacher_df, school_df)
        self.results = {'student': student_results, 'group': group_results}
        return self.results


class MLModel(BaseEvaluationModel):
    """
    机器学习增值评价模型。

    Args:
        parameters: 模型参数字典，可包含method指定使用的机器学习方法

    Returns:
        机器学习增值评价模型实例
    """
    
    def __init__(self, parameters=None):
        """
        初始化机器学习模型。

        Args:
            parameters: 模型参数字典
        """
        params = parameters or {}
        method = params.get('method', 'random_forest')
        super().__init__(f'ml_{method}', params)
    
    def evaluate(self, data):
        """
        执行机器学习评价。

        Args:
            data: 包含所需数据的字典
                data = {
                    'baseline': baseline_df,
                    'current': current_df,
                    'covariates': covariates_df  # 可选
                }

        Returns:
            评价结果，可能包含特征重要性
        """
        from core.algorithms.value_added import ml_value_added
        
        baseline_df = data['baseline']
        current_df = data['current']
        covariates_df = data.get('covariates', None)
        
        # 获取指定的机器学习方法
        ml_method = self.parameters.get('method', 'random_forest')
        
        result = ml_value_added(baseline_df, current_df, covariates_df, ml_method)
        
        # 根据返回类型设置结果
        if isinstance(result, tuple):
            self.results = {'scores': result[0], 'feature_importance': result[1]}
        else:
            self.results = {'scores': result}
        
        return self.results 