from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import AnalysisResult
from .serializers import AnalysisResultSerializer

class AnalysisResultViewSet(viewsets.ModelViewSet):
    queryset = AnalysisResult.objects.all()
    serializer_class = AnalysisResultSerializer
    
    @action(detail=False, methods=['post'])
    def run_analysis(self, request):
        """运行指定模型分析"""
        from django.core.management import call_command
        import io, sys
        
        # 获取参数
        exams = request.data.get('exams', [])
        subject = request.data.get('subject')
        model = request.data.get('model', ['tvam'])
        
        # 执行命令
        output = io.StringIO()
        sys.stdout = output
        try:
            call_command(
                'test_value_added_models',
                exams=exams,
                subject=subject,
                model=model
            )
            # 保存结果
            # ...
            return Response({'status': 'success', 'output': output.getvalue()})
        except Exception as e:
            return Response({'status': 'error', 'message': str(e)})
        finally:
            sys.stdout = sys.__stdout__ 