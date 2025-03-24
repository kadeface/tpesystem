def _prepare_longitudinal_data(self, student_ids, subject_id):
    """
    准备纵向数据（多个考试时间点）
    
    Args:
        student_ids: 学生ID列表
        subject_id: 学科ID
        
    Returns:
        DataFrame: 包含多个时间点的纵向数据
    """
    # 获取学生所有历史成绩
    scores = Score.objects.filter(
        student_id__in=student_ids,
        subject_id=subject_id,
        status='COMPLETE'
    ).order_by('exam__exam_date').values(
        'student_id', 'raw_score', 'standard_score', 'exam_id', 'exam__exam_date'
    )
    
    # 转换为DataFrame并处理时间
    df = pd.DataFrame(list(scores))
    df['exam_date'] = pd.to_datetime(df['exam__exam_date'])
    df['time_point'] = df.groupby('student_id').cumcount() + 1  # 时间编码
    
    # 计算每个学生的基线成绩（首次考试）
    df['base_score'] = df.groupby('student_id')['standard_score'].transform('first')
    
    return df

def _fit_two_level_model(self, longitudinal_data):
    """
    拟合时间层+学生层的两层HLM模型
    
    Args:
        longitudinal_data: 纵向数据
        
    Returns:
        MixedLMResults: 模型结果
    """
    # 中心化处理
    longitudinal_data['time_centered'] = longitudinal_data['time_point'] - longitudinal_data['time_point'].mean()
    longitudinal_data['base_centered'] = longitudinal_data['base_score'] - longitudinal_data['base_score'].mean()
    
    # 构建模型公式
    formula = "standard_score ~ base_centered + time_centered"
    
    # 定义随机效应：学生截距 + 时间斜率
    re_formula = "1 + time_centered"
    
    try:
        model = mixedlm(
            formula,
            longitudinal_data,
            groups=longitudinal_data["student_id"],
            re_formula=re_formula
        )
        results = model.fit()
        return results
    except Exception as e:
        self.stdout.write(self.style.ERROR(f"模型拟合失败: {str(e)}"))
        raise

def _decompose_variance(self, model_results):
    """
    分解时间层和学生层方差
    
    Args:
        model_results: 模型结果
        
    Returns:
        dict: 方差成分
    """
    # 学生层方差（截距+斜率）
    student_var = model_results.cov_re.iloc[0, 0]  # 截距方差
    time_slope_var = model_results.cov_re.iloc[1, 1]  # 时间斜率方差
    
    # 残差方差
    residual_var = model_results.scale
    
    total_var = student_var + time_slope_var + residual_var
    
    return {
        'student_intercept_var': student_var,
        'time_slope_var': time_slope_var,
        'residual_var': residual_var,
        'total_var': total_var,
        'icc_student': (student_var + time_slope_var) / total_var
    } 