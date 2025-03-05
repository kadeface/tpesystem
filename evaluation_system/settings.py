import os
from pathlib import Path
from dotenv import load_dotenv

# 构建项目根目录的路径
BASE_DIR = Path(__file__).resolve().parent.parent

# 开发环境使用文件缓存 - 修改为绝对路径
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
        'LOCATION': os.path.abspath('/var/tmp/django_cache'),  # 使用绝对路径
        'TIMEOUT': 300,  # 5分钟缓存时间
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    }
}

# 或使用数据库缓存（小型项目适用）
# CACHES = {
#     'default': {
#         'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
#         'LOCATION': 'my_cache_table',
#     }
# } 

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',  # 添加 REST Framework
    'core',  # 添加 core 应用
    'django_filters',
    # ...
]

REST_FRAMEWORK = {
    'DEFAULT_FILTER_BACKENDS': ['django_filters.rest_framework.DjangoFilterBackend'],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.DjangoModelPermissionsOrAnonReadOnly'
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 10
}

# 中间件设置
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# 模板设置
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# WSGI 应用
WSGI_APPLICATION = 'evaluation_system.wsgi.application'  # 或 'TPESystem.wsgi.application'

# 加载.env文件中的环境变量
load_dotenv()

# 数据库配置
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'evaluation_db'),
        'USER': os.getenv('DB_USER', 'evaluation_user'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'YYrr181314'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# 开发环境设置
DEBUG = True  # 开发环境设为 True，生产环境必须设为 False

# 如果 DEBUG 为 False，必须设置 ALLOWED_HOSTS
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']  # 添加您的域名 

# 添加 ROOT_URLCONF 设置
ROOT_URLCONF = 'evaluation_system.urls' 

# 安全密钥设置 - 在生产环境中应使用环境变量
SECRET_KEY = os.getenv('SECRET_KEY', 'django-insecure-default-key-for-development-only')

# 静态文件设置
STATIC_URL = '/static/'

# 静态文件收集目录
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# 修改静态文件目录设置，确保目录存在
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

# 语言设置 - 改为中文
LANGUAGE_CODE = 'zh-hans'

# 时区设置 - 改为中国时区
TIME_ZONE = 'Asia/Shanghai'

# 国际化支持
USE_I18N = True

# 本地化格式支持
USE_L10N = True

# 使用时区
USE_TZ = True

# 设置默认自动主键字段类型
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# 在settings.py中添加
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media') 