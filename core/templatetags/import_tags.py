from django import template
import re

register = template.Library()

@register.filter
def regex_findall(value, arg):
    """使用正则表达式从文本中提取内容"""
    try:
        pattern = re.compile(arg)
        return pattern.findall(value)
    except:
        return [] 