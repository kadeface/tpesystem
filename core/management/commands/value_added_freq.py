# 一个新的替代命令
def run_hlm_analysis(self):
    """使用频率派HLM（混合线性模型）进行增值分析"""
    import statsmodels.formula.api as smf
    
    # 准备数据
    df = self.agg_data.copy()
    
    # 创建分组变量
    df['class_grp'] = pd.Categorical(df['norm_class_id'])
    df['school_grp'] = pd.Categorical(df['school_id'])
    
    # 拟合混合线性模型
    logger.info("拟合频率派混合线性模型...")
    model = smf.mixedlm(
        "standard_score ~ prior_score", 
        df,
        groups=df["class_grp"],
        re_formula="~1"
    )
    result = model.fit()
    
    # 提取结果
    logger.info(f"模型拟合完成: AIC={result.aic:.1f}")
    
    # 获取班级随机效应
    rand_effects = result.random_effects
    classes = pd.DataFrame({
        'norm_class_id': list(rand_effects.keys()),
        'value_added': [re[0] for re in rand_effects.values()]
    })
    
    # 计算学校效应
    schools = df.groupby('school_id')['norm_class_id'].unique()
    school_effects = {}
    for school_id, class_ids in schools.items():
        class_ids = [c for c in class_ids if c in rand_effects]
        if class_ids:
            school_effects[school_id] = np.mean([rand_effects[c][0] for c in class_ids])
    
    school_df = pd.DataFrame({
        'school_id': list(school_effects.keys()),
        'value_added': list(school_effects.values())
    })
    
    # 标准化为50分制
    for df in [classes, school_df]:
        df['value_added_std'] = 50 + 10 * (df['value_added'] - df['value_added'].mean()) / df['value_added'].std()
    
    return {
        'classes': classes,
        'schools': school_df,
        'is_freq_model': True
    } 