# 区域教学增值评价系统

## 项目概述

区域教学增值评价系统是一个专为教育管理部门设计的数据分析平台，用于评估学校、教师和学生的教学增值效果。系统基于Django REST Framework构建后端API，使用Vue 3作为前端框架，PostgreSQL作为数据库系统。

## 已完成工作

### 1. 数据模型设计与实现

根据数据仓库4.0规范，完成了以下核心模型：

- **基础维度**：
  - Region (区域)
  - Semester (学期)
  
- **学校维度**：
  - School (学校)
  - Grade (年级)
  - Class (班级)
  
- **教师维度**：
  - Teacher (教师)
  - TeacherTeam (教师团队)
  
- **学生维度**：
  - Student (学生)
  - Family (家庭)
  
- **学科与考试维度**：
  - Subject (学科)
  - Exam (考试)
  - Score (成绩)
  - SubjectRelation (学科关系)
  
- **评价维度**：
  - EvaluationMetrics (评价指标)
  - ValueAddedEvaluation (增值评价)

### 2. API开发

- 创建了核心资源的RESTful API
- 实现了序列化器与视图集
- 添加了过滤和分页功能
- 设置了基本权限控制

### 3. 前端基础组件

- MainLayout.vue - 系统主界面布局
- 集成Element Plus组件库

### 4. 项目环境配置

- 项目结构规范化
- PostgreSQL数据库配置
- 缓存系统配置
- 静态文件管理
- Django Admin配置

### 5. 开发工具与辅助功能

- 测试数据生成命令 (create_test_data.py)
- 数据库连接测试命令 (test_db.py)
- 批量数据上传API (ScoreUploadView)

## 项目配置说明

### 环境要求

- Python 3.8+
- Node.js 14+
- PostgreSQL 12+

### 安装依赖

后端依赖：
```bash
pip install -r requirements.txt
```

前端依赖：
```bash
cd frontend
npm install
```

### 数据库配置

1. 创建PostgreSQL数据库和用户：
```sql
CREATE USER evaluation_user WITH PASSWORD 'your_password';
CREATE DATABASE evaluation_db OWNER evaluation_user;
ALTER USER evaluation_user CREATEDB;
```

2. 创建.env文件(项目根目录)：
```
DB_NAME=evaluation_db
DB_USER=evaluation_user
DB_PASSWORD=your_password
DB_HOST=localhost
DB_PORT=5432
SECRET_KEY=your-secret-key
```

### 运行项目

1. 数据库迁移：
```bash
python manage.py makemigrations
python manage.py migrate
```

2. 创建超级用户：
```bash
python manage.py createsuperuser
```

3. 启动后端服务：
```bash
python manage.py runserver
```

4. 启动前端开发服务器：
```bash
cd frontend
npm run serve
```

## 项目结构

```
evaluation_system/       # 项目配置目录
├── settings.py          # 项目设置
├── urls.py              # URL路由
└── wsgi.py              # WSGI配置

core/                    # 核心应用
├── models.py            # 数据模型定义
├── serializers.py       # API序列化器
├── views.py             # API视图
├── permissions.py       # 权限类
└── management/          # 管理命令
    └── commands/        
        ├── create_test_data.py   # 生成测试数据
        └── test_db.py            # 测试数据库连接

frontend/                # 前端目录
├── src/                 # 源代码
│   ├── components/      # 组件
│   │   └── MainLayout.vue  # 主布局组件
│   ├── router/          # 路由
│   └── main.ts          # 入口文件
└── package.json         # 依赖配置
```

## 下一步开发计划

1. **实现完整的用户认证系统**
   - JWT认证
   - 权限细分
   - 用户角色管理

2. **增值评价算法实现**
   - 多维度评价指标
   - 数据归一化处理
   - 增值效果计算

3. **前端功能完善**
   - 数据可视化组件
   - 富交互表单
   - 报表生成功能
   
4. **系统优化**
   - 缓存优化
   - 批量数据导入优化
   - API性能提升

5. **测试与部署**
   - 单元测试
   - 集成测试
   - 生产环境部署文档

## 贡献

此项目由教育评价团队开发和维护。

## 许可

[MIT License](LICENSE)

## Django Admin功能说明



### 1. 标准Django Admin管理界面

标准管理界面提供了所有数据模型的增删改查功能，并具有强大的筛选、搜索和排序能力。

#### 访问方式

```bash
# 访问地址
http://127.0.0.1:8000/admin/
```

#### 创建超级用户

首次使用需要创建超级用户：

```bash
python manage.py createsuperuser
```
用户名：admin
密码：YYrr181314

#### 主要功能

- **区域管理**：管理区域层级信息
- **学校管理**：管理学校基础信息
- **教师管理**：教师信息维护
- **学生管理**：学生信息管理
- **考试管理**：配置和管理考试
- **成绩管理**：查看和编辑成绩数据
- **增值评价**：查看评价指标和结果

### 2. 自定义管理仪表盘

自定义仪表盘提供了数据概览和关键指标的直观展示，便于决策层快速了解系统状态。

#### 访问方式

```bash
# 访问地址
http://127.0.0.1:8000/dashboard/
```

#### 主要功能

- **数据统计概览**：显示学校、教师、学生总数等关键指标
- **学校类型分布**：以表格形式展示各类学校数量
- **教师职称分布**：展示不同职称教师的数量统计
- **快速操作**：提供常用功能的便捷入口

### 3. 权限管理

系统支持细粒度的权限控制，可以为不同角色设置不同的访问权限：

1. 在Admin后台创建用户组（如"学校管理员"、"区域管理员"）
2. 为用户组分配适当的权限
3. 将用户添加到相应的用户组

#### 常见权限组

- **超级管理员**：拥有系统全部权限
- **区域管理员**：管理特定区域内的学校、教师和学生数据
- **学校管理员**：仅能管理所属学校的数据
- **数据查看员**：只有查看权限，无修改权限

#### 自定义权限

系统实现了`IsSchoolAdmin`等自定义权限类，可实现更精细的权限控制。

## 安装要求更新

请在README.md的安装依赖部分添加以下内容：

```bash
# 创建模板目录
mkdir -p templates/admin
```

将dashboard.html模板文件放置在templates/admin目录下。

## 系统配置更新



```bash
# 访问地址
http://127.0.0.1:8000/dashboard/
```

#### 主要功能

- **区域管理**：管理区域层级信息
- **学校管理**：管理学校基础信息
- **教师管理**：教师信息维护
- **学生管理**：学生信息管理
- **考试管理**：配置和管理考试
- **成绩管理**：查看和编辑成绩数据
- **增值评价**：查看评价指标和结果

### 2. 自定义管理仪表盘

自定义仪表盘提供了数据概览和关键指标的直观展示，便于决策层快速了解系统状态。

#### 访问方式

```bash
# 访问地址
http://127.0.0.1:8000/dashboard/
```

#### 主要功能

- **数据统计概览**：显示学校、教师、学生总数等关键指标
- **学校类型分布**：以表格形式展示各类学校数量
- **教师职称分布**：展示不同职称教师的数量统计
- **快速操作**：提供常用功能的便捷入口

### 3. 权限管理

系统支持细粒度的权限控制，可以为不同角色设置不同的访问权限：

1. 在Admin后台创建用户组（如"学校管理员"、"区域管理员"）
2. 为用户组分配适当的权限
3. 将用户添加到相应的用户组

#### 常见权限组

- **超级管理员**：拥有系统全部权限
- **区域管理员**：管理特定区域内的学校、教师和学生数据
- **学校管理员**：仅能管理所属学校的数据
- **数据查看员**：只有查看权限，无修改权限

#### 自定义权限

系统实现了`IsSchoolAdmin`等自定义权限类，可实现更精细的权限控制。

# 学校数据导入功能说明

## 功能概述

我们实现了一个Django管理命令 `import_schools`，用于从CSV文件导入学校基础数据到系统数据库中。此命令可以批量处理学校信息，并自动关联区域数据。

## 数据格式要求

导入的CSV文件需要包含以下字段（无需标题行）：

1. `id` - 序号（仅作标识用，不导入）
2. `district_id` - 区域ID
3. `school_code` - 学校编码
4. `school_name` - 学校名称
5. `school_type` - 学校类型（该字段在数据中可能为空）
6. `school_level` - 学校等级（P=小学、M=初中、H=高中）
7. `created_at` - 创建时间（不导入）
8. `updated_at` - 更新时间（不导入）

## 学校等级映射规则

系统根据 `school_level` 字段值自动映射为对应的学校类型：

- `P` → PRIMARY（小学）
- `M` → JUNIOR（初中）
- `H` → HIGH（高中）
- 其他值 → 默认为 PRIMARY（小学）

## 使用方法

1. 准备好符合格式要求的CSV文件
2. 运行以下命令导入数据：

```bash
python manage.py import_schools school_info.csv
```

## 导入结果

命令执行过程中会显示导入进度，包括新建或更新的学校信息。完成后会显示成功导入的学校数量以及失败的记录数量。

## 错误处理

- 文件不存在时会显示错误信息并终止导入
- 导入过程中的异常会被捕获并记录，不会影响其他记录的导入
- 所有导入操作在一个数据库事务中完成，确保数据完整性

## 注意事项

- 如果CSV文件编码不是UTF-8，可能会导致中文字符显示为乱码
- 区域ID需要存在于系统中，否则会自动创建新的区域记录
- 学校编码作为唯一标识，相同编码的学校信息会被更新而非新建

区域教学增值评价系统 - 教师数据导入功能
功能说明

系统现已支持从CSV和Excel文件导入教师数据，方便批量录入教师信息。导入功能具有以下特点：
1. 支持多种文件格式：Excel (.xlsx/.xls) 和 CSV文件
自动检测文件类型并使用适当的导入方法
可指定Excel工作表名称
从身份证号自动提取性别和出生日期
5. 根据职称自动判断教师职称等级
6. 提供详细的导入报告和错误统计
导入命令使用方法
基本用法
命令参数
| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| file_path | 必需参数，数据文件路径 | - | 教师数据.xlsx |
| --sheet | Excel工作表名称 | Sheet1 | --sheet=教师信息表 |
| --delimiter | CSV文件分隔符 | tab | --delimiter=comma |
| --debug | 启用调试模式 | - | --debug |
| --show-errors | 显示详细错误信息 | - | --show-errors |
示例命令
数据格式要求
导入文件应包含以下列名：
| 列名 | 说明 | 是否必填 | 最大长度 |
|------|------|----------|----------|
| 姓名 | 教师姓名 | 是 | 50 |
| 学校名称 | 所属学校 | 是 | - |
| 身份证号 | 用于提取性别和出生日期 | 否 | 20 |
| 联系电话 | 手机号码 | 否 | 20 |
| 毕业学校 | 教师毕业院校 | 否 | 100 |
| 专业 | 教师专业背景 | 否 | 100 |
| 最高学历 | 教师最高学历 | 否 | 20 |
| 职称 | 教师职称 | 否 | 50 |
| 教龄 | 教学年限（整数） | 否 | - |
| 任教科目 | 主要任教学科 | 否 | 50 |
| 兼任科目 | 次要任教学科 | 否 | 50 |
| 职务 | 行政职务 | 否 | 50 |
特别功能说明
1. 自动创建学校：如果系统中不存在导入文件中指定的学校，系统会自动创建临时学校记录
字段长度处理：对于超过最大长度的字段，系统会自动截断并发出警告
3. 从身份证提取信息：系统会从身份证号中自动提取性别（第17位：奇数为男，偶数为女）和出生日期
职称等级判断：系统会根据职称名称自动判断职称等级（高级/中级/初级）
班主任识别：如果职务中包含"班主任"字样，将自动设置为班主任
常见问题
1. 导入时提示"找到多个同名学校"：系统会自动选择第一个学校记录使用，可以先清理学校数据再导入
部分字段值被截断：请检查数据库中相应字段的长度限制，可以修改模型增加字段长度
无法读取Excel文件：确保已安装相关依赖 pip install openpyxl pandas
日期格式问题：身份证号中的日期应符合YYYYMMDD格式
导入前准备
确保系统中已创建区域记录
建议先导入学校数据，再导入教师数据
准备好符合格式要求的Excel或CSV文件
备份现有数据，避免导入过程中出现问题
未来计划
未来将支持更多导入功能，包括：
教师教学经历导入
教师培训记录导入
学生基本信息导入
教学评价数据导入

# 导入Excel文件
python manage.py import_teachers 教师数据.xlsx

# 导入CSV文件
python manage.py import_teachers 教师数据.csv --delimiter=comma

## 数据导入指南

系统支持从Excel表格批量导入数据，包括学校、教师、学生、班级、成绩等信息。本指南提供了完整的数据导入流程。

### 准备数据文件

以下是导入所需的数据文件格式说明：

1. **学校信息表**：包含学校代码、学校名称、学校类型等信息
2. **教师信息表**：包含教师工号、姓名、性别等基本信息
3. **学生信息表**：包含学生姓名、考生号、身份证号、学籍号、学校、年级、班级等信息
4. **科任表**：横向格式，每行代表一个班级，各列为不同学科的任课教师
5. **成绩表**：包含考生号、姓名、学校、年级、班级和各科目成绩列

### 数据导入流程

#### 1. 初始化基础数据

首先，如果系统是全新的，需要初始化基础数据（区域、学科等）：

```bash
python manage.py initialize_base_data
```

#### 2. 导入学校数据

导入学校基本信息：

```bash
python manage.py import_schools 学校信息.xlsx --debug
```

#### 3. 导入教师数据 

导入教师基本信息：

```bash
python manage.py import_teachers 教师信息.xlsx --debug
```

#### 4. 导入学生基础数据

一次性导入学生及其关联的学校、年级、班级数据：


```bash
python manage.py import_scores "2025-DIST-M-202407.xls" --exam_id=2025-DIST-M-202407 --exam_name="23-24学年第二学期八年级区测考试" --semester=2023-2024-2 --exam_type=DIST-TEST --skip_teacher --region_id=6 --create_students --sheet="成绩表" --debug
python manage.py import_scores "2025-DIST-M-202401.xlsx" --exam_id=2025-DIST-M-202401 --exam_name="23-24学年第一学期八年级区测考试测" --semester=2023-2024-1 --exam_type=DIST-TEST --skip_teacher --region_id=6 --create_students --sheet="成绩表" --debug     
```

注意：此步骤使用`import_scores`命令是因为它支持学校、年级、班级和学生数据的一站式导入，参数`--skip-teacher`用于跳过教师处理。

#### 5. 导入教师科目班级关联数据

根据科任表导入教师-科目-班级的关联关系：

```bash
python manage.py import_subject_teachers 科任表.xlsx --semester=2023-1 --update --debug
```

#### 6. 导入考试成绩数据

导入各次考试的成绩数据，可以多次执行以导入不同考试的成绩：

```bash
# 期中考试成绩
python manage.py import_scores 期中考试成绩.xlsx --exam_id=MID2023 --exam_name="2023年期中考试" --semester=2023-1 --debug

# 期末考试成绩
python manage.py import_scores 期末考试成绩.xlsx --exam_id=FINAL2023 --exam_name="2023年期末考试" --semester=2023-1 --debug
```

### 数据更新场景

#### 更新学生基本信息

如果学生有转班、变更信息等情况：

```bash
python manage.py import_scores 更新学生信息.xlsx --exam_id=UPDATE2023 --exam_name="信息更新" --semester=2023-1 --skip-teacher --debug
```

#### 更新教师科目班级关联

如果教师任课安排有变更：

```bash
python manage.py import_subject_teachers 更新科任表.xlsx --semester=2023-2 --update --debug
```

#### 更新或补充成绩

如果需要补充或修正某次考试的成绩：

```bash
python manage.py import_scores 更正成绩.xlsx --exam_id=MID2023 --exam_name="2023年期中考试(更正)" --semester=2023-1 --debug
```

### 导入命令参数说明

#### 通用参数

- `--debug`: 显示详细日志，建议在首次导入时启用以检查数据正确性
- `--sheet`: 指定Excel工作表名称，默认为"Sheet1"

#### import_scores 参数

- `--exam_id`: 考试ID前缀，用于生成唯一的考试标识
- `--exam_name`: 考试名称，显示在系统中的考试名称
- `--exam_type`: 考试类型，如"MIDTERM"(期中),"FINAL"(期末),"ENTRANCE"(入学)
- `--semester`: 学期ID，格式为"年份-学期号"，如"2023-1"表示2023年第一学期
- `--skip-teacher`: 跳过教师关联，适用于只想导入学生和班级数据的场景

#### import_subject_teachers 参数

- `--update`: 更新已存在的教师科目关联记录
- `--create-teachers`: 自动创建不存在的教师记录
- `--semester`: 学期ID，用于设置教师科目关联的开始和结束日期

## 数据导入命令

### 导入学生成绩 (import_scores)

从Excel文件导入学生考试成绩数据，同时支持导入学校、年级、班级和学生基本信息。

#### 基本用法

```bash
python manage.py import_scores <excel文件路径> --exam_id=<考试ID> --exam_name=<考试名称> --semester=<学期ID> [选项]
```

#### 必需参数

- `file_path`: Excel文件路径
- `--exam_id`: 考试编号，用于生成系统内的唯一标识
- `--exam_name`: 考试名称，会显示在系统中
- `--semester`: 学期ID，格式为"yyyy-yyyy-t"，例如：2023-2024-2表示2023-2024学年第二学期

#### 可选参数

- `--exam_type`: 考试类型，如MIDTERM（期中）、FINAL（期末）、DIST-TEST（区测）等，默认为MIDTERM
- `--teacher_id`: 默认教师ID，默认为T001
- `--sheet`: Excel工作表名称，默认为Sheet1
- `--debug`: 启用调试模式，显示详细导入信息
- `--skip_teacher`: 不关联教师信息
- `--region_id`: 默认区域ID，默认为REG001
- `--create_students`: 自动创建不存在的学生记录
- `--update_students`: 更新已存在的学生信息

#### 使用示例

导入区测考试成绩：
```bash
python manage.py import_scores "成绩表.xls" --exam_id=2024-DIST-2-0520 --exam_name="23-24学年第二学期八年级区测考试" --semester=2023-2024-2 --exam_type=DIST-TEST --skip_teacher --create_students --debug
```

导入期末考试成绩：
```bash
python manage.py import_scores "期末考试.xlsx" --exam_id=2024-FINAL-2-0630 --exam_name="23-24学年第二学期期末考试" --semester=2023-2024-2 --exam_type=FINAL --region_id=6 --create_students --sheet="成绩表"
```

#### Excel文件要求

导入的Excel文件必须包含以下列：
- `考生号`: 学生考号
- `姓名`: 学生姓名
- `年级`: 学生年级
- `班别`: 学生班级
- `学校代码`: 学校编码
- `学校名称`: 学校名称
- `身份证号`: 学生身份证号
- `学籍号`: 学生学籍号

以及各科目成绩列（列名需与系统中定义的学科名称匹配）：
- `语文`、`数学`、`英语`、`物理`、`化学`等

#### 注意事项

1. **学生识别方式**：系统优先使用**身份证号**查找学生，其次使用**学籍号**，最后才考虑考生号。

2. **自动创建**：使用`--create_students`参数后，如果找不到对应学生记录，系统会自动创建学生记录。

3. **ID格式**：考试ID建议使用有意义的格式，如`年份-考试类型-学期-日期`，例如：`2024-DIST-2-0520`。

# 教师学科班级关联数据导入

系统提供了一个便捷的命令行工具，用于从Excel文件导入教师-学科-班级关联数据，轻松建立三者间的关联关系。

## 数据格式要求

导入工具支持"宽表"格式的Excel文件：

### 必要列
- `学校代码`：学校的唯一标识符
- `年级`：班级所属年级
- `班级`：班级名称（也支持`班别`等命名）

### 学科教师列
- 每个学科作为一列，列名为学科名称（如`语文科任`、`数学科任`等）
- 列内容为对应学科的教师姓名

### 示例数据
|学校代码|学校名称|年级|班级|语文科任|数学科任|英语科任|物理科任|政治科任|历史科任|
|-------|-------|---|---|------|------|------|------|------|------|
|78301|一中|高一|1班|黄珍丽|张明|李华|王强|周红|赵青|
|78301|一中|高一|2班|江媛玲|刘红|陈小|杨刚|赵青|王大|

## 导入命令使用

```bash
python manage.py import_teacher_subjects <file_path> --semester-id <semester_id> [options]
```

### 参数说明
- **必选参数**：
  - `file_path`：Excel文件路径
  - `--semester-id`：学期ID（如：2023-2024-1）
  
- **可选参数**：
  - `--sheet`：Excel工作表名称（默认：Sheet1）
  - `--debug`：启用调试模式
  - `--update`：更新现有记录
  - `--batch-size`：批量处理大小（默认：100）
  - `--skip-validation`：跳过数据验证
  - `--dry-run`：试运行模式，不实际写入数据库
  - `--auto-create-teachers`：自动创建不存在的教师

### 使用示例

```bash
# 基本导入
python manage.py import_teacher_subjects "教师学科班级关联表.xlsx" --semester-id 2023-2024-1

# 调试模式并自动创建不存在的教师
python manage.py import_teacher_subjects "教师学科班级关联表.xlsx" --semester-id 2023-2024-1 --debug --auto-create-teachers

# 试运行模式（不写入数据库）
python manage.py import_teacher_subjects "教师学科班级关联表.xlsx" --semester-id 2023-2024-1 --dry-run
```

## 自动创建教师说明

启用`--auto-create-teachers`选项时，系统会：
1. 为教师生成唯一ID（不超过10个字符）
2. 设置默认生日为1980-01-01
3. 根据学校类型设置教师学段（qualification）
4. 创建基本教师信息并建立相应关联

## 常见问题解决

1. **"班级不存在"错误**：确保班级已在系统中创建（ID格式：学校代码_年级_班级名）
   
2. **"教师不存在"错误**：使用`--auto-create-teachers`选项或先导入教师数据
   
3. **"学科不存在"错误**：确保所有学科已在系统中设置，包括政治与道德与法治的映射
   
4. **事务处理错误**：降低批处理大小（`--batch-size`参数）以定位问题

导入工具会同时更新`TeacherSubjectClass`、`TeacherSubject`和教师-班级关联，确保系统数据一致性。


成绩导入指令 python manage.py import_scores "2025-DIST-M-202307.xlsx" --exam_id=2025-DIST-M-202307 --exam_name="22-23学年第二学期七年级区 测考试测" --semester=2023-2024-1 --exam_type=DIST-TEST --skip_teacher --region_id=6 --create_students --sheet="成绩表" --debug 