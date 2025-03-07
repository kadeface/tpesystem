from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # 其他URL模式...
    path('admin/', admin.site.urls),
    # 如果import_urls是通过这种方式导入的，需要确保路径正确
#    path('import-data/', include('core.import_urls')),
    # ...
] 