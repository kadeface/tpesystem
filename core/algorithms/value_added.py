"""
增值评价算法模块，实现教学质量增值评价的核心计算逻辑。
"""
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import statsmodels.api as sm
import statsmodels.formula.api as smf

def standardize_scores(scores_df):
    """
    将原始分数标准化为Z分数。

    Args:
        scores_df: 包含原始分数的DataFrame
            columns=['student_id', 'raw_score', ...]

    Returns:
        添加了标准分的DataFrame
    """
    scaler = StandardScaler()
    scores_df['standard_score'] = scaler.fit_transform(scores_df[['raw_score']])
    return scores_df

def calculate_value_added(baseline_df, current_df, method='z_score'):
    """
    计算增值分数。

    Args:
        baseline_df: 基线分数DataFrame
        current_df: 当前分数DataFrame
        method: 计算方法，可选 'z_score', 'percentile'

    Returns:
        包含增值分数的DataFrame
    """
    # 合并基线和当前数据
    merged_df = pd.merge(
        baseline_df, current_df, 
        on='student_id', 
        suffixes=('_base', '_current')
    )
    
    # 计算增值分
    if method == 'z_score':
        merged_df['value_added'] = merged_df['standard_score_current'] - merged_df['standard_score_base']
    else:
        merged_df['value_added'] = merged_df['percentile_current'] - merged_df['percentile_base']
    
    return merged_df

def simple_difference_method(baseline_df, current_df, params=None):
    """
    简单差值法计算增值分数。
    
    Args:
        baseline_df: 基线数据DataFrame
        current_df: 当前数据DataFrame
        params: 参数字典
    
    Returns:
        增值评价结果DataFrame
    """
    if params is None:
        params = {}
    
    # 获取模式
    mode = params.get('mode', 'simple')
    score_fields = params.get('score_fields', ['raw_score'])
    
    # 创建结果DataFrame
    result_df = pd.DataFrame()
    result_df['student_id'] = current_df['student_id']
    
    # 简单差值模式 - 直接计算当前分数与基线分数的差值
    if mode == 'simple':
        # 计算每个评分字段的差值
        for field in score_fields:
            # 确保两个DataFrame都有此字段
            if field in baseline_df.columns and field in current_df.columns:
                # 基于student_id合并基线和当前数据
                merged = pd.merge(
                    baseline_df[['student_id', field]], 
                    current_df[['student_id', field]],
                    on='student_id', 
                    suffixes=('_base', '_current')
                )
                
                # 计算差值
                result_df[f'{field}_base'] = merged[f'{field}_base']
                result_df[f'{field}_current'] = merged[f'{field}_current']
                result_df[f'{field}_diff'] = merged[f'{field}_current'] - merged[f'{field}_base']
        
        # 如果只使用一个评分字段，直接用它作为增值分
        if len(score_fields) == 1:
            result_df['value_added'] = result_df[f'{score_fields[0]}_diff']
        else:
            # 计算所有字段的加权平均差值
            value_added = 0
            for field in score_fields:
                if f'{field}_diff' in result_df.columns:
                    # 可以为不同字段设置不同权重
                    weight = params.get(f'{field}_weight', 1.0 / len(score_fields))
                    value_added += result_df[f'{field}_diff'] * weight
            
            result_df['value_added'] = value_added
    
    # TES模式 - 考虑当前排名和进步排名
    elif mode == 'tes':
        # 添加调试信息
        print(f"基线分布: {baseline_df[score_fields[0]].describe()}")
        print(f"当前分布: {current_df[score_fields[0]].describe()}")
        
        # 从参数中获取权重
        current_weight = params.get('current_weight', 0.4)
        progress_weight = params.get('progress_weight', 0.6)
        
        field_results = []
        
        for field in score_fields:
            if field in baseline_df.columns and field in current_df.columns:
                # 合并数据
                merged = pd.merge(
                    baseline_df[['student_id', field]], 
                    current_df[['student_id', field]],
                    on='student_id', 
                    suffixes=('_base', '_current')
                )
                
                # 计算进步分数
                merged[f'{field}_progress'] = merged[f'{field}_current'] - merged[f'{field}_base']
                
                # 添加更强的随机扰动，解决大量数据相同的问题
                merged[f'{field}_progress'] = add_controlled_noise(merged[f'{field}_progress'])
                
                # 计算当前分和标准分也添加微小扰动，确保排名不会有大量平局
                merged[f'{field}_current'] = merged[f'{field}_current'] + np.random.normal(0, 0.001, len(merged))
                
                # 然后再计算排名
                merged[f'{field}_current_rank'] = merged[f'{field}_current'].rank(ascending=False)
                merged[f'{field}_progress_rank'] = merged[f'{field}_progress'].rank(ascending=False)
                
                # 计算当前分数和进步分数（基于排名的归一化分数）
                n = len(merged)
                merged[f'{field}_current_score'] = (n - merged[f'{field}_current_rank'] + 1) / n * 10
                merged[f'{field}_progress_score'] = (n - merged[f'{field}_progress_rank'] + 1) / n * 10
                
                # 计算TES增值分数
                merged[f'{field}_value_added'] = (
                    current_weight * merged[f'{field}_current_score'] + 
                    progress_weight * merged[f'{field}_progress_score']
                )
                
                field_results.append(merged[[
                    'student_id', 
                    f'{field}_base', 
                    f'{field}_current',
                    f'{field}_progress',
                    f'{field}_current_rank',
                    f'{field}_progress_rank',
                    f'{field}_current_score',
                    f'{field}_progress_score',
                    f'{field}_value_added'
                ]])
        
        # 合并所有字段的结果
        if field_results:
            result = field_results[0]
            for i in range(1, len(field_results)):
                result = pd.merge(result, field_results[i], on='student_id')
            
            # 计算总体增值分数（各字段的平均值）
            value_added_fields = [f'{field}_value_added' for field in score_fields if f'{field}_value_added' in result.columns]
            if value_added_fields:
                # 使用显式权重而不是平均值
                if len(value_added_fields) > 1:
                    weights = {}
                    for field in score_fields:
                        weights[f'{field}_value_added'] = params.get(f'{field}_weight', 1.0 / len(score_fields))
                    
                    # 归一化权重
                    weight_sum = sum(weights.values())
                    for field in weights:
                        weights[field] /= weight_sum
                    
                    # 加权计算
                    result['value_added'] = 0
                    for field, weight in weights.items():
                        if field in result.columns:
                            result['value_added'] += result[field] * weight
                else:
                    result['value_added'] = result[value_added_fields[0]]
                
                # 增加总分和排名
                result['current_total_score'] = result[[f'{field}_current_score' for field in score_fields]].sum(axis=1)
                result['progress_total_score'] = result[[f'{field}_progress_score' for field in score_fields]].sum(axis=1)
                
                # 计算总排名
                result['current_rank'] = result['current_total_score'].rank(ascending=False).astype(int)
                result['progress_rank'] = result['progress_total_score'].rank(ascending=False).astype(int)
                result['value_added_rank'] = result['value_added'].rank(ascending=False).astype(int)
            
            result_df = result
    
    return result_df

def predicted_difference_method(base_scores, current_scores, covariates=None):
    """
    预测差值法计算增值分数，通过回归模型控制预测变量。

    Args:
        base_scores: 基线分数的DataFrame，包含student_id和raw_score
        current_scores: 当前分数的DataFrame，包含student_id和raw_score
        covariates: 协变量DataFrame，包含控制变量，如家庭背景等

    Returns:
        包含增值分数的DataFrame，增值分数为实际得分与预测得分的差值
    """
    # 准备数据
    if covariates is not None:
        X = pd.merge(base_scores, covariates, on='student_id')
    else:
        X = base_scores.copy()
    
    # 建立预测模型
    model = LinearRegression()
    X_features = X.drop(['student_id'], axis=1)
    model.fit(X_features, current_scores['raw_score'])
    
    # 预测当前分数
    predicted_scores = model.predict(X_features)
    
    # 计算增值（残差）
    result_df = current_scores.copy()
    result_df['predicted_score'] = predicted_scores
    result_df['value_added'] = result_df['raw_score'] - result_df['predicted_score']
    
    return result_df

def hlm_value_added(student_data, teacher_data=None, school_data=None):
    """
    使用多层线性模型(HLM)计算增值分数。

    Args:
        student_data: 学生数据，包含学生ID、当前分数、基线分数、班级ID等
        teacher_data: 教师数据，包含教师特征
        school_data: 学校数据，包含学校特征

    Returns:
        包含多层次增值评估结果的DataFrame
    """
    # 构建多层线性模型公式
    formula = "current_score ~ baseline_score + student_feature1 + student_feature2"
    
    # 创建分组变量，如班级ID、学校ID
    groups = {'class_id': student_data['class_id'],
              'school_id': student_data['school_id']}
    
    # 拟合多层线性模型
    md = smf.mixedlm(formula, student_data, groups=groups)
    mdf = md.fit()
    
    # 提取随机效应（代表教师/学校贡献）
    random_effects = mdf.random_effects
    
    # 构建结果DataFrame
    result = pd.DataFrame()
    result['class_id'] = list(random_effects.keys())
    result['class_effect'] = [re[0] for re in random_effects.values()]
    
    # 将效应值映射回学生
    student_result = student_data.copy()
    student_result['class_effect'] = student_result['class_id'].map(
        dict(zip(result['class_id'], result['class_effect']))
    )
    student_result['value_added'] = mdf.resid  # 残差作为个体增值
    
    return student_result, result

def ml_value_added(baseline_data, current_data, covariates=None, method='random_forest'):
    """
    使用机器学习方法计算增值分数。

    Args:
        baseline_data: 基线数据，包含学生ID和基线分数
        current_data: 当前数据，包含学生ID和当前分数
        covariates: 协变量数据，包含各种影响因素
        method: 机器学习方法，默认为'random_forest'，也可选'neural_network'等

    Returns:
        包含增值分数的DataFrame
    """
    # 准备数据
    X = pd.merge(baseline_data, covariates, on='student_id') if covariates is not None else baseline_data.copy()
    y = current_data['raw_score']
    
    # 选择模型
    if method == 'random_forest':
        model = RandomForestRegressor(n_estimators=100, random_state=42)
    elif method == 'neural_network':
        # 使用神经网络模型，需导入相应库
        from sklearn.neural_network import MLPRegressor
        model = MLPRegressor(hidden_layer_sizes=(100, 50), max_iter=1000, random_state=42)
    else:
        model = LinearRegression()
    
    # 训练模型
    X_features = X.drop(['student_id'], axis=1)
    model.fit(X_features, y)
    
    # 预测分数
    predicted_scores = model.predict(X_features)
    
    # 计算增值
    result_df = current_data.copy()
    result_df['predicted_score'] = predicted_scores
    result_df['value_added'] = result_df['raw_score'] - result_df['predicted_score']
    
    # 如果使用RandomForest，可以计算特征重要性
    if method == 'random_forest':
        feature_importance = pd.DataFrame({
            'feature': X_features.columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        return result_df, feature_importance
    
    return result_df

def aggregate_value_added(student_va_df, group_by, group_method='mean'):
    """
    聚合学生级别的增值分数到更高级别（如教师、班级、学校）。

    Args:
        student_va_df: 包含学生增值分数的DataFrame
        group_by: 分组列名，如'teacher_id'、'class_id'、'school_id'
        group_method: 聚合方法，默认为'mean'

    Returns:
        按组聚合后的增值分数DataFrame
    """
    # 执行分组聚合
    if group_method == 'mean':
        aggregated = student_va_df.groupby(group_by)['value_added'].mean().reset_index()
    elif group_method == 'median':
        aggregated = student_va_df.groupby(group_by)['value_added'].median().reset_index()
    elif group_method == 'weighted_mean':
        # 加权平均，需提供权重列
        weights = student_va_df['weight']
        aggregated = (student_va_df['value_added'] * weights).groupby(student_va_df[group_by]).sum() / \
                     weights.groupby(student_va_df[group_by]).sum()
        aggregated = aggregated.reset_index()
    
    return aggregated

def add_controlled_noise(series, intensity=0.01, min_noise=0.001):
    """添加受控的随机噪声，保持数据的相对顺序"""
    # 获取数据的标准差，如果接近0则使用一个小值
    std = max(series.std(), 0.1) 
    # 根据数据范围调整噪声幅度，确保最小强度
    noise_scale = max(std * intensity, min_noise)
    # 生成噪声
    noise = np.random.normal(0, noise_scale, len(series))
    # 确保没有值为0的增值分（在应用噪声后）
    result = series + noise
    # 确保所有值至少有微小差异（如果所有原始值都是0）
    if (result == 0).any():
        zero_mask = (result == 0)
        result[zero_mask] = np.random.uniform(0.001, 0.01, zero_mask.sum())
    return result 

def calculate_class_value_added(class_scores_base, class_scores_current):
    """计算班级科目的增值分数，使用T分数差值法"""
    # 合并基线和当前数据
    result_df = pd.merge(
        class_scores_base[['class_id', 'subject_id', 't_score']], 
        class_scores_current[['class_id', 'subject_id', 't_score']],
        on=['class_id', 'subject_id'], 
        suffixes=('_base', '_current')
    )
    
    # 计算增值分数：当前T分 - 基线T分
    result_df['added_value'] = result_df['t_score_current'] - result_df['t_score_base']
    
    # 将增值分标准化为500±100范围（与T分相同量级）
    mean_added = result_df['added_value'].mean()
    std_added = result_df['added_value'].std() or 1  # 避免除以零
    
    # 标准化增值分 = 500 + 100 * Z分数
    result_df['added_value_scaled'] = 500 + 100 * (result_df['added_value'] - mean_added) / std_added
    
    # 使用标准化后的增值分计算综合得分
    result_df['comprehensive_score'] = (
        result_df['t_score_current'] * 0.4 + 
        result_df['added_value_scaled'] * 0.6
    )
    
    # 保留原始增值分，用于展示原始提升情况
    return result_df

def aggregate_student_to_class_t_score(student_scores, class_field='class_id', score_field='standard_score', exam_field='exam_id'):
    """
    将学生分数聚合为班级T分数，使用500+100Z标准，按考试ID分组计算
    
    Args:
        student_scores: 学生分数DataFrame
            columns=['student_id', 'class_id', 'subject_id', 'standard_score', 'exam_id', ...]
        class_field: 班级ID字段名
        score_field: 分数字段名
        exam_field: 考试ID字段名，用于区分不同考试的分数计算
    
    Returns:
        班级T分数DataFrame
    """
    # 如果提供了考试ID字段，则按考试ID分组处理
    if exam_field and exam_field in student_scores.columns:
        # 按考试ID分组处理
        exams = student_scores[exam_field].unique()
        all_class_scores = []
        
        for exam in exams:
            # 筛选当前考试的数据
            exam_data = student_scores[student_scores[exam_field] == exam]
            
            # 按班级和科目分组，计算平均分
            class_means = exam_data.groupby([class_field, 'subject_id'])[score_field].mean()
            overall_mean = exam_data[score_field].mean()
            overall_std = exam_data[score_field].std()
            
            # 转换为DataFrame
            class_scores = class_means.reset_index()
            
            # 添加考试ID信息
            class_scores[exam_field] = exam
            
            # 计算班级T分数: T = 500 + 100 * (班级平均分 - 总体平均分) / 总体标准差
            class_scores['t_score'] = 500 + 100 * (class_scores[score_field] - overall_mean) / overall_std
            
            all_class_scores.append(class_scores)
        
        # 合并所有考试的结果
        if all_class_scores:
            result = pd.concat(all_class_scores)
            return result[[class_field, 'subject_id', exam_field, 't_score']]
        return pd.DataFrame() 
    
    # 没有考试ID信息，使用原来的方法（不推荐，可能混合不同考试）
    class_means = student_scores.groupby([class_field, 'subject_id'])[score_field].mean()
    overall_mean = student_scores[score_field].mean()
    overall_std = student_scores[score_field].std()
    
    # 转换为DataFrame
    class_scores = class_means.reset_index()
    
    # 计算班级T分数: T = 500 + 100 * (班级平均分 - 总体平均分) / 总体标准差
    class_scores['t_score'] = 500 + 100 * (class_scores[score_field] - overall_mean) / overall_std
    
    return class_scores[[class_field, 'subject_id', 't_score']] 