from rest_framework import permissions

class IsSchoolAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        # 检查用户是否为学校管理员
        return request.user.groups.filter(name='School_Admin').exists() 